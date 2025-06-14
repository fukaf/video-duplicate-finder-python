# src/core/unified_hasher.py
import os
from typing import Optional, Union
from .hasher import PerceptualHasher

# Fix for Pillow 10.0+ compatibility
try:
    from PIL import Image
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.Resampling.LANCZOS
except ImportError:
    pass

try:
    from videohash import VideoHash
    VIDEOHASH_AVAILABLE = True
except ImportError:
    VIDEOHASH_AVAILABLE = False

class UnifiedHasher:
    """
    Unified interface for different video hashing methods.
    Supports both the original perceptual hasher and the videohash library.
    """
    
    def __init__(self, hash_method: str = "original"):
        """
        Initialize the unified hasher.
        
        Args:
            hash_method: Either "original" or "videohash"
        """
        self.hash_method = hash_method.lower()
        
        if self.hash_method == "original":
            self.hasher = PerceptualHasher()
        elif self.hash_method == "videohash":
            if not VIDEOHASH_AVAILABLE:
                raise ImportError("videohash library is not installed. Please install it with: pip install videohash")
            # VideoHash doesn't need to be pre-initialized
            self.hasher = None
        else:
            raise ValueError(f"Unsupported hash method: {hash_method}. Use 'original' or 'videohash'")
    
    def compute_video_hash(self, video_path: str) -> Optional[str]:
        """
        Compute hash for a video file using the selected method.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Hash string or None if failed
        """
        if not os.path.exists(video_path):
            return None
            
        try:
            if self.hash_method == "original":
                return self.hasher.compute_video_hash(video_path)
            elif self.hash_method == "videohash":
                # Create VideoHash instance for this video
                video_hash = VideoHash(path=video_path)
                # Convert to hex string for consistency
                return video_hash.hash_hex
        except Exception as e:
            # Log the error if logger is available
            print(f"Error computing hash for {video_path}: {e}")
            return None
    
    def compare_hashes(self, hash1: str, hash2: str) -> float:
        """
        Compare two hashes and return similarity score.
        
        Args:
            hash1: First hash string
            hash2: Second hash string
            
        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not hash1 or not hash2:
            return 0.0
            
        try:
            if self.hash_method == "original":
                # For original hasher, we need to convert back to format expected by comparator
                # This is a simplified comparison - in practice you might want to use the full comparator
                if hash1 == hash2:
                    return 1.0
                # Simple Hamming distance for hex strings
                return self._hamming_similarity(hash1, hash2)
            elif self.hash_method == "videohash":
                # For videohash, we can use the library's comparison methods
                # Convert hex strings back to VideoHash objects for comparison
                # This is a simplified approach - ideally we'd store the VideoHash objects
                return self._hamming_similarity(hash1, hash2)
        except Exception as e:
            print(f"Error comparing hashes: {e}")
            return 0.0
    
    def _hamming_similarity(self, hash1: str, hash2: str) -> float:
        """
        Calculate similarity based on Hamming distance for hex strings.
        
        Args:
            hash1: First hash string (hex)
            hash2: Second hash string (hex)
            
        Returns:
            Similarity score between 0.0 and 1.0
        """
        if len(hash1) != len(hash2):
            return 0.0
            
        try:
            # Convert hex to binary and calculate Hamming distance
            bin1 = bin(int(hash1, 16))[2:].zfill(len(hash1) * 4)
            bin2 = bin(int(hash2, 16))[2:].zfill(len(hash2) * 4)
            
            if len(bin1) != len(bin2):
                return 0.0
                
            # Count differing bits
            diff_bits = sum(c1 != c2 for c1, c2 in zip(bin1, bin2))
            total_bits = len(bin1)
            
            # Convert to similarity (1.0 = identical, 0.0 = completely different)
            similarity = 1.0 - (diff_bits / total_bits)
            return similarity
        except (ValueError, TypeError):
            return 0.0
    
    def get_method_info(self) -> dict:
        """
        Get information about the current hash method.
        
        Returns:
            Dictionary with method information
        """
        if self.hash_method == "original":
            return {
                "method": "original",
                "name": "Original Perceptual Hasher",
                "description": "Custom perceptual hashing using frame sampling and multiple hash techniques",
                "available": True
            }
        elif self.hash_method == "videohash":
            return {
                "method": "videohash",
                "name": "VideoHash Library",
                "description": "Advanced perceptual video hashing using videohash library",
                "available": VIDEOHASH_AVAILABLE
            }
