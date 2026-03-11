# GPU Acceleration

GPU acceleration targets the most CPU-intensive phase: face detection and encoding. Expected speedup is **10–50× over CPU** for large photo libraries.

## Status

> **✅ IMPLEMENTED**
> GPU-capable backends (`InsightFace`, `FaceNet/PyTorch`, `YOLOv8-Face`) are available in `src/backends/` and integrated into `get_face_backend()`. ML Quality Scoring via CLIP/MobileNetV2 is also available.

---

## Supported Backends and GPU Frameworks

| Backend | GPU Framework | Devices |
|---------|--------------|---------|
| **FaceNet/PyTorch** | PyTorch | CUDA (NVIDIA), MPS (Apple Silicon) |
| **InsightFace** | ONNX Runtime | CUDA (NVIDIA), CPU fallback |
| **YOLOv8-Face** | PyTorch | CUDA (NVIDIA), MPS (Apple Silicon) |

CPU-only backends (`face_recognition`, `MediaPipe`) are unaffected — they continue to work as before.

---

## Planned CLI Flags

```bash
# Enable GPU acceleration (auto-selects best GPU backend)
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu

# Specify GPU device number (for multi-GPU systems)
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu --gpu-device 1

# Force a specific GPU backend
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu --face-backend facenet
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu --face-backend insightface

# GPU + face swap (requires encoding-capable backend)
./photo_organizer.py -s ~/Photos -o ~/Organized --gpu --enable-face-swap
```

---

## Installation

### NVIDIA GPU (CUDA)

```bash
# Check CUDA is available
nvidia-smi

# Install PyTorch with CUDA (for FaceNet backend)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install facenet-pytorch

# Or install ONNX Runtime with CUDA (for InsightFace backend)
pip install onnxruntime-gpu insightface
```

### Apple Silicon (MPS)

```bash
# PyTorch includes MPS support — no extra CUDA install needed
pip install torch torchvision  # standard install
pip install facenet-pytorch
```

### CPU-only (no GPU)

```bash
# Standard install, no GPU support
pip install facenet-pytorch  # will use CPU automatically
pip install insightface onnxruntime
```

---

## Auto-Detection Logic

When `--gpu` is passed, `get_face_backend()` will use this selection order:

```
1. FacenetBackend
   - Try torch.cuda.is_available() → use 'cuda:N'
   - Try torch.backends.mps.is_available() → use 'mps'
   - Fall back to 'cpu'

2. If facenet-pytorch not installed → try InsightFaceBackend
   - Try onnxruntime CUDAExecutionProvider
   - Fall back to CPUExecutionProvider

3. If neither installed → warn and fall back to face_recognition or mediapipe (CPU)
```

---

## Planned File Structure

When implemented, the new backends will live in `src/backends/`:

```
src/
  face_backend.py          # Abstract base + auto-selection (updated)
  backends/
    __init__.py
    face_recognition_backend.py   # Existing (moved/refactored)
    mediapipe_backend.py          # Existing (moved/refactored)
    insightface_backend.py        # NEW — ONNX/CUDA
    facenet_backend.py            # NEW — PyTorch/CUDA/MPS
    yolov8_backend.py             # NEW — PyTorch/CUDA/MPS
```

Backwards compatibility: `get_face_backend("face_recognition")` and `get_face_backend("mediapipe")` continue to work unchanged.

---

## Expected Performance

Benchmarks are approximate and depend on GPU model, image resolution, and batch size.

| Backend | Device | Images/sec (face detection) |
|---------|--------|-----------------------------|
| face_recognition (dlib) | CPU | 2–5 |
| MediaPipe | CPU | 5–15 |
| FaceNet/MTCNN | CPU | 3–8 |
| FaceNet/MTCNN | CUDA (RTX 3080) | 50–150 |
| InsightFace | CPU | 5–10 |
| InsightFace | CUDA (RTX 3080) | 80–200 |
| YOLOv8-Face | CPU | 10–25 |
| YOLOv8-Face | CUDA (RTX 3080) | 150–400 |

For a 10,000-photo library (each photo analyzed for faces), estimated time reduction:
- CPU (face_recognition): ~2 hours
- GPU (FaceNet, RTX 3080): ~5–10 minutes

---

## NixOS / Nix Considerations

CUDA in Nix requires `allowUnfree = true` and CUDA packages:

```nix
# flake.nix — add to devShell packages for GPU support
cudaPackages.cudatoolkit
cudaPackages.cudnn
linuxPackages.nvidia_x11
```

A `requirements-gpu.txt` will be provided when the backends are implemented:

```txt
torch>=2.1.0+cu121
torchvision>=0.16.0+cu121
facenet-pytorch>=2.5.3
# or:
insightface>=0.7.3
onnxruntime-gpu>=1.17.0
```

---

## See Also

- [FACE_BACKENDS.md](FACE_BACKENDS.md) — All face backend details and comparison
- [PERFORMANCE.md](PERFORMANCE.md) — General performance tuning
- [CONFIGURATION.md](CONFIGURATION.md) — CLI flag reference
