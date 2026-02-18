# Feature Roadmap

## Status Overview

| Feature | Status |
|---------|--------|
| Resume Capability | ✅ COMPLETED |
| Multi-threaded Processing | ✅ COMPLETED |
| Immich Integration (Phase 1 + 2) | ✅ COMPLETED |
| HDR / Exposure Blending | ✅ COMPLETED |
| Advanced Face Swapping (basic) | ✅ COMPLETED |
| Web Viewer | ✅ COMPLETED |
| Viewer Lifecycle (`scripts/viewer`) | ✅ COMPLETED |
| HEIC Support | ✅ COMPLETED |
| Timestamped Reports | ✅ COMPLETED |
| Additional Face Backends + ML Quality Scoring | ✅ COMPLETED |
| GPU Acceleration | ✅ COMPLETED |
| Web Viewer Group Combine/Split + Reprocess | ✅ COMPLETED |
| Async / Parallel Immich Downloads | ✅ COMPLETED |
| Immich Phase 3 (real-time sync) | ⏳ PLANNED |
| Video Support | ⏳ PLANNED |
| Apple / Google Photos | ⏳ PLANNED |

---

## ✅ Completed

### Resume Capability
Interrupt and resume long-running jobs without losing progress. State saved to `.photo_organizer_state.json` every 50 photos with hash caching.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized           # auto-detects prior run
./photo_organizer.py -s ~/Photos -o ~/Organized --resume  # skip prompt, always resume
./photo_organizer.py -s ~/Photos -o ~/Organized --force-fresh
```

### Multi-threaded Processing
Parallel hash computation via `--threads N`. Speeds up hashing 2–4× on multi-core systems.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --threads 4
```

### Immich Integration (Phase 1 + 2)
Full read and write integration. See [IMMICH.md](IMMICH.md).

- Tag/untag duplicates with structured Immich tags
- Create / delete albums
- Mark best photos as favorites, archive non-best
- Group by recognized person, CLIP semantic search
- Server-side duplicate detection, bulk API operations
- Full cleanup/undo menu

### HDR / Exposure Blending
Detects bracketed exposures from EXIF and merges using OpenCV Debevec HDR + Drago tone mapping.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --enable-hdr
```

### Advanced Face Swapping (basic)
Detects closed eyes via Eye Aspect Ratio, finds best replacement face using encoding distance, blends with `seamlessClone`.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --enable-face-swap
```

Limitations: requires `face_recognition` backend; no multi-face composite; no pose normalization.

### Web Viewer
Built-in stdlib HTTP server. Group grid with Immich thumbnail proxying, report switcher, EXIF comparison, lightbox, set-best, bulk actions, people view.

```bash
scripts/viewer start        # background, auto-stops on directory exit
scripts/viewer status
scripts/viewer stop
```

### HEIC Support
Apple HEIC format processed via `pillow-heif`.

### Timestamped Reports
Reports saved to `reports/report_YYYY-MM-DD_HHMMSS.json` with a `reports/latest.json` symlink. Web viewer dropdown lists all historical reports.

### Web Viewer Group Combine / Split / Reprocess

Three new actions in the web viewer:

- **Merge groups**: Enable bulk select, pick 2+ groups, click "Merge groups" — all photos combined into the lowest-numbered group.
- **Split group**: Open a group detail, check photos to extract, click "Split selected to new group" — a new group is created with those photos.
- **Reprocess best selection**: Select groups, click "Reprocess..." — choose a criterion to re-pick the best photo: largest file, largest dimensions, oldest date, or newest date.

All three modify the report JSON on disk. Immich favorites are updated automatically when a client is configured.

### Async / Parallel Immich Downloads

`ImmichClient.bulk_download_thumbnails()` downloads multiple thumbnails concurrently via a `ThreadPoolExecutor`. `ImmichPhotoSource.prefetch_photos()` now uses this method (default: 8 parallel workers, up from 4 sequential). Expected 4–8× speedup for download-heavy workflows on a typical connection.

```python
# Direct API
results = client.bulk_download_thumbnails(asset_ids, max_workers=8, size='preview')
# {asset_id: bytes_or_None}
```

### Additional Face Backends + ML Quality Scoring

Three new GPU-capable backends added alongside `face_recognition` and `MediaPipe`:

| Backend / Scorer | `--face-backend` | Key Advantage |
|-----------------|-----------------|---------------|
| InsightFace | `insightface` | Best accuracy, 512-d ArcFace, CUDA |
| FaceNet/PyTorch | `facenet` | Modern dlib replacement, CUDA/MPS, batch |
| YOLOv8-Face | `yolov8` | Fastest detection, GPU-capable |
| CLIP Quality Scorer | *(auto when `--gpu`)* | Aesthetic scoring: sharpness, composition, exposure |

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --face-backend facenet --gpu
./photo_organizer.py -s ~/Photos -o ~/Organized --face-backend insightface --gpu
./photo_organizer.py -s ~/Photos -o ~/Organized --face-backend yolov8 --gpu
```

Install GPU backends: `pip install -r requirements-gpu.txt`

See [FACE_BACKENDS.md](FACE_BACKENDS.md) for details.

### GPU Acceleration

10–50× faster face detection using PyTorch (CUDA/MPS) or ONNX Runtime (CUDA). Activated via `--gpu` flag with automatic device detection and CPU fallback.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu --face-backend facenet
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu --gpu-device 1
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu --no-ml-quality  # disable ML scorer
```

**Auto-detection order:** FacenetBackend (CUDA → MPS → CPU) → InsightFaceBackend (CUDA → CPU) → existing CPU backends.

See [GPU_ACCELERATION.md](GPU_ACCELERATION.md) for install instructions and benchmarks.

---

## ⏳ Planned

### Immich Phase 3: Stream Processing
- Real-time sync (process new photos as they arrive in Immich)
- Bi-directional sync
- Use Immich ML models directly

### Video Support
Extract key frames from video clips, compute perceptual hashes, group similar clips alongside photos.

### Apple / Google Photos Integration
- Apple Photos via `osxphotos` (macOS only)
- Google Photos via OAuth2 (read-only)

See [CLOUD_INTEGRATION_DESIGN.md](CLOUD_INTEGRATION_DESIGN.md) for design details.

## Implementation Notes

- All face backends implement `FaceBackend` from `src/face_backend.py`
- GPU support is opt-in via `--gpu`; CPU fallback is automatic
- Each feature is independently flag-gated — no breaking changes to existing workflows
- `--face-backend auto` always works; GPU-capable backends are preferred when `--gpu` is set
