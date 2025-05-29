# src/core/thumbnail.py
import cv2
import os
from pathlib import Path
from typing import Optional
import hashlib

class ThumbnailGenerator:
    """Generate thumbnails for video files"""
    
    def __init__(self, thumbnail_dir: str = "thumbnails", size: tuple = (160, 120)):
        self.thumbnail_dir = thumbnail_dir
        self.size = size
        
        # Create thumbnail directory if it doesn't exist
        Path(self.thumbnail_dir).mkdir(exist_ok=True)
    
    def generate_thumbnail(self, video_path: str) -> Optional[str]:
        """
        Generate thumbnail for a video file
        Args:
            video_path: Path to video file
        Returns:
            Path to generated thumbnail or None if failed
        """
        try:
            # Create unique thumbnail filename based on video path
            video_hash = hashlib.md5(video_path.encode()).hexdigest()
            thumbnail_filename = f"{video_hash}.jpg"
            thumbnail_path = os.path.join(self.thumbnail_dir, thumbnail_filename)
            
            # Skip if thumbnail already exists
            if os.path.exists(thumbnail_path):
                return thumbnail_path
            
            # Open video file
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
            
            # Get frame from 10% into the video (avoid black intro frames)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if frame_count > 0:
                target_frame = max(1, int(frame_count * 0.1))
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            
            # Read frame
            ret, frame = cap.read()
            cap.release()
            
            if not ret or frame is None:
                return None
            
            # Resize frame to thumbnail size
            thumbnail = cv2.resize(frame, self.size)
            
            # Save thumbnail
            success = cv2.imwrite(thumbnail_path, thumbnail)
            
            if success:
                return thumbnail_path
            else:
                return None
                
        except Exception as e:
            print(f"Error generating thumbnail for {video_path}: {e}")
            return None
    
    def get_thumbnail_path(self, video_path: str) -> str:
        """Get the expected thumbnail path for a video"""
        video_hash = hashlib.md5(video_path.encode()).hexdigest()
        thumbnail_filename = f"{video_hash}.jpg"
        return os.path.join(self.thumbnail_dir, thumbnail_filename)
    
    def cleanup_thumbnails(self, valid_video_paths: list):
        """Remove thumbnails for videos that no longer exist"""
        try:
            valid_hashes = set()
            for video_path in valid_video_paths:
                video_hash = hashlib.md5(video_path.encode()).hexdigest()
                valid_hashes.add(f"{video_hash}.jpg")
            
            # Remove thumbnails not in valid set
            removed_count = 0
            for thumbnail_file in os.listdir(self.thumbnail_dir):
                if thumbnail_file.endswith('.jpg') and thumbnail_file not in valid_hashes:
                    thumbnail_path = os.path.join(self.thumbnail_dir, thumbnail_file)
                    try:
                        os.remove(thumbnail_path)
                        removed_count += 1
                    except:
                        pass
            
            print(f"Cleaned up {removed_count} orphaned thumbnails")
            
        except Exception as e:
            print(f"Error during thumbnail cleanup: {e}")
