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


class MediaPipeBackend(FaceBackend):
    """Backend using Google MediaPipe FaceLandmarker (468-point landmarks).

    Uses the MediaPipe Tasks API with a downloaded .task model file.
    The model is expected at ``models/face_landmarker.task`` relative to the
    repository root.
    """

    # 6-point eye contour indices into the 468 FaceMesh landmarks.
    # Ordered to match the dlib/face_recognition 6-point convention
    # (left corner, upper-left, upper-right, right corner, lower-right, lower-left)
    # so that the existing EAR calculation works unchanged.
    _RIGHT_EYE_IDX = [33, 160, 158, 133, 153, 144]
    _LEFT_EYE_IDX = [362, 385, 387, 263, 373, 380]

    _MODEL_FILENAME = "face_landmarker.task"

    def __init__(self):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp_image = mp.Image
        self._mp_image_format = mp.ImageFormat

        model_path = self._find_model()
        if model_path is None:
            raise FileNotFoundError(
                f"MediaPipe model '{self._MODEL_FILENAME}' not found. "
                "Download it with:\n  curl -sSL -o models/face_landmarker.task "
                "https://storage.googleapis.com/mediapipe-models/"
                "face_landmarker/face_landmarker/float16/latest/"
                "face_landmarker.task"
            )

        base_options = BaseOptions(model_asset_path=str(model_path))
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_faces=10,
            output_face_blendshapes=False,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)

    @classmethod
    def _find_model(cls) -> Optional[str]:
        """Locate the model file relative to the repo root."""
        import pathlib
        # Try models/ dir relative to the repo root (one level up from src/)
        candidates = [
            pathlib.Path(__file__).resolve().parent.parent / "models" / cls._MODEL_FILENAME,
            pathlib.Path.cwd() / "models" / cls._MODEL_FILENAME,
        ]
        for p in candidates:
            if p.is_file():
                return str(p)
        return None

    @property
    def name(self) -> str:
        return "mediapipe"

    @property
    def supports_encoding(self) -> bool:
        return False

    def load_image(self, image_path: str) -> np.ndarray:
        from PIL import Image
        img = Image.open(image_path).convert("RGB")
        return np.asarray(img)

    def _detect(self, image: np.ndarray):
        """Run the landmarker and return the raw result."""
        mp_image = self._mp_image(
            image_format=self._mp_image_format.SRGB, data=image)
        return self._landmarker.detect(mp_image)

    def detect_faces(self, image: np.ndarray) -> List[FaceLocation]:
        result = self._detect(image)
        if not result.face_landmarks:
            return []

        h, w = image.shape[:2]
        locations = []
        for face_lm in result.face_landmarks:
            xs = [lm.x for lm in face_lm]
            ys = [lm.y for lm in face_lm]
            top = max(0, int(min(ys) * h))
            bottom = min(h, int(max(ys) * h))
            left = max(0, int(min(xs) * w))
            right = min(w, int(max(xs) * w))
            locations.append(FaceLocation(top=top, right=right,
                                          bottom=bottom, left=left))
        return locations

    def get_landmarks(self, image: np.ndarray) -> List[FaceLandmarks]:
        result = self._detect(image)
        if not result.face_landmarks:
            return []

        h, w = image.shape[:2]
        landmarks = []
        for face_lm in result.face_landmarks:
            def _to_points(indices):
                return [(int(face_lm[i].x * w), int(face_lm[i].y * h))
                        for i in indices]

            left_eye = _to_points(self._LEFT_EYE_IDX)
            right_eye = _to_points(self._RIGHT_EYE_IDX)

            landmarks.append(FaceLandmarks(
                left_eye=left_eye,
                right_eye=right_eye,
                raw={"all_landmarks": [(int(p.x * w), int(p.y * h))
                                       for p in face_lm]},
            ))
        return landmarks


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

    if backend_name in ("mediapipe", "auto"):
        try:
            return MediaPipeBackend()
        except (Exception, SystemExit) as e:
            if backend_name == "mediapipe":
                print(f"Warning: Could not load mediapipe backend: {e}")
                return None

    if backend_name == "auto":
        print("Warning: No face detection backend available.")
        print("Face detection will be DISABLED.")
        print("Photos will be grouped, but best photo selection will be random.")

    return None
