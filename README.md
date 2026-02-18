# Photo Album Organizer

A Python tool to organize large photo collections by automatically grouping similar photos (bursts, duplicates, similar shots) and selecting the best image from each group based on facial expression quality. Full [Immich](https://immich.app/) integration for self-hosted photo management.

## Features

- **Intelligent Grouping**: Perceptual hashing finds visually similar photos even with timestamp errors
- **Flexible Temporal Grouping**: Configurable time window or pure visual similarity matching
- **Face Quality Detection**: Scores faces for smiles and open eyes — pluggable backends (face_recognition, MediaPipe, InsightFace, FaceNet — see [FACE_BACKENDS.md](docs/FACE_BACKENDS.md))
- **GPU Acceleration**: 10–50× faster face detection via PyTorch/ONNX — see [GPU_ACCELERATION.md](docs/GPU_ACCELERATION.md) *(in progress)*
- **Immich Integration**: Full integration with Immich — tag, album, favorite, archive, cleanup, people view
- **Web Viewer**: Built-in review interface with thumbnails, EXIF comparison, bulk actions, report switcher, and people view
- **Viewer Lifecycle**: `scripts/viewer` manages background start/stop with watchdog auto-stop on directory exit
- **Resume Capability**: Interrupt and resume processing without losing progress
- **Interactive Setup**: Guided `-i` mode with save/load settings
- **HEIC + RAW Support**: JPEG, PNG, HEIC, CR2, NEF, ARW, DNG
- **Multi-Format Reports**: Timestamped JSON reports with historical comparison dropdown
- **NixOS Optimized**: First-class NixOS support with automatic environment setup

## Table of Contents

- [Installation](#installation)
  - [NixOS (Recommended)](#nixos-recommended)
  - [Other Linux/macOS](#other-linuxmacos)
- [Usage](#usage)
  - [Interactive Mode](#interactive-mode)
  - [Local Photos](#local-photos)
  - [Immich Integration](#immich-integration)
  - [Web Viewer](#web-viewer)
  - [Immich Cleanup](#immich-cleanup)
  - [Common Use Cases](#common-use-cases)
- [Command Line Options](#command-line-options)
- [Output Structure](#output-structure)
- [Development](#development)
- [Documentation](#documentation)

---

## Installation

### NixOS (Recommended)

```bash
git clone https://github.com/fkadriver/photoAlbumOrganizer.git
cd photoAlbumOrganizer

# Allow direnv (one-time setup)
direnv allow

# Install Python packages (first time only)
pip install -r requirements.txt

# Verify installation
python scripts/verify_environment.py
```

direnv will prompt you on every `cd` into the project. See [docs/DIRENV_SETUP.md](docs/DIRENV_SETUP.md).

**Without direnv:**
```bash
nix develop
pip install -r requirements.txt
./photo_organizer.py -i
```

### Other Linux/macOS

**Ubuntu/Debian:**
```bash
sudo apt-get install python3.11 python3.11-venv cmake build-essential \
  libopenblas-dev liblapack-dev libgl1-mesa-glx libglib2.0-0
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models
```

**macOS:**
```bash
brew install python@3.11 cmake openblas lapack
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models
```

---

## Usage

### Interactive Mode

```bash
./photo_organizer.py -i
```

Guided menu walks through every option. After a run, the summary screen defaults to launching the web viewer. Press `s` to save settings for reuse.

**direnv integration:** entering the project directory shows:
```
[r] Run with saved settings
[i] Interactive setup
[v] Web viewer          ← starts in background, auto-stops on cd out
[s] Drop to shell       ← default (press Enter)
```

### Local Photos

```bash
./photo_organizer.py -s /path/to/photos -o /path/to/output
```

### Immich Integration

```bash
# Store credentials once
mkdir -p ~/.config/photo-organizer
echo 'IMMICH_API_KEY="your-key"' > ~/.config/photo-organizer/immich.conf
echo 'IMMICH_URL="https://your-immich-url"' >> ~/.config/photo-organizer/immich.conf
chmod 600 ~/.config/photo-organizer/immich.conf

# Tag duplicates (safest first step)
scripts/immich.sh tag-only

# Create albums and mark favorites
scripts/immich.sh create-albums

# All options
scripts/immich.sh help
```

See [docs/IMMICH.md](docs/IMMICH.md) for the full guide.

### Web Viewer

```bash
# Lifecycle-managed background viewer (recommended)
scripts/viewer start          # port 8080, loads Immich config automatically
scripts/viewer start 9090     # custom port
scripts/viewer status
scripts/viewer stop

# Or foreground via CLI
./photo_organizer.py --web-viewer \
  --immich-url https://your-immich-url \
  --immich-api-key YOUR_KEY
```

The viewer auto-stops when your shell leaves the project directory. Features: group grid, report switcher, EXIF comparison, full-resolution lightbox, set-best, bulk archive/delete/discard, people view.

### Immich Cleanup

Undo previous organizer changes:

```bash
./photo_organizer.py --cleanup \
  --immich-url https://your-immich-url \
  --immich-api-key YOUR_KEY

# Or via wrapper (delete all Organized- albums):
scripts/immich.sh cleanup "Organized-" no
```

### Common Use Cases

```bash
# Burst photos — default settings
./photo_organizer.py -s ~/Photos -o ~/Organized -t 5

# Ignore timestamps, group purely by visual similarity
./photo_organizer.py -s ~/Photos -o ~/Organized --time-window 0

# Strict duplicate detection
./photo_organizer.py -s ~/Photos -o ~/Organized -t 3 --time-window 0

# Similar compositions (30-minute window)
./photo_organizer.py -s ~/Photos -o ~/Organized -t 8 --time-window 1800

# Dry run — preview without making changes
./photo_organizer.py -s ~/Photos -o ~/Organized --dry-run --verbose
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for a full threshold and time-window guide.

---

## Command Line Options

```
Source Arguments:
  --source-type TYPE        local or immich (default: local)
  -s, --source SOURCE       Source directory (local)
  -o, --output OUTPUT       Output directory

Processing Arguments:
  -t, --threshold N         Similarity threshold 0–64 (default: 5, lower=stricter)
  --time-window SECONDS     Time window for grouping (default: 300, 0=disable)
  --min-group-size N        Minimum photos per group (default: 3, min: 2)
  --threads N               Parallel hash threads (default: 2)

Immich Arguments:
  --immich-url URL          Immich server URL
  --immich-api-key KEY      Immich API key
  --immich-album ALBUM      Process a specific album
  --immich-cache-size MB    Cache size in MB (default: 5000)
  --no-verify-ssl           Disable SSL certificate verification
  --use-full-resolution     Download full resolution (default: thumbnails)

Immich Actions:
  --tag-only                Tag photos as duplicates (Immich only)
  --create-albums           Create Immich albums for each group
  --album-prefix PREFIX     Prefix for created albums (default: Organized-)
  --mark-best-favorite      Mark best photo as favorite (Immich only)
  --archive-non-best        Archive non-best photos (Immich only)
  --immich-group-by-person  Group photos by recognized person
  --immich-person NAME      Filter to specific person
  --immich-use-server-faces Use Immich face data for best-photo selection
  --immich-use-duplicates   Use Immich server-side duplicate detection
  --immich-smart-search Q   Pre-filter with CLIP semantic search

Resume:
  --resume                  Resume from previous interrupted run
  --force-fresh             Force fresh start, delete existing progress

Advanced Image Processing:
  --enable-hdr              Enable HDR merging for bracketed exposures
  --hdr-gamma VALUE         HDR tone mapping gamma (default: 2.2)
  --face-backend BACKEND    face_recognition, mediapipe, insightface, facenet, yolov8, auto
  --enable-face-swap        Enable automatic face swapping

Interactive Mode:
  -i, --interactive         Launch interactive setup menu
  -r, --run-settings FILE   Run from saved settings (default: .photo_organizer_settings.json)

Web Viewer & Cleanup:
  --web-viewer              Launch web viewer (foreground)
  --live-viewer             Start web viewer in background during processing
  --report PATH             Path to report JSON (default: reports/latest.json)
  --port N                  Web viewer port (default: 8080)
  --cleanup                 Launch Immich cleanup menu

Other:
  --verbose                 Detailed output
  --dry-run                 Show what would be done without making changes
  --limit N                 Limit to first N photos (for testing)
```

---

## Output Structure

```
output_directory/
├── group_0001/
│   ├── originals/              # All original photos
│   │   ├── IMG_001.jpg
│   │   ├── IMG_002.jpg
│   │   └── IMG_003.jpg
│   ├── metadata.txt            # Complete EXIF and file metadata
│   └── best_IMG_001.jpg        # Best photo selected from group
├── group_0002/
│   └── ...
└── reports/
    ├── report_2026-01-15_143022.json
    ├── report_2026-01-20_091500.json
    └── latest.json              # Symlink to most recent report
```

---

## Development

### Running Tests

```bash
python scripts/verify_environment.py
./photo_organizer.py -s test_photos -o output --limit 100 --dry-run
./photo_organizer.py -s test_photos -o output --verbose
```

### Project Structure

```
photoAlbumOrganizer/
├── photo_organizer.py          # Main entry point
├── src/
│   ├── face_backend.py         # Pluggable face detection abstraction
│   ├── interactive.py          # Interactive menu and settings
│   ├── organizer.py            # Core PhotoOrganizer class
│   ├── grouping.py             # Perceptual hashing and grouping
│   ├── image_processing.py     # Face detection, HDR, face swapping
│   ├── photo_sources.py        # Local/Immich photo source abstraction
│   ├── immich_client.py        # Immich API client
│   ├── web_viewer.py           # Built-in web viewer
│   ├── cleanup.py              # Immich cleanup/undo operations
│   ├── processing_state.py     # Resume capability
│   └── utils.py                # Logging and utilities
├── scripts/
│   ├── viewer                  # Web viewer lifecycle (start/stop/status + watchdog)
│   ├── immich.sh               # Immich operations wrapper
│   ├── test_immich_connection.py
│   └── verify_environment.py
├── docs/
│   ├── IMMICH.md               # Immich integration guide
│   ├── CONFIGURATION.md        # Threshold, time window, settings guide
│   ├── FACE_BACKENDS.md        # Face detection backends + GPU-capable backends
│   ├── GPU_ACCELERATION.md     # GPU setup and design
│   ├── PERFORMANCE.md          # Performance tuning and supported formats
│   ├── TROUBLESHOOTING.md      # Common issues and fixes
│   ├── DIRENV_SETUP.md         # direnv configuration guide
│   ├── QUICKSTART.md           # Quick start guide
│   └── ENHANCEMENT_ROADMAP.md  # Feature roadmap and status
├── models/                     # Downloaded model files (not tracked in git)
├── requirements.txt
├── flake.nix                   # NixOS development environment
└── .envrc                      # direnv configuration
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Push and open a Pull Request

### Known Issues

- **face_recognition unmaintained** — The library hasn't been updated since ~2020 and uses a 2015-era dlib model. MediaPipe is available as an alternative (`--face-backend mediapipe`). InsightFace and FaceNet/PyTorch backends are in progress.
- **OMP_NUM_THREADS=1 in flake.nix** — OpenBLAS/LAPACK threading disabled to suppress warnings; doesn't affect correctness.

### Future Enhancements

- [x] GPU acceleration for face detection (design complete — see [GPU_ACCELERATION.md](docs/GPU_ACCELERATION.md))
- [x] Additional face backends: InsightFace, FaceNet/PyTorch, YOLOv8-Face (design complete — see [FACE_BACKENDS.md](docs/FACE_BACKENDS.md))
- [ ] Async/parallel Immich downloads (`aiohttp`)
- [ ] Apple Photos integration (macOS, `osxphotos`)
- [ ] Google Photos integration (OAuth2, read-only)
- [ ] Video support
- [ ] ML-based photo quality scoring (CLIP/MobileNetV2)

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/IMMICH.md](docs/IMMICH.md) | Full Immich integration guide |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | Quick start guide |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Threshold, time window, settings |
| [docs/FACE_BACKENDS.md](docs/FACE_BACKENDS.md) | Face detection backends |
| [docs/GPU_ACCELERATION.md](docs/GPU_ACCELERATION.md) | GPU acceleration design |
| [docs/PERFORMANCE.md](docs/PERFORMANCE.md) | Performance tuning, supported formats |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and fixes |
| [docs/DIRENV_SETUP.md](docs/DIRENV_SETUP.md) | direnv configuration |
| [docs/NIXOS_SETUP.md](docs/NIXOS_SETUP.md) | NixOS-specific setup |
| [docs/ENHANCEMENT_ROADMAP.md](docs/ENHANCEMENT_ROADMAP.md) | Feature roadmap |

---

## License

MIT License — see [LICENSE](LICENSE) file for details.

## Acknowledgments

- **[ImageHash](https://github.com/JohannesBuchner/imagehash)** — Perceptual hashing
- **[face_recognition](https://github.com/ageitgey/face_recognition)** — dlib-based face detection
- **[MediaPipe](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker)** — Google face landmarker
- **[Pillow](https://python-pillow.org/)** — Python Imaging Library
- **[OpenCV](https://opencv.org/)** — Computer vision library
- **[Immich](https://immich.app/)** — Self-hosted photo management

## Support

- **Issues**: [GitHub Issues](https://github.com/fkadriver/photoAlbumOrganizer/issues)
- **Documentation**: See `docs/` directory

---

*Created for organizing 20 years of photo memories. Built with a focus on NixOS integration and reproducible environments.*
