"""
Face detection backend abstraction layer.
Supports multiple face detection libraries through a common interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np


@dataclass
class FaceLocation:
    """A detected face bounding box."""
    top: int
    right: int
    bottom: int
    left: int


@dataclass
class FaceLandmarks:
    """Facial landmarks for a single face.

    Backends must provide left_eye and right_eye (6 points each minimum)
    for eye aspect ratio calculation. Additional landmarks are stored in raw.
    """
    left_eye: List[Tuple[int, int]]
    right_eye: List[Tuple[int, int]]
    raw: dict = field(default_factory=dict)


@dataclass
class FaceEncoding:
    """A face encoding vector for identity matching.

    Not all backends support this. Backends that don't will have
    supports_encoding = False, and face swap matching will be unavailable.
    """
    vector: np.ndarray


class FaceBackend(ABC):
    """Abstract base class for face detection backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this backend."""
        pass

    @property
    def supports_encoding(self) -> bool:
        """Whether this backend supports face encoding/identity matching."""
        return False

    @abstractmethod
    def load_image(self, image_path: str) -> np.ndarray:
        """Load an image file into a numpy array (RGB format).

        Args:
            image_path: Path to the image file

        Returns:
            numpy array in RGB format (H, W, 3)
        """
        pass

    @abstractmethod
    def detect_faces(self, image: np.ndarray) -> List[FaceLocation]:
        """Detect face bounding boxes in an image.

        Args:
            image: RGB numpy array from load_image()

        Returns:
            List of FaceLocation objects
        """
        pass

    @abstractmethod
    def get_landmarks(self, image: np.ndarray) -> List[FaceLandmarks]:
        """Get facial landmarks for all faces in an image.

        Must provide at least left_eye and right_eye landmarks
        (6 points each) for EAR calculation.

        Args:
            image: RGB numpy array from load_image()

        Returns:
            List of FaceLandmarks, one per detected face
        """
        pass

    def encode_faces(self, image: np.ndarray) -> List[FaceEncoding]:
        """Compute face identity encodings for all faces in an image.

        Only available if supports_encoding is True.

        Args:
            image: RGB numpy array from load_image()

        Returns:
            List of FaceEncoding objects
        """
        raise NotImplementedError(
            f"{self.name} backend does not support face encoding"
        )

    def face_distance(self, known: FaceEncoding, candidate: FaceEncoding) -> float:
        """Compute distance between two face encodings.

        Lower values mean more similar faces. Only available if
        supports_encoding is True.

        Args:
            known: The reference face encoding
            candidate: The candidate face encoding

        Returns:
            Distance as a float (0.0 = identical)
        """
        raise NotImplementedError(
            f"{self.name} backend does not support face distance"
        )


class FaceRecognitionBackend(FaceBackend):
    """Backend using the face_recognition library (dlib-based)."""

    def __init__(self):
        from importlib.metadata import PackageNotFoundError, version as pkg_version
        try:
            pkg_version("face_recognition_models")
        except PackageNotFoundError:
            pass

        from utils import SuppressStderr
        with SuppressStderr():
            import face_recognition
        self._fr = face_recognition

    @property
    def name(self) -> str:
        return "face_recognition"

    @property
    def supports_encoding(self) -> bool:
        return True

    def load_image(self, image_path: str) -> np.ndarray:
        from utils import SuppressStderr
        with SuppressStderr():
            return self._fr.load_image_file(image_path)

    def detect_faces(self, image: np.ndarray) -> List[FaceLocation]:
        from utils import SuppressStderr
        with SuppressStderr():
            locations = self._fr.face_locations(image)
        return [FaceLocation(top=t, right=r, bottom=b, left=l)
                for (t, r, b, l) in locations]

    def get_landmarks(self, image: np.ndarray) -> List[FaceLandmarks]:
        from utils import SuppressStderr
        with SuppressStderr():
            landmarks_list = self._fr.face_landmarks(image)
        return [
            FaceLandmarks(
                left_eye=lm.get('left_eye', []),
                right_eye=lm.get('right_eye', []),
                raw=lm,
            )
            for lm in landmarks_list
        ]

    def encode_faces(self, image: np.ndarray) -> List[FaceEncoding]:
        from utils import SuppressStderr
        with SuppressStderr():
            encodings = self._fr.face_encodings(image)
        return [FaceEncoding(vector=enc) for enc in encodings]

    def face_distance(self, known: FaceEncoding, candidate: FaceEncoding) -> float:
        from utils import SuppressStderr
        with SuppressStderr():
            dist = self._fr.face_distance([known.vector], candidate.vector)
        return float(dist[0])


def get_face_backend(backend_name: str = "auto") -> Optional[FaceBackend]:
    """Create and return a face detection backend.

    Args:
        backend_name: "face_recognition", "mediapipe", or "auto".
            "auto" tries face_recognition first, then mediapipe.

    Returns:
        A FaceBackend instance, or None if no backend is available.
    """
    if backend_name in ("face_recognition", "auto"):
        try:
            return FaceRecognitionBackend()
        except (Exception, SystemExit) as e:
            if backend_name == "face_recognition":
                print(f"Warning: Could not load face_recognition backend: {e}")
                return None

    # Future: MediaPipe backend would be tried here for "mediapipe" or "auto"
    if backend_name == "mediapipe":
        print("Warning: MediaPipe backend is not yet implemented.")
        return None

    if backend_name == "auto":
        print("Warning: No face detection backend available.")
        print("Face detection will be DISABLED.")
        print("Photos will be grouped, but best photo selection will be random.")

    return None
