"""
teacher_routes.py  ─  Teacher API routes
=========================================
Teacher-only endpoints: upload, list, delete reference PDFs.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from backend.routes.auth_routes import get_current_user
from backend.services.upload_service import save_teacher_upload, delete_teacher_upload

router = APIRouter(tags=["teacher"])


def _require_teacher(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can use this endpoint")
    return user


# ── Upload ──────────────────────────────────────────────────────────────────
@router.post("/upload_teacher_pdf")
async def upload_teacher_pdf(
    files: List[UploadFile] = File(...),
    user:  dict = Depends(_require_teacher),
):
    return await save_teacher_upload(user["username"], files)


# ── Delete upload ──────────────────────────────────────────────────────────
@router.delete("/upload_teacher_pdf/delete/{filename}")
def delete_teacher_pdf(
    filename: str,
    user:     dict = Depends(_require_teacher),
):
    return delete_teacher_upload(user["username"], filename)
