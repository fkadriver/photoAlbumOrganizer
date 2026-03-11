# Completed Features

All features listed here are fully implemented and available.

## Contents

- [Resume Capability](#resume-capability)
- [Multi-threaded Processing](#multi-threaded-processing)
- [Immich Integration](#immich-integration)
- [HDR / Exposure Blending](#hdr--exposure-blending)
- [Advanced Face Swapping](#advanced-face-swapping)
- [Web Viewer](#web-viewer)
- [HEIC Support](#heic-support)
- [Timestamped Reports](#timestamped-reports)
- [Web Viewer Group Combine / Split / Reprocess](#web-viewer-group-combine--split--reprocess)
- [Additional Face Backends + ML Quality Scoring](#additional-face-backends--ml-quality-scoring)
- [GPU Acceleration](#gpu-acceleration)
- [Video Support](#video-support)

---

The Photo Album Organizer detects near-duplicate and similar photos in your library, groups them, selects the best shot from each group, and integrates with [Immich](https://immich.app/) for tagging, album creation, and real-time sync. It supports local filesystem sources, remote Immich libraries, and a hybrid mode for on-server deployments. All features are flag-gated and backward compatible.

---

## Resume Capability

Interrupt and resume long-running jobs without losing progress. State saved to `.photo_organizer_state.json` every 50 photos with hash caching.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized           # auto-detects prior run
./photo_organizer.py -s ~/Photos -o ~/Organized --resume  # skip prompt, always resume
./photo_organizer.py -s ~/Photos -o ~/Organized --force-fresh
```

---

## Multi-threaded Processing

Parallel hash computation via `--threads N`. Speeds up hashing 2–4× on multi-core systems.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --threads 4
```

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

## Web Viewer

Built-in stdlib HTTP server. Group grid with Immich thumbnail proxying, report switcher, EXIF comparison, lightbox, set-best, bulk actions, people view.

```bash
scripts/viewer start        # background, auto-stops on directory exit
scripts/viewer status
scripts/viewer stop
```

---

## HEIC Support

Apple HEIC format processed via `pillow-heif`.

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

---

## Additional Face Backends + ML Quality Scoring

Three GPU-capable backends (InsightFace, FaceNet/PyTorch, YOLOv8-Face) plus a CLIP-based aesthetic quality scorer are available alongside the default `face_recognition` and `MediaPipe` backends. Install GPU backends with `pip install -r requirements-gpu.txt`.

See [Face-Backends.md](Face-Backends.md) for full details, install instructions, and benchmarks.

---

## GPU Acceleration

10–50× faster face detection using PyTorch (CUDA/MPS) or ONNX Runtime (CUDA). Activated via `--gpu` with automatic device detection and CPU fallback. Auto-detection order: FacenetBackend (CUDA → MPS → CPU) → InsightFaceBackend (CUDA → CPU) → existing CPU backends.

See [Gpu-Acceleration.md](Gpu-Acceleration.md) for install instructions and benchmarks.

---

## Video Support

Dedicated video processing mode that groups similar videos together using key frame analysis. Videos are processed separately from images using `--media-type video`.

```bash
# Process only videos from local source
./photo_organizer.py -s ~/Videos -o ~/OrganizedVideos --media-type video

# Process videos from Immich
./photo_organizer.py --source-type immich \
  --immich-url http://localhost:2283 \
  --immich-api-key YOUR_KEY \
  --media-type video \
  --tag-only

# Hybrid mode with videos
./photo_organizer.py --source-type hybrid \
  --immich-library-path /mnt/photos/immich-app/library \
  --immich-url http://localhost:2283 \
  --immich-api-key YOUR_KEY \
  --media-type video \
  --create-albums

# Custom key frame extraction
./photo_organizer.py -s ~/Videos -o ~/Organized \
  --media-type video \
  --video-strategy fixed_interval \
  --video-max-frames 15
```

**How it works:**
1. Extract key frames from videos using OpenCV (scene change detection, fixed interval, or I-frame extraction)
2. Compute perceptual hashes on extracted key frames
3. Compare videos using multi-frame hash distance (weighted average of best frame matches + duration similarity)
4. Group similar videos together (videos are only compared to other videos, never mixed with images)

**Supported formats:** `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`, `.m4v`, `.wmv`, `.flv`, `.mpg`, `.mpeg`, `.3gp`, `.mts`

**Key frame extraction strategies (`--video-strategy`):**
| Strategy | Description | Best For |
|----------|-------------|----------|
| `scene_change` | Detect visual scene changes (default) | Most videos, varied content |
| `fixed_interval` | Extract frame every N seconds | Long videos, consistent content |
| `iframe` | Extract I-frames only (fastest) | Quick processing, codec keyframes |

**Options:**
- `--video-max-frames N`: Maximum key frames to extract per video (default: 10)

