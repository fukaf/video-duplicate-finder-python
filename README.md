# Video Duplicate Finder - Python

A fast and efficient video duplicate detection tool designed to handle large collections (10k+ files). Uses advanced hashing algorithms and perceptual analysis to find duplicate videos even when they differ in resolution, length, or encoding.

## Features

- 🚀 **Fast scanning** - Efficiently processes thousands of video files
- 🎯 **Smart detection** - Finds duplicates even with different resolutions/lengths
- 🗄️ **Database caching** - Stores hash data for quick re-scans
- 🖼️ **Thumbnail preview** - Visual comparison of duplicate videos
- ⚙️ **Configurable similarity** - Adjustable threshold for detection sensitivity
- 📊 **Progress tracking** - Real-time scan progress and status
- 🎨 **User-friendly GUI** - Clean tkinter interface

## Screenshots

*GUI showing duplicate detection results with thumbnail previews*

## Installation

### Prerequisites

- Python 3.7 or higher
- FFmpeg (for video processing)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/fukaf/video-duplicate-finder-python.git
   cd video-duplicate-finder-python
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install FFmpeg**
   - **Windows**: Download from [FFmpeg website](https://ffmpeg.org/download.html)
   - **Linux**: `sudo apt install ffmpeg`
   - **Mac**: `brew install ffmpeg`

## Usage

### GUI Application

```bash
python src/main.py
```

1. **Select directory** - Choose folder containing videos to scan
2. **Configure settings** - Adjust similarity threshold (0.0-1.0)
3. **Start scan** - Click "Start Scan" to begin detection
4. **Review results** - View duplicate groups with thumbnails
5. **Delete duplicates** - Select files to remove

### Command Line (Future)

```bash
python src/cli.py --directory /path/to/videos --threshold 0.8
```

## How It Works

### 1. Video Analysis
- Extracts frames at regular intervals
- Generates perceptual hashes using dHash algorithm
- Calculates additional metadata (duration, resolution, file size)

### 2. Similarity Detection
- Compares hash values using Hamming distance
- Groups similar videos into duplicate clusters
- Configurable similarity threshold for precision control

### 3. Efficient Storage
- SQLite database for persistent hash storage
- Avoids re-processing previously scanned files
- Fast lookup and comparison operations

### 4. Smart Grouping
- Clusters duplicates into groups (not just pairs)
- Handles chains of similar videos
- Identifies best quality version in each group

## Supported Formats

- **Video**: MP4, AVI, MKV, MOV, WMV, FLV, WebM
- **Codecs**: H.264, H.265, VP9, AV1, and more
- **Containers**: Most common video containers

## Configuration

### Similarity Threshold
- **0.9-1.0**: Very strict (near-identical files only)
- **0.8-0.9**: Strict (recommended for most users)
- **0.7-0.8**: Moderate (may include similar but different videos)
- **0.6-0.7**: Loose (higher chance of false positives)

### Performance Settings
- **Cache enabled**: Faster subsequent scans
- **Thread count**: Adjust based on CPU cores
- **Memory usage**: Configure for available RAM

## Project Structure

```
video-duplicate-finder-python/
├── src/
│   ├── core/
│   │   ├── hasher.py          # Video hashing algorithms
│   │   ├── scanner.py         # Main scanning logic
│   │   └── database.py        # SQLite database operations
│   ├── gui/
│   │   └── main_window.py     # Tkinter GUI interface
│   ├── utils/
│   │   └── video_utils.py     # Video processing utilities
│   └── main.py                # Application entry point
├── requirements.txt           # Python dependencies
├── README.md                  # This file
└── .gitignore                # Git ignore patterns
```

## Requirements

See `requirements.txt` for full dependency list:

- **opencv-python**: Video frame extraction
- **pillow**: Image processing and thumbnails
- **numpy**: Numerical operations for hashing
- **python-magic**: File type detection
- **tkinter**: GUI framework (usually included with Python)

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

### Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/

# Code formatting
black src/
flake8 src/
```

## Performance

### Benchmarks
- **1,000 videos**: ~2-5 minutes (first scan)
- **10,000 videos**: ~15-30 minutes (first scan)
- **Subsequent scans**: 80-90% faster with caching

### Optimization Tips
- Enable caching for faster re-scans
- Use SSD storage for database and cache
- Adjust thread count based on CPU cores
- Close other applications during large scans

## Troubleshooting

### Common Issues

**FFmpeg not found**
```bash
# Add FFmpeg to system PATH or install via package manager
```

**Memory errors with large collections**
```bash
# Reduce batch size or increase virtual memory
```

**Slow scanning performance**
```bash
# Enable caching and adjust thread count in settings
```

### Debug Mode

```bash
# Run with debug logging
python src/main.py --debug
```

## Roadmap

- [ ] **CLI interface** for batch processing
- [ ] **Advanced filters** (by duration, resolution, codec)
- [ ] **Duplicate actions** (move, copy, hardlink)
- [ ] **Preview** showing thumbnails of duplicated videos
- [ ] **Metadata comparison** (creation date, EXIF)
- [ ] **Machine learning** enhanced detection

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- OpenCV community for video processing tools
- FFmpeg project for multimedia framework
- Python imaging libraries and contributors

## Support

- 🐛 **Bug reports**: [GitHub Issues](https://github.com/fukaf/video-duplicate-finder-python/issues)
- 💡 **Feature requests**: [GitHub Discussions](https://github.com/fukaf/video-duplicate-finder-python/discussions)

---

**⭐ Star this repository if you find it helpful!**