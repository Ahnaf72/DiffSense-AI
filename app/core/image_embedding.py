"""Image embedding module using CLIP for visual similarity detection.

Provides singleton loader for CLIP model and functions to encode images
into embedding vectors for similarity comparison.

Usage:
    from app.core.image_embedding import encode_image, encode_images_batch
    from app.core.image_embedding import get_clip_model

    vec = encode_image(image_path)
    vecs = encode_images_batch([path1, path2, path3])
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CLIP_MODEL = None
_CLIP_PREPROCESS = None


def get_clip_model():
    """Load CLIP model singleton (lazy loading)."""
    global _CLIP_MODEL, _CLIP_PREPROCESS
    if _CLIP_MODEL is not None:
        return _CLIP_MODEL, _CLIP_PREPROCESS

    try:
        import clip
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Loading CLIP model on device=%s", device)

        _CLIP_MODEL, _CLIP_PREPROCESS = clip.load("ViT-B/32", device=device)
        _CLIP_MODEL.eval()

        logger.info("CLIP model loaded successfully")
        return _CLIP_MODEL, _CLIP_PREPROCESS

    except ImportError:
        logger.error("CLIP not installed. Install with: pip install clip-by-openai")
        raise ImportError("CLIP library not installed")


def encode_image(image_path: Path | str) -> list[float]:
    """Encode a single image into a CLIP embedding vector.

    Args:
        image_path: Path to image file (PNG, JPEG, etc.).

    Returns:
        List of float values (512-dimensional for ViT-B/32).
    """
    from PIL import Image

    model, preprocess = get_clip_model()
    import torch

    device = next(model.parameters()).device

    image = Image.open(image_path).convert("RGB")
    image_input = preprocess(image).unsqueeze(0).to(device)

    with torch.no_grad():
        image_features = model.encode_image(image_input)

    # Normalize and convert to list
    image_features = image_features / image_features.norm(dim=-1, keepdim=True)
    return image_features.cpu().squeeze().tolist()


def encode_images_batch(
    image_paths: list[Path | str],
    *,
    batch_size: int = 32,
) -> list[list[float]]:
    """Encode multiple images into CLIP embedding vectors.

    Args:
        image_paths: List of image file paths.
        batch_size: Number of images per forward pass.

    Returns:
        List of embedding vectors, one per input image.
    """
    if not image_paths:
        return []

    model, preprocess = get_clip_model()
    import torch
    from PIL import Image

    device = next(model.parameters()).device
    all_vectors: list[list[float]] = []

    for start in range(0, len(image_paths), batch_size):
        batch_paths = image_paths[start : start + batch_size]
        batch_images = []
        for path in batch_paths:
            try:
                img = Image.open(path).convert("RGB")
                batch_images.append(preprocess(img))
            except Exception as e:
                logger.warning("Failed to load image %s: %s", path, e)
                batch_images.append(None)

        # Filter out failed loads
        valid_indices = [i for i, img in enumerate(batch_images) if img is not None]
        if not valid_indices:
            continue

        valid_images = torch.stack([batch_images[i] for i in valid_indices]).to(device)

        with torch.no_grad():
            features = model.encode_image(valid_images)

        features = features / features.norm(dim=-1, keepdim=True)
        vectors = features.cpu().tolist()

        # Map back to original order
        for i, idx in enumerate(valid_indices):
            all_vectors.append(vectors[i])

    logger.info("Encoded %d images in %d batches", len(image_paths), -(-len(image_paths) // batch_size))
    return all_vectors


def compute_image_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two image embedding vectors.

    CLIP embeddings are already normalized, so similarity is just dot product.

    Args:
        vec_a: First embedding vector.
        vec_b: Second embedding vector.

    Returns:
        Cosine similarity in [-1, 1].
    """
    import numpy as np

    a = np.asarray(vec_a, dtype=np.float32)
    b = np.asarray(vec_b, dtype=np.float32)
    return float(np.dot(a, b))


def unload_clip_model() -> None:
    """Explicitly unload CLIP model to free memory."""
    global _CLIP_MODEL, _CLIP_PREPROCESS
    if _CLIP_MODEL is not None:
        import torch
        del _CLIP_MODEL
        del _CLIP_PREPROCESS
        _CLIP_MODEL = None
        _CLIP_PREPROCESS = None
        torch.cuda.empty_cache()
        logger.info("CLIP model unloaded")
