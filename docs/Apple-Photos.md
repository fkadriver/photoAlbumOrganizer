# Apple Photos Integration

Read directly from your macOS Photos library using [osxphotos](https://github.com/RhetTbull/osxphotos) — no export step needed. The organizer reads photo files, metadata, face recognition data, ML quality scores, and native duplicate detection directly from your Photos library database.

> **macOS only.** Requires Python on macOS and the `osxphotos` package.

---

## Installation

```bash
pip install osxphotos pillow-heif
```

`pillow-heif` adds HEIC/HEIF read support for Apple's native photo format.

---

## Basic Usage

```bash
# Auto-detect your Photos library, process locally-available photos
./photo_organizer.py --source-type apple -o ~/Organized

# Interactive guided setup (macOS shows "apple" as a source option)
./photo_organizer.py -i

# Specify a library path explicitly
./photo_organizer.py --source-type apple \
  --apple-library ~/Pictures/Photos\ Library.photoslibrary \
  -o ~/Organized

# Live web viewer during processing
./photo_organizer.py --source-type apple -o ~/Organized --live-viewer
```

---

## iCloud Photos

By default (`--apple-local-only`), the organizer skips photos that are stored in iCloud but not yet downloaded to your Mac. This avoids slow or failed iCloud downloads during processing.

```bash
# Default: skip iCloud-only photos (fast, no downloads)
./photo_organizer.py --source-type apple -o ~/Organized

# Include iCloud photos — triggers on-demand download via Photos.app
./photo_organizer.py --source-type apple --apple-include-icloud -o ~/Organized
```

### Batch Processing Your Full iCloud Library

For large iCloud libraries, use the batch script to process photos in time-window batches. Photos are read directly from the Apple Photos library — iCloud downloads happen on-demand, so no separate export directory is needed.

```bash
# Preview the batch plan (no processing)
python scripts/process_icloud_batches.py --dry-run

# Process in 6-month windows (default) with 7-day overlap at boundaries
python scripts/process_icloud_batches.py

# Smaller windows for very large libraries
python scripts/process_icloud_batches.py --months 3

# Resume a specific batch after interruption
python scripts/process_icloud_batches.py --only-batch 2

# Custom output directory
python scripts/process_icloud_batches.py --output-dir ~/icloud-organized
```

The batch script splits your library into calendar-month time windows with configurable overlap at boundaries (so burst shots straddling a date boundary stay together). Results land in `~/icloud-organized/batch_01/`, `batch_02/`, etc.

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--months N` | 6 | Months per batch window |
| `--overlap-days N` | 7 | Overlap days between adjacent batches |
| `--output-dir DIR` | `~/icloud-organized` | Root directory for organized output |
| `--only-batch N` | — | Process only batch N (1-indexed) |
| `--cpu-limit N` | 90 | CPU usage limit % |
| `--threads N` | 4 | Organizer threads |
| `--dry-run` | — | Print plan without processing |

---

## Album Filter

```bash
# Process only photos in a specific album
./photo_organizer.py --source-type apple \
  --apple-album "Summer 2024" \
  -o ~/Organized/Summer
```

---

## People / Face Recognition

Apple Photos performs face detection and lets you name recognized people. The organizer exposes this data in two ways:

### 1. Group by Person

Process photos organized by who appears in them:

```bash
# Group all recognized people
./photo_organizer.py --source-type apple \
  --apple-group-by-person \
  -o ~/Organized

# Filter to a single person
./photo_organizer.py --source-type apple \
  --apple-group-by-person \
  --apple-person "Connor Jensen" \
  -o ~/Organized/Connor
```

### 2. People Tab in the Web Viewer

When you run the web viewer (`--web-viewer` or `--live-viewer`), the **People** tab shows all named people from your Photos library:

- Thumbnail from each person's key photo
- Photo count
- Click a person to see their locally-available photos

```bash
# Start the web viewer after a run
./photo_organizer.py --web-viewer --source-type apple

# Or live during processing
./photo_organizer.py --source-type apple -o ~/Organized --live-viewer
```

---

## Apple ML Quality Scores

Apple Photos runs its own ML model on every photo and produces quality scores. The organizer reads these and stores them in photo metadata:

| Field | Description |
|-------|-------------|
| `apple_score` | Overall aesthetic quality (0–1) |
| `apple_curation` | Curation likelihood — Apple's "would this make the highlights reel?" score (0–1) |

These complement the organizer's own MobileNetV2 ML quality scoring for best-photo selection.

---

## Native Duplicate Detection

Apple Photos flags photos it considers duplicates. The organizer exposes this via the `duplicate_group` metadata field — all photos in the same Apple-detected duplicate group share the same canonical UUID. This lets you see Apple's duplicate decisions alongside the organizer's own perceptual-hash grouping.

---

## Burst Shot Metadata

Each photo includes:

| Field | Description |
|-------|-------------|
| `is_burst` | `True` if this photo is part of a burst sequence |
| `burst_key` | `True` if this is the key photo Apple selected from the burst |

---

## Command Line Reference

```
Apple Photos Arguments (--source-type apple, macOS only):
  --apple-library PATH      Path to Photos library (auto-detected if omitted)
                            Default: ~/Pictures/Photos Library.photoslibrary
  --apple-album ALBUM       Filter to a specific album name
  --apple-group-by-person   Group photos by recognized person (Apple face data)
  --apple-person NAME       Filter to one person (requires --apple-group-by-person)
  --apple-local-only        Skip iCloud-only photos not yet on this Mac (default)
  --apple-include-icloud    Include iCloud-only photos (triggers on-demand download)
  --apple-start-date DATE   Only include photos on or after DATE (YYYY-MM-DD)
  --apple-end-date DATE     Only include photos on or before DATE (YYYY-MM-DD)
```

---

## Interactive Mode

Run `./photo_organizer.py -i` on macOS to get the guided setup. At **Step 1: Source Type** you will see:

```
  Where are your photos?
    [1] local  — Photos on your local filesystem
    [2] apple  — Apple Photos library (macOS — reads via osxphotos)
    [3] immich — Immich photo management server (downloads via HTTP)
    [4] hybrid — Immich on same machine (direct filesystem + API)
  Choice [local]:
```

Selecting `apple` walks you through:
- Photos library path (leave blank to auto-detect)
- Output directory
- Album filter
- Group by person (and optional person name filter)
- Local-only vs. iCloud-include
- Date range filter (start date / end date, optional)

Settings are saved to `.photo_organizer_settings.json` so you can rerun with `./photo_organizer.py -r`.

---

## Limitations

- **Read-only**: the organizer cannot write back to your Photos library (no tagging, no albums, no favorites via this source). All output goes to the `--output` directory.
- **macOS only**: `osxphotos` reads the Photos SQLite database directly; this is not available on Linux or Windows.
- **dlib / face_recognition**: The `dlib` package does not build on macOS Sequoia (Apple removed the Carbon `fp.h` header). Use `--face-backend mediapipe` (default) or a GPU backend instead.
- **iCloud throttling**: On-demand iCloud download (`--apple-include-icloud`) is limited by your internet speed and Photos.app's download rate. The batch script is recommended for full-library processing.

---

## Troubleshooting

**"Only N photos found" — I have thousands**

Most of your library is probably iCloud-only. Check:
```python
python3 -c "
import osxphotos
db = osxphotos.PhotosDB()
photos = db.photos()
local = sum(1 for p in photos if p.path)
print(f'Total: {len(photos)}, Local: {local}, iCloud-only: {len(photos)-local}')
"
```
Use the batch download script to bring photos local before running the organizer.

**"Could not export photo"**

This occurs when `--apple-include-icloud` is set but a photo can't be downloaded (network issue, iCloud error). The photo is skipped and processing continues.

**osxphotos not found**

```bash
pip install osxphotos
```

**HEIC photos not loading**

```bash
pip install pillow-heif
```
