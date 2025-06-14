import cv2
import numpy as np
import imagehash
from PIL import Image
from typing import List, Tuple, Optional, Dict
import hashlib
import struct

# Fix for Pillow 10.0+ compatibility with older imagehash versions
# If ANTIALIAS doesn't exist, create it as an alias to LANCZOS
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

class PerceptualHasher:
    """Advanced perceptual hashing for video duplicate detection"""
    
    def __init__(self, hash_size: int = 8, sample_frames: int = 7):
        self.hash_size = hash_size
        self.sample_frames = sample_frames
        
    def compute_video_hash(self, video_path: str) -> Optional[str]:
        """
        Compute perceptual hash for a video file using multiple techniques
        Returns: Combined perceptual hash string or None if failed
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
            
            # Get video properties
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = frame_count / fps if fps > 0 else 0
            
            if frame_count == 0:
                cap.release()
                return None
            
            # Sample frames at strategic intervals
            frame_hashes = []
            temporal_features = []
            
            # Sample from beginning, middle, end and some random points
            sample_positions = self._get_sample_positions(frame_count, self.sample_frames)
            
            for frame_pos in sample_positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                
                ret, frame = cap.read()
                if ret:
                    # Resize frame to standard size for consistent comparison
                    frame_resized = cv2.resize(frame, (256, 256))
                    
                    # Compute multiple perceptual hashes
                    frame_hash = self._compute_perceptual_frame_hash(frame_resized)
                    if frame_hash:
                        frame_hashes.append(frame_hash)
                        
                    # Extract temporal features (motion, brightness changes)
                    temporal_feature = self._extract_temporal_features(frame_resized)
                    temporal_features.append(temporal_feature)
            
            cap.release()
            
            if not frame_hashes:
                return None
              # Combine all features into a comprehensive hash
            return self._create_comprehensive_hash(frame_hashes, temporal_features, duration)
            
        except Exception as e:
            print(f"Error computing hash for {video_path}: {e}")
            return None
    
    def _get_sample_positions(self, frame_count: int, sample_count: int) -> List[int]:
        """Get strategic frame positions for sampling"""
        if frame_count <= sample_count:
            return list(range(frame_count))
        
        positions = []
        
        # Always sample first and last frame
        positions.append(0)
        positions.append(frame_count - 1)
        
        # Sample at key percentages for better duplicate detection
        # These positions are less likely to be affected by minor edits
        key_percentages = [0.1, 0.25, 0.5, 0.75, 0.9]  # 10%, 25%, 50%, 75%, 90%
        
        for pct in key_percentages:
            if len(positions) >= sample_count:
                break
            pos = int(frame_count * pct)
            if pos not in positions and pos < frame_count:
                positions.append(pos)
        
        # Fill remaining slots with evenly distributed frames
        while len(positions) < sample_count and len(positions) < frame_count:
            step = frame_count // (sample_count - len(positions) + 1)
            for i in range(1, sample_count - len(positions) + 1):
                pos = i * step
                if pos not in positions and pos < frame_count:
                    positions.append(pos)
                    break
        
        return sorted(list(set(positions)))
    
    def _compute_perceptual_frame_hash(self, frame: np.ndarray) -> Optional[Dict[str, str]]:
        """Compute multiple perceptual hashes for a single frame"""
        try:
            # Convert to PIL Image for imagehash
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            
            # Compute multiple hash types for robustness
            dhash = str(imagehash.dhash(pil_image, hash_size=self.hash_size))
            phash = str(imagehash.phash(pil_image, hash_size=self.hash_size))
            ahash = str(imagehash.average_hash(pil_image, hash_size=self.hash_size))
            whash = str(imagehash.whash(pil_image, hash_size=self.hash_size))
            
            # Add color histogram hash (custom)
            color_hash = self._compute_color_histogram_hash(frame)
            
            # Add edge hash (custom)
            edge_hash = self._compute_edge_hash(frame)
            
            return {
                'dhash': dhash,
                'phash': phash, 
                'ahash': ahash,
                'whash': whash,
                'color_hash': color_hash,
                'edge_hash': edge_hash
            }
            
        except Exception as e:
            print(f"Error computing frame hash: {e}")
            return None
    
    def _compute_color_histogram_hash(self, frame: np.ndarray) -> str:
        """Compute color histogram-based hash"""
        try:
            # Resize to small size for speed
            small_frame = cv2.resize(frame, (32, 32))
            
            # Compute histogram for each channel
            hist_b = cv2.calcHist([small_frame], [0], None, [16], [0, 256])
            hist_g = cv2.calcHist([small_frame], [1], None, [16], [0, 256])
            hist_r = cv2.calcHist([small_frame], [2], None, [16], [0, 256])
            
            # Normalize and create hash
            hist_combined = np.concatenate([hist_b.flatten(), hist_g.flatten(), hist_r.flatten()])
            hist_normalized = hist_combined / (hist_combined.sum() + 1e-8)
            
            # Convert to binary representation
            threshold = np.median(hist_normalized)
            binary_hist = (hist_normalized > threshold).astype(int)
            
            # Convert to hex string
            hex_str = ''.join([str(b) for b in binary_hist])
            return hex_str[:32]  # Limit length
            
        except Exception:
            return "0" * 32
    
    def _compute_edge_hash(self, frame: np.ndarray) -> str:
        """Compute edge-based hash"""
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Resize to standard size
            gray_resized = cv2.resize(gray, (16, 16))
            
            # Apply Canny edge detection
            edges = cv2.Canny(gray_resized, 50, 150)
            
            # Create binary hash
            binary = (edges > 0).astype(int)
            
            # Convert to hex string
            hex_str = ''.join([str(b) for b in binary.flatten()])
            return hex_str[:64]  # Limit length
            
        except Exception:
            return "0" * 64
    
    def _extract_temporal_features(self, frame: np.ndarray) -> Dict[str, float]:
        """Extract temporal features from frame"""
        try:
            # Convert to grayscale for analysis
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Brightness statistics
            mean_brightness = np.mean(gray)
            std_brightness = np.std(gray)
            
            # Edge density
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            
            # Contrast (using Laplacian variance)
            contrast = cv2.Laplacian(gray, cv2.CV_64F).var()
            
            return {
                'brightness': mean_brightness / 255.0,
                'brightness_std': std_brightness / 255.0,
                'edge_density': edge_density,
                'contrast': min(contrast / 1000.0, 1.0)  # Normalize
            }
            
        except Exception:
            return {
                'brightness': 0.0,
                'brightness_std': 0.0,
                'edge_density': 0.0,
                'contrast': 0.0
            }
    
    def _create_comprehensive_hash(self, frame_hashes: List[Dict], temporal_features: List[Dict], duration: float) -> str:
        """Create a comprehensive hash from all features"""
        try:
            # Aggregate perceptual hashes
            dhashes = [fh['dhash'] for fh in frame_hashes if fh and 'dhash' in fh]
            phashes = [fh['phash'] for fh in frame_hashes if fh and 'phash' in fh]
            ahashes = [fh['ahash'] for fh in frame_hashes if fh and 'ahash' in fh]
            whashes = [fh['whash'] for fh in frame_hashes if fh and 'whash' in fh]
            color_hashes = [fh['color_hash'] for fh in frame_hashes if fh and 'color_hash' in fh]
            edge_hashes = [fh['edge_hash'] for fh in frame_hashes if fh and 'edge_hash' in fh]
            
            # Create consensus hashes (most common bits)
            consensus_dhash = self._create_consensus_hash(dhashes)
            consensus_phash = self._create_consensus_hash(phashes)
            consensus_ahash = self._create_consensus_hash(ahashes)
            consensus_whash = self._create_consensus_hash(whashes)
            consensus_color = self._create_consensus_hash(color_hashes)
            consensus_edge = self._create_consensus_hash(edge_hashes)
            
            # Aggregate temporal features
            avg_brightness = np.mean([tf['brightness'] for tf in temporal_features])
            avg_contrast = np.mean([tf['contrast'] for tf in temporal_features])
            avg_edge_density = np.mean([tf['edge_density'] for tf in temporal_features])
            
            # Encode temporal features as short strings
            brightness_code = f"{int(avg_brightness * 15):X}"
            contrast_code = f"{int(avg_contrast * 15):X}"
            edge_code = f"{int(avg_edge_density * 15):X}"
            duration_code = f"{int(min(duration, 3600) / 60):02X}"  # Duration in minutes, max 60
            
            # Combine everything into a structured hash
            comprehensive_hash = (
                f"v2:"  # Version identifier
                f"{len(frame_hashes):02X}:"  # Number of frames sampled
                f"{duration_code}:"  # Duration
                f"{brightness_code}{contrast_code}{edge_code}:"  # Temporal features
                f"{consensus_dhash[:16]}:"  # Truncated consensus hashes
                f"{consensus_phash[:16]}:"
                f"{consensus_ahash[:16]}:"
                f"{consensus_whash[:16]}:"
                f"{consensus_color[:16]}:"
                f"{consensus_edge[:16]}"
            )
            
            return comprehensive_hash
            
        except Exception as e:
            print(f"Error creating comprehensive hash: {e}")
            return None
    
    def _create_consensus_hash(self, hashes: List[str]) -> str:
        """Create consensus hash from multiple hash strings"""
        if not hashes:
            return "0" * 16
        
        if len(hashes) == 1:
            return hashes[0]
        
        try:
            # Find the most common length
            lengths = [len(h) for h in hashes]
            common_length = max(set(lengths), key=lengths.count)
            
            # Filter to hashes of common length
            filtered_hashes = [h for h in hashes if len(h) == common_length]
            
            if not filtered_hashes:
                return hashes[0]
            
            # Create consensus by majority vote for each position
            consensus = []
            for i in range(common_length):
                chars = [h[i] for h in filtered_hashes if i < len(h)]
                if chars:
                    # Most common character at this position
                    most_common = max(set(chars), key=chars.count)
                    consensus.append(most_common)
                else:
                    consensus.append('0')
            
            return ''.join(consensus)
            
        except Exception:
            return hashes[0] if hashes else "0" * 16
    
    def compute_similarity(self, hash1: str, hash2: str) -> float:
        """
        Compute similarity between two comprehensive video hashes
        Returns: Similarity score 0.0-1.0 (higher = more similar)
        """
        if not hash1 or not hash2:
            return 0.0
        
        try:
            # Parse hash components
            parts1 = hash1.split(':')
            parts2 = hash2.split(':')
            
            if len(parts1) < 9 or len(parts2) < 9:
                # Fallback to old hash format
                return self._compare_legacy_hash(hash1, hash2)
            
            # Extract components
            version1, frame_count1, duration1, temporal1 = parts1[0], parts1[1], parts1[2], parts1[3]
            version2, frame_count2, duration2, temporal2 = parts2[0], parts2[1], parts2[2], parts2[3]
            
            dhash1, phash1, ahash1, whash1, color1, edge1 = parts1[4:10]
            dhash2, phash2, ahash2, whash2, color2, edge2 = parts2[4:10]
            
            # Duration similarity
            dur1 = int(duration1, 16) if duration1.isdigit() or all(c in '0123456789ABCDEF' for c in duration1) else 0
            dur2 = int(duration2, 16) if duration2.isdigit() or all(c in '0123456789ABCDEF' for c in duration2) else 0
            duration_similarity = 1.0 - min(abs(dur1 - dur2) / max(dur1, dur2, 1), 1.0)
            
            # Temporal features similarity
            temporal_similarity = self._compare_hex_strings(temporal1, temporal2)
            
            # Perceptual hash similarities
            dhash_sim = self._compare_hash_strings(dhash1, dhash2)
            phash_sim = self._compare_hash_strings(phash1, phash2)
            ahash_sim = self._compare_hash_strings(ahash1, ahash2)
            whash_sim = self._compare_hash_strings(whash1, whash2)
            color_sim = self._compare_hash_strings(color1, color2)
            edge_sim = self._compare_hash_strings(edge1, edge2)
              # Weighted combination (emphasize most effective hash types for video similarity)
            similarity = (
                phash_sim * 0.30 +      # Perceptual hash (most robust to scaling/compression)
                dhash_sim * 0.25 +      # Difference hash (good for similar content)
                whash_sim * 0.20 +      # Wavelet hash (frequency domain, good for compression)
                ahash_sim * 0.10 +      # Average hash (simple but effective baseline)
                color_sim * 0.08 +      # Color distribution (important for videos)
                edge_sim * 0.04 +       # Edge patterns (structural similarity)
                temporal_similarity * 0.02 +  # Temporal features (brightness, contrast)
                duration_similarity * 0.01    # Duration match (videos should be similar length)
            )
            
            # Apply non-linear scaling to enhance high similarity scores
            # This makes truly similar videos cluster more tightly together
            if similarity > 0.7:
                # Boost high similarity scores
                similarity = 0.7 + (similarity - 0.7) * 1.5
            elif similarity > 0.5:
                # Moderate boost for medium similarity
                similarity = 0.5 + (similarity - 0.5) * 1.2
            
            return max(0.0, min(1.0, similarity))
            
        except Exception as e:
            print(f"Error computing similarity: {e}")
            return 0.0
    
    def _compare_legacy_hash(self, hash1: str, hash2: str) -> float:
        """Compare old format hashes for backward compatibility"""
        try:
            parts1 = hash1.split(':', 2)
            parts2 = hash2.split(':', 2)
            
            if len(parts1) < 3 or len(parts2) < 3:
                return 0.0
              # Simple string comparison for legacy format
            return self._compare_hash_strings(parts1[2], parts2[2])
            
        except Exception:
            return 0.0
    
    def _compare_hash_strings(self, hash_str1: str, hash_str2: str) -> float:
        """Compare hash strings using enhanced Hamming distance with threshold"""
        if not hash_str1 or not hash_str2:
            return 0.0
            
        min_len = min(len(hash_str1), len(hash_str2))
        if min_len == 0:
            return 0.0
        
        # Use only the overlapping portion
        hash_str1 = hash_str1[:min_len]
        hash_str2 = hash_str2[:min_len]
        
        # Enhanced Hamming distance with position weighting
        # Give more weight to differences in the beginning of the hash
        weighted_differences = 0.0
        total_weight = 0.0
        
        for i, (c1, c2) in enumerate(zip(hash_str1, hash_str2)):
            # Position weight: earlier positions get slightly more weight
            weight = 1.0 + (0.3 * (1 - i / min_len))
            total_weight += weight
            
            if c1 != c2:
                # For hex characters, calculate distance based on numeric difference
                try:
                    if c1 in '0123456789ABCDEF' and c2 in '0123456789ABCDEF':
                        val1 = int(c1, 16)
                        val2 = int(c2, 16)
                        # Normalize difference (0-15 range becomes 0-1)
                        char_diff = abs(val1 - val2) / 15.0
                    else:
                        char_diff = 1.0  # Complete mismatch for non-hex chars
                except:
                    char_diff = 1.0
                
                weighted_differences += char_diff * weight
            
        similarity = 1.0 - (weighted_differences / total_weight)
        return max(0.0, similarity)
    
    def _compare_hex_strings(self, hex1: str, hex2: str) -> float:
        """Compare hex-encoded feature strings"""
        if not hex1 or not hex2:
            return 0.0
        
        try:
            # Convert to integers and compare
            val1 = int(hex1, 16) if all(c in '0123456789ABCDEF' for c in hex1) else 0
            val2 = int(hex2, 16) if all(c in '0123456789ABCDEF' for c in hex2) else 0
            
            max_val = max(val1, val2, 1)
            similarity = 1.0 - (abs(val1 - val2) / max_val)
            
            return max(0.0, similarity)
            
        except Exception:
            return self._compare_hash_strings(hex1, hex2)


# Legacy compatibility - maintain old VideoHasher class for existing code
class VideoHasher:
    """Legacy compatibility wrapper for PerceptualHasher"""
    
    def __init__(self):
        self.perceptual_hasher = PerceptualHasher()
    
    def compute_hash(self, video_path: str) -> Optional[str]:
        """Compute hash using new perceptual method"""
        return self.perceptual_hasher.compute_video_hash(video_path)
    
    def compare_hashes(self, hash1: str, hash2: str) -> float:
        """Compare hashes using new similarity method"""
        return self.perceptual_hasher.compute_similarity(hash1, hash2)