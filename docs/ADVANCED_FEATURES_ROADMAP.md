# Advanced Features Roadmap

Implementation status and design notes for advanced Photo Album Organizer features.

---

## Status Overview

| Feature | Status |
|---------|--------|
| Immich Integration | ✅ COMPLETED |
| Resume Capability | ✅ COMPLETED |
| Multi-threaded Processing | ✅ COMPLETED |
| HDR / Exposure Blending | ✅ COMPLETED |
| Advanced Face Swapping | ✅ COMPLETED (basic) |
| Timestamped Reports | ✅ COMPLETED |
| Web Viewer | ✅ COMPLETED |
| HEIC Support | ✅ COMPLETED |
| GPU Acceleration | 🔧 IN PROGRESS |
| Additional Face Backends | 🔧 IN PROGRESS |
| ML-Based Selection | ⏳ PLANNED |
| Video Support | ⏳ PLANNED |

---

## ✅ Completed

### Multi-threaded Processing
**Effort:** Low | **Impact:** High

Parallel hash computation via `--threads N` (default: 2). Threading is applied at the hash computation phase where most time is spent on I/O and image decoding.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --threads 4
```

---

### Resume Capability
**See:** [RESUME_CAPABILITY.md](RESUME_CAPABILITY.md)

State saved to JSON (migrated from the original pickle format) every 50 photos. Auto-detected on next run with a prompt to resume or start fresh.

---

### HDR / Exposure Blending
**Effort:** Medium | **Impact:** Medium

Detects bracketed exposures from `ExposureTime` EXIF values, merges using OpenCV Debevec HDR, and applies Drago tone mapping. Output: `hdr_merged.jpg` in each group directory.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --enable-hdr --hdr-gamma 2.2
```

---

### Advanced Face Swapping (Basic Version)
**Effort:** High | **Impact:** Medium

Detects closed eyes via Eye Aspect Ratio (EAR) calculated from 6-point eye contours. Finds replacement faces from other photos in the group using face encoding distance. Blends using OpenCV `seamlessClone`.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --enable-face-swap
```

Limitations of current implementation:
- Requires `face_recognition` backend (encoding support)
- Single-pass (no multi-face composite across multiple sources)
- No pose normalization before blending

---

### Immich Integration
**See:** [IMMICH.md](IMMICH.md)

Full Phase 1 (read-only) and Phase 2 (write) complete:
- Tag/untag duplicates with structured Immich tags
- Create / delete albums
- Mark favorites, archive photos
- Group by person, CLIP semantic search
- Server-side duplicate detection
- Bulk API operations, concurrent prefetching
- Full cleanup/undo menu

---

## 🔧 In Progress

### GPU Acceleration for Face Detection
**Effort:** 2–3 days | **Impact:** Very High

**Design:** See [GPU_ACCELERATION.md](GPU_ACCELERATION.md)

New GPU-capable backends (`FacenetBackend`, `InsightFaceBackend`) with automatic device selection (CUDA → MPS → CPU). Activated via `--gpu` flag.

**Expected speedup:** 10–50× for face detection on NVIDIA GPUs.

**Implementation plan:**
1. Create `src/backends/` directory
2. Implement `FacenetBackend` (facenet-pytorch, PyTorch device auto-detect)
3. Implement `InsightFaceBackend` (ONNX Runtime, CUDAExecutionProvider)
4. Add `--gpu` and `--gpu-device` CLI flags to `photo_organizer.py`
5. Update `get_face_backend()` auto-selection logic
6. Add `requirements-gpu.txt`

---

### Additional Face Backends
**Effort:** 2–3 days | **Impact:** High

**Design:** See [FACE_BACKENDS.md](FACE_BACKENDS.md)

Three new backends to add alongside existing `face_recognition` and `MediaPipe`:

| Backend | Key Advantage |
|---------|--------------|
| InsightFace | Best accuracy, 512-d ArcFace, CUDA |
| FaceNet/PyTorch | Modern dlib replacement, CUDA/MPS, batch processing |
| YOLOv8-Face | Fastest detection, GPU, good for large libraries |

**Implementation plan:**
1. Create `src/backends/__init__.py`
2. Add `insightface_backend.py`, `facenet_backend.py`, `yolov8_backend.py`
3. Register in `get_face_backend()` with new backend name strings
4. Update `--face-backend` choices in `photo_organizer.py` argument parser
5. Update documentation

---

## ⏳ Planned

### ML-Based Photo Quality Scoring
**Effort:** 7–10 days | **Impact:** High | **Complexity:** Very High

Use a CLIP or MobileNetV2 model to score photo aesthetic quality (sharpness, composition, exposure) as an additional signal for best-photo selection. Could be trained/fine-tuned from user feedback via the web viewer.

**Key challenge:** Gathering labeled training data. The web viewer's "set best" action is a natural feedback signal.

---

### Video Support
**Effort:** 3–5 days | **Impact:** Medium

Extract key frames from video clips, compute perceptual hashes, group similar clips alongside photos.

```python
class VideoHandler:
    def extract_key_frames(self, video_path) -> List[np.ndarray]:
        """Sample ~10 representative frames for hashing."""
```

---

### Async/Parallel Immich Downloads
**Effort:** 2–3 days | **Impact:** Medium (Immich only)

Replace synchronous `requests` in `immich_client.py` with `aiohttp` for concurrent photo fetching. Expected 3–5× speedup for download-heavy workflows.

---

## Implementation Notes

- All face backends must implement `FaceBackend` (see `src/face_backend.py`)
- GPU support is always opt-in — CPU fallback is automatic
- New features are independently flag-gated — no breaking changes
- `--face-backend auto` always works; new backends are tried before falling back to existing ones when `--gpu` is set

## Contributing

See README for contributing guidelines. To discuss implementation of any planned feature, open a GitHub issue with the `enhancement` label.
