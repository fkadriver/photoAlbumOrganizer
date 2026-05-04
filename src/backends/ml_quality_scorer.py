"""
ML-based image quality scoring for aesthetic photo selection.

Uses pyiqa TOPIQ-IAA (primary) or MobileNetV2 (fallback) to score images on
aesthetic quality. Complements face-based scoring for best-photo selection.

Install:
    pip install pyiqa torch  # TOPIQ-IAA via pyiqa
    # or lightweight fallback:
    pip install torch torchvision   # MobileNetV2 (built into torchvision)
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import torch
    from PIL import Image as PILImage

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class MLQualityScorer:
    """ML-based aesthetic quality scorer for images.

    Uses pyiqa TOPIQ-IAA to score image quality, or falls back to
    MobileNetV2-based scoring if pyiqa is unavailable.

    Score range 0.0–1.0:
    - 0.0–0.3: Poor quality (blurry, bad exposure, poor composition)
    - 0.3–0.6: Average quality
    - 0.6–0.8: Good quality
    - 0.8–1.0: Excellent quality (sharp, well-exposed, good composition)

    Attributes:
        device: PyTorch device being used
        model_type: 'topiq' or 'mobilenet'
    """

    def __init__(self, device: str = 'cpu', prefer_clip: bool = True):
        """Initialize ML Quality Scorer.

        Args:
            device: PyTorch device ('cpu', 'cuda:0', 'mps')
            prefer_clip: Ignored; kept for API compatibility.
        """
        self._device = device
        self._model = None
        self._model_type = None
        self._torch = None

        if self._init_topiq():
            self._model_type = 'topiq'
        elif self._init_mobilenet():
            self._model_type = 'mobilenet'

        if self._model_type is None:
            raise ImportError(
                "No ML backend available. Install with:\n"
                "  pip install pyiqa torch  # For TOPIQ-IAA\n"
                "  # or:\n"
                "  pip install torch torchvision  # For MobileNetV2"
            )

    def _init_topiq(self) -> bool:
        """Try to initialize TOPIQ-IAA via pyiqa."""
        try:
            import pyiqa
            import torch
            self._torch = torch
            self._model = pyiqa.create_metric('topiq_iaa', device=self._device, as_loss=False)
            return True
        except Exception:
            return False

    def _init_mobilenet(self) -> bool:
        """Try to initialize MobileNetV2 fallback model."""
        try:
            import torch
            from torchvision import models, transforms

            self._torch = torch
            self._model = models.mobilenet_v2(
                weights=models.MobileNet_V2_Weights.IMAGENET1K_V1
            )
            self._model.eval()
            self._model.to(self._device)

            self._transform = transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225]
                ),
            ])
            return True
        except Exception:
            return False

    @property
    def device(self) -> str:
        """Return current device string."""
        return self._device

    @property
    def model_type(self) -> str:
        """Return model type ('topiq' or 'mobilenet')."""
        return self._model_type

    def score(self, image_path: str) -> float:
        """Score an image's aesthetic quality.

        Args:
            image_path: Path to the image file

        Returns:
            Quality score from 0.0 (poor) to 1.0 (excellent)
        """
        if self._model_type == 'topiq':
            return self._score_topiq(image_path)
        else:
            from PIL import Image
            return self._score_mobilenet(Image.open(image_path).convert("RGB"))

    def score_array(self, image: np.ndarray) -> float:
        """Score an image from numpy array.

        Args:
            image: RGB numpy array (H, W, 3)

        Returns:
            Quality score from 0.0 (poor) to 1.0 (excellent)
        """
        from PIL import Image

        if self._model_type == 'topiq':
            pil_image = Image.fromarray(image)
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp_path = tmp.name
            try:
                pil_image.save(tmp_path)
                return self._score_topiq(tmp_path)
            finally:
                os.unlink(tmp_path)
        else:
            return self._score_mobilenet(Image.fromarray(image))

    def _score_topiq(self, image_path: str) -> float:
        """Score image using TOPIQ-IAA via pyiqa."""
        with self._torch.no_grad():
            score = self._model(image_path)
        return float(np.clip(score.item(), 0.0, 1.0))

    def _score_mobilenet(self, image: Any) -> float:
        """Score image using MobileNetV2 feature analysis.

        Uses activation statistics as a proxy for image quality.
        Well-exposed, sharp images tend to have higher activation variance.
        """
        tensor = self._transform(image).unsqueeze(0).to(self._device)
        with self._torch.no_grad():
            features = self._model.features(tensor)

        mean_act = features.mean().item()
        std_act = features.std().item()
        mean_score = np.clip((mean_act - 0.2) / 1.5, 0.0, 1.0)
        std_score = np.clip((std_act - 0.2) / 1.0, 0.0, 1.0)
        return float(np.clip(0.4 * mean_score + 0.6 * std_score, 0.0, 1.0))

    def score_batch(self, image_paths: List[str]) -> List[float]:
        """Score multiple images in a batch (GPU-optimized).

        Args:
            image_paths: List of paths to image files

        Returns:
            List of quality scores, one per image
        """
        if self._model_type == 'topiq':
            return self._score_batch_topiq(image_paths)
        else:
            return self._score_batch_mobilenet(image_paths)

    def _score_batch_topiq(self, image_paths: List[str]) -> List[float]:
        """Score images using TOPIQ-IAA; GPU stays warm across calls."""
        scores = []
        with self._torch.no_grad():
            for path in image_paths:
                score = self._model(path)
                scores.append(float(np.clip(score.item(), 0.0, 1.0)))
        return scores

    def _score_batch_mobilenet(self, image_paths: List[str]) -> List[float]:
        """Batch score images using MobileNetV2."""
        from PIL import Image

        tensors = [
            self._transform(Image.open(p).convert("RGB"))
            for p in image_paths
        ]
        batch = self._torch.stack(tensors).to(self._device)

        with self._torch.no_grad():
            features = self._model.features(batch)

        scores = []
        for i in range(features.shape[0]):
            feat = features[i]
            mean_act = feat.mean().item()
            std_act = feat.std().item()
            mean_score = np.clip((mean_act - 0.2) / 1.5, 0.0, 1.0)
            std_score = np.clip((std_act - 0.2) / 1.0, 0.0, 1.0)
            scores.append(float(np.clip(0.4 * mean_score + 0.6 * std_score, 0.0, 1.0)))

        return scores


def get_quality_scorer(
    device: str = 'cpu',
    prefer_clip: bool = True
) -> Optional[MLQualityScorer]:
    """Get ML Quality Scorer instance if available.

    Args:
        device: PyTorch device ('cpu', 'cuda:0', 'mps')
        prefer_clip: Ignored; kept for API compatibility.

    Returns:
        MLQualityScorer instance or None if not available
    """
    try:
        return MLQualityScorer(device=device, prefer_clip=prefer_clip)
    except ImportError:
        return None
    except Exception as e:
        print(f"Warning: Could not initialize ML quality scorer: {e}")
        return None
