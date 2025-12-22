# Photo Album Organizer

A Python tool to organize large photo collections by automatically grouping similar photos (bursts, duplicates, similar shots) and creating composite images with the best facial expressions.

## Features

- **Intelligent Grouping**: Uses perceptual hashing to find visually similar photos, even with timestamp errors
- **Temporal Awareness**: Groups photos taken within a configurable time window
- **Face Quality Detection**: Scores faces for smiles and open eyes
- **Best Photo Selection**: Automatically selects the best photo from each group
- **Metadata Preservation**: Extracts and saves all EXIF and file metadata
- **Original Preservation**: Keeps all original photos in organized folders
- **Multi-Format Support**: Handles JPEG, PNG, HEIC, and RAW formats (CR2, NEF, ARW, DNG)

## Installation

### Prerequisites

- Python 3.8 or higher
- CMake (required for dlib installation)

### Install CMake

**macOS:**
```bash
brew install cmake
```

**Ubuntu/Debian:**
```bash
sudo apt-get install cmake
```

**Windows:**
Download from [cmake.org](https://cmake.org/download/)

### Install Python Dependencies

```bash
pip install -r requirements.txt
```

**Note**: `face_recognition` installation may take several minutes as it compiles dlib.

## Usage

### Basic Usage

```bash
python photo_organizer.py -s /path/to/photos -o /path/to/output
```

### Command Line Options

```
-s, --source SOURCE       Source directory containing photos (required)
-o, --output OUTPUT       Output directory for organized photos (required)
-t, --threshold THRESHOLD Similarity threshold (0-64, default=5)
                         Lower values = stricter matching
                         Higher values = more loose grouping
--time-window SECONDS    Time window for grouping photos (default=300)
                         Photos within this window are grouped together
--verbose                Enable verbose output
--dry-run               Show what would be done without organizing
```

### Examples

**Basic organization:**
```bash
python photo_organizer.py -s ~/Photos -o ~/OrganizedPhotos
```

**Stricter similarity matching:**
```bash
python photo_organizer.py -s ~/Photos -o ~/Organized -t 3
```

**Looser grouping with longer time window:**
```bash
python photo_organizer.py -s ~/Photos -o ~/Organized -t 8 --time-window 600
```

**Test run without making changes:**
```bash
python photo_organizer.py -s ~/Photos -o ~/Organized --dry-run --verbose
```

## Output Structure

The organizer creates the following structure:

```
output_directory/
├── group_0001/
│   ├── originals/              # All original photos in this group
│   │   ├── IMG_001.jpg
│   │   ├── IMG_002.jpg
│   │   └── IMG_003.jpg
│   ├── metadata.txt            # Complete metadata for all photos
│   └── best_IMG_001.jpg        # Best photo selected from group
├── group_0002/
│   ├── originals/
│   ├── metadata.txt
│   └── best_IMG_045.jpg
└── ...
```

### Metadata File Format

Each `metadata.txt` contains:
- Filename and full path
- File size and timestamps
- Image dimensions and format
- All EXIF data (camera model, settings, GPS, date/time, etc.)

## How It Works

1. **Discovery**: Recursively scans source directory for supported image formats
2. **Hashing**: Computes perceptual hashes (dHash) for each photo
3. **Grouping**: Groups photos with similar hashes and timestamps
4. **Face Detection**: Analyzes faces in each photo for quality (smiles, open eyes)
5. **Selection**: Chooses the best photo from each group
6. **Organization**: Creates structured output with originals preserved

## Similarity Threshold Guide

The threshold parameter controls how similar photos must be to be grouped together:

- **0-3**: Very strict (only nearly identical photos)
- **4-6**: Recommended for burst photos (default: 5)
- **7-10**: Looser grouping (similar compositions)
- **11+**: Very loose (may group unrelated photos)

## Performance

- **Processing Speed**: ~100-200 photos per minute (varies by size and CPU)
- **Memory Usage**: ~2-4GB for typical collections
- **128GB Photo Library**: Estimated 4-8 hours total processing time

**Recommendation**: Test on a small subset first (e.g., one year's photos) to tune parameters.

## Supported Formats

- **JPEG**: .jpg, .jpeg
- **PNG**: .png
- **HEIC**: .heic (Apple Photos)
- **RAW**: .cr2 (Canon), .nef (Nikon), .arw (Sony), .dng (Adobe)

## Troubleshooting

### Installation Issues

**dlib won't install:**
- Ensure CMake is installed and in PATH
- On Windows, install Visual Studio Build Tools
- Try: `pip install --no-cache-dir dlib`

**face_recognition fails:**
- Install dlib first separately
- On macOS with M1/M2: May need to install via conda

### Runtime Issues

**Out of memory:**
- Process in smaller batches
- Reduce image size during processing (future enhancement)

**Slow processing:**
- Use SSD instead of HDD for source and output
- Reduce similarity threshold to create fewer, smaller groups
- Consider multi-threading (future enhancement)

**No faces detected:**
- Check that photos contain clear, front-facing faces
- Adjust lighting and resolution requirements

## Future Enhancements

- [ ] Advanced face swapping with alignment and blending
- [ ] Multi-threaded processing for better performance
- [ ] GPU acceleration for face detection
- [ ] Progressive web interface for reviewing groups
- [ ] HDR/exposure blending for merged photos
- [ ] Batch processing with resume capability
- [ ] Cloud storage integration (Google Photos, iCloud)

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details

## Acknowledgments

- Uses [ImageHash](https://github.com/JohannesBuchner/imagehash) for perceptual hashing
- Uses [face_recognition](https://github.com/ageitgey/face_recognition) for face detection
- Built with [Pillow](https://python-pillow.org/) and [OpenCV](https://opencv.org/)

## Author

Created for organizing 20 years of photo memories across multiple formats and folder structures.
