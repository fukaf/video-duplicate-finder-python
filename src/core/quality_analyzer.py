# src/core/quality_analyzer.py
import os
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import cv2

class VideoQualityAnalyzer:
    """Analyzes and compares video quality for duplicate selection"""
    
    def __init__(self):
        self.quality_weights = {
            'resolution': 0.4,      # Higher resolution is better
            'bitrate': 0.3,         # Higher bitrate usually means better quality
            'file_size': 0.2,       # Larger file often means better quality
            'duration': 0.1         # Longer duration might be more complete
        }
    
    def compare_video_quality(self, file1_path: str, file2_path: str, 
                            file1_metadata: Dict = None, file2_metadata: Dict = None) -> Dict:
        """
        Compare quality between two videos
        Returns: Dictionary with comparison results and recommendation
        """
        # Get metadata if not provided
        if file1_metadata is None:
            file1_metadata = self.get_video_metadata(file1_path)
        if file2_metadata is None:
            file2_metadata = self.get_video_metadata(file2_path)
        
        # Calculate quality scores
        file1_score = self._calculate_quality_score(file1_metadata)
        file2_score = self._calculate_quality_score(file2_metadata)
        
        # Determine which is better
        better_file = file1_path if file1_score > file2_score else file2_path
        worse_file = file2_path if file1_score > file2_score else file1_path
        
        # Create detailed comparison
        comparison = {
            'file1': {
                'path': file1_path,
                'metadata': file1_metadata,
                'quality_score': file1_score,
                'filename': Path(file1_path).name
            },
            'file2': {
                'path': file2_path,
                'metadata': file2_metadata,
                'quality_score': file2_score,
                'filename': Path(file2_path).name
            },
            'recommendation': {
                'keep': better_file,
                'delete': worse_file,
                'confidence': abs(file1_score - file2_score),
                'reasons': self._get_quality_reasons(file1_metadata, file2_metadata)
            }
        }
        
        return comparison
    
    def get_video_metadata(self, file_path: str) -> Dict:
        """Extract comprehensive video metadata"""
        try:
            if not os.path.exists(file_path):
                return {}
            
            # Basic file info
            stat = os.stat(file_path)
            metadata = {
                'file_size': stat.st_size,
                'file_size_mb': round(stat.st_size / (1024 * 1024), 2),
                'modified': stat.st_mtime,
                'filename': Path(file_path).name
            }
            
            # Video properties using OpenCV
            cap = cv2.VideoCapture(file_path)
            if cap.isOpened():
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = frame_count / fps if fps > 0 else 0
                
                # Calculate additional metrics
                pixel_count = width * height
                bitrate = (stat.st_size * 8) / duration if duration > 0 else 0
                aspect_ratio = width / height if height > 0 else 0
                
                metadata.update({
                    'width': width,
                    'height': height,
                    'fps': fps,
                    'frame_count': frame_count,
                    'duration': round(duration, 2),
                    'duration_formatted': self._format_duration(duration),
                    'bitrate': bitrate,
                    'bitrate_kbps': round(bitrate / 1000, 2),
                    'resolution': f"{width}x{height}",
                    'pixel_count': pixel_count,
                    'aspect_ratio': round(aspect_ratio, 2),
                    'megapixels': round(pixel_count / 1000000, 2)
                })
                
                cap.release()
            
            return metadata
            
        except Exception as e:
            print(f"Error getting metadata for {file_path}: {e}")
            return {'error': str(e)}
    
    def _calculate_quality_score(self, metadata: Dict) -> float:
        """Calculate a quality score based on video properties"""
        if not metadata or 'error' in metadata:
            return 0.0
        
        score = 0.0
        
        # Resolution score (normalized by common resolutions)
        pixel_count = metadata.get('pixel_count', 0)
        resolution_scores = {
            1920 * 1080: 1.0,   # 1080p
            1280 * 720: 0.8,    # 720p
            854 * 480: 0.6,     # 480p
            640 * 360: 0.4,     # 360p
        }
        
        resolution_score = 0.0
        for res, res_score in resolution_scores.items():
            if pixel_count >= res:
                resolution_score = res_score
                break
        
        # Normalize very high resolutions
        if pixel_count > 1920 * 1080:
            resolution_score = min(1.0 + (pixel_count - 1920*1080) / (4096*2160 - 1920*1080) * 0.2, 1.2)
        
        score += resolution_score * self.quality_weights['resolution']
        
        # Bitrate score (normalized)
        bitrate_kbps = metadata.get('bitrate_kbps', 0)
        bitrate_score = min(bitrate_kbps / 5000, 1.0)  # Normalize to 5Mbps max
        score += bitrate_score * self.quality_weights['bitrate']
        
        # File size score (relative to duration)
        file_size_mb = metadata.get('file_size_mb', 0)
        duration = metadata.get('duration', 1)
        size_per_minute = file_size_mb / (duration / 60) if duration > 0 else 0
        size_score = min(size_per_minute / 50, 1.0)  # Normalize to 50MB per minute
        score += size_score * self.quality_weights['file_size']
        
        # Duration score (longer is generally better for duplicates)
        duration_score = min(duration / 7200, 1.0)  # Normalize to 2 hours max
        score += duration_score * self.quality_weights['duration']
        
        return round(score, 3)
    
    def _get_quality_reasons(self, metadata1: Dict, metadata2: Dict) -> List[str]:
        """Get human-readable reasons for quality comparison"""
        reasons = []
        
        # Compare resolution
        res1 = metadata1.get('pixel_count', 0)
        res2 = metadata2.get('pixel_count', 0)
        if res1 != res2:
            if res1 > res2:
                reasons.append(f"File 1 has higher resolution ({metadata1.get('resolution', 'unknown')} vs {metadata2.get('resolution', 'unknown')})")
            else:
                reasons.append(f"File 2 has higher resolution ({metadata2.get('resolution', 'unknown')} vs {metadata1.get('resolution', 'unknown')})")
        
        # Compare bitrate
        br1 = metadata1.get('bitrate_kbps', 0)
        br2 = metadata2.get('bitrate_kbps', 0)
        if abs(br1 - br2) > 500:  # Significant difference
            if br1 > br2:
                reasons.append(f"File 1 has higher bitrate ({br1:.0f} kbps vs {br2:.0f} kbps)")
            else:
                reasons.append(f"File 2 has higher bitrate ({br2:.0f} kbps vs {br1:.0f} kbps)")
        
        # Compare file size
        size1 = metadata1.get('file_size_mb', 0)
        size2 = metadata2.get('file_size_mb', 0)
        if abs(size1 - size2) > 50:  # Significant difference
            if size1 > size2:
                reasons.append(f"File 1 is larger ({size1:.1f} MB vs {size2:.1f} MB)")
            else:
                reasons.append(f"File 2 is larger ({size2:.1f} MB vs {size1:.1f} MB)")
        
        # Compare duration
        dur1 = metadata1.get('duration', 0)
        dur2 = metadata2.get('duration', 0)
        if abs(dur1 - dur2) > 30:  # 30 second difference
            if dur1 > dur2:
                reasons.append(f"File 1 is longer ({self._format_duration(dur1)} vs {self._format_duration(dur2)})")
            else:
                reasons.append(f"File 2 is longer ({self._format_duration(dur2)} vs {self._format_duration(dur1)})")
        
        if not reasons:
            reasons.append("Files have very similar quality metrics")
        
        return reasons
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
    
    def analyze_duplicate_group(self, file_paths: List[str]) -> Dict:
        """Analyze a group of duplicate videos and rank by quality"""
        if len(file_paths) < 2:
            return {'files': [], 'recommendation': None}
        
        # Get metadata for all files
        file_data = []
        for file_path in file_paths:
            metadata = self.get_video_metadata(file_path)
            quality_score = self._calculate_quality_score(metadata)
            
            file_data.append({
                'path': file_path,
                'filename': Path(file_path).name,
                'metadata': metadata,
                'quality_score': quality_score
            })
        
        # Sort by quality score (highest first)
        file_data.sort(key=lambda x: x['quality_score'], reverse=True)
        
        # Create recommendation
        best_file = file_data[0]
        files_to_delete = file_data[1:]
        
        return {
            'files': file_data,
            'recommendation': {
                'keep': best_file['path'],
                'delete': [f['path'] for f in files_to_delete],
                'best_file': best_file,
                'space_saved_mb': sum(f['metadata'].get('file_size_mb', 0) for f in files_to_delete),
                'quality_differences': self._get_group_quality_differences(file_data)
            }
        }
    
    def _get_group_quality_differences(self, file_data: List[Dict]) -> List[str]:
        """Get quality differences for a group of files"""
        if len(file_data) < 2:
            return []
        
        best = file_data[0]
        differences = []
        
        for i, file_info in enumerate(file_data[1:], 1):
            reasons = self._get_quality_reasons(best['metadata'], file_info['metadata'])
            differences.append(f"File {i+1} vs Best: {'; '.join(reasons)}")
        
        return differences
