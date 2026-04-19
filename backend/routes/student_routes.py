"""
student_routes.py  ─  Student API routes
=========================================
Student-only endpoints: upload, list, delete, run check, view results.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from backend.routes.auth_routes import get_current_user
from backend.db.user_db import get_uploads, get_results
from backend.services.upload_service import save_student_upload, delete_student_upload
from backend.services.plagiarism_service import run_plagiarism_check, get_viewer_data

router = APIRouter(tags=["student"])


def _require_student(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Only students can use this endpoint")
    return user


class CheckRequest(BaseModel):
    filename: str


# ── Upload ──────────────────────────────────────────────────────────────────
@router.post("/upload_student_pdf")
async def upload_student_pdf(
    file: UploadFile = File(...),
    user: dict = Depends(_require_student),
):
    return await save_student_upload(user["username"], file)


# ── List uploads ────────────────────────────────────────────────────────────
@router.get("/my/uploads")
def my_uploads(user: dict = Depends(get_current_user)):
    files = get_uploads(user["username"], user["role"])
    return {"files": files}


# ── Delete upload ──────────────────────────────────────────────────────────
@router.delete("/upload_student_pdf/delete/{filename}")
def delete_student_pdf(
    filename: str,
    user:     dict = Depends(_require_student),
):
    return delete_student_upload(user["username"], filename)


# ── Run plagiarism check ──────────────────────────────────────────────────
@router.post("/run_check")
def run_check(
    req:  CheckRequest,
    user: dict = Depends(get_current_user),
):
    if user["role"] not in ("student", "teacher"):
        raise HTTPException(status_code=403, detail="Admins cannot run checks")
    result = run_plagiarism_check(user["username"], user["role"], req.filename)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Check failed"))
    return result


# ── View results ──────────────────────────────────────────────────────────
@router.get("/my/results")
def my_results(user: dict = Depends(get_current_user)):
    rows = get_results(user["username"], user["role"])
    serialized = []
    for r in rows:
        r2 = dict(r)
        if hasattr(r2.get("created_at"), "strftime"):
            r2["created_at"] = r2["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        serialized.append(r2)
    return {"results": serialized}


# ── Interactive viewer data ───────────────────────────────────────────────
@router.post("/viewer_data")
def viewer_data(
    req:  CheckRequest,
    user: dict = Depends(get_current_user),
):
    if user["role"] not in ("student", "teacher"):
        raise HTTPException(status_code=403, detail="Admins cannot use viewer")
    result = get_viewer_data(user["username"], user["role"], req.filename)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Viewer failed"))
    return result
