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
| Additional Face Backends + ML Quality Scoring | 🔧 IN PROGRESS |
| GPU Acceleration | 🔧 IN PROGRESS |
| Async Immich Downloads | ⏳ PLANNED |
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

---

## 🔧 In Progress

### Additional Face Backends + ML Quality Scoring
**Design complete — implementation next.**

Three new pluggable backends to add alongside `face_recognition` and `MediaPipe`, plus ML-based photo quality scoring as a fourth scorer:

| Backend / Scorer | `--face-backend` | Key Advantage |
|-----------------|-----------------|---------------|
| InsightFace | `insightface` | Best accuracy, 512-d ArcFace, CUDA |
| FaceNet/PyTorch | `facenet` | Modern dlib replacement, CUDA/MPS, batch |
| YOLOv8-Face | `yolov8` | Fastest detection, GPU-capable |
| CLIP Quality Scorer | *(auto, no flag)* | Aesthetic scoring: sharpness, composition, exposure |

The CLIP/MobileNetV2 quality scorer runs alongside whichever face backend is active, adding an aesthetic quality signal to best-photo selection beyond face quality alone. It uses the same GPU device as the face backend when `--gpu` is set.

**Implementation plan:**
1. Create `src/backends/` directory with `__init__.py`
2. Add `insightface_backend.py`, `facenet_backend.py`, `yolov8_backend.py`
3. Add `ml_quality_scorer.py` (CLIP or MobileNetV2, optional, auto-used when available)
4. Register in `get_face_backend()`, update `--face-backend` choices
5. Ship `requirements-gpu.txt` for optional GPU dependencies

See [FACE_BACKENDS.md](FACE_BACKENDS.md) for full design and interface pseudocode.

### GPU Acceleration
**Design complete — implementation next.**

10–50× faster face detection using PyTorch (CUDA/MPS) or ONNX Runtime (CUDA). Activated via `--gpu` flag with automatic device detection and CPU fallback.

```bash
# Planned usage:
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu --face-backend facenet
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu --gpu-device 1
```

**Auto-detection order:** FacenetBackend (CUDA → MPS → CPU) → InsightFaceBackend (CUDA → CPU) → existing CPU backends.

See [GPU_ACCELERATION.md](GPU_ACCELERATION.md) for full design, file structure, and install instructions.

---

## ⏳ Planned

### Async / Parallel Immich Downloads
Replace synchronous `requests` in `immich_client.py` with `aiohttp` for concurrent fetching. Expected 3–5× speedup for download-heavy workflows.

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
