"""
InsightFace backend for face detection and encoding.

Uses RetinaFace for detection and ArcFace for 512-dimensional face embeddings.
GPU acceleration via ONNX Runtime CUDAExecutionProvider.

Install:
    pip install insightface onnxruntime      # CPU
    pip install insightface onnxruntime-gpu  # GPU (CUDA)
"""

import sys
from pathlib import Path
from typing import List, Optional

import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from face_backend import FaceBackend, FaceLocation, FaceLandmarks, FaceEncoding


class InsightFaceBackend(FaceBackend):
    """Backend using InsightFace (RetinaFace + ArcFace).

    Provides state-of-the-art accuracy with 512-dimensional ArcFace embeddings.
    GPU acceleration available via ONNX Runtime CUDA provider.

    Attributes:
        gpu: Whether GPU acceleration is enabled
        gpu_device: CUDA device index (0 = first GPU)
    """

    # InsightFace provides 106-point landmarks in the format:
    # [left_eye (5), right_eye (5), nose (1), mouth_left (1), mouth_right (1), ...]
    # We extract 6 points per eye for EAR calculation by using the face mesh points
    # Indices for left eye contour (5 points around eye)
    _LEFT_EYE_IDX = [35, 36, 37, 38, 39]  # 5-point eye contour
    _RIGHT_EYE_IDX = [89, 90, 91, 92, 93]  # 5-point eye contour

    def __init__(self, gpu: bool = False, gpu_device: int = 0):
        """Initialize InsightFace backend.

        Args:
            gpu: Enable GPU acceleration via CUDA
            gpu_device: CUDA device index (default: 0)
        """
        try:
            import insightface
            from insightface.app import FaceAnalysis
        except ImportError:
            raise ImportError(
                "InsightFace not installed. Install with:\n"
                "  pip install insightface onnxruntime  # CPU\n"
                "  pip install insightface onnxruntime-gpu  # GPU"
            )

        self.gpu = gpu
        self.gpu_device = gpu_device

        # Set up ONNX Runtime execution providers
        if gpu:
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            ctx_id = gpu_device
        else:
            providers = ['CPUExecutionProvider']
            ctx_id = -1

        # Initialize FaceAnalysis with buffalo_l model (best accuracy)
        # Suppress INFO logs during model download
        self._app = FaceAnalysis(
            name='buffalo_l',
            providers=providers,
        )
        self._app.prepare(ctx_id=ctx_id, det_size=(640, 640))

        self._device_info = self._get_device_info()

    def _get_device_info(self) -> str:
        """Get string describing current compute device."""
        if self.gpu:
            try:
                import onnxruntime as ort
                available_providers = ort.get_available_providers()
                if 'CUDAExecutionProvider' in available_providers:
                    return f"CUDA:{self.gpu_device}"
            except Exception:
                pass
        return "CPU"

    @property
    def name(self) -> str:
        return "insightface"

    @property
    def supports_encoding(self) -> bool:
        return True

    @property
    def device(self) -> str:
        """Return current device string (e.g., 'CUDA:0' or 'CPU')."""
        return self._device_info

    def load_image(self, image_path: str) -> np.ndarray:
        """Load image as RGB numpy array."""
        from PIL import Image
        img = Image.open(image_path).convert("RGB")
        return np.asarray(img)

    def _get_faces(self, image: np.ndarray):
        """Run face analysis and return raw face objects.

        InsightFace expects BGR input, so we convert from RGB.
        """
        # Convert RGB to BGR for InsightFace
        bgr_image = image[:, :, ::-1]
        return self._app.get(bgr_image)

    def detect_faces(self, image: np.ndarray) -> List[FaceLocation]:
        """Detect face bounding boxes in an image."""
        faces = self._get_faces(image)
        locations = []

        for face in faces:
            bbox = face.bbox.astype(int)
            # bbox is [x1, y1, x2, y2]
            locations.append(FaceLocation(
                top=int(bbox[1]),
                right=int(bbox[2]),
                bottom=int(bbox[3]),
                left=int(bbox[0]),
            ))

        return locations

    def get_landmarks(self, image: np.ndarray) -> List[FaceLandmarks]:
        """Get facial landmarks for all faces in an image.

        InsightFace provides 106-point (2D) or 478-point (3D) landmarks.
        We extract 6 points per eye for EAR calculation.
        """
        faces = self._get_faces(image)
        landmarks = []

        for face in faces:
            # face.landmark_2d_106 is a (106, 2) array
            # face.kps is a (5, 2) array with key points:
            #   [left_eye, right_eye, nose, mouth_left, mouth_right]
            kps = face.kps if hasattr(face, 'kps') else None
            lm106 = face.landmark_2d_106 if hasattr(face, 'landmark_2d_106') else None

            if lm106 is not None:
                # Use 106-point landmarks for detailed eye contours
                # InsightFace 106-point landmark indices:
                # Left eye: 33-41 (outer to inner)
                # Right eye: 87-95 (outer to inner)
                left_eye = [(int(lm106[i][0]), int(lm106[i][1]))
                            for i in range(33, 42)]
                right_eye = [(int(lm106[i][0]), int(lm106[i][1]))
                             for i in range(87, 96)]

                raw = {
                    'all_landmarks': [(int(p[0]), int(p[1])) for p in lm106],
                    'kps': [(int(p[0]), int(p[1])) for p in kps] if kps is not None else [],
                }
            elif kps is not None:
                # Fallback to 5-point key points
                # Create synthetic 6-point eye contours from single point
                left_center = (int(kps[0][0]), int(kps[0][1]))
                right_center = (int(kps[1][0]), int(kps[1][1]))

                # Generate 6 points around each eye center
                def make_eye_contour(center, radius=5):
                    import math
                    return [
                        (center[0] - radius, center[1]),
                        (center[0] - radius // 2, center[1] - radius // 2),
                        (center[0] + radius // 2, center[1] - radius // 2),
                        (center[0] + radius, center[1]),
                        (center[0] + radius // 2, center[1] + radius // 2),
                        (center[0] - radius // 2, center[1] + radius // 2),
                    ]

                left_eye = make_eye_contour(left_center)
                right_eye = make_eye_contour(right_center)
                raw = {'kps': [(int(p[0]), int(p[1])) for p in kps]}
            else:
                # No landmarks available
                left_eye = []
                right_eye = []
                raw = {}

            landmarks.append(FaceLandmarks(
                left_eye=left_eye,
                right_eye=right_eye,
                raw=raw,
            ))

        return landmarks

    def encode_faces(self, image: np.ndarray) -> List[FaceEncoding]:
        """Compute 512-dimensional ArcFace embeddings for all faces."""
        faces = self._get_faces(image)
        encodings = []

        for face in faces:
            if hasattr(face, 'embedding') and face.embedding is not None:
                encodings.append(FaceEncoding(vector=face.embedding))
            else:
                # No embedding available for this face
                encodings.append(FaceEncoding(vector=np.zeros(512)))

        return encodings

    def face_distance(self, known: FaceEncoding, candidate: FaceEncoding) -> float:
        """Compute cosine distance between two face embeddings.

        ArcFace embeddings use cosine similarity, so we compute 1 - cosine_sim.
        Lower values mean more similar faces.
        """
        # Normalize vectors
        known_norm = known.vector / (np.linalg.norm(known.vector) + 1e-10)
        candidate_norm = candidate.vector / (np.linalg.norm(candidate.vector) + 1e-10)

        # Cosine similarity
        cosine_sim = np.dot(known_norm, candidate_norm)

        # Convert to distance (0 = identical, 2 = opposite)
        return float(1.0 - cosine_sim)
