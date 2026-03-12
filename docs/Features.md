# Completed Features

All features listed here are fully implemented and available.

## Contents

- [Apple Photos Integration](#apple-photos-integration)
- [Immich Integration](#immich-integration)
- [Multi-threaded Processing](#multi-threaded-processing)
- [Video Support](#video-support)
- [HEIC Support](#heic-support)
- [GPU Acceleration](#gpu-acceleration)
- [HDR / Exposure Blending](#hdr--exposure-blending)
- [Advanced Face Swapping](#advanced-face-swapping)
- [Additional Face Backends + ML Quality Scoring](#additional-face-backends--ml-quality-scoring)
- [Resume Capability](#resume-capability)
- [Web Viewer](#web-viewer)
- [Timestamped Reports](#timestamped-reports)
- [Web Viewer Group Combine / Split / Reprocess](#web-viewer-group-combine--split--reprocess)

---

The Photo Album Organizer detects near-duplicate and similar photos in your library, groups them, selects the best shot from each group, and integrates with [Apple Photos](https://www.apple.com/macos/photos/) and [Immich](https://immich.app/) for rich metadata, face recognition, and library management. It supports local filesystem sources, Apple Photos libraries (macOS), remote Immich libraries, and a hybrid mode for on-server deployments. All features are flag-gated and backward compatible.

---

## Apple Photos Integration

Read-only access to your macOS Photos library via [osxphotos](https://github.com/RhetTbull/osxphotos):

- **People recognition** — uses Apple's built-in face detection to group photos by recognized person; shown in the web viewer people tab
- **Apple ML quality scores** — `score.overall` and `score.curation` fed into best-photo selection alongside MobileNetV2 scoring
- **Native duplicate detection** — `PhotoInfo.duplicates` exposes Apple's own duplicate groups, pre-computed by Photos.app
- **Burst shot metadata** — `is_burst`, `burst_key` stored per photo for downstream burst-aware grouping
- **iCloud-aware** — by default only processes locally-available photos (`--apple-local-only`); `--apple-include-icloud` triggers on-demand iCloud download
- **Album filter** — `--apple-album ALBUM` restricts to a specific Photos album
- **Group by person** — `--apple-group-by-person [--apple-person NAME]` processes one person at a time using Apple's face data
- **Interactive mode** — `./photo_organizer.py -i` shows the `apple` source option on macOS; walks through library path, album, person filter, and local-only settings
- **Web viewer people tab** — thumbnail for each named person served from their key photo; clicking shows all their locally-available photos
- **Batch iCloud processing** — `scripts/process_icloud_batches.py` downloads your full iCloud library in date-range batches then runs the organizer on each batch

```bash
pip install osxphotos pillow-heif

# Auto-detect library, skip iCloud-only photos
./photo_organizer.py --source-type apple -o ~/Organized

# Group by recognized person
./photo_organizer.py --source-type apple --apple-group-by-person -o ~/Organized

# Process a specific album
./photo_organizer.py --source-type apple --apple-album "Summer 2024" -o ~/Organized/Summer
```

See [Apple-Photos.md](Apple-Photos.md) for the full guide.

---

## Immich Integration

Full read/write integration with [Immich](https://immich.app/):

- **Tag duplicates** in Immich without downloading (tag-only mode)
- **Create albums** grouping similar photos together
- **Mark best photo** as favorite; archive non-best
- **Hybrid mode** — direct filesystem access on the same server as Immich (no HTTP download overhead)
- **Group by person / people** — use Immich's recognized faces to group photos by who appears in them
- **Parallel downloads** — 8 concurrent thumbnail workers for 4–8× faster processing
- **Real-time sync** — daemon mode (`--daemon`) polls for new photos; bi-directional sync detects Immich UI changes
- **Cleanup menu** — undo all tags, albums, and favorites created by the organizer

See [Immich.md](Immich.md) for full configuration and usage details.

---

## Multi-threaded Processing

Parallel hash computation via `--threads N`. Speeds up hashing 2–4× on multi-core systems.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --threads 4
```

---

## Video Support

Dedicated video processing mode that groups similar videos together using key frame analysis. Videos are processed separately from images using `--media-type video`.

```bash
./photo_organizer.py -s ~/Videos -o ~/OrganizedVideos --media-type video
```

**Supported formats:** `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`, `.m4v`, `.wmv`, `.flv`, `.mpg`, `.mpeg`, `.3gp`, `.mts`

**Key frame extraction strategies (`--video-strategy`):**
| Strategy | Description | Best For |
|----------|-------------|----------|
| `scene_change` | Detect visual scene changes (default) | Most videos, varied content |
| `fixed_interval` | Extract frame every N seconds | Long videos, consistent content |
| `iframe` | Extract I-frames only (fastest) | Quick processing, codec keyframes |

**Options:**
- `--video-max-frames N`: Maximum key frames to extract per video (default: 10)

---

## HEIC Support

Apple HEIC format processed via `pillow-heif`.

---

## GPU Acceleration

10–50× faster face detection using PyTorch (CUDA/MPS) or ONNX Runtime (CUDA). Activated via `--gpu` with automatic device detection and CPU fallback. Auto-detection order: FacenetBackend (CUDA → MPS → CPU) → InsightFaceBackend (CUDA → CPU) → existing CPU backends.

See [Gpu-Acceleration.md](Gpu-Acceleration.md) for install instructions and benchmarks.

---

## HDR / Exposure Blending

Detects bracketed exposures from EXIF and merges using OpenCV Debevec HDR + Drago tone mapping.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --enable-hdr
```

---

## Advanced Face Swapping

Detects closed eyes via Eye Aspect Ratio, finds best replacement face using encoding distance, blends with `seamlessClone`.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --enable-face-swap
```

Limitations: requires `face_recognition` backend; no multi-face composite; no pose normalization.

---

## Additional Face Backends + ML Quality Scoring

Three GPU-capable backends (InsightFace, FaceNet/PyTorch, YOLOv8-Face) plus a CLIP-based aesthetic quality scorer are available alongside the default `face_recognition` and `MediaPipe` backends. Install GPU backends with `pip install -r requirements-gpu.txt`.

See [Face-Backends.md](Face-Backends.md) for full details, install instructions, and benchmarks.

---

## Resume Capability

Interrupt and resume long-running jobs without losing progress. State saved to `.photo_organizer_state.json` every 50 photos with hash caching.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized           # auto-detects prior run
./photo_organizer.py -s ~/Photos -o ~/Organized --resume  # skip prompt, always resume
./photo_organizer.py -s ~/Photos -o ~/Organized --force-fresh
```

---

## Web Viewer

Built-in stdlib HTTP server. Group grid with Immich thumbnail proxying, report switcher, EXIF comparison, lightbox, set-best, bulk actions, people view.

```bash
scripts/viewer start        # background, auto-stops on directory exit
scripts/viewer status
scripts/viewer stop
```

---

## Timestamped Reports

Reports saved to `reports/report_YYYY-MM-DD_HHMMSS.json` with a `reports/latest.json` symlink. Web viewer dropdown lists all historical reports.

---

## Web Viewer Group Combine / Split / Reprocess

Three actions in the web viewer:

- **Merge groups**: Enable bulk select, pick 2+ groups, click "Merge groups" — all photos combined into the lowest-numbered group.
- **Split group**: Open a group detail, check photos to extract, click "Split selected to new group" — a new group is created with those photos.
- **Reprocess best selection**: Select groups, click "Reprocess..." — choose a criterion to re-pick the best photo: largest file, largest dimensions, oldest date, or newest date.

All three modify the report JSON on disk. Immich favorites are updated automatically when a client is configured.
