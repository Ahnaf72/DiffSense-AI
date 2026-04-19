"""
admin_routes.py  ─  Admin API routes
=====================================
All admin-only endpoints: user management, reference PDFs, dashboard.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File

from backend.routes.auth_routes import get_current_user
from backend.db.supabase_client import db
from backend.db.user_db import create_user_db, drop_user_db, get_uploads
from backend.services.auth_service import hash_password
from backend.services.upload_service import save_reference_upload, delete_reference_pdf
from backend.services.plagiarism_service import get_dashboard_stats

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── Dashboard ──────────────────────────────────────────────────────────────
@router.get("/dashboard-stats")
def dashboard_stats(_admin: dict = Depends(_require_admin)):
    return get_dashboard_stats()


# ── User Management ────────────────────────────────────────────────────────
@router.get("/users")
def list_users(_admin: dict = Depends(_require_admin)):
    rows = db.list_users()
    return {
        "teachers": [u for u in rows if u["role"] == "teacher"],
        "students": [u for u in rows if u["role"] == "student"],
        "admins":   [u for u in rows if u["role"] == "admin"],
    }


@router.post("/users/add")
def add_user(
    username:     str = Form(...),
    full_name:    str = Form(...),
    password:     str = Form(...),
    role:         str = Form(...),
    _admin:       dict = Depends(_require_admin),
):
    existing = db.get_user_by_username(username)
    if existing:
        return {"exists": True}

    hashed = hash_password(password)
    result = db.insert_user(username, full_name, hashed, role)
    # PostgREST returns a list with the inserted row
    if isinstance(result, list) and len(result) > 0:
        new_id = result[0].get("id")
    elif isinstance(result, dict):
        new_id = result.get("id")
    else:
        new_id = None

    create_user_db(username, role)
    return {"success": True, "user_id": new_id}


@router.delete("/users/delete/{username}")
def delete_user(
    username: str,
    _admin:   dict = Depends(_require_admin),
):
    user_obj = db.get_user_by_username(username)
    if not user_obj:
        raise HTTPException(status_code=404, detail="User not found")
    if user_obj["role"] == "admin":
        raise HTTPException(status_code=403, detail="Cannot delete admin accounts")

    drop_user_db(username, user_obj["role"])
    db.delete_user(username)
    return {"deleted": username}


# ── Reference PDFs ─────────────────────────────────────────────────────────
@router.get("/pdfs")
def list_reference_pdfs(_admin: dict = Depends(_require_admin)):
    rows = db.list_reference_pdfs()
    return [
        {
            "name":        r["filename"],
            "uploaded_by": r["uploaded_by"],
            "uploaded_at": r["uploaded_at"][:19].replace("T", " ")
                            if isinstance(r["uploaded_at"], str)
                            else str(r["uploaded_at"])[:19],
        }
        for r in rows
    ]


@router.post("/upload_reference")
async def upload_reference(
    files:  List[UploadFile] = File(...),
    _admin: dict = Depends(_require_admin),
):
    return await save_reference_upload(_admin["username"], files)


@router.delete("/pdfs/delete/{filename}")
def delete_pdf(
    filename: str,
    _admin:   dict = Depends(_require_admin),
):
    return delete_reference_pdf(filename)
