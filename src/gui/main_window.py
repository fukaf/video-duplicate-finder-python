# src/gui/main_window.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import threading
import multiprocessing
import io
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
        except tk.TclError:            # Widget might be destroyed
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
        # Track checkbox states for duplicate groups
        self.group_checkbox_states = {}  # group_id -> boolean
        
        # Track active threads
        self.scan_thread = None
        self.is_closing = False
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
        
    def on_closing(self):
        """Handle window close event properly"""
        self.is_closing = True
        
        # Stop any running scan
        if hasattr(self, 'scanner') and self.scanner:
            self.logger.info("Stopping scanner before exit...")
            self.scanner.stop()
        
        # Wait for scan thread to finish (with timeout)
        if self.scan_thread and self.scan_thread.is_alive():
            self.logger.info("Waiting for scan thread to finish...")
            self.scan_thread.join(timeout=3.0)  # Wait max 3 seconds
            
            if self.scan_thread.is_alive():
                self.logger.warning("Scan thread did not finish cleanly")
        
        # Cleanup logging handlers
        if hasattr(self, 'text_handler'):
            self.logger.removeHandler(self.text_handler)
        
        self.logger.info("Application closing...")
        self.root.destroy()
    def run(self):
        """Start the application"""
        self.root.mainloop()
    
    def setup_ui(self):
        # Create main container for the scanner interface
        main_container = ttk.Frame(self.root, padding="5")
        main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
          # Setup main scanner interface
        self.setup_main_tab(main_container)
        
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
        
        cores_frame.columnconfigure(0, weight=1)        # Control buttons
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
        
        # Third row of buttons for checkbox operations
        ttk.Button(control_frame, text="Select All Groups", 
                  command=self.select_all_groups).grid(row=2, column=0, padx=5, pady=5)
        
        ttk.Button(control_frame, text="Deselect All Groups", 
                  command=self.deselect_all_groups).grid(row=2, column=1, padx=5, pady=5)
        
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
        
        self.results_tree = ttk.Treeview(results_frame, columns=("select", "quality", "resolution", "size", "duration", "recommendation"), 
                                        show="tree headings")
        self.results_tree.heading("#0", text="Files")
        self.results_tree.heading("select", text="Auto-Delete")
        self.results_tree.heading("quality", text="Quality")
        self.results_tree.heading("resolution", text="Resolution")
        self.results_tree.heading("size", text="Size")
        self.results_tree.heading("duration", text="Duration")
        self.results_tree.heading("recommendation", text="Recommendation")
        
        self.results_tree.column("select", width=80)
        self.results_tree.column("quality", width=60)
        self.results_tree.column("resolution", width=80)
        self.results_tree.column("size", width=80)
        self.results_tree.column("duration", width=80)
        self.results_tree.column("recommendation", width=100)
        
        self.results_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.results_tree.bind("<<TreeviewSelect>>", self.on_file_select)
        self.results_tree.bind("<Button-1>", self.on_tree_click)  # Handle checkbox clicks
        
        # Scrollbar for results
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        
        # Log area at the bottom of the scanner tab
        log_frame = ttk.LabelFrame(left_panel, text="Processing Log", padding="5")
        log_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Log control frame
        log_control_frame = ttk.Frame(log_frame)
        log_control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Label(log_control_frame, text="Log Level:").grid(row=0, column=0, padx=(0, 5))
        
        self.log_level_var = tk.StringVar(value="INFO")
        log_level_combo = ttk.Combobox(log_control_frame, textvariable=self.log_level_var, 
                                     values=["DEBUG", "INFO", "WARNING", "ERROR"], 
                                     width=10, state="readonly")
        log_level_combo.grid(row=0, column=1, padx=5)
        log_level_combo.bind("<<ComboboxSelected>>", self.change_log_level)
        
        ttk.Button(log_control_frame, text="Clear Log", command=self.clear_log).grid(row=0, column=2, padx=5)
        ttk.Button(log_control_frame, text="Save Log", command=self.save_log).grid(row=0, column=3, padx=5)
        
        # Log text widget with scrollbar
        log_text_frame = ttk.Frame(log_frame)
        log_text_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.log_text = tk.Text(log_text_frame, wrap=tk.WORD, state='disabled', height=8,
                               font=('Consolas', 9), bg='#f8f8f8', fg='#333333')
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        log_scrollbar = ttk.Scrollbar(log_text_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        # Configure text tags for different log levels
        self.log_text.tag_configure("DEBUG", foreground="#666666")
        self.log_text.tag_configure("INFO", foreground="#000000")
        self.log_text.tag_configure("WARNING", foreground="#ff8c00")
        self.log_text.tag_configure("ERROR", foreground="#dc143c")
        self.log_text.tag_configure("CRITICAL", foreground="#8b0000", font=('Consolas', 9, 'bold'))
        
        # Configure log frame grid weights
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        log_text_frame.columnconfigure(0, weight=1)
        log_text_frame.rowconfigure(0, weight=1)
        
        # Configure main grid weights
        left_panel.columnconfigure(1, weight=1)
        left_panel.rowconfigure(4, weight=2)  # Results tree gets more space
        left_panel.rowconfigure(5, weight=1)  # Log area gets less space
        main_frame.columnconfigure(0, weight=2)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
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
        ttk.Button(action_frame, text="Auto-Delete Lower Quality", command=self.auto_delete_lower_quality).grid(row=1, column=1, padx=5)
        ttk.Button(action_frame, text="Delete All Low Quality", command=self.delete_all_low_quality).grid(row=1, column=2, padx=5)
        
        parent.columnconfigure(0, weight=1)
    
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
        console_handler.setLevel(logging.WARNING)  # Only warnings and errors to console        self.logger.addHandler(console_handler)
    
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
                title="Save Log File"
            )
            
            if filename:
                content = self.log_text.get(1.0, tk.END)
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.logger.info(f"Log saved to {filename}")
                messagebox.showinfo("Log Saved", f"Log saved successfully to:\n{filename}")
        except Exception as e:
            self.logger.error(f"Failed to save log: {e}")
            messagebox.showerror("Error", f"Failed to save log: {e}")
    
    def add_info_message(self, message, message_type="info"):
        """Add a message to the info text area and log it
        
        Args:
            message (str): The message text
            message_type (str): Type of message - "info", "success", "warning", "error", "progress"
        """
        # Ensure this runs in the main thread
        if threading.current_thread() is not threading.main_thread():
            self.root.after(0, lambda: self.add_info_message(message, message_type))
            return
            
        try:
            # Log the message too (except progress updates)
            if message_type != "progress":
                log_level = {
                    "info": logging.INFO,
                    "success": logging.INFO,
                    "warning": logging.WARNING,
                    "error": logging.ERROR,
                }.get(message_type, logging.INFO)
                
                self.logger.log(log_level, message)
            
            # Also show important messages in the log text area for convenience
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {message}"
            
            # Add to log text widget if it exists
            if hasattr(self, 'log_text'):
                self.log_text.configure(state='normal')
                
                # Only keep the last 100 lines
                line_count = int(self.log_text.index('end-1c').split('.')[0])
                if line_count > 100:
                    self.log_text.delete('1.0', '2.0')
                
                # Insert the new message with appropriate color
                tag_name = {
                    "info": "INFO",
                    "success": "INFO", 
                    "warning": "WARNING",
                    "error": "ERROR",
                    "progress": "DEBUG"
                }.get(message_type, "INFO")
                
                self.log_text.insert(tk.END, formatted_message + "\n", tag_name)
                
                # Autoscroll to bottom
                self.log_text.see(tk.END)
                
                # Make read-only again
                self.log_text.configure(state='disabled')
        except Exception as e:
            print(f"Error adding info message: {e}")
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
        self.group_checkbox_states = {}  # Clear checkbox states
        
        # Clean up previous scanner instance
        self.scanner = None
        
        # Start scanning in separate thread
        self.scan_thread = threading.Thread(target=self._scan_directory, args=(directory,), daemon=True)
        self.scan_thread.start()
    
    def _scan_directory(self, directory):
        """Run scan in background thread"""
        try:
            # Check if we're closing
            if self.is_closing:
                return
            
            self.logger.debug("Initializing scanner...")
            # Add src path for imports
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.scanner import VideoScanner
            
            # Store scanner instance so stop button can access it
            self.scanner = VideoScanner(
                similarity_threshold=self.threshold_var.get(),
                progress_callback=self.update_progress,
                num_workers=int(self.cpu_cores_var.get()),
                logger=self.logger
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
            
            # Check if all videos in the group have the same duration
            duration_differences = group_analysis['duration_differences']

            # Consider durations "same" if they're within 2 seconds of each other
            if duration_differences < 2.0:
                same_duration = True
            else:
                same_duration = False
              # Determine group tag based on duration matching
            group_tag = "same_duration" if same_duration else "different_duration"
            
            # Create group status text
            duration_status = "✓ Same Duration" if same_duration else "⚠ Different Durations"
            
            # Set default checkbox state (checked by default)
            checkbox_state = "☑"  # Checked checkbox
            
            group_id = self.results_tree.insert("", "end", 
                                               text=f"Group {i+1} ({len(group)} files) - Save {space_saved_mb:.1f}MB - {duration_status}", 
                                               values=(checkbox_state, "", "", "", "", f"Keep best, delete {len(group)-1}"),
                                               tags=(group_tag,))
            
            # Store checkbox state for this group
            self.group_checkbox_states[group_id] = True
            
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
                                                 values=("", quality_score, resolution, size_str, duration, recommendation),
                                                 tags=(file_path, tag_color))
            
            # Auto-expand groups with different durations
            if not same_duration:
                self.results_tree.item(group_id, open=True)
                self.logger.info(f"Auto-expanded Group {i+1} due to different video durations")
        
        # Configure tag colors
        self.results_tree.tag_configure("keep", foreground="green")
        self.results_tree.tag_configure("delete", foreground="red")
        self.results_tree.tag_configure("same_duration", background="#e8f5e8", foreground="darkgreen")  # Light green background
        self.results_tree.tag_configure("different_duration", background="#fff3cd", foreground="darkorange")  # Light yellow background
    
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
            
            scanner = VideoScanner(num_workers=int(self.cpu_cores_var.get()), logger=self.logger)
            thumbnail_path = scanner.get_file_thumbnail(file_path)
            
            self.logger.debug(f"Loading thumbnail for {file_path}")
            self.logger.debug(f"Thumbnail path from database: {thumbnail_path}")
            
            if thumbnail_path and os.path.exists(thumbnail_path) and PIL_AVAILABLE:
                # Load and display thumbnail
                self.logger.debug(f"Loading thumbnail from {thumbnail_path}")
                image = Image.open(thumbnail_path)
                image = image.resize((200, 150), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                
                self.thumbnail_label.config(image=photo, text="")
                self.thumbnail_label.image = photo  # Keep a reference
                self.logger.debug("Thumbnail loaded and displayed successfully")
            else:
                if not thumbnail_path:
                    self.logger.debug("No thumbnail path found in database")
                elif not os.path.exists(thumbnail_path):
                    self.logger.debug(f"Thumbnail file does not exist: {thumbnail_path}")
                elif not PIL_AVAILABLE:
                    self.logger.debug("PIL not available for thumbnail display")
                    
                self.thumbnail_label.config(image="", text="No thumbnail available")
                self.thumbnail_label.image = None
        except Exception as e:
            self.logger.error(f"Error loading thumbnail: {e}")
            self.thumbnail_label.config(image="", text="Thumbnail error")
            self.thumbnail_label.image = None
    
    def scan_complete(self):
        """Reset UI after scan completion"""
        self.scan_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.progress_var.set(100)
        self.status_label.config(text="Scan complete")
        
        # Show completion message box
        if hasattr(self, 'duplicate_groups') and self.duplicate_groups:
            total_groups = len(self.duplicate_groups)
            total_files = sum(len(group) for group in self.duplicate_groups)
            
            message = f"Scan completed successfully!\n\n"
            message += f"Found {total_groups} duplicate groups containing {total_files} files.\n"
            message += f"Check the results below for quality recommendations."
            
            messagebox.showinfo("Scan Complete", message)
        else:
            messagebox.showinfo("Scan Complete", 
                              "Scan completed successfully!\n\n"
                              "No duplicate files were found in the scanned directory.")
        
        # Add info message to the log area
        if hasattr(self, 'duplicate_groups') and self.duplicate_groups:
            self.add_info_message(f"Scan complete: Found {len(self.duplicate_groups)} duplicate groups", "success")
        else:
            self.add_info_message("Scan complete: No duplicates found", "info")
    
    def stop_scan(self):
        """Stop current scan"""
        self.logger.info("Stop button pressed")
        if hasattr(self, 'scanner') and self.scanner:
            self.logger.info("Stopping scanner...")
            self.scanner.stop()
            self.status_label.config(text="Stopping scan...")
        else:
            self.logger.info("No active scanner found")
        
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
            self.logger.info("Cache cleared successfully")
            messagebox.showinfo("Cache Cleared", "All cached data has been cleared")
        except Exception as e:
            self.logger.error(f"Failed to clear cache: {e}")
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
            
            scanner = VideoScanner(num_workers=int(self.cpu_cores_var.get()), logger=self.logger)
            
            def progress_callback(current, total):
                progress = (current / total) * 100 if total > 0 else 0
                self.root.after(0, lambda: self.progress_var.set(progress))
            
            scanner.generate_thumbnails(file_paths, progress_callback)
            
            self.root.after(0, lambda: self.status_label.config(text="Thumbnails generated"))
            
        except Exception as e:
            error_msg = f"Thumbnail generation failed: {e}"
            self.logger.error(error_msg)
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
                                       f"Are you sure you want to delete:\n{file_path}\n\n"
                                       f"This will also remove the file from the database and delete its thumbnail.")
            if result:
                try:
                    # Remove from database first to get thumbnail info
                    src_path = Path(__file__).parent.parent
                    sys.path.insert(0, str(src_path))
                    from core.database import VideoDatabase
                    
                    db = VideoDatabase()
                    
                    # Get thumbnail path before removing from database
                    thumbnail_path = db.get_file_thumbnail(file_path)
                    
                    # Delete the actual file
                    os.remove(file_path)
                    
                    # Remove from database (this will also try to delete thumbnail)
                    db._remove_file(file_path)
                    
                    # Remove from tree view
                    self.results_tree.delete(item)
                    
                    # Show success message
                    msg = "File deleted successfully"
                    if thumbnail_path:
                        msg += f"\nThumbnail also removed: {Path(thumbnail_path).name}"
                    
                    self.logger.info(f"Deleted file: {file_path}")
                    if thumbnail_path:
                        self.logger.info(f"Deleted thumbnail: {thumbnail_path}")
                    
                    messagebox.showinfo("Deleted", msg)
                    
                except Exception as e:
                    error_msg = f"Failed to delete file: {e}"
                    self.logger.error(error_msg)
                    messagebox.showerror("Error", error_msg)
    
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

    def delete_all_low_quality(self):
        """Delete all low quality files in selected duplicate groups"""
        if not self.duplicate_groups:
            messagebox.showwarning("No Duplicates", "No duplicate groups found. Please scan for duplicates first.")
            return
        
        # Get selected groups
        selected_groups = self.get_selected_groups()
        if not selected_groups:
            messagebox.showwarning("No Groups Selected", "No duplicate groups are selected for auto-delete.\n\nPlease check the boxes next to the groups you want to process.")
            return
        
        # Get actual file paths for selected groups
        selected_file_groups = []
        for group_item in selected_groups:
            # Get all file paths from this group
            file_paths = []
            for child in self.results_tree.get_children(group_item):
                tags = self.results_tree.item(child, "tags")
                if tags and len(tags) > 0 and tags[0] not in ['keep', 'delete', 'same_duration', 'different_duration']:
                    file_paths.append(tags[0])
            if file_paths:
                selected_file_groups.append(file_paths)
        
        if not selected_file_groups:
            messagebox.showwarning("No Valid Groups", "No valid file groups found in selected items.")
            return
        
        # Confirm the operation
        total_selected = len(selected_file_groups)
        result = messagebox.askyesno("Confirm Batch Delete", 
                                   f"Delete low quality files in {total_selected} selected duplicate groups?\n\n"
                                   f"This will analyze each selected group and delete lower quality duplicates.\n"
                                   f"Groups where low quality videos are much longer will be skipped.")
        
        if not result:
            return
        
        try:
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.quality_analyzer import VideoQualityAnalyzer
            from core.database import VideoDatabase
            
            quality_analyzer = VideoQualityAnalyzer()
            db = VideoDatabase()
            
            # Track statistics
            total_deleted = 0
            total_space_saved = 0.0
            skipped_groups = []
            processed_groups = 0
              # Progress tracking
            total_selected = len(selected_file_groups)
            self.logger.info(f"Starting batch deletion of low quality files in {total_selected} selected groups...")
            
            for group_index, file_paths in enumerate(selected_file_groups):
                try:
                    if len(file_paths) < 2:
                        continue
                    
                    self.logger.info(f"Processing group {group_index + 1}/{total_selected}: {len(file_paths)} files")
                    
                    # Analyze group quality
                    group_analysis = quality_analyzer.analyze_duplicate_group(file_paths)
                    
                    if not group_analysis['recommendation']['delete']:
                        self.logger.info(f"Group {group_index + 1}: No files recommended for deletion")
                        continue
                    
                    # Check for duration mismatch (skip if low quality file is much longer)
                    best_file = group_analysis['recommendation']['best_file']
                    files_to_delete = group_analysis['recommendation']['delete']
                    
                    should_skip = False
                    skip_reason = ""
                    
                    for delete_path in files_to_delete:
                        # Find the file data for this delete path
                        delete_file_data = None
                        for file_data in group_analysis['files']:
                            if file_data['path'] == delete_path:
                                delete_file_data = file_data
                                break
                        
                        if delete_file_data:
                            best_duration = best_file['metadata'].get('duration', 0)
                            delete_duration = delete_file_data['metadata'].get('duration', 0)
                            
                            # Skip if the "low quality" file is significantly longer (more than 20% longer)
                            if delete_duration > best_duration * 1.2 and delete_duration > best_duration + 30:
                                should_skip = True
                                skip_reason = f"Low quality file is much longer ({delete_duration:.1f}s vs {best_duration:.1f}s)"
                                break
                    
                    if should_skip:
                        self.logger.warning(f"Group {group_index + 1}: Skipped - {skip_reason}")
                        skipped_groups.append({
                            'group_index': group_index + 1,
                            'reason': skip_reason,
                            'files': [Path(f).name for f in file_paths]
                        })
                        continue
                    
                    # Delete the files
                    group_deleted = 0
                    group_space_saved = 0.0
                    
                    for delete_path in files_to_delete:
                        try:
                            # Get file size before deletion
                            file_size_mb = 0
                            for file_data in group_analysis['files']:
                                if file_data['path'] == delete_path:
                                    file_size_mb = file_data['metadata'].get('file_size_mb', 0)
                                    break
                            
                            # Delete the actual file
                            if os.path.exists(delete_path):
                                os.remove(delete_path)
                                group_deleted += 1
                                group_space_saved += file_size_mb
                                self.logger.info(f"Deleted: {Path(delete_path).name} ({file_size_mb:.1f} MB)")
                                
                                # Remove from database (includes thumbnail cleanup)
                                db._remove_file(delete_path)
                            
                        except Exception as file_e:
                            self.logger.error(f"Failed to delete {Path(delete_path).name}: {file_e}")
                    
                    if group_deleted > 0:
                        total_deleted += group_deleted
                        total_space_saved += group_space_saved
                        processed_groups += 1
                        self.logger.info(f"Group {group_index + 1}: Deleted {group_deleted} files, saved {group_space_saved:.1f} MB")
                    
                except Exception as group_e:
                    self.logger.error(f"Error processing group {group_index + 1}: {group_e}")
                    continue
            
            # Show summary
            summary_msg = f"Batch deletion completed!\n\n"
            summary_msg += f"Processed: {processed_groups} groups\n"
            summary_msg += f"Files deleted: {total_deleted}\n"
            summary_msg += f"Space saved: {total_space_saved:.1f} MB\n"
            
            if skipped_groups:
                summary_msg += f"\nSkipped groups: {len(skipped_groups)}\n"
                summary_msg += "(Groups skipped due to duration mismatches)"
            
            self.logger.info(summary_msg.replace('\n', ' '))
            messagebox.showinfo("Batch Deletion Complete", summary_msg)
            
            # Show details of skipped groups if any
            if skipped_groups:
                skip_details = "Skipped Groups (duration mismatches):\n\n"
                for skip_info in skipped_groups[:10]:  # Show first 10
                    skip_details += f"Group {skip_info['group_index']}: {skip_info['reason']}\n"
                    skip_details += f"Files: {', '.join(skip_info['files'][:3])}"
                    if len(skip_info['files']) > 3:
                        skip_details += f" + {len(skip_info['files']) - 3} more"
                    skip_details += "\n\n"
                
                if len(skipped_groups) > 10:
                    skip_details += f"... and {len(skipped_groups) - 10} more groups"
                
                # Create a new window to show skipped groups
                self._show_skipped_groups_dialog(skip_details)
            
            # Refresh the results view
            self.logger.info("Refreshing results view...")
            self.compare_database()
            
        except Exception as e:
            error_msg = f"Failed to perform batch deletion: {e}"
            self.logger.error(error_msg)
            messagebox.showerror("Error", error_msg)

    def _show_skipped_groups_dialog(self, details_text):
        """Show a dialog with details of skipped groups"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Skipped Groups Details")
        dialog.geometry("600x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Text widget with scrollbar
        frame = ttk.Frame(dialog, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        text_widget = scrolledtext.ScrolledText(frame, wrap=tk.WORD, state=tk.NORMAL)
        text_widget.pack(fill=tk.BOTH, expand=True)
        text_widget.insert(tk.END, details_text)
        text_widget.configure(state=tk.DISABLED)
        
        # Close button
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(button_frame, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)

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
            
            # Initialize scanner with similarity threshold and other settings
            scanner = VideoScanner(
                similarity_threshold=self.threshold_var.get(),
                num_workers=int(self.cpu_cores_var.get()), 
                logger=self.logger
            )
            
            self.logger.info(f"Comparing database with similarity threshold: {self.threshold_var.get()}")
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
            self.logger.error(error_msg)
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
            self.root.after(0, lambda: self.status_label.config(text="Database comparison failed"))
    
    def show_database_stats(self):
        """Show statistics about the current database"""
        try:
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.scanner import VideoScanner
            
            scanner = VideoScanner(num_workers=int(self.cpu_cores_var.get()), logger=self.logger)
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
                
                self.logger.info("Database statistics retrieved successfully")
                messagebox.showinfo("Database Statistics", stats_text)
            else:
                self.logger.warning("No statistics available from database")
                messagebox.showwarning("Database Stats", "Could not retrieve database statistics")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get database stats: {e}")

    def clean_database(self):
        """Clean database by removing entries for non-existent files and orphaned thumbnails"""
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
            
            # Count thumbnails
            thumbnail_dir = src_path / "thumbnails"
            thumbnail_count = 0
            if thumbnail_dir.exists():
                thumbnail_files = [f for f in thumbnail_dir.glob("*.jpg")]
                thumbnail_count = len(thumbnail_files)
            
            if missing_count == 0:
                # Check for orphaned thumbnails even if no missing files
                result = messagebox.askyesno("Clean Database", 
                                           f"No missing files found.\n\n"
                                           f"Would you like to clean up orphaned thumbnails?\n"
                                           f"Found {thumbnail_count} thumbnail files.")
                if not result:
                    return
                
                # Clean orphaned thumbnails only
                self.status_label.config(text="Cleaning orphaned thumbnails...")
                self.root.update()
                
                # Get valid thumbnails from database
                valid_thumbnails = [f.get('thumbnail_path') for f in before_files 
                                  if f.get('thumbnail_path') and os.path.exists(f.get('thumbnail_path'))]
                
                orphaned_count = db._cleanup_orphaned_thumbnails(valid_thumbnails)
                
                self.status_label.config(text="Thumbnail cleanup complete")
                messagebox.showinfo("Thumbnail Cleanup Complete", 
                                  f"Removed {orphaned_count} orphaned thumbnails.")
                return
            
            # Confirm cleanup
            result = messagebox.askyesno("Confirm Database Cleanup", 
                                       f"Found {missing_count} missing files out of {before_count} total files.\n"
                                       f"Found {thumbnail_count} thumbnail files.\n\n"
                                       f"This will remove database entries for files that no longer exist\n"
                                       f"and clean up orphaned thumbnails.\n\n"
                                       f"Continue with cleanup?")
            
            if result:
                self.status_label.config(text="Cleaning database and thumbnails...")
                self.root.update()
                
                # Capture cleanup output
                import io
                old_stdout = sys.stdout
                captured_output = io.StringIO()
                sys.stdout = captured_output
                
                # Perform cleanup
                db.cleanup_missing_files()
                
                # Restore stdout and get captured output
                sys.stdout = old_stdout
                cleanup_messages = captured_output.getvalue()
                
                # Log cleanup messages
                for line in cleanup_messages.split('\n'):
                    if line.strip():
                        self.logger.info(line)
                
                # Get stats after cleanup
                after_files = db.get_all_files()
                after_count = len(after_files)
                cleaned_count = before_count - after_count
                
                # Count thumbnails after cleanup
                thumbnail_count_after = 0
                if thumbnail_dir.exists():
                    thumbnail_files = [f for f in thumbnail_dir.glob("*.jpg")]
                    thumbnail_count_after = len(thumbnail_files)
                
                thumbnails_removed = thumbnail_count - thumbnail_count_after
                
                self.status_label.config(text="Database cleanup complete")
                
                messagebox.showinfo("Database Cleanup Complete", 
                                  f"Database cleanup completed successfully!\n\n"
                                  f"Removed {cleaned_count} entries for missing files\n"
                                  f"Removed {thumbnails_removed} orphaned thumbnails\n"
                                  f"Database now contains {after_count} files\n"                                  f"See log tab for details")                
        except Exception as e:
            error_msg = f"Failed to clean database: {e}"
            self.logger.error(error_msg)
            self.status_label.config(text="Database cleanup failed")
            messagebox.showerror("Error", error_msg)
    
    def on_tree_click(self, event):
        """Handle clicks on the TreeView to toggle checkboxes"""
        # Get the item that was clicked using the correct identify method
        region = self.results_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
            
        item = self.results_tree.identify("item", event.x, event.y)
        if not item:
            return
        
        # Only handle clicks on group items (not individual files)
        parent = self.results_tree.parent(item)
        if parent:  # This is a file item, not a group
            return
        
        # Check if click is in the select column (checkbox column)
        column = self.results_tree.identify("column", event.x, event.y)
        if column == "#1":  # #1 is the select column
            self.toggle_group_checkbox(item)
    
    def toggle_group_checkbox(self, group_item):
        """Toggle the checkbox state for a duplicate group"""
        current_state = self.group_checkbox_states.get(group_item, True)
        new_state = not current_state
        self.group_checkbox_states[group_item] = new_state
        
        # Update the visual representation
        checkbox_symbol = "☑" if new_state else "☐"
        current_values = list(self.results_tree.item(group_item, "values"))
        current_values[0] = checkbox_symbol
        self.results_tree.item(group_item, values=current_values)
        
        self.logger.debug(f"Toggled group checkbox: {'checked' if new_state else 'unchecked'}")
    
    def select_all_groups(self):
        """Select all duplicate groups for auto-delete"""
        for item in self.results_tree.get_children():
            self.group_checkbox_states[item] = True
            current_values = list(self.results_tree.item(item, "values"))
            current_values[0] = "☑"
            self.results_tree.item(item, values=current_values)
        
        self.logger.info("Selected all duplicate groups for auto-delete")
        
    def deselect_all_groups(self):
        """Deselect all duplicate groups from auto-delete"""
        for item in self.results_tree.get_children():
            self.group_checkbox_states[item] = False
            current_values = list(self.results_tree.item(item, "values"))
            current_values[0] = "☐"
            self.results_tree.item(item, values=current_values)
        
        self.logger.info("Deselected all duplicate groups from auto-delete")
    
    def get_selected_groups(self):
        """Get list of group items that are selected for auto-delete"""
        selected_groups = []
        for item in self.results_tree.get_children():
            if self.group_checkbox_states.get(item, False):
                selected_groups.append(item)
        return selected_groups