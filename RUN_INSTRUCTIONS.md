# DiffSense-AI - Run Instructions

## Prerequisites

### System Requirements
- Python 3.14+
- PostgreSQL 15+ with pgvector extension
- Redis 7+ (for Celery queue)
- 8GB RAM minimum (16GB recommended for embedding model)
- 10GB disk space (for models and uploads)

### External Services
- Supabase project (PostgreSQL + pgvector)
- Redis server (local or cloud)
- Hugging Face (for model download - one-time setup)

## Installation

### 1. Clone Repository
```bash
cd d:\DiffSense-AI\DiffSense-AI
```

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create `.env` file in project root:
```bash
# App
APP_NAME=DiffSense-AI
APP_ENV=development
DEBUG=true
LOG_LEVEL=INFO

# Server
HOST=0.0.0.0
PORT=8000

# Supabase
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

# Auth
SECRET_KEY=your_secret_key_here_change_in_production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Storage
UPLOAD_DIR=uploads

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Scoring Weights (optional, defaults: 0.6, 0.3, 0.1)
SCORING_WEIGHT_PLAGIARISM=0.6
SCORING_WEIGHT_PARAPHRASE=0.3
SCORING_WEIGHT_SEMANTIC=0.1
```

### 4. Setup Database

#### Create Supabase Project
1. Go to https://supabase.com
2. Create new project
3. Enable pgvector extension in SQL editor:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

#### Run Migrations
Use the Supabase MCP server to apply migrations:
- `match_chunks` function
- `match_chunks_batch` function
- `set_chunk_embedding` function
- `idx_chunks_embedding` (HNSW index)
- `score_breakdown` column on reports table

Or run via Supabase SQL editor with the SQL from migration files.

### 5. Start Services

#### Start Redis
```bash
redis-server
```

#### Start Celery Worker
```bash
celery -A app.core.worker worker --loglevel=info
```

#### Start FastAPI Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Running the Integration Test

```bash
python integration_test.py
```

This tests:
- Pipeline modules (chunking, embeddings, scoring)
- Scoring system (weights, computation)
- Color coding logic

## Running Unit Tests

```bash
python -m pytest tests/ -v --tb=short
```

## Offline Operation

### Initial Setup (Requires Internet)
1. First run downloads embedding model from Hugging Face
2. Model is cached locally in `~/.cache/huggingface/`

### Offline Operation
After initial model download, the system works fully offline:
- No external API calls for embeddings
- All processing happens locally
- Only database connection required (Supabase)

### Verify Offline Mode
```bash
# Disconnect internet
# Run integration test - should pass without network
python integration_test.py
```

## Development Workflow

### 1. Upload Document
```bash
POST /api/v1/documents/upload
Content-Type: multipart/form-data
title: "My Document"
file: document.pdf
```

### 2. Process Document (Automatic)
- Celery task extracts text, chunks, generates embeddings
- Check status via GET /api/v1/documents/{id}

### 3. Analyze Document
```bash
POST /api/v1/documents/{id}/analyze
```

### 4. Get Report
```bash
GET /api/v1/reports/{report_id}/detailed
```

## Admin Corpus Management

### Upload Reference PDF
```bash
POST /api/v1/references/upload
Content-Type: multipart/form-data
title: "Reference Paper"
file: reference.pdf
```

### Precompute Embeddings
```bash
POST /api/v1/references/{ref_id}/embed
```

### List References
```bash
GET /api/v1/references?active_only=true
```

### Delete Reference
```bash
DELETE /api/v1/references/{ref_id}
```

## Troubleshooting

### Model Download Fails
- Check internet connection
- Verify Hugging Face is accessible
- Manually download model: `sentence-transformers/all-MiniLM-L6-v2`

### Celery Worker Not Starting
- Verify Redis is running: `redis-cli ping`
- Check Celery broker URL in .env
- Check for port conflicts

### Database Connection Errors
- Verify Supabase URL and keys in .env
- Check pgvector extension is installed
- Verify migrations are applied

### Embedding Model Memory Error
- Reduce batch size in pipeline.py
- Close other applications
- Increase system RAM

## Production Deployment

### Security Checklist
- [ ] Change SECRET_KEY in production
- [ ] Set DEBUG=false
- [ ] Use HTTPS
- [ ] Restrict Celery broker access
- [ ] Enable rate limiting
- [ ] Set up monitoring (Sentry, etc.)
- [ ] Configure backup strategy

### Scaling
- Run multiple Celery workers: `celery -A app.core.worker worker --concurrency=4`
- Use managed Redis (e.g., Redis Cloud)
- Use managed PostgreSQL (Supabase)
- Load balance API servers

### Monitoring
- Check Celery logs for task failures
- Monitor database connection pool
- Track embedding model memory usage
- Set up alerts for high error rates
