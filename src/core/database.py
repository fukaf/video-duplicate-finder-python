# src/core/database.py
import sqlite3
import json
import os
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime
import hashlib

class VideoDatabase:
    """SQLite database for efficient video metadata and hash storage"""
    
    def __init__(self, db_path: str = "video_duplicates.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize database with required tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Files table for storing video metadata and hashes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    file_hash TEXT,
                    file_size INTEGER,
                    file_modified TEXT,
                    file_created TEXT,
                    thumbnail_path TEXT,
                    scan_date TEXT,
                    metadata TEXT,
                    UNIQUE(file_path)
                )
            ''')
            
            # Create index for fast hash lookups
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_file_hash ON files(file_hash)
            ''')
            
            # Create index for fast path lookups
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_file_path ON files(file_path)
            ''')
            
            # Duplicate groups table for storing duplicate relationships
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS duplicate_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_hash TEXT NOT NULL,
                    file1_path TEXT NOT NULL,
                    file2_path TEXT NOT NULL,
                    similarity_score REAL NOT NULL,
                    scan_date TEXT,
                    FOREIGN KEY (file1_path) REFERENCES files(file_path),
                    FOREIGN KEY (file2_path) REFERENCES files(file_path)
                )
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_group_hash ON duplicate_groups(group_hash)
            ''')
            
            conn.commit()
    
    def store_file_hash(self, file_path: str, file_hash: str, file_info: Dict):
        """Store file hash and metadata"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO files 
                    (file_path, file_hash, file_size, file_modified, file_created, scan_date, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    file_path,
                    file_hash,
                    file_info.get('size', 0),
                    file_info.get('modified', ''),
                    file_info.get('created', ''),
                    datetime.now().isoformat(),
                    json.dumps(file_info)
                ))
                
                conn.commit()
                
        except Exception as e:
            print(f"Error storing file hash for {file_path}: {e}")
    
    def get_file_hash(self, file_path: str) -> Optional[str]:
        """Get cached hash for a file if it exists and is still valid"""
        try:
            # Check if file still exists and hasn't been modified
            if not os.path.exists(file_path):
                self._remove_file(file_path)
                return None
            
            file_stat = os.stat(file_path)
            current_modified = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            current_size = file_stat.st_size
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT file_hash, file_modified, file_size 
                    FROM files 
                    WHERE file_path = ?
                ''', (file_path,))
                
                result = cursor.fetchone()
                if result:
                    stored_hash, stored_modified, stored_size = result
                    
                    # Check if file hasn't been modified
                    if (stored_modified == current_modified and 
                        stored_size == current_size):
                        return stored_hash
                    else:
                        # File was modified, remove old entry
                        self._remove_file(file_path)
                        
                return None
                
        except Exception as e:
            print(f"Error getting file hash for {file_path}: {e}")
            return None
    
    def store_file_thumbnail(self, file_path: str, thumbnail_path: str):
        """Store thumbnail path for a file"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE files 
                    SET thumbnail_path = ?
                    WHERE file_path = ?
                ''', (thumbnail_path, file_path))
                
                conn.commit()
                
        except Exception as e:
            print(f"Error storing thumbnail for {file_path}: {e}")
    
    def get_file_thumbnail(self, file_path: str) -> Optional[str]:
        """Get thumbnail path for a file"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT thumbnail_path 
                    FROM files 
                    WHERE file_path = ?
                ''', (file_path,))
                
                result = cursor.fetchone()
                if result and result[0]:
                    thumbnail_path = result[0]
                    # Check if thumbnail still exists
                    if os.path.exists(thumbnail_path):
                        return thumbnail_path
                    else:
                        # Thumbnail missing, clear the reference
                        self.store_file_thumbnail(file_path, "")
                        
                return None
                
        except Exception as e:
            print(f"Error getting thumbnail for {file_path}: {e}")
            return None
    
    def store_duplicate_group(self, duplicates: List[Tuple[str, str, float]]):
        """Store a group of duplicates"""
        try:
            if not duplicates:
                return
            
            # Create a group hash from all files in the group
            file_paths = set()
            for file1, file2, _ in duplicates:
                file_paths.add(file1)
                file_paths.add(file2)
            
            group_hash = hashlib.md5(
                "|".join(sorted(file_paths)).encode()
            ).hexdigest()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Clear existing duplicates for this group
                cursor.execute('''
                    DELETE FROM duplicate_groups 
                    WHERE group_hash = ?
                ''', (group_hash,))
                
                # Insert new duplicates
                scan_date = datetime.now().isoformat()
                for file1, file2, similarity in duplicates:
                    cursor.execute('''
                        INSERT INTO duplicate_groups 
                        (group_hash, file1_path, file2_path, similarity_score, scan_date)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (group_hash, file1, file2, similarity, scan_date))
                
                conn.commit()
                
        except Exception as e:
            print(f"Error storing duplicate group: {e}")
    
    def get_all_files(self) -> List[Dict]:
        """Get all files from database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT file_path, file_hash, file_size, file_modified, 
                           thumbnail_path, scan_date, metadata
                    FROM files
                    ORDER BY file_path
                ''')
                
                results = []
                for row in cursor.fetchall():
                    metadata = {}
                    try:
                        metadata = json.loads(row[6]) if row[6] else {}
                    except:
                        pass
                        
                    results.append({
                        'file_path': row[0],
                        'file_hash': row[1],
                        'file_size': row[2],
                        'file_modified': row[3],
                        'thumbnail_path': row[4],
                        'scan_date': row[5],
                        'metadata': metadata
                    })
                
                return results
                
        except Exception as e:
            print(f"Error getting all files: {e}")
            return []
    
    def get_files_count(self) -> int:
        """Get total number of files in database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM files')
                result = cursor.fetchone()
                return result[0] if result else 0
        except:
            return 0
    
    def get_duplicates_count(self) -> int:
        """Get total number of duplicate pairs"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM duplicate_groups')
                result = cursor.fetchone()
                return result[0] if result else 0
        except:
            return 0
    
    def clear_all(self):
        """Clear all data from database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM duplicate_groups')
                cursor.execute('DELETE FROM files')
                conn.commit()
        except Exception as e:
            print(f"Error clearing database: {e}")
    
    def _remove_file(self, file_path: str):
        """Remove file from database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM files WHERE file_path = ?', (file_path,))
                cursor.execute('DELETE FROM duplicate_groups WHERE file1_path = ? OR file2_path = ?', 
                             (file_path, file_path))
                conn.commit()
        except Exception as e:
            print(f"Error removing file {file_path}: {e}")
    
    def cleanup_missing_files(self):
        """Remove entries for files that no longer exist"""
        try:
            files = self.get_all_files()
            removed_count = 0
            
            for file_info in files:
                file_path = file_info['file_path']
                if not os.path.exists(file_path):
                    self._remove_file(file_path)
                    removed_count += 1
            
            print(f"Cleaned up {removed_count} missing files from database")
            
        except Exception as e:
            print(f"Error during cleanup: {e}")
