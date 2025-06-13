# src/gui/main_window.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import threading
from typing import List
import os
import sys
from datetime import datetime
import logging
from queue import Queue

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class TextHandler(logging.Handler):
    """Custom logging handler that writes to a tkinter Text widget"""
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        
    def emit(self, record):
        msg = self.format(record)
        # Schedule the text update in the main thread
        self.text_widget.after(0, self._append_text, msg)
    
    def _append_text(self, msg):
        try:
            self.text_widget.configure(state='normal')
            self.text_widget.insert(tk.END, msg + '\n')
            self.text_widget.configure(state='disabled')
            # Auto-scroll to bottom
            self.text_widget.see(tk.END)
        except tk.TclError:
            # Widget might be destroyed
            pass
        
class MainWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Video Duplicate Finder - Python")
        self.root.geometry("1200x800")
        
        self.setup_logging()
        self.setup_ui()
        self.scanner = None
        self.duplicate_groups = []
    def setup_logging(self):
        """Setup logging configuration"""
        # Create logger
        self.logger = logging.getLogger('VideoFinder')
        self.logger.setLevel(logging.DEBUG)
        
        # Clear any existing handlers
        self.logger.handlers.clear()
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                                    datefmt='%H:%M:%S')
        
        # We'll add the text handler after creating the text widget
        self.log_formatter = formatter    
    def run(self):
        """Start the application"""
        self.root.mainloop()

    def setup_ui(self):
        # Create main container with notebook for tabs
        main_container = ttk.Frame(self.root, padding="5")
        main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Create notebook for tabbed interface
        notebook = ttk.Notebook(main_container)
        notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Main tab for scanning and results
        main_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text="Scanner")
        
        # Log tab for debug output
        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="Log")
        
        # Setup main tab content
        self.setup_main_tab(main_tab)
        
        # Setup log tab content
        self.setup_log_tab(log_tab)
        
        # Configure grid weights
        main_container.columnconfigure(0, weight=1)
        main_container.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Now setup the text logging handler
        self.setup_text_logging()
        
        # Log startup message
        self.logger.info("Video Duplicate Finder started")
        
    def setup_main_tab(self, parent):
        """Setup the main scanner tab"""
        # Main frame with horizontal split
        main_frame = ttk.Frame(parent, padding="5")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Left panel for controls and results tree
        left_panel = ttk.Frame(main_frame)
        left_panel.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        # Right panel for thumbnail preview
        right_panel = ttk.LabelFrame(main_frame, text="Preview", padding="5")
        right_panel.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Directory selection
        dir_frame = ttk.Frame(left_panel)
        dir_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(dir_frame, text="Scan Directory:").grid(row=0, column=0, sticky=tk.W)
        
        self.dir_var = tk.StringVar()
        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_var, width=50)
        self.dir_entry.grid(row=0, column=1, padx=5, sticky=(tk.W, tk.E))
        
        ttk.Button(dir_frame, text="Browse", command=self.browse_directory).grid(row=0, column=2)
        
        # Settings frame
        settings_frame = ttk.LabelFrame(left_panel, text="Settings", padding="5")
        settings_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(settings_frame, text="Similarity Threshold:").grid(row=0, column=0, sticky=tk.W)
        self.threshold_var = tk.DoubleVar(value=0.8)
        threshold_scale = ttk.Scale(settings_frame, from_=0.5, to=1.0, 
                                  variable=self.threshold_var, orient=tk.HORIZONTAL)
        threshold_scale.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        
        self.threshold_label = ttk.Label(settings_frame, text="0.8")
        self.threshold_label.grid(row=0, column=2)
        threshold_scale.configure(command=self.update_threshold_label)
          # Cache settings
        self.use_cache_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="Use cached hashes", 
                       variable=self.use_cache_var).grid(row=1, column=0, columnspan=2, sticky=tk.W)
        
        # CPU cores setting
        ttk.Label(settings_frame, text="CPU Cores:").grid(row=2, column=0, sticky=tk.W, pady=(5,0))
        
        import multiprocessing
        max_cores = multiprocessing.cpu_count()
        self.cpu_cores_var = tk.IntVar(value=max_cores)
        
        cores_frame = ttk.Frame(settings_frame)
        cores_frame.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=(5,0))
        
        self.cores_scale = ttk.Scale(cores_frame, from_=1, to=max_cores, 
                                   variable=self.cpu_cores_var, orient=tk.HORIZONTAL)
        self.cores_scale.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        self.cores_label = ttk.Label(cores_frame, text=f"{max_cores}")
        self.cores_label.grid(row=0, column=1, padx=(5,0))
        self.cores_scale.configure(command=self.update_cores_label)
        
        cores_frame.columnconfigure(0, weight=1)
          # Control buttons
        control_frame = ttk.Frame(left_panel)
        control_frame.grid(row=2, column=0, columnspan=2, pady=10)
        
        self.scan_button = ttk.Button(control_frame, text="Start Scan", command=self.start_scan)
        self.scan_button.grid(row=0, column=0, padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="Stop", command=self.stop_scan, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=5)
        
        ttk.Button(control_frame, text="Clear Cache", command=self.clear_cache).grid(row=0, column=2, padx=5)
        
        ttk.Button(control_frame, text="Generate Thumbnails", 
                  command=self.generate_thumbnails).grid(row=0, column=3, padx=5)
          # Second row of buttons for database operations
        ttk.Button(control_frame, text="Compare Database", 
                  command=self.compare_database).grid(row=1, column=0, padx=5, pady=5)
        
        ttk.Button(control_frame, text="Database Stats", 
                  command=self.show_database_stats).grid(row=1, column=1, padx=5, pady=5)
                  
        ttk.Button(control_frame, text="Clean Database", 
                  command=self.clean_database).grid(row=1, column=2, padx=5, pady=5)
        
        # Status and progress
        status_frame = ttk.Frame(left_panel)
        status_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.grid(row=0, column=0, sticky=tk.W)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(status_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        
        # Results tree
        results_frame = ttk.LabelFrame(left_panel, text="Duplicate Groups", padding="5")
        results_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Configure grid weights
        left_panel.columnconfigure(1, weight=1)
        left_panel.rowconfigure(4, weight=1)
        main_frame.columnconfigure(0, weight=2)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        self.results_tree = ttk.Treeview(results_frame, columns=("quality", "resolution", "size", "duration", "recommendation"), 
                                        show="tree headings")
        self.results_tree.heading("#0", text="Files")
        self.results_tree.heading("quality", text="Quality")
        self.results_tree.heading("resolution", text="Resolution")
        self.results_tree.heading("size", text="Size")
        self.results_tree.heading("duration", text="Duration")
        self.results_tree.heading("recommendation", text="Recommendation")
        
        self.results_tree.column("quality", width=60)
        self.results_tree.column("resolution", width=80)
        self.results_tree.column("size", width=80)
        self.results_tree.column("duration", width=80)
        self.results_tree.column("recommendation", width=100)
        
        self.results_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.results_tree.bind("<<TreeviewSelect>>", self.on_file_select)
        
        # Scrollbar for results
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        
        # Right panel for thumbnails and details
        self.setup_preview_panel(right_panel)
    
    def setup_preview_panel(self, parent):
        """Setup the enhanced preview panel for quality comparison"""
        # Thumbnail display
        self.thumbnail_label = ttk.Label(parent, text="Select a file to preview")
        self.thumbnail_label.grid(row=0, column=0, pady=10)
        
        # Quality comparison frame
        quality_frame = ttk.LabelFrame(parent, text="Quality Comparison", padding="5")
        quality_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        
        # Selected file details
        self.file_path_var = tk.StringVar()
        self.file_size_var = tk.StringVar()
        self.file_resolution_var = tk.StringVar()
        self.file_duration_var = tk.StringVar()
        self.file_bitrate_var = tk.StringVar()
        self.quality_score_var = tk.StringVar()
        
        # Create details grid
        details_labels = [
            ("Path:", self.file_path_var),
            ("Size:", self.file_size_var),
            ("Resolution:", self.file_resolution_var),
            ("Duration:", self.file_duration_var),
            ("Bitrate:", self.file_bitrate_var),
            ("Quality Score:", self.quality_score_var)
        ]
        
        for i, (label_text, var) in enumerate(details_labels):
            ttk.Label(quality_frame, text=label_text).grid(row=i, column=0, sticky=tk.W)
            if label_text == "Path:":
                label = ttk.Label(quality_frame, textvariable=var, wraplength=250)
            else:
                label = ttk.Label(quality_frame, textvariable=var)
            label.grid(row=i, column=1, sticky=tk.W, padx=5)
        
        # Quality recommendation frame
        recommendation_frame = ttk.LabelFrame(parent, text="Recommendation", padding="5")
        recommendation_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)
        
        self.recommendation_text = tk.Text(recommendation_frame, height=4, width=40, wrap=tk.WORD)
        self.recommendation_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        rec_scrollbar = ttk.Scrollbar(recommendation_frame, orient=tk.VERTICAL, command=self.recommendation_text.yview)
        rec_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.recommendation_text.configure(yscrollcommand=rec_scrollbar.set)
        
        recommendation_frame.columnconfigure(0, weight=1)
        
        # Action buttons
        action_frame = ttk.Frame(parent)
        action_frame.grid(row=3, column=0, pady=10)
        
        ttk.Button(action_frame, text="Compare Quality", command=self.compare_group_quality).grid(row=0, column=0, padx=5)
        ttk.Button(action_frame, text="Open File", command=self.open_selected_file).grid(row=0, column=1, padx=5)
        ttk.Button(action_frame, text="Delete File", command=self.delete_selected_file).grid(row=0, column=2, padx=5)
        ttk.Button(action_frame, text="Show in Explorer", command=self.show_in_explorer).grid(row=1, column=0, padx=5)
        ttk.Button(action_frame, text="Auto-Delete Lower Quality", command=self.auto_delete_lower_quality).grid(row=1, column=1, columnspan=2, padx=5)
        
        parent.columnconfigure(0, weight=1)
    
    def setup_log_tab(self, parent):
        """Setup the log tab with scrollable text widget"""
        log_frame = ttk.Frame(parent, padding="5")
        log_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Log control frame
        control_frame = ttk.Frame(log_frame)
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Label(control_frame, text="Log Level:").grid(row=0, column=0, padx=(0, 5))
        
        self.log_level_var = tk.StringVar(value="INFO")
        log_level_combo = ttk.Combobox(control_frame, textvariable=self.log_level_var, 
                                     values=["DEBUG", "INFO", "WARNING", "ERROR"], 
                                     width=10, state="readonly")
        log_level_combo.grid(row=0, column=1, padx=5)
        log_level_combo.bind("<<ComboboxSelected>>", self.change_log_level)
        
        ttk.Button(control_frame, text="Clear Log", command=self.clear_log).grid(row=0, column=2, padx=5)
        ttk.Button(control_frame, text="Save Log", command=self.save_log).grid(row=0, column=3, padx=5)
        
        # Log text widget with scrollbar
        text_frame = ttk.Frame(log_frame)
        text_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.log_text = tk.Text(text_frame, wrap=tk.WORD, state='disabled',
                               font=('Consolas', 9), bg='#f8f8f8', fg='#333333')
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        log_scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        # Configure text tags for different log levels
        self.log_text.tag_configure("DEBUG", foreground="#666666")
        self.log_text.tag_configure("INFO", foreground="#000000")
        self.log_text.tag_configure("WARNING", foreground="#ff8c00")
        self.log_text.tag_configure("ERROR", foreground="#dc143c")
        self.log_text.tag_configure("CRITICAL", foreground="#8b0000", font=('Consolas', 9, 'bold'))
        
        # Configure grid weights
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
    
    def setup_text_logging(self):
        """Setup the text widget logging handler"""
        # Create and configure the text handler
        self.text_handler = TextHandler(self.log_text)
        self.text_handler.setFormatter(self.log_formatter)
        self.text_handler.setLevel(logging.INFO)
        
        # Add to logger
        self.logger.addHandler(self.text_handler)
        
        # Also add console handler for backup
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(self.log_formatter)
        console_handler.setLevel(logging.WARNING)  # Only warnings and errors to console
        self.logger.addHandler(console_handler)
    
    def change_log_level(self, event=None):
        """Change the logging level"""
        level_name = self.log_level_var.get()
        level = getattr(logging, level_name)
        self.text_handler.setLevel(level)
        self.logger.info(f"Log level changed to {level_name}")
    
    def clear_log(self):
        """Clear the log text widget"""
        self.log_text.configure(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state='disabled')
        self.logger.info("Log cleared")
    
    def save_log(self):
        """Save log content to file"""
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".log",
                filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")],
                title="Save Log File"            )
            
            if filename:
                content = self.log_text.get(1.0, tk.END)
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.logger.info(f"Log saved to {filename}")
                messagebox.showinfo("Log Saved", f"Log saved successfully to:\n{filename}")
        except Exception as e:
            self.logger.error(f"Failed to save log: {e}")
            messagebox.showerror("Error", f"Failed to save log: {e}")
    
    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.dir_var.set(directory)
    
    def update_threshold_label(self, value):
        self.threshold_label.config(text=f"{float(value):.2f}")
    
    def update_cores_label(self, value):
        self.cores_label.config(text=f"{int(float(value))}")
    
    def start_scan(self):
        directory = self.dir_var.get()
        if not directory or not Path(directory).exists():
            messagebox.showerror("Error", "Please select a valid directory")
            return
        
        self.logger.info(f"Starting scan of directory: {directory}")
        self.logger.info(f"Similarity threshold: {self.threshold_var.get()}")
        self.logger.info(f"Use cache: {self.use_cache_var.get()}")
        self.logger.info(f"CPU cores: {int(self.cpu_cores_var.get())}")
        
        self.scan_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.progress_var.set(0)
        self.status_label.config(text="Scanning...")
        
        # Clear previous results
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.duplicate_groups = []
        
        # Start scanning in separate thread
        self.scan_thread = threading.Thread(target=self._scan_directory, args=(directory,))
        self.scan_thread.start()
    
    def _scan_directory(self, directory):
        """Run scan in background thread"""
        try:
            self.logger.debug("Initializing scanner...")
            # Add src path for imports
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.scanner import VideoScanner
              # Store scanner instance so stop button can access it
            self.scanner = VideoScanner(
                similarity_threshold=self.threshold_var.get(),
                progress_callback=self.update_progress,
                num_workers=int(self.cpu_cores_var.get())
            )
            
            self.logger.info("Scanner initialized, starting directory scan...")
            duplicates = self.scanner.scan_directory(directory, use_cache=self.use_cache_var.get())
            
            self.logger.info(f"Scan completed. Found {len(duplicates)} duplicate pairs")
            
            # Group duplicates
            self.duplicate_groups = self._group_duplicates_by_cluster(duplicates)
            self.logger.info(f"Grouped into {len(self.duplicate_groups)} duplicate groups")

            # Update UI in main thread
            self.root.after(0, self.display_results, self.duplicate_groups)
        except Exception as e:
            error_msg = f"Scan failed: {e}"
            self.logger.error(error_msg)
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
        finally:
            self.root.after(0, self.scan_complete)
    
    def _group_duplicates_by_cluster(self, duplicates):
        """Group duplicate pairs into clusters of similar videos"""
        if not duplicates:
            return []
        
        self.logger.debug(f"Processing {len(duplicates)} duplicate pairs:")
        for i, (file1, file2, similarity) in enumerate(duplicates):
            self.logger.debug(f"  Pair {i+1}: {Path(file1).name} <-> {Path(file2).name} (similarity: {similarity:.3f})")
        
        # Simple clustering: group files that appear in multiple pairs
        file_groups = {}
        group_id = 0
        
        for file1, file2, similarity in duplicates:
            # Find if either file is already in a group
            group1 = file_groups.get(file1)
            group2 = file_groups.get(file2)
            
            if group1 is not None and group2 is not None:
                # Both files already in groups - merge groups if different
                if group1 != group2:
                    # Merge groups (update all files in group2 to group1)
                    for file_path, gid in file_groups.items():
                        if gid == group2:
                            file_groups[file_path] = group1
            elif group1 is not None:
                # file1 in group, add file2
                file_groups[file2] = group1
            elif group2 is not None:
                # file2 in group, add file1
                file_groups[file1] = group2
            else:
                # Neither file in a group, create new group
                file_groups[file1] = group_id
                file_groups[file2] = group_id
                group_id += 1

        # Convert to list of groups
        groups = {}
        for file_path, gid in file_groups.items():
            if gid not in groups:
                groups[gid] = []
            groups[gid].append(file_path)
        
        # Only return groups with 2 or more files
        result_groups = [group for group in groups.values() if len(group) >= 2]
        self.logger.debug(f"Created {len(result_groups)} groups from clustering")
        return result_groups
    
    def update_progress(self, current, total):
        """Update progress bar - called from background thread"""
        progress = (current / total) * 100 if total > 0 else 0
        self.root.after(0, lambda: self.progress_var.set(progress))
    
    def display_results(self, duplicate_groups):
        """Display scan results with quality analysis"""
        self.status_label.config(text=f"Found {len(duplicate_groups)} duplicate groups")
        
        # Import quality analyzer
        src_path = Path(__file__).parent.parent
        sys.path.insert(0, str(src_path))
        from core.quality_analyzer import VideoQualityAnalyzer
        
        quality_analyzer = VideoQualityAnalyzer()
        
        for i, group in enumerate(duplicate_groups):
            # Analyze quality for this group
            group_analysis = quality_analyzer.analyze_duplicate_group(group)
            
            # Calculate total space that could be saved
            total_size_mb = sum(f['metadata'].get('file_size_mb', 0) for f in group_analysis['files'])
            space_saved_mb = group_analysis['recommendation']['space_saved_mb']
            
            group_id = self.results_tree.insert("", "end", 
                                               text=f"Group {i+1} ({len(group)} files) - Save {space_saved_mb:.1f}MB", 
                                               values=("", "", "", "", f"Keep best, delete {len(group)-1}"))
            
            # Add files sorted by quality
            for j, file_info in enumerate(group_analysis['files']):
                file_path = file_info['path']
                metadata = file_info['metadata']
                
                # Format values for display
                quality_score = f"{file_info['quality_score']:.2f}"
                resolution = metadata.get('resolution', 'Unknown')
                size_str = f"{metadata.get('file_size_mb', 0):.1f}MB"
                duration = metadata.get('duration_formatted', 'Unknown')
                
                # Determine recommendation
                if j == 0:
                    recommendation = "KEEP (Best Quality)"
                    tag_color = "keep"
                else:
                    recommendation = "DELETE (Lower Quality)"
                    tag_color = "delete"
                
                item_id = self.results_tree.insert(group_id, "end", 
                                                 text=Path(file_path).name,
                                                 values=(quality_score, resolution, size_str, duration, recommendation),
                                                 tags=(file_path, tag_color))
        
        # Configure tag colors
        self.results_tree.tag_configure("keep", foreground="green")
        self.results_tree.tag_configure("delete", foreground="red")
    
    def _format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def on_file_select(self, event):
        """Handle file selection in tree"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        tags = self.results_tree.item(item, "tags")
        
        if tags:
            file_path = tags[0]
            self.show_file_preview(file_path)
    
    def show_file_preview(self, file_path):
        """Show thumbnail and quality details for selected file"""
        try:
            # Import quality analyzer
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.quality_analyzer import VideoQualityAnalyzer
            
            quality_analyzer = VideoQualityAnalyzer()
            metadata = quality_analyzer.get_video_metadata(file_path)
            
            # Update file details with quality information
            self.file_path_var.set(file_path)
            self.file_size_var.set(f"{metadata.get('file_size_mb', 0):.1f} MB")
            self.file_resolution_var.set(metadata.get('resolution', 'Unknown'))
            self.file_duration_var.set(metadata.get('duration_formatted', 'Unknown'))
            self.file_bitrate_var.set(f"{metadata.get('bitrate_kbps', 0):.0f} kbps")
            
            # Calculate and show quality score
            quality_score = quality_analyzer._calculate_quality_score(metadata)
            self.quality_score_var.set(f"{quality_score:.2f}/1.0")
            
            # Try to load thumbnail
            self.load_thumbnail(file_path)
            
        except Exception as e:
            print(f"Error showing preview for {file_path}: {e}")
            # Set default values on error
            self.file_path_var.set(file_path)
            self.file_size_var.set("Error reading file")
            self.file_resolution_var.set("Unknown")
            self.file_duration_var.set("Unknown")
            self.file_bitrate_var.set("Unknown")
            self.quality_score_var.set("N/A")
    
    def load_thumbnail(self, file_path):
        """Load and display thumbnail for video file"""
        try:
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.scanner import VideoScanner
            
            scanner = VideoScanner(num_workers=int(self.cpu_cores_var.get()))
            thumbnail_path = scanner.get_file_thumbnail(file_path)
            
            if thumbnail_path and os.path.exists(thumbnail_path) and PIL_AVAILABLE:
                # Load and display thumbnail
                image = Image.open(thumbnail_path)
                image = image.resize((200, 150), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                
                self.thumbnail_label.config(image=photo, text="")
                self.thumbnail_label.image = photo  # Keep a reference
            else:
                self.thumbnail_label.config(image="", text="No thumbnail available")
                self.thumbnail_label.image = None
        except Exception as e:
            print(f"Error loading thumbnail: {e}")
            self.thumbnail_label.config(image="", text="Thumbnail error")
            self.thumbnail_label.image = None
    
    def scan_complete(self):
        """Reset UI after scan completion"""
        self.scan_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.progress_var.set(100)
        self.status_label.config(text="Scan complete")
    
    def stop_scan(self):
        """Stop current scan"""
        print("Stop button pressed")
        if hasattr(self, 'scanner') and self.scanner:
            print("Stopping scanner...")
            self.scanner.stop()
            self.status_label.config(text="Stopping scan...")
        else:
            print("No active scanner found")
        
        # Reset UI immediately
        self.scan_complete()
    
    def clear_cache(self):
        """Clear all cached data"""
        try:
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.scanner import VideoScanner
            
            scanner = VideoScanner(num_workers=int(self.cpu_cores_var.get()))
            scanner.clear_cache()
            messagebox.showinfo("Cache Cleared", "All cached data has been cleared")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to clear cache: {e}")
    
    def generate_thumbnails(self):
        """Generate thumbnails for all files in results"""
        if not self.duplicate_groups:
            messagebox.showwarning("No Results", "Please run a scan first")
            return
        
        # Collect all unique file paths
        all_files = set()
        for group in self.duplicate_groups:
            all_files.update(group)
        
        if not all_files:
            return
          # Start thumbnail generation in background
        self.status_label.config(text="Generating thumbnails...")
        self.progress_var.set(0)
        
        thread = threading.Thread(target=self._generate_thumbnails_background, 
                                 args=(list(all_files),))
        thread.start()
    
    def _generate_thumbnails_background(self, file_paths):
        """Generate thumbnails in background thread"""
        try:
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.scanner import VideoScanner
            
            scanner = VideoScanner(num_workers=int(self.cpu_cores_var.get()))
            
            def progress_callback(current, total):
                progress = (current / total) * 100 if total > 0 else 0
                self.root.after(0, lambda: self.progress_var.set(progress))
            
            scanner.generate_thumbnails(file_paths, progress_callback)
            
            self.root.after(0, lambda: self.status_label.config(text="Thumbnails generated"))
            
        except Exception as e:
            error_msg = f"Thumbnail generation failed: {e}"
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
    
    def open_selected_file(self):
        """Open selected file with default application"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        tags = self.results_tree.item(item, "tags")
        
        if tags:
            file_path = tags[0]
            try:
                os.startfile(file_path)  # Windows
            except:
                try:
                    os.system(f'open "{file_path}"')  # macOS
                except:
                    os.system(f'xdg-open "{file_path}"')  # Linux
    
    def delete_selected_file(self):
        """Delete selected file after confirmation"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        tags = self.results_tree.item(item, "tags")
        
        if tags:
            file_path = tags[0]
            result = messagebox.askyesno("Confirm Delete", 
                                       f"Are you sure you want to delete:\n{file_path}")
            if result:
                try:
                    os.remove(file_path)
                    self.results_tree.delete(item)
                    
                    # Remove from database as well
                    try:
                        src_path = Path(__file__).parent.parent
                        sys.path.insert(0, str(src_path))
                        from core.database import VideoDatabase
                        
                        db = VideoDatabase()
                        db._remove_file(file_path)
                    except Exception as db_e:
                        print(f"Warning: Failed to remove file from database: {db_e}")
                    
                    messagebox.showinfo("Deleted", "File deleted successfully")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to delete file: {e}")
    
    def show_in_explorer(self):
        """Show selected file in Windows Explorer"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        tags = self.results_tree.item(item, "tags")
        
        if tags:
            file_path = tags[0]
            try:
                os.system(f'explorer /select,"{file_path}"')
            except Exception as e:
                print(f"Error showing in explorer: {e}")
    
    def compare_group_quality(self):
        """Compare quality of all files in the selected duplicate group"""
        selection = self.results_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a duplicate group or file")
            return
        
        # Get the parent group
        item = selection[0]
        parent = self.results_tree.parent(item)
        if parent:  # Selected a file, get its parent group
            group_item = parent
        else:  # Selected a group
            group_item = item
        
        # Get all files in the group
        file_paths = []
        for child in self.results_tree.get_children(group_item):
            tags = self.results_tree.item(child, "tags")
            if tags and len(tags) > 0 and tags[0] not in ['keep', 'delete']:
                file_paths.append(tags[0])
        
        if len(file_paths) < 2:
            messagebox.showwarning("Invalid Group", "Need at least 2 files to compare quality")
            return
        
        # Perform quality analysis
        try:
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.quality_analyzer import VideoQualityAnalyzer
            
            quality_analyzer = VideoQualityAnalyzer()
            group_analysis = quality_analyzer.analyze_duplicate_group(file_paths)
            
            # Show detailed comparison in recommendation text
            self.recommendation_text.delete(1.0, tk.END)
            
            recommendation = group_analysis['recommendation']
            
            # Header
            self.recommendation_text.insert(tk.END, "QUALITY ANALYSIS RESULTS\n", "header")
            self.recommendation_text.insert(tk.END, "="*30 + "\n\n")
            
            # Best file recommendation
            best_file = recommendation['best_file']
            self.recommendation_text.insert(tk.END, f"RECOMMENDED TO KEEP:\n", "keep")
            self.recommendation_text.insert(tk.END, f"• {Path(best_file['path']).name}\n")
            self.recommendation_text.insert(tk.END, f"  Quality Score: {best_file['quality_score']:.2f}\n")
            self.recommendation_text.insert(tk.END, f"  Resolution: {best_file['metadata'].get('resolution', 'Unknown')}\n")
            self.recommendation_text.insert(tk.END, f"  Size: {best_file['metadata'].get('file_size_mb', 0):.1f} MB\n\n")
            
            # Files to delete
            self.recommendation_text.insert(tk.END, f"RECOMMENDED TO DELETE:\n", "delete")
            for file_path in recommendation['delete']:
                file_data = next(f for f in group_analysis['files'] if f['path'] == file_path)
                self.recommendation_text.insert(tk.END, f"• {Path(file_path).name}\n")
                self.recommendation_text.insert(tk.END, f"  Quality Score: {file_data['quality_score']:.2f}\n")
                self.recommendation_text.insert(tk.END, f"  Resolution: {file_data['metadata'].get('resolution', 'Unknown')}\n")
                self.recommendation_text.insert(tk.END, f"  Size: {file_data['metadata'].get('file_size_mb', 0):.1f} MB\n")
            
            # Space savings
            self.recommendation_text.insert(tk.END, f"\nSPACE SAVINGS: {recommendation['space_saved_mb']:.1f} MB\n")
            
            # Quality differences
            if recommendation['quality_differences']:
                self.recommendation_text.insert(tk.END, f"\nQUALITY DIFFERENCES:\n")
                for diff in recommendation['quality_differences']:
                    self.recommendation_text.insert(tk.END, f"• {diff}\n")
            
            # Configure text colors
            self.recommendation_text.tag_configure("header", font=("TkDefaultFont", 10, "bold"))
            self.recommendation_text.tag_configure("keep", foreground="green", font=("TkDefaultFont", 9, "bold"))
            self.recommendation_text.tag_configure("delete", foreground="red", font=("TkDefaultFont", 9, "bold"))
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to analyze quality: {e}")
    
    def auto_delete_lower_quality(self):
        """Automatically delete lower quality files in selected group"""
        selection = self.results_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a duplicate group")
            return
        
        # Get the parent group
        item = selection[0]
        parent = self.results_tree.parent(item)
        if parent:  # Selected a file, get its parent group
            group_item = parent
        else:  # Selected a group
            group_item = item
        
        # Get all files in the group
        file_paths = []
        for child in self.results_tree.get_children(group_item):
            tags = self.results_tree.item(child, "tags")
            if tags and len(tags) > 0 and tags[0] not in ['keep', 'delete']:
                file_paths.append(tags[0])
        
        if len(file_paths) < 2:
            messagebox.showwarning("Invalid Group", "Need at least 2 files for auto-deletion")
            return
        
        try:
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.quality_analyzer import VideoQualityAnalyzer
            
            quality_analyzer = VideoQualityAnalyzer()
            group_analysis = quality_analyzer.analyze_duplicate_group(file_paths)
            
            files_to_delete = group_analysis['recommendation']['delete']
            space_saved = group_analysis['recommendation']['space_saved_mb']
            
            if not files_to_delete:
                messagebox.showinfo("No Action", "No files recommended for deletion")
                return
              # Confirm deletion
            file_list = "\n".join([f"• {Path(f).name}" for f in files_to_delete])
            result = messagebox.askyesno("Confirm Auto-Delete", 
                                       f"Delete {len(files_to_delete)} lower quality files?\n\n"
                                       f"Files to delete:\n{file_list}\n\n"
                                       f"Space saved: {space_saved:.1f} MB")
            
            if result:
                deleted_count = 0
                deleted_files = []
                
                for file_path in files_to_delete:
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                        deleted_files.append(file_path)
                        
                        # Remove from tree view
                        for child in self.results_tree.get_children(group_item):
                            tags = self.results_tree.item(child, "tags")
                            if tags and tags[0] == file_path:
                                self.results_tree.delete(child)
                                break
                                
                    except Exception as e:
                        print(f"Error deleting {file_path}: {e}")
                
                # Remove deleted files from database
                try:
                    from core.database import VideoDatabase
                    db = VideoDatabase()
                    for file_path in deleted_files:
                        db._remove_file(file_path)
                except Exception as db_e:
                    print(f"Warning: Failed to remove some files from database: {db_e}")
                
                messagebox.showinfo("Deletion Complete", 
                                  f"Successfully deleted {deleted_count} files\n"
                                  f"Space saved: {space_saved:.1f} MB")
                
                # Update group display
                remaining_children = len(self.results_tree.get_children(group_item))
                if remaining_children == 0:
                    self.results_tree.delete(group_item)
                else:
                    # Update group text
                    group_text = self.results_tree.item(group_item, "text")
                    updated_text = group_text.split(" - Save")[0]  # Remove old savings info
                    self.results_tree.item(group_item, text=f"{updated_text} - {remaining_children} files remaining")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to auto-delete files: {e}")

    def compare_database(self):
        """Compare existing files in database for duplicates"""
        try:
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.scanner import VideoScanner
            
            self.status_label.config(text="Comparing database entries...")
            self.progress_var.set(0)
            
            # Clear previous results
            for item in self.results_tree.get_children():
                self.results_tree.delete(item)
            self.duplicate_groups = []
            
            # Run comparison in background thread
            thread = threading.Thread(target=self._compare_database_background)
            thread.start()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start database comparison: {e}")
    
    def _compare_database_background(self):
        """Run database comparison in background thread"""
        try:
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.scanner import VideoScanner
            
            scanner = VideoScanner(num_workers=int(self.cpu_cores_var.get()))
            duplicates = scanner.compare_existing_database()
            
            if duplicates:
                # Group duplicates
                self.duplicate_groups = self._group_duplicates_by_cluster(duplicates)
                
                # Update UI in main thread
                self.root.after(0, self.display_results, self.duplicate_groups)
                self.root.after(0, lambda: self.status_label.config(text=f"Database comparison complete - Found {len(self.duplicate_groups)} duplicate groups"))
            else:
                self.root.after(0, lambda: self.status_label.config(text="No duplicates found in database"))
                self.root.after(0, lambda: messagebox.showinfo("Database Comparison", "No duplicate files found in the existing database"))
                
        except Exception as e:
            error_msg = f"Database comparison failed: {e}"
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
            self.root.after(0, lambda: self.status_label.config(text="Database comparison failed"))
    
    def show_database_stats(self):
        """Show statistics about the current database"""
        try:
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.scanner import VideoScanner
            
            scanner = VideoScanner(num_workers=int(self.cpu_cores_var.get()))
            stats = scanner.get_database_stats()
            
            if stats:
                stats_text = f"""Database Statistics:

Total Files: {stats['total_files']}
Files with Hashes: {stats['files_with_hashes']}
Existing Files: {stats['existing_files']}
Missing Files: {stats['missing_files']}
Total Size: {stats['total_size_mb']:.1f} MB
Database Path: {stats['database_path']}

Ready for comparison: {stats['files_with_hashes']} files"""
                
                messagebox.showinfo("Database Statistics", stats_text)
            else:
                messagebox.showwarning("Database Stats", "Could not retrieve database statistics")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get database stats: {e}")

    def clean_database(self):
        """Clean database by removing entries for non-existent files"""
        try:
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.database import VideoDatabase
            
            # Show current stats before cleanup
            db = VideoDatabase()
            
            # Get stats before cleanup
            before_files = db.get_all_files()
            before_count = len(before_files)
            missing_files = [f for f in before_files if not os.path.exists(f['file_path'])]
            missing_count = len(missing_files)
            
            if missing_count == 0:
                messagebox.showinfo("Clean Database", "Database is already clean! No missing files found.")
                return
            
            # Confirm cleanup
            result = messagebox.askyesno("Confirm Database Cleanup", 
                                       f"Found {missing_count} missing files out of {before_count} total files.\n\n"
                                       f"This will remove database entries for files that no longer exist on disk.\n\n"
                                       f"Continue with cleanup?")
            
            if result:
                self.status_label.config(text="Cleaning database...")
                self.root.update()
                
                # Perform cleanup
                db.cleanup_missing_files()
                
                # Get stats after cleanup
                after_files = db.get_all_files()
                after_count = len(after_files)
                cleaned_count = before_count - after_count
                
                self.status_label.config(text="Database cleanup complete")
                
                messagebox.showinfo("Database Cleanup Complete", 
                                  f"Database cleanup completed successfully!\n\n"
                                  f"Removed {cleaned_count} entries for missing files\n"
                                  f"Database now contains {after_count} files")
                
        except Exception as e:
            error_msg = f"Failed to clean database: {e}"
            self.status_label.config(text="Database cleanup failed")
            messagebox.showerror("Error", error_msg)