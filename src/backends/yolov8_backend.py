"""
YOLOv8-Face backend for ultra-fast face detection.

Uses Ultralytics YOLOv8 with a face-specific model for high-speed
detection. Best for large photo libraries where speed matters more
than encoding precision.

Note: This backend does NOT support face encoding, so face-swap
functionality is unavailable.

Install:
    pip install ultralytics
"""

import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from face_backend import FaceBackend, FaceLocation, FaceLandmarks, FaceEncoding


class YOLOv8FaceBackend(FaceBackend):
    """Backend using YOLOv8 for ultra-fast face detection.

    Provides the highest throughput for face detection (150-400 images/sec
    on RTX 3080) but does NOT support face encoding.

    Best for:
    - Very large photo libraries (10,000+ photos)
    - Quick face detection without identity matching
    - Systems where speed is prioritized over face-swap capability

    Attributes:
        gpu: Whether GPU acceleration is enabled
        gpu_device: CUDA device index (0 = first GPU)
    """

    # Model download URL and local cache path
    _MODEL_NAME = "yolov8n-face.pt"
    _MODEL_URL = "https://github.com/akanametov/yolov8-face/releases/download/v1.0.0/yolov8n-face.pt"

    def __init__(self, gpu: bool = False, gpu_device: int = 0):
        """Initialize YOLOv8-Face backend.

        Args:
            gpu: Enable GPU acceleration
            gpu_device: CUDA device index (default: 0)
        """
        try:
            from ultralytics import YOLO
            import torch
        except ImportError:
            raise ImportError(
                "ultralytics not installed. Install with:\n"
                "  pip install ultralytics"
            )

        self.gpu = gpu
        self.gpu_device = gpu_device
        self._torch = torch

        # Determine device
        if gpu:
            if torch.cuda.is_available():
                self._device = f'cuda:{gpu_device}'
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                self._device = 'mps'
            else:
                print("Warning: GPU requested but not available, using CPU")
                self._device = 'cpu'
        else:
            self._device = 'cpu'

        # Get model path (download if needed)
        model_path = self._get_model_path()

        # Initialize YOLO model
        self._model = YOLO(model_path)

    def _get_model_path(self) -> str:
        """Get path to YOLOv8-face model, downloading if necessary."""
        # Check in models directory relative to repo root
        repo_root = Path(__file__).resolve().parent.parent.parent
        models_dir = repo_root / "models"
        model_path = models_dir / self._MODEL_NAME

        if model_path.exists():
            return str(model_path)

        # Check in current working directory
        cwd_model = Path.cwd() / "models" / self._MODEL_NAME
        if cwd_model.exists():
            return str(cwd_model)

        # Try to download the model
        print(f"Downloading {self._MODEL_NAME}...")
        models_dir.mkdir(parents=True, exist_ok=True)

        try:
            import urllib.request
            urllib.request.urlretrieve(self._MODEL_URL, model_path)
            print(f"Downloaded to {model_path}")
            return str(model_path)
        except Exception as e:
            # Fall back to standard YOLOv8n and hope it works for faces
            print(f"Could not download face model: {e}")
            print("Falling back to standard yolov8n.pt")
            return "yolov8n.pt"

    @property
    def name(self) -> str:
        return "yolov8"

    @property
    def supports_encoding(self) -> bool:
        return False

    @property
    def device(self) -> str:
        """Return current device string (e.g., 'cuda:0', 'mps', or 'cpu')."""
        return self._device

    def load_image(self, image_path: str) -> np.ndarray:
        """Load image as RGB numpy array."""
        from PIL import Image
        img = Image.open(image_path).convert("RGB")
        return np.asarray(img)

    def _run_inference(self, image: np.ndarray):
        """Run YOLO inference and return results."""
        # YOLO can accept numpy arrays directly
        results = self._model(
            image,
            device=self._device,
            verbose=False,
        )
        return results[0] if results else None

    def detect_faces(self, image: np.ndarray) -> List[FaceLocation]:
        """Detect face bounding boxes in an image."""
        result = self._run_inference(image)

        if result is None or result.boxes is None:
            return []

        locations = []
        boxes = result.boxes

        for box in boxes:
            # box.xyxy is [x1, y1, x2, y2]
            xyxy = box.xyxy[0].cpu().numpy().astype(int)
            x1, y1, x2, y2 = xyxy

            locations.append(FaceLocation(
                top=int(y1),
                right=int(x2),
                bottom=int(y2),
                left=int(x1),
            ))

        return locations

    def get_landmarks(self, image: np.ndarray) -> List[FaceLandmarks]:
        """Get facial landmarks for all faces in an image.

        YOLOv8-face provides 5-point landmarks when using the face model:
        [left_eye, right_eye, nose, mouth_left, mouth_right]

        We create synthetic 6-point eye contours for EAR calculation.
        """
        result = self._run_inference(image)

        if result is None:
            return []

        landmarks = []

        # Check if keypoints are available (face model provides them)
        if hasattr(result, 'keypoints') and result.keypoints is not None:
            kps_data = result.keypoints.data.cpu().numpy()

            for kps in kps_data:
                # kps is (5, 3) or (5, 2) array
                # [left_eye, right_eye, nose, mouth_left, mouth_right]
                if len(kps) < 5:
                    continue

                left_center = (int(kps[0][0]), int(kps[0][1]))
                right_center = (int(kps[1][0]), int(kps[1][1]))
                nose = (int(kps[2][0]), int(kps[2][1]))
                mouth_left = (int(kps[3][0]), int(kps[3][1]))
                mouth_right = (int(kps[4][0]), int(kps[4][1]))

                # Generate 6-point eye contours from center points
                def make_eye_contour(center: Tuple[int, int], radius: int = 8) -> List[Tuple[int, int]]:
                    cx, cy = center
                    return [
                        (cx - radius, cy),
                        (cx - radius // 2, cy - radius // 2),
                        (cx + radius // 2, cy - radius // 2),
                        (cx + radius, cy),
                        (cx + radius // 2, cy + radius // 2),
                        (cx - radius // 2, cy + radius // 2),
                    ]

                # Estimate eye radius based on inter-eye distance
                eye_dist = np.sqrt((right_center[0] - left_center[0])**2 +
                                   (right_center[1] - left_center[1])**2)
                eye_radius = max(5, int(eye_dist / 8))

                left_eye = make_eye_contour(left_center, eye_radius)
                right_eye = make_eye_contour(right_center, eye_radius)

                raw = {
                    'left_eye_center': left_center,
                    'right_eye_center': right_center,
                    'nose': nose,
                    'mouth_left': mouth_left,
                    'mouth_right': mouth_right,
                    'kps': [left_center, right_center, nose, mouth_left, mouth_right],
                }

                landmarks.append(FaceLandmarks(
                    left_eye=left_eye,
                    right_eye=right_eye,
                    raw=raw,
                ))
        else:
            # No keypoints available, create landmarks from bounding boxes
            # This provides basic face location but not detailed eye positions
            if result.boxes is not None:
                for box in result.boxes:
                    xyxy = box.xyxy[0].cpu().numpy().astype(int)
                    x1, y1, x2, y2 = xyxy

                    # Estimate eye positions from face bounding box
                    width = x2 - x1
                    height = y2 - y1

                    # Eyes are typically at ~30% height, 25% and 75% width
                    left_center = (x1 + int(width * 0.3), y1 + int(height * 0.35))
                    right_center = (x1 + int(width * 0.7), y1 + int(height * 0.35))

                    eye_radius = max(5, int(width * 0.08))

                    def make_eye_contour(center: Tuple[int, int], radius: int) -> List[Tuple[int, int]]:
                        cx, cy = center
                        return [
                            (cx - radius, cy),
                            (cx - radius // 2, cy - radius // 2),
                            (cx + radius // 2, cy - radius // 2),
                            (cx + radius, cy),
                            (cx + radius // 2, cy + radius // 2),
                            (cx - radius // 2, cy + radius // 2),
                        ]

                    landmarks.append(FaceLandmarks(
                        left_eye=make_eye_contour(left_center, eye_radius),
                        right_eye=make_eye_contour(right_center, eye_radius),
                        raw={'estimated_from_bbox': True},
                    ))

        return landmarks

    def detect_faces_batch(self, images: List[np.ndarray]) -> List[List[FaceLocation]]:
        """Batch detect faces from multiple images (GPU-optimized).

        Args:
            images: List of RGB numpy arrays

        Returns:
            List of lists, one per image, each containing FaceLocations
        """
        results = self._model(
            images,
            device=self._device,
            verbose=False,
        )

        all_locations = []

        for result in results:
            locations = []
            if result.boxes is not None:
                for box in result.boxes:
                    xyxy = box.xyxy[0].cpu().numpy().astype(int)
                    x1, y1, x2, y2 = xyxy
                    locations.append(FaceLocation(
                        top=int(y1),
                        right=int(x2),
                        bottom=int(y2),
                        left=int(x1),
                    ))
            all_locations.append(locations)

        return all_locations
