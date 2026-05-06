"""OpenCLIP ViT-B-32 wrapper — lazy-loaded singleton for image/text encoding."""

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_encoder = None  # module-level singleton


class CLIPEncoder:
    """Wraps OpenCLIP ViT-B-32 (laion2b_s34b_b79k) for 512-d embeddings."""

    EMBEDDING_DIM = 512

    def __init__(self):
        self.model = None
        self.preprocess = None
        self.tokenizer = None
        self.device = "cpu"
        self._loaded = False

    def load(self) -> None:
        """Load model on first use — keeps ~350 MB in RAM."""
        if self._loaded:
            return
        import torch
        import open_clip

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Loading OpenCLIP ViT-B-32 on %s …", self.device)

        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        self.model = self.model.to(self.device).eval()
        self.tokenizer = open_clip.get_tokenizer("ViT-B-32")
        self._loaded = True
        logger.info("OpenCLIP model loaded (%s)", self.device)

    # ------------------------------------------------------------------
    def encode_image(self, image_path: Path) -> np.ndarray:
        """Encode a single image → normalized 512-d float32 vector."""
        import torch
        from PIL import Image as PILImage

        self.load()
        img = PILImage.open(image_path).convert("RGB")
        tensor = self.preprocess(img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            features = self.model.encode_image(tensor)
            features /= features.norm(dim=-1, keepdim=True)

        return features.cpu().numpy().flatten().astype(np.float32)

    # ------------------------------------------------------------------
    def encode_text(self, text: str) -> np.ndarray:
        """Encode a query string → normalized 512-d float32 vector."""
        import torch

        self.load()
        tokens = self.tokenizer([text]).to(self.device)

        with torch.no_grad():
            features = self.model.encode_text(tokens)
            features /= features.norm(dim=-1, keepdim=True)

        return features.cpu().numpy().flatten().astype(np.float32)

    # ------------------------------------------------------------------
    def encode_images_batch(
        self, image_paths: list[Path], batch_size: int = 16
    ) -> list[np.ndarray]:
        """Batch-encode images for throughput. Returns list of 512-d vectors."""
        import torch
        from PIL import Image as PILImage

        self.load()
        all_features: list[np.ndarray] = []

        for i in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[i : i + batch_size]
            tensors = []
            for p in batch_paths:
                try:
                    img = PILImage.open(p).convert("RGB")
                    tensors.append(self.preprocess(img))
                except Exception as e:
                    logger.error("Skip %s: %s", p, e)
                    tensors.append(self.preprocess(PILImage.new("RGB", (224, 224))))

            batch = torch.stack(tensors).to(self.device)
            with torch.no_grad():
                feats = self.model.encode_image(batch)
                feats /= feats.norm(dim=-1, keepdim=True)

            all_features.extend(feats.cpu().numpy().astype(np.float32))

        return all_features


def get_clip_encoder() -> CLIPEncoder:
    """Return the module-level singleton, creating it on first call."""
    global _encoder
    if _encoder is None:
        _encoder = CLIPEncoder()
    return _encoder
