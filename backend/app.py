"""
app.py  ─  DiffSense-AI FastAPI Application
=============================================
Main entry point. Registers all route modules and configures the app.

Architecture:
  backend/
    app.py              ← this file
    config.py           ← settings
    db/                 ← database layer (Supabase REST API)
    services/           ← business logic (auth, plagiarism, uploads)
    routes/             ← API endpoints (auth, admin, student, teacher, system)
    core/               ← AI engine, NLP utils, PDF utils
  frontend/             ← HTML/CSS/JS
  data/                 ← uploaded files, results, models
"""

import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

from backend.config import config

# ── App setup ──────────────────────────────────────────────────────────────
app = FastAPI(title="DiffSense-AI", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register route modules ────────────────────────────────────────────────
from backend.routes.auth_routes     import router as auth_router
from backend.routes.admin_routes    import router as admin_router
from backend.routes.student_routes  import router as student_router
from backend.routes.teacher_routes  import router as teacher_router
from backend.routes.system_routes   import router as system_router

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(student_router)
app.include_router(teacher_router)
app.include_router(system_router)

# ── Ensure directories exist ──────────────────────────────────────────────
config.ensure_directories()

# ── Static file mounts ────────────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

app.mount("/data",           StaticFiles(directory="data"), name="data")
app.mount("/student_files",  StaticFiles(directory=config.STUDENT_ROOT), name="student_files")
app.mount("/teacher_files",  StaticFiles(directory=config.TEACHER_ROOT), name="teacher_files")
os.makedirs(os.path.join(FRONTEND_DIR, "assets"), exist_ok=True)
app.mount("/assets",         StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="frontend_assets")

# ── Frontend HTML routes ──────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def serve_index():
    with open(os.path.join(FRONTEND_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/admin.html", response_class=HTMLResponse)
def serve_admin():
    with open(os.path.join(FRONTEND_DIR, "admin.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/teacher.html", response_class=HTMLResponse)
def serve_teacher():
    with open(os.path.join(FRONTEND_DIR, "teacher.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/student.html", response_class=HTMLResponse)
def serve_student():
    with open(os.path.join(FRONTEND_DIR, "student.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/styles.css")
def serve_styles():
    return FileResponse(os.path.join(FRONTEND_DIR, "styles.css"), media_type="text/css")

@app.get("/script.js")
def serve_script():
    return FileResponse(os.path.join(FRONTEND_DIR, "script.js"), media_type="application/javascript")

# ── Startup event: pre-load AI model ─────────────────────────────────────
@app.on_event("startup")
def _load_models_on_startup():
    logger = logging.getLogger(__name__)
    try:
        from backend.core.nlp_utils import get_embeddings
        logger.info("Pre-loading embedding model on startup...")
        test = get_embeddings(["system startup probe"])
        if test is not None:
            logger.info("Embedding model loaded successfully on startup")
        else:
            logger.warning("Embedding model unavailable - system will run in degraded mode")
    except Exception as e:
        logger.error(f"Failed to pre-load embedding model: {e}")
