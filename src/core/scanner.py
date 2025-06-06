# src/core/scanner.py
import os
import sqlite3
from pathlib import Path
from typing import List, Tuple, Dict, Callable, Optional
import hashlib
import json
from datetime import datetime
import threading

from .hasher import PerceptualHasher
from .comparator import EfficientComparator
from .database import VideoDatabase

class VideoScanner:
    """Main scanner class for efficient video duplicate detection"""
    
    SUPPORTED_FORMATS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp'}
    
    def __init__(self, similarity_threshold: float = 0.8, 
                 progress_callback: Optional[Callable[[int, int], None]] = None,
                 db_path: str = "video_duplicates.db"):
        self.similarity_threshold = similarity_threshold
        self.progress_callback = progress_callback
        self.hasher = PerceptualHasher()
        self.comparator = EfficientComparator(similarity_threshold)
        self.database = VideoDatabase(db_path)
        self._stop_requested = False
        
    def scan_directory(self, directory: str, use_cache: bool = True) -> List[Tuple[str, str, float]]:
        """
        Scan directory for video duplicates
        Args:
            directory: Directory path to scan
            use_cache: Whether to use cached hashes from database
        Returns:
            List of duplicate pairs with similarity scores
        """
        try:
            self._stop_requested = False
            
            # Step 1: Find all video files
            video_files = self._find_video_files(directory)
            if not video_files:
                return []
            
            # Step 2: Process files and compute hashes
            file_hashes = self._process_files(video_files, use_cache)
            
            if self._stop_requested:
                return []
            
            # Step 3: Find duplicates efficiently
            duplicates = self.comparator.find_duplicates_parallel(file_hashes)
            
            # Step 4: Group duplicates by similarity clusters
            grouped_duplicates = self._group_duplicates(duplicates)
            
            return grouped_duplicates
            
        except Exception as e:
            print(f"Error during scan: {e}")
            return []
    
    def _find_video_files(self, directory: str) -> List[str]:
        """Find all video files in directory recursively"""
        video_files = []
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                if Path(file).suffix.lower() in self.SUPPORTED_FORMATS:
                    full_path = os.path.join(root, file)
                    video_files.append(full_path)
        
        return video_files
    
    def _process_files(self, video_files: List[str], use_cache: bool) -> Dict[str, str]:
        """Process video files and compute hashes"""
        file_hashes = {}
        total_files = len(video_files)
        processed = 0
        
        for file_path in video_files:
            if self._stop_requested:
                break
                
            try:
                # Check cache first
                cached_hash = None
                if use_cache:
                    cached_hash = self.database.get_file_hash(file_path)
                
                if cached_hash:
                    file_hashes[file_path] = cached_hash
                else:
                    # Compute new hash
                    file_hash = self.hasher.compute_video_hash(file_path)
                    if file_hash:
                        file_hashes[file_path] = file_hash
                        
                        # Store in database
                        file_info = self._get_file_info(file_path)
                        self.database.store_file_hash(file_path, file_hash, file_info)
                
                processed += 1
                if self.progress_callback:
                    self.progress_callback(processed, total_files)
                    
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                processed += 1
                continue
        
        return file_hashes
    
    def _get_file_info(self, file_path: str) -> Dict:
        """Get file metadata"""
        try:
            stat = os.stat(file_path)
            return {
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'created': datetime.fromtimestamp(stat.st_ctime).isoformat()
            }
        except:
            return {}
    
    def _group_duplicates(self, duplicates: List[Tuple[str, str, float]]) -> List[Tuple[str, str, float]]:
        """Group duplicate pairs into clusters"""
        if not duplicates:
            return []
        
        # For now, return sorted by similarity
        # TODO: Implement proper clustering algorithm
        return sorted(duplicates, key=lambda x: x[2], reverse=True)
    
    def get_cached_files_count(self) -> int:
        """Get number of files already cached in database"""
        return self.database.get_files_count()
    
    def clear_cache(self):
        """Clear all cached data"""
        self.database.clear_all()
    
    def stop(self):
        """Request scan to stop"""
        self._stop_requested = True
    
    def get_file_thumbnail(self, file_path: str) -> Optional[str]:
        """Get thumbnail path for a video file"""
        return self.database.get_file_thumbnail(file_path)
    
    def generate_thumbnails(self, file_paths: List[str], 
                          progress_callback: Optional[Callable[[int, int], None]] = None):
        """Generate thumbnails for video files"""
        from .thumbnail import ThumbnailGenerator
        
        generator = ThumbnailGenerator()
        total = len(file_paths)
        
        for i, file_path in enumerate(file_paths):
            if self._stop_requested:
                break
                
            try:
                thumbnail_path = generator.generate_thumbnail(file_path)
                if thumbnail_path:
                    self.database.store_file_thumbnail(file_path, thumbnail_path)
                    
                if progress_callback:
                    progress_callback(i + 1, total)
                    
            except Exception as e:
                print(f"Error generating thumbnail for {file_path}: {e}")
