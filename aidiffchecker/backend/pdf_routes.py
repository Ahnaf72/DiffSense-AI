from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
import shutil
import os
from backend.auth import get_current_user
from backend.db import get_db
import mysql.connector

router = APIRouter()

UPLOAD_DIR = "data/user_uploads"
REF_DIR = "data/reference_pdfs"

# Student upload
@router.post("/upload/student")
def upload_student(file: UploadFile = File(...), user=Depends(get_current_user)):
    if user['role'] != 'student':
        raise HTTPException(status_code=403, detail="Not allowed")
    save_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    # Save to DB
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT INTO user_uploads (username, filename, role) VALUES (%s,%s,%s)", 
                   (user['username'], file.filename, user['role']))
    db.commit()
    return {"message": "Uploaded successfully"}

# Teacher upload
@router.post("/upload/teacher")
def upload_teacher(files: list[UploadFile] = File(...), user=Depends(get_current_user)):
    if user['role'] != 'teacher':
        raise HTTPException(status_code=403, detail="Not allowed")
    db = get_db()
    cursor = db.cursor()
    for file in files:
        save_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        cursor.execute("INSERT INTO user_uploads (username, filename, role) VALUES (%s,%s,%s)", 
                       (user['username'], file.filename, user['role']))
    db.commit()
    return {"message": f"{len(files)} files uploaded"}

# Admin upload
@router.post("/upload/admin")
def upload_admin(files: list[UploadFile] = File(...), user=Depends(get_current_user)):
    if user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Not allowed")
    db = get_db()
    cursor = db.cursor()
    for file in files:
        save_path = os.path.join(REF_DIR, file.filename)
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        cursor.execute("INSERT INTO reference_pdfs (filename) VALUES (%s)", (file.filename,))
    db.commit()
    return {"message": f"{len(files)} reference files uploaded"}