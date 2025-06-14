# src/core/unified_hasher.py
import os
from typing import Optional, Union

# Fix for Pillow 10.0+ compatibility - must be done before any other PIL imports
try:
    from PIL import Image
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.Resampling.LANCZOS
        # Also add other deprecated constants for completeness
        if not hasattr(Image, 'BICUBIC'):
            Image.BICUBIC = Image.Resampling.BICUBIC
        if not hasattr(Image, 'LANCZOS'):
            Image.LANCZOS = Image.Resampling.LANCZOS
        if not hasattr(Image, 'NEAREST'):
            Image.NEAREST = Image.Resampling.NEAREST
except ImportError:
    pass

from .hasher import PerceptualHasher

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
        else:            raise ValueError(f"Unsupported hash method: {hash_method}. Use 'original' or 'videohash'")
    
    def compute_video_hash(self, video_path: str) -> Optional[str]:
        """
        Compute hash for a video file using the selected method.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Hash string or serialized data for videohash, None if failed
        """
        if not os.path.exists(video_path):
            return None
            
        try:
            if self.hash_method == "original":
                return self.hasher.compute_video_hash(video_path)
            elif self.hash_method == "videohash":
                # Create VideoHash instance for this video
                video_hash = VideoHash(path=video_path)
                # Convert hex string to integer for proper comparison
                # Remove '0x' prefix and convert to int
                hex_value = video_hash.hash_hex
                if hex_value.startswith('0x'):
                    hex_value = hex_value[2:]
                # Store as integer string for database storage
                return str(int(hex_value, 16))
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
                # For original hasher, use existing comparison logic
                # This is a simplified comparison - you might want to use the full comparator
                if hash1 == hash2:
                    return 1.0
                # Simple Hamming distance for hex strings
                return self._hamming_similarity(hash1, hash2)
            elif self.hash_method == "videohash":
                # For videohash, compute Hamming distance between integer values
                try:
                    # Convert string representations back to integers
                    val1 = int(hash1)
                    val2 = int(hash2)
                    
                    # Calculate Hamming distance
                    xor_result = val1 ^ val2
                    hamming_distance = bin(xor_result).count('1')
                    
                    # Convert to similarity (64 bits total for videohash)
                    total_bits = 64
                    similarity = 1.0 - (hamming_distance / total_bits)
                    
                    return similarity
                except (ValueError, TypeError):
                    return 0.0
        except Exception as e:
            print(f"Error comparing hashes: {e}")
            return 0.0
    
    def is_similar_videohash(self, hash1: str, hash2: str, threshold: int = 10) -> bool:
        """
        Check if two videohash values are similar using the recommended method.
        
        Args:
            hash1: First hash string
            hash2: Second hash string
            threshold: Maximum Hamming distance for similarity (default 10)
            
        Returns:
            True if similar, False otherwise
        """
        if not hash1 or not hash2:
            return False
            
        try:
            # Convert string representations back to integers
            val1 = int(hash1)
            val2 = int(hash2)
            
            # Calculate Hamming distance
            xor_result = val1 ^ val2
            hamming_distance = bin(xor_result).count('1')
            
            # VideoHash typically considers videos similar if Hamming distance <= 10
            return hamming_distance <= threshold
        except (ValueError, TypeError):
            return False
    
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
