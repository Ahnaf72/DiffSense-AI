# =============================================================================
# DiffSense-AI Dockerfile
# Multi-stage build for minimal image size with CPU-only PyTorch
# =============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY aidiffchecker/backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    tesseract-ocr \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application code
COPY aidiffchecker/ /app/aidiffchecker/
COPY setup_offline.py /app/

# Models will be downloaded at startup if ALLOW_MODEL_DOWNLOADS=true
# For production, pre-bake models into the image by uncommenting:
# COPY models/ /app/models/

# Create required directories (including models dir for runtime download)
RUN mkdir -p \
    /app/data/result_pdfs \
    /app/models \
    /app/aidiffchecker/backend/data/reference_pdfs \
    /app/aidiffchecker/backend/data/user_uploads \
    /app/aidiffchecker/backend/data/teacher_uploads \
    /app/aidiffchecker/backend/data/embed_cache_offline \
    /app/aidiffchecker/backend/data/faiss_indexes

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MODEL_DIR=/app/models \
    OFFLINE_MODE=false \
    ALLOW_MODEL_DOWNLOADS=true

# Expose API port (Railway sets PORT env var automatically)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/system/health || exit 1

# Run the application (Railway provides PORT env var)
CMD ["sh", "-c", "uvicorn aidiffchecker.backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
