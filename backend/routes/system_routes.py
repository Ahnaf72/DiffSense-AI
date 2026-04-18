"""
system_routes.py  ─  System status & health routes
====================================================
"""

import os
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from backend.db.supabase_client import db, get_db
from backend.config import config
from backend.routes.auth_routes import get_current_user

router = APIRouter(tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/api/system/status")
def system_status(db_inst=Depends(get_db)):
    """Return comprehensive system status for frontend offline badge."""
    # Model status
    try:
        from backend.core.model_manager import model_manager
        from backend.core.nlp_utils import check_offline_readiness, _model_type, _cached_model

        if _cached_model is None:
            from backend.core.nlp_utils import get_embeddings
            get_embeddings(["status probe"])

        offline_status = check_offline_readiness()
        model_status = model_manager.get_model_status()

        fastembed_status = "not_attempted"
        if offline_status.get("fastembed_attempted"):
            fastembed_status = "ok" if offline_status.get("fastembed_available") else "unavailable"

        st_status = "not_attempted"
        if model_status.get("sentence_transformer", {}).get("attempted"):
            st_status = "ok" if model_status.get("sentence_transformer", {}).get("loaded") else "unavailable"

        if _model_type == "sentence_transformer":
            st_status = "ok"

        fully_ready = offline_status.get("fully_offline_ready", False)
    except Exception as e:
        logger.error(f"Error checking model status: {e}")
        fastembed_status = "error"
        st_status = "error"
        fully_ready = False
        offline_status = {"missing_models": []}

    # Database status
    db_status = "ok"
    try:
        db_inst.health_check()
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "error"

    return {
        "models": {
            "fastembed": fastembed_status,
            "sentence_transformer": st_status,
        },
        "database": db_status,
        "offline_mode": config.OFFLINE_MODE,
        "degraded": not fully_ready,
        "missing_models": offline_status.get("missing_models", []),
        "uptime": "ok",
    }


@router.get("/api/system/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "offline": config.OFFLINE_MODE}


@router.get("/download_report/{username}/{filename}")
def download_report(
    username: str,
    filename: str,
    current_user: dict = Depends(get_current_user),
):
    """Download a result PDF report."""
    if current_user["username"] != username and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    file_path = os.path.join(config.RESULT_ROOT, username, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report not found")

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/viewer", response_class=HTMLResponse)
def serve_viewer():
    """Serve the interactive plagiarism viewer."""
    viewer_path = os.path.join("backend", "static", "viewer.html")
    if not os.path.exists(viewer_path):
        raise HTTPException(status_code=404, detail="viewer.html not found")
    with open(viewer_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
