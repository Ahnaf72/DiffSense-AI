# DiffSense-AI Offline Deployment Guide

Complete guide for deploying DiffSense-AI in offline, air-gapped, or restricted network environments.

---

## Table of Contents

1. [Quick Start (Standard Deployment)](#quick-start-standard-deployment)
2. [Air-Gap Deployment Process](#air-gap-deployment-process)
3. [Model & Asset Reference](#model--asset-reference)
4. [Environment Variables](#environment-variables)
5. [Troubleshooting](#troubleshooting)
6. [Verification Checklist](#verification-checklist)
7. [Performance Notes](#performance-notes)
8. [Architecture Overview](#architecture-overview)

---

## Quick Start (Standard Deployment)

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- MySQL 8.0 (or use Docker container)
- ~2GB disk space (models + dependencies)
- Internet connection (for initial setup only)

### Step 1: Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd DiffSense-AI

# Run offline setup (downloads models and assets)
python setup_offline.py
```

### Step 2: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and set required values
# IMPORTANT: Change SECRET_KEY for production!
```

### Step 3: Deploy with Docker

```bash
# Build and start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### Step 4: Verify Deployment

```bash
# Check system status
curl http://localhost/api/system/status

# Expected response:
# {"models":{"fastembed":"ok","sentence_transformer":"ok"},"database":"ok","offline_mode":true,"degraded":false}
```

### Step 5: Access Application

- **Frontend:** http://localhost
- **API Docs:** http://localhost:8000/docs
- **Default Admin:** username: `admin`, password: `admin123`

> **IMPORTANT:** Change the default admin password immediately after first login!

---

## Air-Gap Deployment Process

For environments with no internet access, follow this three-phase process.

### Phase 1: Preparation (Internet-Connected Machine)

```bash
# 1. Clone repository
git clone <repository-url>
cd DiffSense-AI

# 2. Run full offline setup
python setup_offline.py

# 3. Download Python packages for offline installation
pip download -r aidiffchecker/backend/requirements.txt -d ./offline_packages

# 4. Download CPU-only PyTorch wheel
pip download torch --index-url https://download.pytorch.org/whl/cpu -d ./offline_packages

# 5. Save Docker images
docker-compose build
docker save diffsense-ai_diffsense-api:latest -o diffsense-api.tar
docker save mysql:8.0 -o mysql.tar
docker save nginx:alpine -o nginx.tar

# 6. Create transfer bundle
tar -czvf diffsense-bundle.tar.gz \
    aidiffchecker/ \
    models/ \
    offline_packages/ \
    docker-compose.yml \
    Dockerfile \
    nginx.conf \
    init.sql \
    .env.example \
    setup_offline.py \
    diffsense-api.tar \
    mysql.tar \
    nginx.tar \
    OFFLINE_DEPLOYMENT.md
```

### Phase 2: Transfer

Transfer `diffsense-bundle.tar.gz` to the air-gapped machine via:
- USB drive
- Optical media (DVD/Blu-ray)
- Approved secure file transfer
- Cross-domain solution (if applicable)

### Phase 3: Deployment (Air-Gapped Machine)

```bash
# 1. Extract bundle
tar -xzvf diffsense-bundle.tar.gz
cd DiffSense-AI

# 2. Load Docker images
docker load -i diffsense-api.tar
docker load -i mysql.tar
docker load -i nginx.tar

# 3. (Alternative) Install Python packages locally
pip install --no-index --find-links=./offline_packages -r aidiffchecker/backend/requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env - MUST set SECRET_KEY to a secure random value!

# 5. Start services
docker-compose up -d

# 6. Verify deployment
curl http://localhost/api/system/status
```

---

## Model & Asset Reference

### AI Models

| Model | Size | Purpose | Required |
|-------|------|---------|----------|
| BAAI/bge-small-en-v1.5 | ~133 MB | Fast embedding generation | Yes |
| all-MiniLM-L6-v2 | ~80 MB | Semantic similarity | Yes |

### Frontend Assets

| Asset | Size | Purpose |
|-------|------|---------|
| TailwindCSS 3.4.1 | ~2.5 MB | CSS framework |
| Chart.js 4.4.0 | ~280 KB | Admin dashboard charts |
| login-bg.jpg | ~50 KB | Login page background |

### Total Storage Requirements

| Component | Size |
|-----------|------|
| AI Models | ~220 MB |
| Frontend Assets | ~3 MB |
| Python Dependencies | ~1.5 GB |
| Docker Images | ~2 GB |
| **Total** | **~4 GB** |

---

## Environment Variables

Create a `.env` file from `.env.example` and configure:

### Required Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (none) | **MUST CHANGE** - JWT signing key (32+ random chars) |
| `MYSQL_PASSWORD` | `rootpassword` | Database root password |

### Offline Mode Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `OFFLINE_MODE` | `false` | Enable offline mode (`true`/`false`) |
| `ALLOW_MODEL_DOWNLOADS` | `false` | Allow runtime model downloads |
| `MODEL_DIR` | `./models` | Path to pre-downloaded models |

### Database Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MYSQL_HOST` | `localhost` | MySQL server hostname |
| `MYSQL_PORT` | `3306` | MySQL server port |
| `MYSQL_USER` | `root` | MySQL username |
| `MYSQL_DATABASE` | `admin_db` | Main database name |

### Path Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `REFERENCE_DIR` | `backend/data/reference_pdfs` | Reference documents folder |
| `STUDENT_ROOT` | `backend/data/user_uploads` | Student uploads folder |
| `TEACHER_ROOT` | `backend/data/teacher_uploads` | Teacher uploads folder |
| `RESULT_ROOT` | `data/result_pdfs` | Generated reports folder |

### Security Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT token expiration |

### Example .env for Production

```env
# Security (CHANGE THESE!)
SECRET_KEY=your-very-long-random-secret-key-here-min-32-chars
MYSQL_PASSWORD=strong-database-password-here

# Offline Mode
OFFLINE_MODE=true
ALLOW_MODEL_DOWNLOADS=false
MODEL_DIR=/app/models

# Database
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_DATABASE=admin_db

# Token expiration (minutes)
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

---

## Troubleshooting

### "Model downloads disabled" Error

**Cause:** Models not pre-downloaded and `ALLOW_MODEL_DOWNLOADS=false`

**Solution:**
```bash
# On internet-connected machine
python setup_offline.py --models-only

# Or enable downloads (not recommended for air-gap)
ALLOW_MODEL_DOWNLOADS=true
```

### "System running in degraded mode" Warning

**Cause:** AI models failed to load, system using BM25 keyword-only matching

**Symptoms:**
- Amber "Degraded Mode" badge in frontend
- Warning banner on dashboard pages
- Only exact word matches detected (no semantic/paraphrase detection)

**Solution:**
```bash
# Check model files exist
ls -la models/embeddings/
ls -la models/sentence_transformers/

# Verify checksums
python setup_offline.py --verify

# Check API logs
docker-compose logs diffsense-api | grep -i model
```

### Frontend Assets 404 Errors

**Cause:** CDN replacement not applied or assets not downloaded

**Solution:**
```bash
# Re-run asset download
python setup_offline.py --assets-only

# Verify files exist
ls -la aidiffchecker/frontend/assets/css/
ls -la aidiffchecker/frontend/assets/js/
ls -la aidiffchecker/frontend/assets/images/
```

### MySQL Connection Refused

**Cause:** Database container not ready or misconfigured

**Solution:**
```bash
# Check MySQL container status
docker-compose ps mysql
docker-compose logs mysql

# Verify healthcheck
docker inspect diffsense-mysql | grep -A 10 Health

# Test connection manually
docker exec -it diffsense-mysql mysql -u root -p -e "SELECT 1"
```

### API Returns 500 Internal Server Error

**Solution:**
```bash
# Check API logs
docker-compose logs diffsense-api

# Common issues:
# - Missing environment variables
# - Database connection failed
# - Model loading failed

# Restart with fresh logs
docker-compose restart diffsense-api
docker-compose logs -f diffsense-api
```

### Docker Build Fails

**Cause:** Network issues or missing dependencies

**Solution:**
```bash
# Build with no cache
docker-compose build --no-cache

# For air-gap: ensure all images are loaded
docker images | grep -E "mysql|nginx|diffsense"
```

---

## Verification Checklist

Run through this checklist after deployment:

### System Status

- [ ] `curl http://localhost/api/system/status` returns `offline_mode: true`
- [ ] `curl http://localhost/api/system/status` returns `degraded: false`
- [ ] `curl http://localhost/api/system/health` returns `status: ok`

### Frontend

- [ ] Login page loads at http://localhost
- [ ] Green "Offline Mode" badge visible (top-right corner)
- [ ] No browser console errors (F12 → Console)
- [ ] TailwindCSS styles applied correctly
- [ ] Login background image displays

### Authentication

- [ ] Admin login works (admin/admin123)
- [ ] Password change works
- [ ] Role-based redirects work (admin→admin.html, teacher→teacher.html, student→student.html)

### Core Functionality

- [ ] PDF upload works (student and teacher)
- [ ] Plagiarism check completes successfully
- [ ] Report PDF generates and downloads
- [ ] Results display in dashboard
- [ ] Chart.js charts render in admin dashboard

### Docker Health

- [ ] `docker-compose ps` shows all containers "Up" and "healthy"
- [ ] `docker-compose logs` shows no critical errors
- [ ] MySQL data persists after `docker-compose restart`

---

## Performance Notes

### Response Times

| Operation | Normal Mode | Degraded Mode |
|-----------|-------------|---------------|
| First request (model loading) | 2-5 seconds | <1 second |
| PDF plagiarism check (10 pages) | 1-3 seconds | 0.5-1 second |
| PDF plagiarism check (50 pages) | 5-10 seconds | 2-4 seconds |
| Report generation | 1-2 seconds | 1-2 seconds |

### Memory Usage

| Component | RAM Usage |
|-----------|-----------|
| FastAPI + both models loaded | ~1.5 GB |
| FastAPI degraded mode (no models) | ~200 MB |
| MySQL | ~400 MB |
| Nginx | ~10 MB |
| **Total (normal)** | **~2 GB** |

### Recommendations

1. **Minimum RAM:** 4 GB (8 GB recommended)
2. **CPU:** 2+ cores (4+ recommended for concurrent users)
3. **Disk:** SSD recommended for faster model loading
4. **First Request:** Allow 5-10 seconds for initial model loading

### Scaling

For high-traffic deployments:

```yaml
# In docker-compose.yml, add replicas
diffsense-api:
  deploy:
    replicas: 3
```

Update nginx.conf for load balancing:
```nginx
upstream api {
    least_conn;
    server diffsense-api:8000;
}
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Browser                             │
└─────────────────────────────┬───────────────────────────────────┘
                              │ HTTP :80
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Nginx (diffsense-nginx)                     │
│  ┌─────────────────┐  ┌──────────────────────────────────────┐  │
│  │  Static Files   │  │         Reverse Proxy                │  │
│  │  /index.html    │  │  /api/* → diffsense-api:8000        │  │
│  │  /admin.html    │  │  /token → diffsense-api:8000        │  │
│  │  /assets/*      │  │  /upload_* → diffsense-api:8000     │  │
│  └─────────────────┘  └──────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────┘
                              │ HTTP :8000
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FastAPI (diffsense-api)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Auth      │  │   PDF       │  │    Plagiarism Engine    │  │
│  │   /token    │  │   Routes    │  │  ┌─────────────────────┐│  │
│  │   JWT       │  │   Upload    │  │  │ ModelManager        ││  │
│  └─────────────┘  │   Download  │  │  │ - bge-small-en-v1.5 ││  │
│                   └─────────────┘  │  │ - MiniLM-L6-v2      ││  │
│                                    │  │ - BM25 (fallback)   ││  │
│                                    │  └─────────────────────┘│  │
│                                    └─────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────┘
                              │ MySQL :3306
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MySQL (diffsense-mysql)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  admin_db   │  │ student_*   │  │      teacher_*          │  │
│  │  - users    │  │ - uploads   │  │      - uploads          │  │
│  │             │  │ - results   │  │      - results          │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Docker Volumes                               │
│  mysql_data     - Database persistence                          │
│  ./models       - AI models (read-only)                         │
│  ./data         - PDF uploads and results                       │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow: Plagiarism Check

```
1. Student uploads PDF
       │
       ▼
2. PDF stored in user_uploads/{username}/
       │
       ▼
3. Student clicks "Check"
       │
       ▼
4. Engine loads PDF, extracts sentences
       │
       ▼
5. ModelManager provides embeddings
   ├── Normal: Neural embeddings (bge + MiniLM)
   └── Degraded: BM25 keyword matching only
       │
       ▼
6. Compare against reference_pdfs/
       │
       ▼
7. Generate similarity report (PDF)
       │
       ▼
8. Store result in result_pdfs/{username}/
       │
       ▼
9. Save metadata to MySQL comparisons table
       │
       ▼
10. Return result URL to frontend
```

---

## Support

For issues and questions:
- Check the [Troubleshooting](#troubleshooting) section
- Review Docker logs: `docker-compose logs`
- Check system status: `curl http://localhost/api/system/status`

---

*Generated for DiffSense-AI Offline Deployment*
