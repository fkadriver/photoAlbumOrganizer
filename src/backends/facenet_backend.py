"""
FaceNet/PyTorch backend for face detection and encoding.

Uses MTCNN for multi-scale face detection and InceptionResnetV1 for
128-dimensional face embeddings. Primary GPU backend with native
CUDA and MPS (Apple Silicon) support.

Install:
    pip install facenet-pytorch  # CPU
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
    pip install facenet-pytorch  # GPU (CUDA)
"""

import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from face_backend import FaceBackend, FaceLocation, FaceLandmarks, FaceEncoding


class FacenetBackend(FaceBackend):
    """Backend using facenet-pytorch (MTCNN + InceptionResnetV1).

    Primary GPU backend with native PyTorch CUDA and MPS support.
    Provides 128-dimensional face embeddings compatible with dlib distance.

    Attributes:
        gpu: Whether GPU acceleration is enabled
        gpu_device: CUDA device index (0 = first GPU)
        device: PyTorch device being used
    """

    def __init__(self, gpu: bool = False, gpu_device: int = 0):
        """Initialize FaceNet backend.

        Args:
            gpu: Enable GPU acceleration
            gpu_device: CUDA device index (default: 0, ignored for MPS)
        """
        try:
            import torch
            from facenet_pytorch import MTCNN, InceptionResnetV1
        except ImportError:
            raise ImportError(
                "facenet-pytorch not installed. Install with:\n"
                "  pip install facenet-pytorch  # CPU\n"
                "  pip install torch torchvision --index-url "
                "https://download.pytorch.org/whl/cu121\n"
                "  pip install facenet-pytorch  # GPU"
            )

        self.gpu = gpu
        self.gpu_device = gpu_device
        self._torch = torch

        # Determine device
        if gpu:
            if torch.cuda.is_available():
                self._device = torch.device(f'cuda:{gpu_device}')
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                self._device = torch.device('mps')
            else:
                print("Warning: GPU requested but not available, using CPU")
                self._device = torch.device('cpu')
        else:
            self._device = torch.device('cpu')

        # Initialize MTCNN for face detection
        # keep_all=True returns all detected faces
        # post_process=False keeps images as tensors for encoding
        self._mtcnn = MTCNN(
            keep_all=True,
            device=self._device,
            post_process=False,
            select_largest=False,
            min_face_size=20,
        )

        # Initialize InceptionResnetV1 for face encoding
        # pretrained='vggface2' uses VGGFace2 trained weights
        self._resnet = InceptionResnetV1(
            pretrained='vggface2'
        ).eval().to(self._device)

    @property
    def name(self) -> str:
        return "facenet"

    @property
    def supports_encoding(self) -> bool:
        return True

    @property
    def device(self) -> str:
        """Return current device string (e.g., 'cuda:0', 'mps', or 'cpu')."""
        return str(self._device)

    def load_image(self, image_path: str) -> np.ndarray:
        """Load image as RGB numpy array."""
        from PIL import Image
        img = Image.open(image_path).convert("RGB")
        return np.asarray(img)

    def _detect_with_landmarks(self, image: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[list]]:
        """Detect faces and return boxes, probabilities, and landmarks.

        Returns:
            Tuple of (boxes, probs, landmarks) or (None, None, None) if no faces
            boxes: (N, 4) array of [x1, y1, x2, y2] bounding boxes
            probs: (N,) array of detection probabilities
            landmarks: List of (5, 2) arrays of facial landmarks per face
        """
        from PIL import Image

        # MTCNN expects PIL Image
        pil_image = Image.fromarray(image)

        # Detect faces with landmarks
        boxes, probs, landmarks = self._mtcnn.detect(pil_image, landmarks=True)

        return boxes, probs, landmarks

    def detect_faces(self, image: np.ndarray) -> List[FaceLocation]:
        """Detect face bounding boxes in an image."""
        boxes, probs, _ = self._detect_with_landmarks(image)

        if boxes is None:
            return []

        locations = []
        for box in boxes:
            # box is [x1, y1, x2, y2]
            x1, y1, x2, y2 = box.astype(int)
            locations.append(FaceLocation(
                top=int(y1),
                right=int(x2),
                bottom=int(y2),
                left=int(x1),
            ))

        return locations

    def get_landmarks(self, image: np.ndarray) -> List[FaceLandmarks]:
        """Get facial landmarks for all faces in an image.

        MTCNN provides 5-point landmarks:
        [left_eye, right_eye, nose, mouth_left, mouth_right]

        We create synthetic 6-point eye contours for EAR calculation.
        """
        boxes, probs, face_landmarks = self._detect_with_landmarks(image)

        if face_landmarks is None:
            return []

        landmarks = []
        for lm in face_landmarks:
            # lm is (5, 2) array: [left_eye, right_eye, nose, mouth_left, mouth_right]
            left_center = (int(lm[0][0]), int(lm[0][1]))
            right_center = (int(lm[1][0]), int(lm[1][1]))
            nose = (int(lm[2][0]), int(lm[2][1]))
            mouth_left = (int(lm[3][0]), int(lm[3][1]))
            mouth_right = (int(lm[4][0]), int(lm[4][1]))

            # Generate 6-point eye contours from center points
            # This approximates the dlib 6-point eye format for EAR calculation
            def make_eye_contour(center: Tuple[int, int], radius: int = 8) -> List[Tuple[int, int]]:
                """Create 6-point eye contour from center point.

                Points ordered: left corner, upper-left, upper-right,
                right corner, lower-right, lower-left
                """
                cx, cy = center
                return [
                    (cx - radius, cy),           # left corner
                    (cx - radius // 2, cy - radius // 2),  # upper-left
                    (cx + radius // 2, cy - radius // 2),  # upper-right
                    (cx + radius, cy),           # right corner
                    (cx + radius // 2, cy + radius // 2),  # lower-right
                    (cx - radius // 2, cy + radius // 2),  # lower-left
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

        return landmarks

    def encode_faces(self, image: np.ndarray) -> List[FaceEncoding]:
        """Compute 128-dimensional face embeddings for all faces.

        Uses InceptionResnetV1 trained on VGGFace2 dataset.
        """
        from PIL import Image

        pil_image = Image.fromarray(image)

        # Extract aligned face tensors
        # Returns (N, 3, 160, 160) tensor or None
        faces = self._mtcnn(pil_image)

        if faces is None:
            return []

        # Handle single face case
        if faces.dim() == 3:
            faces = faces.unsqueeze(0)

        # Move to device and compute embeddings
        faces = faces.to(self._device)

        with self._torch.no_grad():
            embeddings = self._resnet(faces)

        # Convert to numpy and create FaceEncoding objects
        embeddings_np = embeddings.cpu().numpy()

        return [FaceEncoding(vector=emb) for emb in embeddings_np]

    def face_distance(self, known: FaceEncoding, candidate: FaceEncoding) -> float:
        """Compute Euclidean distance between two face embeddings.

        Uses L2 distance similar to dlib/face_recognition for compatibility.
        Lower values mean more similar faces.
        """
        return float(np.linalg.norm(known.vector - candidate.vector))

    def encode_faces_batch(self, images: List[np.ndarray]) -> List[List[FaceEncoding]]:
        """Batch encode faces from multiple images (GPU-optimized).

        This method processes multiple images together on the GPU for
        better throughput compared to single-image encoding.

        Args:
            images: List of RGB numpy arrays

        Returns:
            List of lists, one per image, each containing FaceEncodings
        """
        from PIL import Image

        all_faces = []
        face_counts = []

        # Extract faces from all images
        for image in images:
            pil_image = Image.fromarray(image)
            faces = self._mtcnn(pil_image)

            if faces is None:
                face_counts.append(0)
            elif faces.dim() == 3:
                all_faces.append(faces.unsqueeze(0))
                face_counts.append(1)
            else:
                all_faces.append(faces)
                face_counts.append(faces.shape[0])

        if not all_faces:
            return [[] for _ in images]

        # Concatenate all faces and encode in one batch
        batch = self._torch.cat(all_faces, dim=0).to(self._device)

        with self._torch.no_grad():
            embeddings = self._resnet(batch)

        embeddings_np = embeddings.cpu().numpy()

        # Split embeddings back by image
        results = []
        idx = 0
        for count in face_counts:
            if count == 0:
                results.append([])
            else:
                results.append([
                    FaceEncoding(vector=embeddings_np[idx + i])
                    for i in range(count)
                ])
                idx += count

        return results
