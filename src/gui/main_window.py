# src/gui/main_window.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
from typing import List
import os
import sys
from datetime import datetime

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class MainWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Video Duplicate Finder - Python")
        self.root.geometry("1200x800")
        
        self.setup_ui()
        self.scanner = None
        self.duplicate_groups = []
        
    def setup_ui(self):
        # Main frame with horizontal split
        main_frame = ttk.Frame(self.root, padding="10")
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
        
        self.results_tree = ttk.Treeview(results_frame, columns=("similarity", "size", "action"), 
                                        show="tree headings")
        self.results_tree.heading("#0", text="Files")
        self.results_tree.heading("similarity", text="Similarity")
        self.results_tree.heading("size", text="Size")
        self.results_tree.heading("action", text="Action")
        
        self.results_tree.column("similarity", width=80)
        self.results_tree.column("size", width=80)
        self.results_tree.column("action", width=80)
        
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
        """Setup the preview panel for thumbnails and file details"""
        # Thumbnail display
        self.thumbnail_label = ttk.Label(parent, text="Select a file to preview")
        self.thumbnail_label.grid(row=0, column=0, pady=10)
        
        # File details
        details_frame = ttk.LabelFrame(parent, text="File Details", padding="5")
        details_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        
        self.file_path_var = tk.StringVar()
        self.file_size_var = tk.StringVar()
        self.file_modified_var = tk.StringVar()
        
        ttk.Label(details_frame, text="Path:").grid(row=0, column=0, sticky=tk.W)
        path_label = ttk.Label(details_frame, textvariable=self.file_path_var, wraplength=300)
        path_label.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(details_frame, text="Size:").grid(row=1, column=0, sticky=tk.W)
        ttk.Label(details_frame, textvariable=self.file_size_var).grid(row=1, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(details_frame, text="Modified:").grid(row=2, column=0, sticky=tk.W)
        ttk.Label(details_frame, textvariable=self.file_modified_var).grid(row=2, column=1, sticky=tk.W, padx=5)
        
        # Action buttons
        action_frame = ttk.Frame(parent)
        action_frame.grid(row=2, column=0, pady=10)
        
        ttk.Button(action_frame, text="Open File", command=self.open_selected_file).grid(row=0, column=0, padx=5)
        ttk.Button(action_frame, text="Delete File", command=self.delete_selected_file).grid(row=0, column=1, padx=5)
        ttk.Button(action_frame, text="Show in Explorer", command=self.show_in_explorer).grid(row=0, column=2, padx=5)
        
        parent.columnconfigure(0, weight=1)
    
    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.dir_var.set(directory)
    
    def update_threshold_label(self, value):
        self.threshold_label.config(text=f"{float(value):.2f}")
    
    def start_scan(self):
        directory = self.dir_var.get()
        if not directory or not Path(directory).exists():
            messagebox.showerror("Error", "Please select a valid directory")
            return
        
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
            # Add src path for imports
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.scanner import VideoScanner
            
            scanner = VideoScanner(
                similarity_threshold=self.threshold_var.get(),
                progress_callback=self.update_progress
            )
            
            duplicates = scanner.scan_directory(directory, use_cache=self.use_cache_var.get())
            
            # Group duplicates
            self.duplicate_groups = self._group_duplicates_by_cluster(duplicates)
            
            # Update UI in main thread
            self.root.after(0, self.display_results, self.duplicate_groups)
            
        except Exception as e:
            error_msg = f"Scan failed: {e}"
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
        finally:
            self.root.after(0, self.scan_complete)
    
    def _group_duplicates_by_cluster(self, duplicates):
        """Group duplicate pairs into clusters of similar videos"""
        if not duplicates:
            return []
        
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
        
        return list(groups.values())
    
    def update_progress(self, current, total):
        """Update progress bar - called from background thread"""
        progress = (current / total) * 100 if total > 0 else 0
        self.root.after(0, lambda: self.progress_var.set(progress))
    
    def display_results(self, duplicate_groups):
        """Display scan results"""
        self.status_label.config(text=f"Found {len(duplicate_groups)} duplicate groups")
        
        for i, group in enumerate(duplicate_groups):
            group_id = self.results_tree.insert("", "end", text=f"Group {i+1} ({len(group)} files)", 
                                               values=("", "", ""))
            
            for file_path in group:
                try:
                    file_size = os.path.getsize(file_path)
                    size_str = self._format_file_size(file_size)
                except:
                    size_str = "Unknown"
                
                self.results_tree.insert(group_id, "end", text=Path(file_path).name, 
                                       values=("", size_str, ""), tags=(file_path,))
    
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
        """Show thumbnail and details for selected file"""
        try:
            # Update file details
            self.file_path_var.set(file_path)
            
            if os.path.exists(file_path):
                stat = os.stat(file_path)
                self.file_size_var.set(self._format_file_size(stat.st_size))
                self.file_modified_var.set(
                    datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                )
            else:
                self.file_size_var.set("File not found")
                self.file_modified_var.set("")
            
            # Try to load thumbnail
            self.load_thumbnail(file_path)
            
        except Exception as e:
            print(f"Error showing preview for {file_path}: {e}")
    
    def load_thumbnail(self, file_path):
        """Load and display thumbnail for video file"""
        try:
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.scanner import VideoScanner
            
            scanner = VideoScanner()
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
        if hasattr(self, 'scanner') and self.scanner:
            self.scanner.stop()
        self.scan_complete()
    
    def clear_cache(self):
        """Clear all cached data"""
        try:
            src_path = Path(__file__).parent.parent
            sys.path.insert(0, str(src_path))
            from core.scanner import VideoScanner
            
            scanner = VideoScanner()
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
            
            scanner = VideoScanner()
            
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
    
    def run(self):
        self.root.mainloop()