"""
upload_service.py  ─  File upload handling service
===================================================
Manages file uploads for students, teachers, and admins.
Handles deduplication, directory creation, and DB persistence.
"""

import os
import shutil
from typing import List
from fastapi import UploadFile

from backend.config import config
from backend.db.supabase_client import db
from backend.db.user_db import save_upload


def _deduplicated_path(directory: str, filename: str) -> tuple[str, str]:
    """Return (final_filepath, final_filename) with deduplication."""
    base, ext = os.path.splitext(filename)
    counter = 1
    file_path = os.path.join(directory, filename)
    final_name = filename
    while os.path.exists(file_path):
        final_name = f"{base}({counter}){ext}"
        file_path = os.path.join(directory, final_name)
        counter += 1
    return file_path, final_name


async def save_student_upload(username: str, file: UploadFile) -> dict:
    """Save a student PDF upload."""
    dest_dir = os.path.join(config.STUDENT_ROOT, username)
    os.makedirs(dest_dir, exist_ok=True)

    file_path, final_name = _deduplicated_path(dest_dir, file.filename)

    with open(file_path, "wb") as f:
        f.write(await file.read())

    save_upload(username, "student", final_name)
    return {"success": True, "message": f"{final_name} uploaded successfully!"}


async def save_teacher_upload(username: str, files: List[UploadFile]) -> dict:
    """Save teacher PDF uploads."""
    dest_dir = os.path.join(config.TEACHER_ROOT, username)
    os.makedirs(dest_dir, exist_ok=True)

    saved = []
    for file in files:
        file_path, final_name = _deduplicated_path(dest_dir, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        save_upload(username, "teacher", final_name)
        saved.append(final_name)

    return {"success": True, "message": f"{len(saved)} PDF(s) uploaded successfully"}


async def save_reference_upload(username: str, files: List[UploadFile]) -> dict:
    """Save admin reference PDF uploads."""
    ref_dir = config.REFERENCE_DIR
    os.makedirs(ref_dir, exist_ok=True)

    user_row = db.get_user_by_username(username)
    user_id = user_row["id"] if user_row else None

    saved_files = []
    failed_files = []

    for file in files:
        file_path, final_name = _deduplicated_path(ref_dir, file.filename)
        try:
            with open(file_path, "wb") as f:
                f.write(await file.read())
            db.insert_reference_pdf(final_name, user_id)
            saved_files.append(final_name)
        except Exception as e:
            failed_files.append({"filename": final_name, "error": str(e)})

    msg = ""
    if saved_files:
        msg += f"Uploaded: {', '.join(saved_files)}. "
    if failed_files:
        msg += "Failed: " + ", ".join(f["filename"] for f in failed_files)

    return {"message": msg}


def delete_student_upload(username: str, filename: str) -> dict:
    """Delete a student's uploaded file."""
    file_path = os.path.join(config.STUDENT_ROOT, username, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    save_upload(username, "student", filename, delete=True)
    return {"message": f"{filename} deleted"}


def delete_teacher_upload(username: str, filename: str) -> dict:
    """Delete a teacher's uploaded file."""
    file_path = os.path.join(config.TEACHER_ROOT, username, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    save_upload(username, "teacher", filename, delete=True)
    return {"message": f"{filename} deleted"}


def delete_reference_pdf(filename: str) -> dict:
    """Delete a reference PDF (admin only)."""
    file_path = os.path.join(config.REFERENCE_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    db.delete_reference_pdf(filename)
    return {"message": f"{filename} deleted successfully"}
