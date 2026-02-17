# Face Detection Backends

The photo organizer uses a pluggable face detection system (`src/face_backend.py`) with a common `FaceBackend` abstract base class. All backends provide face detection and landmark extraction; some also provide face encoding for identity matching (required for face-swap).

## Backend Comparison

| Backend | `--face-backend` | Detection | Landmarks | Encoding | GPU | Install |
|---------|-----------------|-----------|-----------|----------|-----|---------|
| **face_recognition** | `face_recognition` | dlib HOG/CNN | 68-point | ✅ 128-d (dlib) | ❌ | High (dlib compile) |
| **MediaPipe** | `mediapipe` | FaceLandmarker | 468-point | ❌ | ❌ | Low (`pip install mediapipe`) |
| **InsightFace** | `insightface` | RetinaFace | 106-point | ✅ 512-d (ArcFace) | ✅ CUDA/CPU | Medium (`pip install insightface`) |
| **FaceNet/PyTorch** | `facenet` | MTCNN | 5-point | ✅ 128-d | ✅ CUDA/MPS/CPU | Medium (`pip install facenet-pytorch`) |
| **YOLOv8-Face** | `yolov8` | YOLOv8 | 5-point | ❌ | ✅ CUDA/MPS/CPU | Medium (`pip install ultralytics`) |
| **Auto** (default) | `auto` | Best available | — | — | — | — |

---

## Currently Available Backends

### face_recognition (dlib)

The original backend. Uses dlib's HOG-based face detector and 68-point landmark predictor with 128-dimensional face encodings. Required for `--enable-face-swap`.

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --face-backend face_recognition
```

**Install:**
```bash
pip install dlib face_recognition
pip install git+https://github.com/ageitgey/face_recognition_models
# Or pre-built:
pip install dlib-binary face_recognition
```

**Limitations:**
- CPU-only (no GPU path)
- Unmaintained since ~2020, 2015-era dlib model
- Verbose BLAS/LAPACK warnings (suppressed automatically)
- Requires compilation on non-NixOS systems

---

### MediaPipe

Google's lightweight face landmarker. No compilation needed — just `pip install mediapipe` and a downloaded model file. Provides 468-point FaceMesh landmarks (mapped to 6-point eye contours for EAR calculation).

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --face-backend mediapipe
```

**Install:**
```bash
pip install mediapipe
mkdir -p models
curl -sSL -o models/face_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
```

**Limitations:**
- No face encoding — face-swap feature unavailable
- CPU-only in the current integration

---

## Planned Backends

The following backends are designed and ready for implementation. They will be added as `src/backends/` submodules and registered in `get_face_backend()`.

### InsightFace *(Planned)*

State-of-the-art accuracy using the buffalo_l model (RetinaFace detection + ArcFace encoding). ONNX Runtime execution providers enable automatic GPU acceleration.

**Capabilities:**
- Detection: RetinaFace (excellent on small/occluded faces)
- Landmarks: 106-point
- Encoding: 512-d ArcFace embeddings (better than dlib 128-d)
- GPU: CUDA via ONNX Runtime `CUDAExecutionProvider`
- Face-swap: ✅ supported (has encoding)

**Planned interface:**
```python
class InsightFaceBackend(FaceBackend):
    def __init__(self, gpu: bool = False, gpu_device: int = 0):
        import insightface
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if gpu \
                    else ['CPUExecutionProvider']
        self._app = insightface.app.FaceAnalysis(
            name='buffalo_l',
            providers=providers
        )
        self._app.prepare(ctx_id=gpu_device if gpu else -1)

    @property
    def name(self) -> str:
        return "insightface"

    @property
    def supports_encoding(self) -> bool:
        return True
```

**Install (when available):**
```bash
pip install insightface onnxruntime
# For GPU:
pip install insightface onnxruntime-gpu
```

---

### FaceNet/PyTorch *(Planned — primary GPU backend)*

Uses facenet-pytorch: MTCNN for detection and InceptionResnetV1 for 128-d face embeddings. Native PyTorch enables automatic CUDA/MPS/CPU device selection.

