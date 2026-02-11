# Photo Album Organizer

A Python tool to organize large photo collections by automatically grouping similar photos (bursts, duplicates, similar shots) and selecting the best image from each group based on facial expression quality. Now with full [Immich](https://immich.app/) integration for self-hosted photo management!

## Features

- **Intelligent Grouping**: Uses perceptual hashing to find visually similar photos, even with timestamp errors
- **Flexible Temporal Grouping**: Configurable time window or pure visual similarity matching
- **Face Quality Detection**: Scores faces for smiles and open eyes using pluggable backends (face_recognition or MediaPipe)
- **Best Photo Selection**: Automatically selects the best photo from each group
- **Configurable Group Size**: Set minimum photos per group (default 3, min 2)
- **Immich Integration**: Full integration with Immich self-hosted photo management
  - Tag duplicates with structured tags (best/non-best/group/person)
  - Create organized albums automatically
  - Mark best photos as favorites
  - Archive non-best photos (hides without deleting)
  - Group by recognized person (Immich face detection)
  - Use Immich server-side duplicate detection
  - CLIP semantic search to pre-filter photos
  - Concurrent photo prefetching for faster processing
  - Bulk API operations for efficiency
  - Process photos without downloading (tag-only mode)
  - Smart caching for performance
- **Metadata Preservation**: Extracts and saves all EXIF and file metadata to text files
- **Original Preservation**: Keeps all original photos safely in organized folders
- **Multi-Format Support**: Handles JPEG, PNG, HEIC, and RAW formats (CR2, NEF, ARW, DNG)
- **Resume Capability**: Interrupt and resume processing without losing progress (perfect for large libraries)
- **Interactive Setup Menu**: Guided `-i` mode walks you through all options — no need to memorize CLI flags
- **Save/Load Settings**: Save your interactive configuration to JSON and reload it next time
- **NixOS Optimized**: First-class NixOS support with automatic environment setup

## Table of Contents

- [Installation](#installation)
  - [NixOS (Recommended)](#nixos-recommended)
  - [Other Linux/macOS](#other-linuxmacos)
  - [Windows](#windows)
- [Usage](#usage)
  - [Interactive Mode](#interactive-mode)
  - [Local Photos](#basic-usage)
  - [Immich Integration](#immich-integration)
- [Command Line Options](#command-line-options)
- [Output Structure](#output-structure)
- [Configuration Guide](#configuration-guide)
- [Face Detection Backends](#face-detection-backends)
- [Performance](#performance)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Immich Integration Guide](docs/IMMICH.md)
- [Cloud Integration Design](docs/CLOUD_INTEGRATION_DESIGN.md)

## Installation

### NixOS (Recommended)

NixOS users get automatic environment setup with all dependencies properly linked. See [docs/NIXOS_SETUP.md](docs/NIXOS_SETUP.md) for detailed instructions.

**Quick Start with direnv (automatic environment):**

```bash
# Clone the repository
git clone https://github.com/fkadriver/photoAlbumOrganizer.git
cd photoAlbumOrganizer

# Allow direnv (one-time setup)
direnv allow

# Install Python packages (first time only)
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models

# Verify installation
python scripts/verify_environment.py

# Ready to use! (direnv will prompt to run or drop to shell on cd)
python photo_organizer.py -i        # Interactive guided setup
python photo_organizer.py -s ~/Photos -o ~/Organized  # Direct CLI
```

**Without direnv:**

```bash
# Enter development environment
nix develop

# Install Python packages
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models

# Run the organizer
python photo_organizer.py -s ~/Photos -o ~/Organized
```

See [docs/DIRENV_SETUP.md](docs/DIRENV_SETUP.md) for automatic environment activation setup.

### Other Linux/macOS

**Prerequisites:**
- Python 3.11 or higher
- CMake (required for dlib)
- System libraries: OpenBLAS, LAPACK, OpenCV dependencies

**Ubuntu/Debian:**

```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install python3.11 python3.11-venv python3.11-dev
sudo apt-get install cmake build-essential
sudo apt-get install libopenblas-dev liblapack-dev
sudo apt-get install libgl1-mesa-glx libglib2.0-0

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models
```

**macOS:**

```bash
# Install Homebrew dependencies
brew install python@3.11 cmake openblas lapack

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models
```

### Windows

```powershell
# Install Python 3.11 from python.org
# Install Visual Studio Build Tools
# Install CMake from cmake.org

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install Python packages
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models
```

## Usage

### Interactive Mode

The easiest way to get started — a guided menu walks you through every option with sensible defaults:

```bash
python photo_organizer.py -i
```

The menu covers source type, paths, processing tuning, advanced features (HDR, face-swap), and run options. Press Enter to accept defaults or change only what you need.

**Saving and loading settings:**

At the summary screen, press `s` to save your configuration to `.photo_organizer_settings.json`. The next time you run with `-i`, the menu detects the file and offers to load it — skipping the full walkthrough and jumping straight to review. API keys are never saved to the file; they are re-prompted on load.

**direnv integration:**

If you use direnv, entering the project directory will prompt you to run with saved settings, launch interactive setup, or drop to a shell. Press Enter to drop to the shell (default).

### Basic Usage (Local Photos)

```bash
python photo_organizer.py -s /path/to/photos -o /path/to/output
```

### Immich Integration

The Photo Album Organizer now includes full integration with [Immich](https://immich.app/) self-hosted photo management!

**Quick Start with Immich:**

```bash
# Test connection
python scripts/test_immich_connection.py

# Tag duplicates in Immich (safest, recommended first step)
python photo_organizer.py \
  --source-type immich \
  --immich-url https://your-immich-url \
  --immich-api-key YOUR_KEY \
  --tag-only

# Or use the convenient wrapper script
./scripts/immich.sh tag-only
./scripts/immich.sh create-albums
./scripts/immich.sh help
```

**See the complete Immich guide:** [docs/IMMICH.md](docs/IMMICH.md)

**Quick setup script:** [scripts/immich.sh](scripts/immich.sh) - Convenient wrapper for all Immich operations

### Common Use Cases

**Organize burst photos with default settings:**
```bash
python photo_organizer.py -s ~/Photos/2024 -o ~/Organized/2024
```

**Group all visually similar photos regardless of timestamp:**
```bash
python photo_organizer.py -s ~/Photos -o ~/Organized --time-window 0
```

**Stricter similarity for near-duplicates only:**
```bash
python photo_organizer.py -s ~/Photos -o ~/Organized -t 3
```

**Looser grouping for similar compositions:**
```bash
python photo_organizer.py -s ~/Photos -o ~/Organized -t 8
```

**Custom time window (10 minutes instead of default 5):**
```bash
python photo_organizer.py -s ~/Photos -o ~/Organized --time-window 600
```

**Dry run to preview without changes:**
```bash
python photo_organizer.py -s ~/Photos -o ~/Organized --dry-run --verbose
```

## Command Line Options

```
Source Arguments:
  --source-type TYPE        Photo source type: local or immich (default: local)
  -s, --source SOURCE       Source directory containing photos (local source)
  -o, --output OUTPUT       Output directory for organized photos

Processing Arguments:
  -t, --threshold N         Similarity threshold (0-64, default=5)
                           Lower = stricter matching (0-3: only near-duplicates)
                           Higher = looser grouping (7-10: similar compositions)

  --time-window SECONDS    Time window in seconds for grouping (default=300)
                           Photos within this window are grouped together
                           Only applies when timestamps are available
                           Use 0 to disable and group purely by visual similarity

  --min-group-size N       Minimum photos per group (default: 3, min: 2)
  --threads N              Number of threads for parallel processing (default: 2)

Immich Arguments:
  --immich-url URL         Immich server URL (e.g., http://immich:2283)
  --immich-api-key KEY     Immich API key
  --immich-album ALBUM     Process a specific Immich album
  --immich-cache-dir DIR   Cache directory for Immich photos
  --immich-cache-size MB   Cache size in MB (default: 5000)
  --no-verify-ssl          Disable SSL certificate verification
  --use-full-resolution    Download full resolution (default: use thumbnails)

Immich Actions:
  --tag-only               Only tag photos as duplicates (Immich only)
  --create-albums          Create Immich albums for each group
  --album-prefix PREFIX    Prefix for created albums (default: Organized-)
  --mark-best-favorite     Mark best photo in each group as favorite (Immich only)
  --archive-non-best       Archive non-best photos (hides without deleting, Immich only)
  --immich-group-by-person Group photos by recognized person (Immich only)
  --immich-person NAME     Filter to specific person name (Immich only)
  --immich-use-server-faces Use Immich face data for best-photo selection
  --immich-use-duplicates  Use Immich server-side duplicate detection for grouping
  --immich-smart-search Q  Pre-filter photos using CLIP semantic search query

Resume Capability:
  --resume                 Resume from previous interrupted run
  --force-fresh            Force fresh start, delete any existing progress
  --state-file PATH        Custom path for state file (for resume)

Advanced Image Processing:
  --enable-hdr             Enable HDR merging for bracketed exposure shots
  --hdr-gamma VALUE        HDR tone mapping gamma value (default: 2.2)
  --face-backend BACKEND   Face detection backend: auto, face_recognition,
                           or mediapipe (default: auto)
  --enable-face-swap       Enable automatic face swapping to fix closed
                           eyes/bad expressions
  --swap-closed-eyes       Swap faces with closed eyes (default: True)

Interactive Mode:
  -i, --interactive        Launch interactive setup menu (guided walkthrough)
                           Settings can be saved/loaded from
                           .photo_organizer_settings.json
  -r, --run-settings FILE  Run directly from a saved settings JSON file
                           (default: .photo_organizer_settings.json)

Other Arguments:
  --verbose                Enable detailed output during processing
  --dry-run                Show what would be done without making changes
  --limit N                Limit processing to first N photos (for testing)
```

### Choosing the Right Options

**For burst photos from the same moment:**
```bash
python photo_organizer.py -s ~/Photos -o ~/Organized -t 5
# Default settings work well - groups visually similar photos taken within 5 minutes
```

**For photos with incorrect timestamps:**
```bash
python photo_organizer.py -s ~/Photos -o ~/Organized --time-window 0
# Ignores timestamps, groups purely by visual similarity
```

**For finding duplicates across your entire library:**
```bash
python photo_organizer.py -s ~/Photos -o ~/Organized -t 3 --time-window 0
# Very strict matching, no time restrictions
```
 
**For grouping similar compositions (different angles of same scene):**
```bash
python photo_organizer.py -s ~/Photos -o ~/Organized -t 8 --time-window 1800
# Looser matching, 30-minute window
```

## Output Structure

The organizer creates a structured output with preserved originals:

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
└── group_NNNN/
    └── ...
```

### Metadata File Contents

Each `metadata.txt` contains comprehensive information:

- **File Information**: Original filename, full path, file size
- **Timestamps**: Creation time, modification time
- **Image Properties**: Dimensions, format, color mode
- **EXIF Data**: Camera model, lens, settings (ISO, aperture, shutter speed)
- **Location Data**: GPS coordinates (if available)
- **Date/Time**: Original capture timestamp from EXIF

Example:
```
Photo Group - 3 images
================================================================================

Photo 1: IMG_2024_001.jpg
--------------------------------------------------------------------------------
filename: IMG_2024_001.jpg
filepath: /home/user/Photos/2024/IMG_2024_001.jpg
filesize: 4234567
dimensions: 4032x3024
format: JPEG
exif_Make: Canon
exif_Model: Canon EOS R5
exif_DateTimeOriginal: 2024:03:15 14:23:45
exif_FNumber: 2.8
exif_ExposureTime: 1/500
exif_ISOSpeedRatings: 400
```

## Configuration Guide

### Similarity Threshold Guide

The threshold parameter controls how similar photos must be to be grouped:

| Threshold | Use Case | Description |
|-----------|----------|-------------|
| **0-3** | Duplicates | Only near-identical photos (different exposures of same shot) |
| **4-6** | Burst photos | Recommended for typical burst sequences (default: 5) |
| **7-10** | Similar scenes | Groups photos of same subject from different angles |
| **11+** | Very loose | May group unrelated but visually similar photos |

### Time Window Guide

| Window | Use Case |
|--------|----------|
| **60s** | High-speed bursts, sports photography |
| **300s (default)** | Standard burst photography, family photos |
| **600s** | Event photography, multiple compositions of scenes |
| **--time-window 0** | Duplicate detection across entire library |

## Face Detection Backends

The organizer uses a pluggable face detection backend controlled by `--face-backend`:

| Backend | `--face-backend` | Detection | Landmarks (EAR) | Face Encoding | Install Complexity |
|---------|-------------------|-----------|-----------------|---------------|-------------------|
| **face_recognition** | `face_recognition` | dlib HOG/CNN | 68-point (dlib) | Yes (128-d) | High (requires dlib compilation) |
| **MediaPipe** | `mediapipe` | FaceLandmarker | 468-point (FaceMesh) | No | Low (`pip install mediapipe`) |
| **Auto** (default) | `auto` | Tries face_recognition first, then MediaPipe | — | — | — |

### Currently Supported

**face_recognition (dlib)** — The original backend. Provides face encoding for identity matching (needed for face-swap). Requires dlib compilation (or `dlib-binary`). Can be noisy (DGESVD warnings) but works reliably.

**MediaPipe** — Google's lightweight face detection. No compilation needed, just `pip install mediapipe`. Requires downloading a model file:

```bash
mkdir -p models
curl -sSL -o models/face_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
```

MediaPipe provides 468-point landmarks (mapped to 6-point eye contours for EAR calculation) but does not support face encoding, so the face-swap feature (`--enable-face-swap`) is unavailable with this backend.

**Immich Server-Side Faces** — When using `--immich-use-server-faces`, the organizer uses Immich's built-in face detection data (bounding boxes, person recognition) for best-photo selection. This avoids downloading photos for face analysis and scores by face area (larger faces = clearer shots). Combine with `--immich-group-by-person` to organize by person.

### Other Alternatives (Not Yet Implemented)

These backends could be added in the future via the `FaceBackend` abstraction:

| Library | Strengths | Limitations |
|---------|-----------|-------------|
| **InsightFace** | State-of-the-art accuracy, fast GPU inference, face encoding via ArcFace | Heavy install (~1GB models), ONNX Runtime dependency |
| **DeepFace** | Unified API for multiple models (VGGFace, ArcFace, Facenet), face encoding | Meta-library with large dependencies, slower |
| **YOLOv8-Face** | Best detection speed, good for large libraries | Detection only (no landmarks or encoding), Ultralytics dependency |
| **RetinaFace** | Excellent accuracy on small/occluded faces, 5-point landmarks | No encoding, moderate speed |
| **dlib (direct)** | Fewer dependencies than face_recognition, same underlying models | Same 2015-era model limitations |

## How It Works

1. **Discovery Phase**
   - Recursively scans source directory for supported image formats
   - Extracts metadata from each photo (EXIF data, file info, timestamps)

2. **Hashing Phase**
   - Computes perceptual hash (dHash) for each photo
   - Creates visual fingerprint resistant to minor edits/resizing

3. **Grouping Phase**
   - Compares perceptual hashes using Hamming distance
   - Groups photos below similarity threshold
   - Optionally filters by temporal proximity

4. **Analysis Phase**
   - Detects faces using pluggable backend (face_recognition or MediaPipe)
   - Scores faces for quality (open eyes, smiling)
   - Uses OpenCV for additional facial feature detection

5. **Selection Phase**
   - Ranks photos in each group by face quality scores
   - Selects best overall photo from group
   - Falls back to first photo if no faces detected

6. **Organization Phase**
   - Creates structured output directories
   - Copies originals to preserve source files
   - Saves comprehensive metadata
   - Copies best photo to group root

## Performance

### Processing Speeds

- **Small collections** (< 1,000 photos): 5-10 minutes
- **Medium collections** (1,000-10,000 photos): 30-60 minutes
- **Large collections** (10,000-50,000 photos): 2-4 hours
- **Very large collections** (128GB+): 4-8 hours

**Factors affecting speed:**
- CPU speed and core count
- Storage type (SSD vs HDD)
- Image resolution and format
- Number of faces in photos

### Memory Usage

- **Typical**: 2-4 GB RAM
- **Large libraries**: 4-8 GB RAM
- **Peak usage**: During hash computation and face detection

### Optimization Tips

1. **Use SSD** for both source and output directories
2. **Process in batches** by year or event for very large libraries
3. **Start with higher threshold** (e.g., -t 7) to create fewer, larger groups
4. **Test on subset first** to tune parameters before full run

**Example batch processing:**
```bash
# Process by year
for year in 2020 2021 2022 2023 2024; do
  python photo_organizer.py -s ~/Photos/$year -o ~/Organized/$year
done
```

## Supported Formats

| Format | Extensions | Notes |
|--------|-----------|-------|
| **JPEG** | .jpg, .jpeg | Most common, fully supported |
| **PNG** | .png | Lossless format, fully supported |
| **HEIC** | .heic | Apple Photos format, requires Pillow HEIC support |
| **RAW** | .cr2, .nef, .arw, .dng | Canon, Nikon, Sony, Adobe RAW formats |

**Note on RAW formats**: RAW files are processed for similarity detection and metadata extraction. The "best photo" output will be in the original RAW format.

## Troubleshooting

### Installation Issues

**dlib won't compile:**
```bash
# Ensure build tools are installed
# Ubuntu/Debian:
sudo apt-get install build-essential cmake python3.11-dev

# Try pre-built version instead:
pip install dlib-binary
```

**face_recognition import error:**
```bash
# Reinstall face_recognition_models
pip uninstall face_recognition_models -y
pip install git+https://github.com/ageitgey/face_recognition_models

# Verify:
python -c "import face_recognition; print('Success!')"
```

**OpenCV missing libraries (non-NixOS):**
```bash
# Ubuntu/Debian:
sudo apt-get install libgl1-mesa-glx libglib2.0-0

# macOS: usually works out of the box
# Windows: Install Visual C++ Redistributable
```

### Runtime Issues

**"Out of memory" errors:**
- Process smaller batches
- Close other applications
- Use a machine with more RAM
- Consider processing by year or folder

**Slow processing:**
- Move photos to SSD
- Increase similarity threshold to reduce groups
- Process fewer photos at once
- Check if antivirus is scanning files

**No faces detected:**
- Ensure photos contain clear, front-facing faces
- Check photo quality and lighting
- Face detection works best with faces > 50x50 pixels
- Profile/side faces may not be detected

**Wrong "best photo" selected:**
- Face detection prefers:
  - Open eyes (weighted heavily)
  - Smiles
  - Multiple faces all meeting criteria
- Manual review recommended for important photo groups

### NixOS Specific Issues

**Library linking errors:**
```bash
# Ensure LD_LIBRARY_PATH is set correctly
echo $LD_LIBRARY_PATH
# Should include paths to libGL, libstdc++, glib, etc.

# Reload environment
direnv reload
# or
exit && nix develop
```

**DGESVD warnings:**
These are harmless BLAS/LAPACK threading warnings. They're suppressed in the NixOS environment but don't affect functionality.

## Development

### Running Tests

```bash
# Verify environment
python scripts/verify_environment.py

# Test with limited photos (processes first 100 photos only)
python photo_organizer.py -s ~/Photos -o ~/Organized --limit 100

# Run with verbose output to debug
python photo_organizer.py -s test_photos -o output --verbose

# Dry run to test without changes
python photo_organizer.py -s test_photos -o output --dry-run

# Combine test mode with resume capability
python photo_organizer.py -s ~/Photos -o ~/Organized --limit 100 --resume
```

### Project Structure

```
photoAlbumOrganizer/
├── photo_organizer.py         # Main entry point (CLI argument parsing)
├── src/                       # Python source code
│   ├── interactive.py        # Interactive setup menu and settings save/load
│   ├── organizer.py          # Core PhotoOrganizer class
│   ├── grouping.py           # Perceptual hashing and similarity grouping
│   ├── image_processing.py   # Face detection, HDR, and face swapping
│   ├── face_backend.py       # Pluggable face detection backend abstraction
│   ├── photo_sources.py      # Photo source abstraction (local/Immich)
│   ├── immich_client.py      # Immich API client
│   ├── processing_state.py   # Resume capability state management
│   └── utils.py              # Logging setup and utilities
├── scripts/                   # Utility scripts
│   ├── immich.sh             # Immich wrapper script
│   ├── test_immich_connection.py  # Test Immich connectivity
│   └── verify_environment.py      # Environment verification
├── docs/                      # Documentation
│   ├── IMMICH.md             # Immich integration guide
│   ├── IMMICH_INTEGRATION.md # Immich integration details
│   ├── RESUME_CAPABILITY.md  # Resume feature guide
│   ├── CLOUD_INTEGRATION_DESIGN.md  # Apple/Google Photos design
│   ├── NIXOS_SETUP.md        # NixOS setup guide
│   ├── DIRENV_SETUP.md       # direnv configuration guide
│   ├── QUICKSTART.md         # Quick start guide
│   └── ...                   # Additional documentation
├── models/                    # Downloaded model files (not tracked in git)
│   └── face_landmarker.task  # MediaPipe face model (download separately)
├── requirements.txt          # Python dependencies
├── flake.nix                 # NixOS development environment
├── shell.nix                 # Alternative NixOS shell
├── .envrc                    # direnv configuration
├── README.md                 # This file
└── LICENSE                   # MIT License
```

### Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Recent Enhancements

- [x] **Enhanced Immich Actions** - Archive non-best, structured tags, CLIP search, server-side duplicates
  - `--archive-non-best` to hide non-best photos without deleting
  - Structured tags via Immich tag API (best/non-best/group/person)
  - `--immich-use-duplicates` to use Immich server-side duplicate detection
  - `--immich-smart-search` for CLIP semantic search pre-filtering
  - Concurrent photo prefetching for faster processing
  - Bulk API operations for efficiency

- [x] **Group by Person** - Organize photos by recognized person using Immich face detection
  - `--immich-group-by-person` to group by person
  - `--immich-person` to filter to specific person
  - `--immich-use-server-faces` for server-side face quality scoring

- [x] **Configurable Group Size** - `--min-group-size N` (default 3, min 2)

- [x] **JSON State Files** - Migrated from pickle to JSON for security and portability
  - Automatic migration from old `.pkl` files on resume

- [x] **Interactive Setup Menu** - Guided `-i` mode with save/load settings
  - Step-by-step walkthrough of all options with sensible defaults
  - Save configuration to `.photo_organizer_settings.json` for reuse
  - API keys excluded from saved files and re-prompted on load
  - direnv prompt on directory entry to run or launch setup

- [x] **Immich Integration** - Full integration with Immich self-hosted photo management
  - Tag duplicates directly in Immich
  - Create organized albums
  - Mark best photos as favorites
  - Smart caching for performance
  - See [docs/IMMICH.md](docs/IMMICH.md) for details

- [x] **Resume Capability** - Interrupt and resume long-running jobs without losing progress
  - Automatic state persistence every 50 photos
  - Graceful interruption with Ctrl+C
  - Hash caching for faster resume
  - Skip already-processed groups
  - See [docs/RESUME_CAPABILITY.md](docs/RESUME_CAPABILITY.md) for details

### Known Issues

- **face_recognition unmaintained** — The [face_recognition](https://github.com/ageitgey/face_recognition) library hasn't been updated since ~2020 and relies on a 2015-era dlib model. MediaPipe is now available as an alternative backend via `--face-backend mediapipe`. Note: MediaPipe does not support face encoding, so face-swap matching is unavailable with it.
- **OMP_NUM_THREADS=1 in flake.nix** — OpenBLAS/LAPACK threading is disabled to suppress warnings, which reduces numerical performance on multi-core systems. The runtime `SuppressStderr` utility may make this unnecessary.

### Future Enhancements

- [ ] Additional face backends (InsightFace, DeepFace, YOLOv8-Face)
- [ ] GPU acceleration for face detection
- [ ] Web interface for reviewing and managing groups
- [ ] Apple Photos integration (macOS only, via `osxphotos`) — see [design doc](docs/CLOUD_INTEGRATION_DESIGN.md)
- [ ] Google Photos integration (OAuth2, read-only) — see [design doc](docs/CLOUD_INTEGRATION_DESIGN.md)
- [ ] Video support for organizing video clips
- [ ] Shared album support in Immich
- [ ] Async/parallel downloads for Immich (using aiohttp)

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- **[ImageHash](https://github.com/JohannesBuchner/imagehash)** - Perceptual hashing library
- **[face_recognition](https://github.com/ageitgey/face_recognition)** - Face detection and recognition (dlib-based)
- **[MediaPipe](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker)** - Google's face landmarker (alternative backend)
- **[Pillow](https://python-pillow.org/)** - Python Imaging Library
- **[OpenCV](https://opencv.org/)** - Computer vision library
- **[dlib](http://dlib.net/)** - Machine learning toolkit

## Support

- **Issues**: [GitHub Issues](https://github.com/fkadriver/photoAlbumOrganizer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/fkadriver/photoAlbumOrganizer/discussions)
- **Documentation**: See markdown files in repository

## Author

Created for organizing 20 years of photo memories across multiple formats and folder structures. Built with a focus on NixOS integration and reproducible environments.

---

**Star this repo** if you find it useful! ⭐
