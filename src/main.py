# src/main.py
"""
Video Duplicate Finder - Main Entry Point
Fast and efficient video duplicate detection for large collections
"""

import sys
import os
from pathlib import Path

# Add src to path for relative imports
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))

def main():
    """Main entry point for the application"""
    try:
        from gui.main_window import MainWindow
        
        print("Starting Video Duplicate Finder...")
        app = MainWindow()
        app.run()
        
    except ImportError as e:
        print(f"Import error: {e}")
        print("Please ensure all dependencies are installed:")
        print("pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"Error starting application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
