"""
Model Manager: Centralized offline-first model loading with graceful degradation.

Handles loading of:
- FastEmbed (BAAI/bge-small-en-v1.5) for nlp_utils.py
- SentenceTransformer (all-MiniLM-L6-v2) for engine.py

Loading priority:
1. Local ./models/ directory (air-gap deployment)
2. HuggingFace cache (~/.cache/)
3. Download from HF Hub (only if ALLOW_MODEL_DOWNLOADS=true)

Returns None if model unavailable → enables BM25-only degraded mode.
"""

import os
import logging
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ModelManager:
    """Thread-safe singleton for managing embedding models."""

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # State tracking
        self._fastembed_model = None
        self._sentence_transformer_model = None
        self._fastembed_attempted = False
        self._st_attempted = False

        # Configuration (loaded from config.py which reads .env)
        from backend.config import config
        self._model_dir = config.MODEL_DIR
        self._offline_mode = config.OFFLINE_MODE
        self._allow_downloads = config.ALLOW_MODEL_DOWNLOADS

        self._initialized = True
        logger.info(f"ModelManager initialized - OFFLINE_MODE={self._offline_mode}, ALLOW_DOWNLOADS={self._allow_downloads}")

    async def get_embedding_model(self):
        """
        Get FastEmbed model for BAAI/bge-small-en-v1.5.
        Returns TextEmbedding instance or None if unavailable.
        Thread-safe with async lock.
        """
        async with self._lock:
            if self._fastembed_model is not None:
                return self._fastembed_model

            if self._fastembed_attempted:
                return None

            self._fastembed_attempted = True

            try:
                from fastembed import TextEmbedding
            except ImportError:
                logger.error("fastembed library not installed - cannot load embedding model")
                return None

            model_name = "BAAI/bge-small-en-v1.5"
            local_path = Path(self._model_dir) / "embeddings" / "BAAI-bge-small-en-v1.5"

            # Priority 1: Local models directory
            if local_path.exists() and self._verify_model_integrity(local_path, model_name):
                try:
                    logger.info(f"Loading {model_name} from local path: {local_path}")
                    self._fastembed_model = TextEmbedding(
                        model_name=str(local_path),
                        max_length=128,
                    )
                    logger.info(f"✓ {model_name} loaded successfully from local directory")
                    return self._fastembed_model
                except Exception as e:
                    logger.warning(f"Failed to load from local path: {e}")

            # Priority 2: HuggingFace cache (check if already downloaded)
            hf_cache = Path.home() / ".cache" / "fastembed"
            if hf_cache.exists():
                try:
                    logger.info(f"Attempting to load {model_name} from HF cache")
                    self._fastembed_model = TextEmbedding(
                        model_name=model_name,
                        max_length=128,
                    )
                    logger.info(f"✓ {model_name} loaded from HuggingFace cache")
                    return self._fastembed_model
                except Exception as e:
                    logger.warning(f"Failed to load from HF cache: {e}")

            # Priority 3: Download (only if allowed)
            if self._allow_downloads and not self._offline_mode:
                try:
                    logger.info(f"Downloading {model_name} from HuggingFace Hub...")
                    self._fastembed_model = TextEmbedding(
                        model_name=model_name,
                        max_length=128,
                    )
                    logger.info(f"✓ {model_name} downloaded and loaded successfully")
                    return self._fastembed_model
                except Exception as e:
                    logger.error(f"Failed to download model: {e}")
            else:
                logger.warning(f"Model download disabled (OFFLINE_MODE={self._offline_mode}, ALLOW_DOWNLOADS={self._allow_downloads})")

            logger.error(f"✗ {model_name} unavailable - system will run in degraded mode")
            return None

    async def get_sentence_transformer_model(self):
        """
        Get SentenceTransformer model for all-MiniLM-L6-v2.
        Returns SentenceTransformer instance or None if unavailable.
        Thread-safe with async lock.
        """
        async with self._lock:
            if self._sentence_transformer_model is not None:
                return self._sentence_transformer_model

            if self._st_attempted:
                return None

            self._st_attempted = True

            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                logger.error("sentence-transformers library not installed - cannot load model")
                return None

            model_name = "all-MiniLM-L6-v2"
            local_path = Path(self._model_dir) / "sentence_transformers" / model_name

            # Priority 1: Local models directory
            if local_path.exists() and self._verify_model_integrity(local_path, model_name):
                try:
                    logger.info(f"Loading {model_name} from local path: {local_path}")
                    self._sentence_transformer_model = SentenceTransformer(str(local_path))
                    logger.info(f"✓ {model_name} loaded successfully from local directory")
                    return self._sentence_transformer_model
                except Exception as e:
                    logger.warning(f"Failed to load from local path: {e}")

            # Priority 2: HuggingFace cache
            hf_cache = Path.home() / ".cache" / "torch" / "sentence_transformers"
            if hf_cache.exists():
                try:
                    logger.info(f"Attempting to load {model_name} from HF cache")
                    self._sentence_transformer_model = SentenceTransformer(model_name)
                    logger.info(f"✓ {model_name} loaded from HuggingFace cache")
                    return self._sentence_transformer_model
                except Exception as e:
                    logger.warning(f"Failed to load from HF cache: {e}")

            # Priority 3: Download (only if allowed)
            if self._allow_downloads and not self._offline_mode:
                try:
                    logger.info(f"Downloading {model_name} from HuggingFace Hub...")
                    self._sentence_transformer_model = SentenceTransformer(model_name)
                    logger.info(f"✓ {model_name} downloaded and loaded successfully")
                    return self._sentence_transformer_model
                except Exception as e:
                    logger.error(f"Failed to download model: {e}")
            else:
                logger.warning(f"Model download disabled (OFFLINE_MODE={self._offline_mode}, ALLOW_DOWNLOADS={self._allow_downloads})")

            logger.error(f"✗ {model_name} unavailable - system will run in degraded mode")
            return None

    def is_fully_offline_ready(self) -> bool:
        """
        Check if at least one model is loaded and ready.
        Returns True if EITHER FastEmbed or SentenceTransformer is available.
        """
        return (self._fastembed_model is not None or
                self._sentence_transformer_model is not None)

    def get_missing_models(self) -> list[str]:
        """
        Return list of model names that are missing/unavailable.
        Used by /api/system/status endpoint.
        """
        missing = []

        if self._fastembed_attempted and self._fastembed_model is None:
            missing.append("BAAI/bge-small-en-v1.5")

        if self._st_attempted and self._sentence_transformer_model is None:
            missing.append("all-MiniLM-L6-v2")

        return missing

    def _verify_model_integrity(self, model_path: Path, model_name: str) -> bool:
        """
        Verify model integrity using SHA256 checksums from .model_registry.json.
        If registry doesn't exist, skip verification (trust local models).

        Returns True if:
        - Registry doesn't exist (trust mode)
        - Model not in registry (trust mode)
        - Checksum matches

        Returns False only if checksum explicitly mismatches.
        """
        registry_path = Path(self._model_dir) / ".model_registry.json"

        if not registry_path.exists():
            logger.debug(f"No model registry found at {registry_path} - skipping verification")
            return True

        try:
            with open(registry_path, 'r') as f:
                registry = json.load(f)

            if model_name not in registry:
                logger.debug(f"{model_name} not in registry - skipping verification")
                return True

            expected_hash = registry[model_name].get("sha256")
            if not expected_hash:
                logger.debug(f"No checksum for {model_name} - skipping verification")
                return True

            # Compute SHA256 of all files in model directory
            sha256 = hashlib.sha256()
            for file_path in sorted(model_path.rglob("*")):
                if file_path.is_file():
                    sha256.update(file_path.read_bytes())

            computed_hash = sha256.hexdigest()

            if computed_hash != expected_hash:
                logger.error(f"✗ SHA256 mismatch for {model_name}!")
                logger.error(f"  Expected: {expected_hash}")
                logger.error(f"  Got:      {computed_hash}")
                logger.error(f"  Model may be corrupted or tampered with!")
                return False

            logger.info(f"✓ SHA256 verification passed for {model_name}")
            return True

        except Exception as e:
            logger.warning(f"Failed to verify model integrity: {e}")
            return True  # Don't block loading on verification errors

    def get_model_status(self) -> dict:
        """
        Return detailed status of all models for debugging/monitoring.
        """
        return {
            "fastembed": {
                "loaded": self._fastembed_model is not None,
                "attempted": self._fastembed_attempted,
                "name": "BAAI/bge-small-en-v1.5",
            },
            "sentence_transformer": {
                "loaded": self._sentence_transformer_model is not None,
                "attempted": self._st_attempted,
                "name": "all-MiniLM-L6-v2",
            },
            "offline_mode": self._offline_mode,
            "allow_downloads": self._allow_downloads,
            "model_dir": self._model_dir,
            "fully_ready": self.is_fully_offline_ready(),
            "missing_models": self.get_missing_models(),
        }


# Global singleton instance
model_manager = ModelManager()
