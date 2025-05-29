import cv2
import numpy as np
import imagehash
from PIL import Image
from typing import List, Tuple, Optional
import hashlib

class PerceptualHasher:
    """Fast perceptual hashing for video duplicate detection"""
    
    def __init__(self, hash_size: int = 8):
        self.hash_size = hash_size
        
    def compute_video_hash(self, video_path: str) -> Optional[str]:
        """
        Compute perceptual hash for a video file
        Returns: Combined hash string or None if failed
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
            
            # Get video properties
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if frame_count == 0:
                cap.release()
                return None
            
            # Sample frames at regular intervals
            sample_count = min(10, frame_count)
            frame_hashes = []
            
            for i in range(sample_count):
                frame_pos = int((i / sample_count) * frame_count)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                
                ret, frame = cap.read()
                if ret:
                    frame_hash = self._compute_frame_hash(frame)
                    if frame_hash:
                        frame_hashes.append(frame_hash)
            
            cap.release()
            
            if not frame_hashes:
                return None
            
            # Combine frame hashes
            return self._combine_hashes(frame_hashes)
            
        except Exception as e:
            print(f"Error computing hash for {video_path}: {e}")
            return None
    
    def _compute_frame_hash(self, frame: np.ndarray) -> Optional[str]:
        """Compute hash for a single frame"""
        try:
            # Convert to PIL Image for imagehash
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            
            # Compute multiple hash types for robustness
            dhash = str(imagehash.dhash(pil_image, hash_size=self.hash_size))
            phash = str(imagehash.phash(pil_image, hash_size=self.hash_size))
            
            return f"{dhash}:{phash}"
            
        except Exception:
            return None
    
    def _combine_hashes(self, frame_hashes: List[str]) -> str:
        """Combine multiple frame hashes into single video hash"""
        combined = "|".join(frame_hashes)
        # Create a shorter representative hash
        md5_hash = hashlib.md5(combined.encode()).hexdigest()
        return f"{len(frame_hashes)}:{md5_hash}:{combined[:100]}"
    
    def compute_similarity(self, hash1: str, hash2: str) -> float:
        """
        Compute similarity between two video hashes
        Returns: Similarity score 0.0-1.0 (higher = more similar)
        """
        if not hash1 or not hash2:
            return 0.0
        
        try:
            # Parse hash components
            parts1 = hash1.split(':', 2)
            parts2 = hash2.split(':', 2)
            
            if len(parts1) < 3 or len(parts2) < 3:
                return 0.0
            
            frame_count1 = int(parts1[0])
            frame_count2 = int(parts2[0])
            
            # Frame count similarity
            count_similarity = min(frame_count1, frame_count2) / max(frame_count1, frame_count2)
            
            # Hash similarity
            hash_similarity = self._compare_hash_strings(parts1[2], parts2[2])
            
            # Combined score
            return (count_similarity * 0.3) + (hash_similarity * 0.7)
            
        except Exception:
            return 0.0
    
    def _compare_hash_strings(self, hash_str1: str, hash_str2: str) -> float:
        """Compare hash strings using Hamming distance"""
        if len(hash_str1) != len(hash_str2):
            min_len = min(len(hash_str1), len(hash_str2))
            hash_str1 = hash_str1[:min_len]
            hash_str2 = hash_str2[:min_len]
        
        if not hash_str1:
            return 0.0
        
        # Hamming distance
        differences = sum(c1 != c2 for c1, c2 in zip(hash_str1, hash_str2))
        similarity = 1.0 - (differences / len(hash_str1))
        
        return max(0.0, similarity)
