"""
GPU-capable face detection backends.

This package contains implementations of FaceBackend that support GPU acceleration
via CUDA (NVIDIA) or MPS (Apple Silicon).

Available backends:
- InsightFaceBackend: RetinaFace detection + ArcFace 512-d encoding (CUDA via ONNX)
- FacenetBackend: MTCNN detection + InceptionResnetV1 128-d encoding (CUDA/MPS)
- YOLOv8FaceBackend: Fast YOLOv8 detection, no encoding (CUDA/MPS)
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from face_backend import FaceBackend

# Lazy imports to avoid requiring all dependencies at once
_insightface_backend: Optional["FaceBackend"] = None
_facenet_backend: Optional["FaceBackend"] = None
_yolov8_backend: Optional["FaceBackend"] = None


def get_insightface_backend(gpu: bool = False, gpu_device: int = 0) -> Optional["FaceBackend"]:
    """Get InsightFace backend instance.

    Args:
        gpu: Enable GPU acceleration via CUDA
        gpu_device: CUDA device index (0 = first GPU)

    Returns:
        InsightFaceBackend instance or None if not available
    """
    try:
        from backends.insightface_backend import InsightFaceBackend
        return InsightFaceBackend(gpu=gpu, gpu_device=gpu_device)
    except ImportError as e:
        return None
    except Exception as e:
        print(f"Warning: Could not load InsightFace backend: {e}")
        return None


def get_facenet_backend(gpu: bool = False, gpu_device: int = 0) -> Optional["FaceBackend"]:
    """Get FaceNet/PyTorch backend instance.

    Args:
        gpu: Enable GPU acceleration via CUDA or MPS
        gpu_device: CUDA device index (0 = first GPU, ignored for MPS)

    Returns:
        FacenetBackend instance or None if not available
    """
    try:
        from backends.facenet_backend import FacenetBackend
        return FacenetBackend(gpu=gpu, gpu_device=gpu_device)
    except ImportError as e:
        return None
    except Exception as e:
        print(f"Warning: Could not load FaceNet backend: {e}")
        return None


def get_yolov8_backend(gpu: bool = False, gpu_device: int = 0) -> Optional["FaceBackend"]:
    """Get YOLOv8-Face backend instance.

    Args:
        gpu: Enable GPU acceleration via CUDA or MPS
        gpu_device: CUDA device index (0 = first GPU, ignored for MPS)

    Returns:
        YOLOv8FaceBackend instance or None if not available
    """
    try:
        from backends.yolov8_backend import YOLOv8FaceBackend
        return YOLOv8FaceBackend(gpu=gpu, gpu_device=gpu_device)
    except ImportError as e:
        return None
    except Exception as e:
        print(f"Warning: Could not load YOLOv8 backend: {e}")
        return None


def get_quality_scorer(device: str = 'cpu', prefer_clip: bool = True):
    """Get ML Quality Scorer instance if available.

    Args:
        device: PyTorch device ('cpu', 'cuda:0', 'mps')
        prefer_clip: Try CLIP first, fall back to MobileNetV2

    Returns:
        MLQualityScorer instance or None if not available
    """
    try:
        from backends.ml_quality_scorer import MLQualityScorer
        return MLQualityScorer(device=device, prefer_clip=prefer_clip)
    except ImportError:
        return None
    except Exception as e:
        print(f"Warning: Could not initialize ML quality scorer: {e}")
        return None


__all__ = [
    'get_insightface_backend',
    'get_facenet_backend',
    'get_yolov8_backend',
    'get_quality_scorer',
]
