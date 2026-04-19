"""
Centralized Configuration for DiffSense-AI

Reads settings from environment variables with sensible defaults.
Use .env file for local development (loaded via python-dotenv).

Usage:
    from backend.config import config

    SECRET_KEY = config.SECRET_KEY
    db_url = config.ADMIN_DB_URL
"""

import os
from pathlib import Path
from functools import lru_cache

# Load .env file if present
try:
    from dotenv import load_dotenv
    # Look for .env in project root (parent of backend/)
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, rely on system env vars


class Config:
    """
    Application configuration loaded from environment variables.
    All settings have sensible defaults for development.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # OFFLINE MODE SETTINGS
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def OFFLINE_MODE(self) -> bool:
        """
        When True, system assumes no internet access.
        Models must be pre-downloaded via setup_offline.py.
        """
        return os.getenv("OFFLINE_MODE", "false").lower() == "true"

    @property
    def ALLOW_MODEL_DOWNLOADS(self) -> bool:
        """
        When True, allows downloading models from HuggingFace Hub.
        Should be False in production/air-gapped environments.
        """
        return os.getenv("ALLOW_MODEL_DOWNLOADS", "false").lower() == "true"

    @property
    def MODEL_DIR(self) -> str:
        """Directory containing pre-downloaded models."""
        return os.getenv("MODEL_DIR", "./models")

    # ─────────────────────────────────────────────────────────────────────────
    # DATABASE SETTINGS (Supabase / PostgreSQL)
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def DATABASE_URL(self) -> str:
        """SQLAlchemy connection URL for PostgreSQL (Supabase)."""
        return os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres")

    @property
    def SUPABASE_URL(self) -> str:
        """Supabase project URL."""
        return os.getenv("SUPABASE_URL", "")

    @property
    def SUPABASE_ANON_KEY(self) -> str:
        """Supabase anon key for REST API."""
        return os.getenv("SUPABASE_ANON_KEY", "")

    @property
    def SUPABASE_SERVICE_KEY(self) -> str:
        """Supabase service_role key for admin REST API access."""
        return os.getenv("SUPABASE_SERVICE_KEY", "")

    @property
    def ADMIN_DB_URL(self) -> str:
        """SQLAlchemy connection URL for admin database (same as DATABASE_URL)."""
        return self.DATABASE_URL

    # ─────────────────────────────────────────────────────────────────────────
    # SECURITY SETTINGS
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def SECRET_KEY(self) -> str:
        """
        Secret key for JWT token signing.
        CRITICAL: Change this in production!
        """
        key = os.getenv("SECRET_KEY", "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET")
        if key == "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET":
            import warnings
            warnings.warn(
                "Using default SECRET_KEY! Set SECRET_KEY environment variable in production.",
                RuntimeWarning
            )
        return key

    @property
    def ALGORITHM(self) -> str:
        """JWT signing algorithm."""
        return os.getenv("JWT_ALGORITHM", "HS256")

    @property
    def ACCESS_TOKEN_EXPIRE_MINUTES(self) -> int:
        """JWT token expiration time in minutes."""
        return int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # ─────────────────────────────────────────────────────────────────────────
    # PATH SETTINGS
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def REFERENCE_DIR(self) -> str:
        """Directory for admin-uploaded reference PDFs."""
        return os.getenv("REFERENCE_DIR", "backend/data/reference_pdfs")

    @property
    def STUDENT_ROOT(self) -> str:
        """Root directory for student PDF uploads (subdirs per user)."""
        return os.getenv("STUDENT_ROOT", "backend/data/user_uploads")

    @property
    def TEACHER_ROOT(self) -> str:
        """Root directory for teacher PDF uploads (subdirs per user)."""
        return os.getenv("TEACHER_ROOT", "backend/data/teacher_uploads")

    @property
    def RESULT_ROOT(self) -> str:
        """Root directory for generated plagiarism reports."""
        return os.getenv("RESULT_ROOT", "data/result_pdfs")

    @property
    def EMBED_CACHE_DIR(self) -> str:
        """Directory for embedding cache files."""
        return os.getenv("EMBED_CACHE_DIR", "backend/data/embed_cache_offline")

    @property
    def FAISS_INDEX_DIR(self) -> str:
        """Directory for FAISS index persistence."""
        return os.getenv("FAISS_INDEX_DIR", "backend/data/faiss_indexes")

    # ─────────────────────────────────────────────────────────────────────────
    # DETECTION THRESHOLDS (Model-tuned - DO NOT change unless retraining)
    # ─────────────────────────────────────────────────────────────────────────

    # Direct copy detection
    DIRECT_SEM_SIM: float = 0.92        # Cosine threshold for near-identical
    DIRECT_WORD_OVERLAP: float = 0.75   # Word overlap threshold
    DIRECT_COMBINED_OV: float = 0.60    # Combined overlap for direct classification
    DIRECT_WORD_SEM_FLOOR: float = 0.73 # Semantic floor for word-overlap check

    # Paraphrase detection
    PARAPHRASE_SEM_SIM: float = 0.82    # Cosine threshold for paraphrase
    PARAPHRASE_HIGH_SEM: float = 0.85   # High semantic = paraphrase even with low overlap
    PARAPHRASE_WORD_FLOOR: float = 0.22 # Minimum word overlap for paraphrase
    PARAPHRASE_CONTENT_MIN: int = 3     # Minimum shared content words

    # Semantic similarity detection
    SEMANTIC_SEM_SIM: float = 0.73      # Cosine threshold for semantic match
    SEMANTIC_RELATIVE_MARGIN: float = 0.08  # Must be 8pp above doc-level mean

    # Table and image matching
    TABLE_SIM_THRESHOLD: float = 0.95
    IMAGE_DIFF_THRESHOLD: int = 1000    # MSE threshold

    # ─────────────────────────────────────────────────────────────────────────
    # PERFORMANCE SETTINGS
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def BATCH_SIZE(self) -> int:
        """Batch size for embedding generation."""
        return int(os.getenv("BATCH_SIZE", "256"))

    @property
    def MAX_WORKERS(self) -> int:
        """Maximum parallel workers for processing."""
        return int(os.getenv("MAX_WORKERS", "4"))

    @property
    def BM25_TOP_K(self) -> int:
        """Number of BM25 candidates to consider."""
        return int(os.getenv("BM25_TOP_K", "5"))

    @property
    def EMBEDDING_CACHE_SIZE(self) -> int:
        """Maximum number of embeddings to cache in memory."""
        return int(os.getenv("EMBEDDING_CACHE_SIZE", "10000"))

    # ─────────────────────────────────────────────────────────────────────────
    # CHUNKING SETTINGS
    # ─────────────────────────────────────────────────────────────────────────

    CHUNK_WORDS: int = 30       # Window width in words
    CHUNK_STEP: int = 5         # Slide step in words
    MIN_CHUNK_WORDS: int = 8    # Discard windows shorter than this

    # ─────────────────────────────────────────────────────────────────────────
    # UTILITY METHODS
    # ─────────────────────────────────────────────────────────────────────────

    def ensure_directories(self):
        """Create all required directories if they don't exist."""
        dirs = [
            self.REFERENCE_DIR,
            self.STUDENT_ROOT,
            self.TEACHER_ROOT,
            self.RESULT_ROOT,
            self.EMBED_CACHE_DIR,
            self.FAISS_INDEX_DIR,
            self.MODEL_DIR,
        ]
        for d in dirs:
            Path(d).mkdir(parents=True, exist_ok=True)

    def __repr__(self):
        return (
            f"Config(\n"
            f"  OFFLINE_MODE={self.OFFLINE_MODE},\n"
            f"  ALLOW_MODEL_DOWNLOADS={self.ALLOW_MODEL_DOWNLOADS},\n"
            f"  MODEL_DIR={self.MODEL_DIR},\n"
            f"  DATABASE_URL={'***' if self.DATABASE_URL else 'not set'},\n"
            f"  REFERENCE_DIR={self.REFERENCE_DIR},\n"
            f")"
        )


# Global singleton instance
config = Config()
