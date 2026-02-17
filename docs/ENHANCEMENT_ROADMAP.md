# Enhancement Roadmap

Planned and completed enhancements for Photo Album Organizer.

---

## ✅ Completed Features

### Resume Capability & Hash Persistence
**Status:** ✅ COMPLETED

Interrupt and resume long-running jobs without losing progress. State is saved to `.photo_organizer_state.json` every 50 photos, with hash caching for faster resume.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized         # auto-detects prior run, prompts
./photo_organizer.py -s ~/Photos -o ~/Organized --resume  # skip prompt, always resume
./photo_organizer.py -s ~/Photos -o ~/Organized --force-fresh  # skip prompt, start fresh
```

---

### Multi-Threading
**Status:** ✅ COMPLETED

Parallel hash computation via `--threads N`. Speeds up the hashing phase 2–4× on multi-core systems.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --threads 4
```

---

### Immich Integration
**Status:** ✅ COMPLETED (full Phase 1 + Phase 2)

Full integration with [Immich](https://immich.app/) self-hosted photo management:
- ✅ Connect to Immich API, read photos
- ✅ Tag duplicates with structured tags (`photo-organizer/best`, `photo-organizer/non-best`)
- ✅ Create organized albums
- ✅ Mark best photos as favorites
- ✅ Archive non-best photos
- ✅ Group by recognized person
- ✅ CLIP semantic search pre-filtering
- ✅ Server-side duplicate detection
- ✅ Concurrent prefetching, bulk API operations
- ✅ Cleanup/undo all organizer changes

See [IMMICH.md](IMMICH.md) for usage.

---

### Web Viewer
**Status:** ✅ COMPLETED

Built-in stdlib HTTP server — no Flask or React required. Features:
- ✅ Group grid with Immich thumbnail proxying
- ✅ Report switcher dropdown (compare runs)
- ✅ Click to expand groups with EXIF metadata
- ✅ Full-resolution lightbox
- ✅ Set best photo interactively
- ✅ Bulk actions: archive, delete, discard
- ✅ People view (browse by recognized person)
- ✅ Background lifecycle manager (`scripts/viewer`) with watchdog auto-stop
- ✅ direnv `[v]` prompt integration

```bash
scripts/viewer start   # background, auto-stops when you leave the directory
```

---

### HDR / Exposure Blending
**Status:** ✅ COMPLETED

Detects bracketed exposures from EXIF and merges them using OpenCV Debevec HDR + Drago tone mapping.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --enable-hdr
```

---

### Advanced Face Swapping
**Status:** ✅ COMPLETED (basic version)

Detects closed eyes using Eye Aspect Ratio (EAR), identifies the same person across photos using face encodings, and swaps the face region using seamless clone blending.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --enable-face-swap
```

---

### Interactive Setup Menu
**Status:** ✅ COMPLETED

Full guided `-i` mode with save/load settings, direnv prompt integration, and summary screen with web viewer as default action.

---

### HEIC Support
**Status:** ✅ COMPLETED

Apple HEIC format processed via Pillow with `pillow-heif` plugin.

---

### Timestamped Reports
**Status:** ✅ COMPLETED

Reports saved to `reports/report_YYYY-MM-DD_HHMMSS.json` with a `reports/latest.json` symlink. The web viewer dropdown lists all historical reports.

---

## 🔧 In Progress / Planned

### GPU Acceleration for Face Detection
**Status:** 🔧 IN PROGRESS — design complete, implementation next

10–50× faster face detection using PyTorch (CUDA/MPS) or ONNX Runtime (CUDA). New backends: FaceNet/PyTorch and InsightFace.

See [GPU_ACCELERATION.md](GPU_ACCELERATION.md) for the full design.

```bash
# Planned usage:
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu --face-backend facenet
```

---

### Additional Face Backends
**Status:** 🔧 IN PROGRESS — design complete, implementation next

Three new pluggable backends to complement `face_recognition` and `MediaPipe`:
- **InsightFace** — state-of-the-art accuracy, 512-d ArcFace encoding, CUDA
- **FaceNet/PyTorch** — MTCNN detection, 128-d encoding, CUDA/MPS
- **YOLOv8-Face** — fastest detection, GPU-capable, detection-only

See [FACE_BACKENDS.md](FACE_BACKENDS.md) for the full design.

---

### Immich Phase 3: Stream Processing
**Status:** ⏳ PLANNED

- Real-time sync (process new photos as they arrive)
- Async/parallel downloads via `aiohttp`
- Bi-directional sync

---

### Video Support
**Status:** ⏳ PLANNED

Extract key frames from videos, compute perceptual hashes, group similar clips.

---

### Apple Photos / Google Photos Integration
**Status:** ⏳ PLANNED (design exists)

- Apple Photos via `osxphotos` (macOS only)
- Google Photos via OAuth2 (read-only)

See [CLOUD_INTEGRATION_DESIGN.md](CLOUD_INTEGRATION_DESIGN.md) for design details.

---

### ML-Based Photo Quality Scoring
**Status:** ⏳ PLANNED

Use CLIP or MobileNetV2 to score aesthetic quality (composition, sharpness, lighting) beyond face quality metrics.

---

## Implementation Notes

- All new face backends follow the `FaceBackend` abstract interface in `src/face_backend.py`
- GPU support is opt-in via `--gpu` flag with automatic device detection and CPU fallback
- Each feature is independently toggled by CLI flag — no breaking changes to existing workflows
