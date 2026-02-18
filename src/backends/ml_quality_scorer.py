"""
ML-based image quality scoring for aesthetic photo selection.

Uses CLIP (primary) or MobileNetV2 (fallback) to score images on
aesthetic quality metrics like sharpness, composition, and exposure.
Complements face-based scoring for best-photo selection.

Install:
    pip install transformers torch  # CLIP via HuggingFace
    # or lightweight fallback:
    pip install torch torchvision   # MobileNetV2 (built into torchvision)
"""

import sys
from pathlib import Path
from typing import Optional, List, Tuple, TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import torch
    from PIL import Image as PILImage

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class MLQualityScorer:
    """ML-based aesthetic quality scorer for images.

    Uses CLIP embeddings with aesthetic prompts to score image quality,
    or falls back to MobileNetV2-based scoring if CLIP unavailable.

    The score represents aesthetic quality on a 0.0-1.0 scale:
    - 0.0-0.3: Poor quality (blurry, bad exposure, poor composition)
    - 0.3-0.6: Average quality
    - 0.6-0.8: Good quality
    - 0.8-1.0: Excellent quality (sharp, well-exposed, good composition)

    Attributes:
        device: PyTorch device being used
        model_type: 'clip' or 'mobilenet'
    """

    # CLIP prompts for aesthetic quality assessment
    _POSITIVE_PROMPTS = [
        "a high quality photo",
        "a professional photograph",
        "a sharp, well-focused image",
        "a beautifully composed photo",
        "excellent lighting and exposure",
        "a stunning photograph",
    ]

    _NEGATIVE_PROMPTS = [
        "a low quality photo",
        "a blurry image",
        "poor lighting",
        "overexposed photo",
        "underexposed photo",
        "badly composed image",
        "out of focus",
    ]

    def __init__(self, device: str = 'cpu', prefer_clip: bool = True):
        """Initialize ML Quality Scorer.

        Args:
            device: PyTorch device ('cpu', 'cuda:0', 'mps')
            prefer_clip: Try CLIP first, fall back to MobileNetV2
        """
        self._device = device
        self._model = None
        self._processor = None
        self._model_type = None
        self._torch = None

        # Try to initialize CLIP or MobileNetV2
        if prefer_clip:
            if self._init_clip():
                self._model_type = 'clip'
            elif self._init_mobilenet():
                self._model_type = 'mobilenet'
        else:
            if self._init_mobilenet():
                self._model_type = 'mobilenet'
            elif self._init_clip():
                self._model_type = 'clip'

        if self._model_type is None:
            raise ImportError(
                "No ML backend available. Install with:\n"
                "  pip install transformers torch  # For CLIP\n"
                "  # or:\n"
                "  pip install torch torchvision  # For MobileNetV2"
            )

    def _init_clip(self) -> bool:
        """Try to initialize CLIP model."""
        try:
            import torch
            from transformers import CLIPProcessor, CLIPModel

            self._torch = torch

            # Load CLIP model and processor
            model_name = "openai/clip-vit-base-patch32"
            self._processor = CLIPProcessor.from_pretrained(model_name)
            self._model = CLIPModel.from_pretrained(model_name)
            self._model.eval()
            self._model.to(self._device)

            # Pre-compute text embeddings for prompts
            self._positive_embeds = self._encode_texts(self._POSITIVE_PROMPTS)
            self._negative_embeds = self._encode_texts(self._NEGATIVE_PROMPTS)

            return True
        except Exception as e:
            return False

    def _init_mobilenet(self) -> bool:
        """Try to initialize MobileNetV2 model."""
        try:
            import torch
            from torchvision import models, transforms

            self._torch = torch

            # Load pre-trained MobileNetV2
            self._model = models.mobilenet_v2(pretrained=True)
            self._model.eval()
            self._model.to(self._device)

            # MobileNetV2 preprocessing
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
        except Exception as e:
            return False

    def _encode_texts(self, texts: List[str]) -> Any:
        """Encode text prompts using CLIP."""
        inputs = self._processor(
            text=texts,
            return_tensors="pt",
            padding=True
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with self._torch.no_grad():
            text_embeds = self._model.get_text_features(**inputs)
            text_embeds = text_embeds / text_embeds.norm(dim=-1, keepdim=True)

        return text_embeds

    @property
    def device(self) -> str:
        """Return current device string."""
        return self._device

    @property
    def model_type(self) -> str:
        """Return model type ('clip' or 'mobilenet')."""
        return self._model_type

    def score(self, image_path: str) -> float:
        """Score an image's aesthetic quality.

        Args:
            image_path: Path to the image file

        Returns:
            Quality score from 0.0 (poor) to 1.0 (excellent)
        """
        from PIL import Image

        image = Image.open(image_path).convert("RGB")

        if self._model_type == 'clip':
            return self._score_clip(image)
        else:
            return self._score_mobilenet(image)

    def score_array(self, image: np.ndarray) -> float:
        """Score an image from numpy array.

        Args:
            image: RGB numpy array (H, W, 3)

        Returns:
            Quality score from 0.0 (poor) to 1.0 (excellent)
        """
        from PIL import Image

        pil_image = Image.fromarray(image)

        if self._model_type == 'clip':
            return self._score_clip(pil_image)
        else:
            return self._score_mobilenet(pil_image)

    def _score_clip(self, image: Any) -> float:
        """Score image using CLIP aesthetic prompts."""
        # Encode image
        inputs = self._processor(
            images=image,
            return_tensors="pt"
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with self._torch.no_grad():
            image_embeds = self._model.get_image_features(**inputs)
            image_embeds = image_embeds / image_embeds.norm(dim=-1, keepdim=True)

        # Compute similarity to positive and negative prompts
        pos_sim = (image_embeds @ self._positive_embeds.T).mean().item()
        neg_sim = (image_embeds @ self._negative_embeds.T).mean().item()

        # Convert to 0-1 score
        # Higher similarity to positive prompts = higher score
        # Score = sigmoid((pos_sim - neg_sim) * scale)
        diff = pos_sim - neg_sim
        score = 1.0 / (1.0 + np.exp(-diff * 5.0))  # Scale factor 5.0

        return float(np.clip(score, 0.0, 1.0))

    def _score_mobilenet(self, image: Any) -> float:
        """Score image using MobileNetV2 feature analysis.

        Uses activation statistics as a proxy for image quality.
        Well-exposed, sharp images tend to have higher activation variance.
        """
        # Transform image
        tensor = self._transform(image).unsqueeze(0).to(self._device)

        # Extract features (skip final classifier)
        with self._torch.no_grad():
            # Use features from the last conv layer
            features = self._model.features(tensor)

        # Compute quality metrics from activations
        # Higher mean activation and variance indicate better image quality
        mean_act = features.mean().item()
        std_act = features.std().item()

        # Normalize to 0-1 range (based on empirical observations)
        # Good images typically have mean_act in [0.5, 2.0] and std_act in [0.5, 1.5]
        mean_score = np.clip((mean_act - 0.2) / 1.5, 0.0, 1.0)
        std_score = np.clip((std_act - 0.2) / 1.0, 0.0, 1.0)

        # Combined score (weighted average)
        score = 0.4 * mean_score + 0.6 * std_score

        return float(np.clip(score, 0.0, 1.0))

    def score_batch(self, image_paths: List[str]) -> List[float]:
        """Score multiple images in a batch (GPU-optimized).

        Args:
            image_paths: List of paths to image files

        Returns:
            List of quality scores, one per image
        """
        from PIL import Image

        if self._model_type == 'clip':
            return self._score_batch_clip(image_paths)
        else:
            return self._score_batch_mobilenet(image_paths)

    def _score_batch_clip(self, image_paths: List[str]) -> List[float]:
        """Batch score images using CLIP."""
        from PIL import Image

        images = [Image.open(p).convert("RGB") for p in image_paths]

        inputs = self._processor(
            images=images,
            return_tensors="pt",
            padding=True
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with self._torch.no_grad():
            image_embeds = self._model.get_image_features(**inputs)
            image_embeds = image_embeds / image_embeds.norm(dim=-1, keepdim=True)

        scores = []
        for emb in image_embeds:
            emb = emb.unsqueeze(0)
            pos_sim = (emb @ self._positive_embeds.T).mean().item()
            neg_sim = (emb @ self._negative_embeds.T).mean().item()
            diff = pos_sim - neg_sim
            score = 1.0 / (1.0 + np.exp(-diff * 5.0))
            scores.append(float(np.clip(score, 0.0, 1.0)))

        return scores

    def _score_batch_mobilenet(self, image_paths: List[str]) -> List[float]:
        """Batch score images using MobileNetV2."""
        from PIL import Image

        tensors = []
        for path in image_paths:
            image = Image.open(path).convert("RGB")
            tensors.append(self._transform(image))

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
            score = 0.4 * mean_score + 0.6 * std_score
            scores.append(float(np.clip(score, 0.0, 1.0)))

        return scores


def get_quality_scorer(
    device: str = 'cpu',
    prefer_clip: bool = True
) -> Optional[MLQualityScorer]:
    """Get ML Quality Scorer instance if available.

    Args:
        device: PyTorch device ('cpu', 'cuda:0', 'mps')
        prefer_clip: Try CLIP first, fall back to MobileNetV2

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
