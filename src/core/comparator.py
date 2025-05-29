# src/core/comparator.py
from collections import defaultdict
from typing import List, Tuple, Dict
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import multiprocessing as mp

class EfficientComparator:
    """O(n) duplicate detection using hash bucketing"""
    
    def __init__(self, similarity_threshold: float = 0.8, num_workers: int = None):
        self.similarity_threshold = similarity_threshold
        self.num_workers = num_workers or mp.cpu_count()
        
    def find_duplicates(self, file_hashes: Dict[str, str]) -> List[Tuple[str, str, float]]:
        """
        Find duplicate videos efficiently using hash bucketing
        Args:
            file_hashes: Dict mapping file paths to their hashes
        Returns:
            List of (file1, file2, similarity) tuples
        """
        if len(file_hashes) < 2:
            return []
        
        # Step 1: Group by hash buckets - O(n)
        hash_buckets = self._create_hash_buckets(file_hashes)
        
        # Step 2: Compare within buckets - O(k²) where k << n
        duplicates = []
        
        for bucket_files in hash_buckets.values():
            if len(bucket_files) > 1:
                bucket_duplicates = self._compare_bucket(bucket_files, file_hashes)
                duplicates.extend(bucket_duplicates)
        
        return duplicates
    
    def _create_hash_buckets(self, file_hashes: Dict[str, str]) -> Dict[str, List[str]]:
        """Group files by hash bucket for efficient comparison"""
        buckets = defaultdict(list)
        
        for file_path, file_hash in file_hashes.items():
            if not file_hash:
                continue
            
            # Use first part of hash as bucket key
            bucket_key = self._get_bucket_key(file_hash)
            buckets[bucket_key].append(file_path)
        
        return buckets
    
    def _get_bucket_key(self, file_hash: str) -> str:
        """Extract bucket key from hash for grouping similar hashes"""
        try:
            # Use the MD5 part of the hash (more stable)
            parts = file_hash.split(':', 2)
            if len(parts) >= 2:
                # Use first 8 characters of MD5 for bucketing
                return parts[1][:8]
            else:
                return file_hash[:8]
        except:
            return "unknown"
    
    def _compare_bucket(self, bucket_files: List[str], 
                       file_hashes: Dict[str, str]) -> List[Tuple[str, str, float]]:
        """Compare all files within a bucket"""
        duplicates = []
        
        for i in range(len(bucket_files)):
            for j in range(i + 1, len(bucket_files)):
                file1, file2 = bucket_files[i], bucket_files[j]
                hash1, hash2 = file_hashes[file1], file_hashes[file2]
                
                from .hasher import PerceptualHasher
                hasher = PerceptualHasher()
                similarity = hasher.compute_similarity(hash1, hash2)
                
                if similarity >= self.similarity_threshold:
                    duplicates.append((file1, file2, similarity))
        
        return duplicates
    
    def find_duplicates_parallel(self, file_hashes: Dict[str, str]) -> List[Tuple[str, str, float]]:
        """Parallel version for large datasets"""
        hash_buckets = self._create_hash_buckets(file_hashes)
        
        # Process buckets in parallel
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = []
            
            for bucket_files in hash_buckets.values():
                if len(bucket_files) > 1:
                    future = executor.submit(self._compare_bucket, bucket_files, file_hashes)
                    futures.append(future)
            
            # Collect results
            duplicates = []
            for future in futures:
                try:
                    bucket_duplicates = future.result()
                    duplicates.extend(bucket_duplicates)
                except Exception as e:
                    print(f"Error in parallel comparison: {e}")
        
        return duplicates