**Capabilities:**
- Detection: MTCNN (multi-scale, robust)
- Landmarks: 5-point
- Encoding: 128-d InceptionResnetV1 (modern replacement for dlib)
- GPU: CUDA (`cuda`), Apple Silicon (`mps`), or CPU fallback
- Batch processing: multiple images processed together on GPU
- Face-swap: ✅ supported (has encoding)

**Planned interface:**
```python
class FacenetBackend(FaceBackend):
    def __init__(self, gpu: bool = False, gpu_device: int = 0):
        import torch
        from facenet_pytorch import MTCNN, InceptionResnetV1

        if gpu:
            if torch.cuda.is_available():
                self._device = torch.device(f'cuda:{gpu_device}')
            elif torch.backends.mps.is_available():
                self._device = torch.device('mps')
            else:
                self._device = torch.device('cpu')
        else:
            self._device = torch.device('cpu')

        self._mtcnn = MTCNN(keep_all=True, device=self._device)
        self._resnet = InceptionResnetV1(pretrained='vggface2').eval().to(self._device)

    @property
    def name(self) -> str:
        return "facenet"

    @property
    def supports_encoding(self) -> bool:
        return True
```

**Install (when available):**
```bash
pip install facenet-pytorch
# For GPU (PyTorch with CUDA):
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install facenet-pytorch
```

---

### YOLOv8-Face *(Planned)*

Fastest detection using Ultralytics YOLOv8. Best for very large libraries where speed matters more than encoding precision.

**Capabilities:**
- Detection: YOLOv8n-face (excellent speed, good accuracy)
- Landmarks: 5-point
- Encoding: ❌ not supported
- GPU: CUDA/MPS via PyTorch
- Face-swap: ❌ unavailable (no encoding)

**Planned interface:**
```python
class YOLOv8FaceBackend(FaceBackend):
    def __init__(self, gpu: bool = False):
        from ultralytics import YOLO
        self._model = YOLO('yolov8n-face.pt')
        self._device = 'cuda' if gpu and torch.cuda.is_available() else 'cpu'

    @property
    def name(self) -> str:
        return "yolov8"

    @property
    def supports_encoding(self) -> bool:
        return False
```

**Install (when available):**
```bash
pip install ultralytics
```

---

## Auto-Selection Logic

The `auto` backend (default) selects the best available backend:

```
--gpu flag set?
  YES → try FacenetBackend (CUDA/MPS) → try InsightFaceBackend (CUDA) → fall back to CPU
  NO  → try face_recognition → try MediaPipe → warn and disable
```

When `--enable-face-swap` is used, the backend **must** support encoding. If auto-selected backend doesn't support it, the organizer will warn and disable face-swap rather than fail.

---

## Immich Server-Side Faces

When using `--immich-use-server-faces`, the organizer uses Immich's built-in face detection data (bounding boxes, person recognition) instead of downloading photos for local analysis. Scoring is by face area (larger faces = clearer shots).

```bash
./photo_organizer.py --source-type immich \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" \
  --immich-use-server-faces \
  --tag-only
```

Combine with `--immich-group-by-person` to organize by recognized person.

---

## Adding a Custom Backend

Implement `FaceBackend` from `src/face_backend.py`:

```python
from face_backend import FaceBackend, FaceLocation, FaceLandmarks, FaceEncoding
import numpy as np
from typing import List

class MyBackend(FaceBackend):
    @property
    def name(self) -> str:
        return "my_backend"

    def load_image(self, image_path: str) -> np.ndarray:
        ...  # return RGB numpy array

    def detect_faces(self, image: np.ndarray) -> List[FaceLocation]:
        ...  # return list of FaceLocation

    def get_landmarks(self, image: np.ndarray) -> List[FaceLandmarks]:
        ...  # return list of FaceLandmarks (must have left_eye, right_eye)
```

Then register it in `get_face_backend()` in `face_backend.py`.

---

## See Also

- [GPU_ACCELERATION.md](GPU_ACCELERATION.md) — GPU setup and configuration
- [CONFIGURATION.md](CONFIGURATION.md) — General configuration options
- [PERFORMANCE.md](PERFORMANCE.md) — Performance tuning
