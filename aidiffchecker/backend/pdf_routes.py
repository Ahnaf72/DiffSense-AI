from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
import shutil
import os
from backend.auth import get_current_user
from backend.admin_db import get_admin_db, db as supabase_db
from backend.user_db import create_user_db, save_upload, save_result
from pydantic import BaseModel

class CheckRequest(BaseModel):
    filename: str
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
    save_upload(user['username'], 'student', file.filename)
    return {"message": "Uploaded successfully"}

# Teacher upload
@router.post("/upload/teacher")
def upload_teacher(files: list[UploadFile] = File(...), user=Depends(get_current_user)):
    if user['role'] != 'teacher':
        raise HTTPException(status_code=403, detail="Not allowed")
    for file in files:
        save_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        save_upload(user['username'], 'teacher', file.filename)
    return {"message": f"{len(files)} files uploaded"}

# Admin upload
@router.post("/upload/admin")
def upload_admin(files: list[UploadFile] = File(...), user=Depends(get_current_user)):
    if user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Not allowed")
    for file in files:
        save_path = os.path.join(REF_DIR, file.filename)
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        user_row = supabase_db.get_user_by_username(user['username'])
        supabase_db.insert_reference_pdf(file.filename, user_row['id'] if user_row else None)
    return {"message": f"{len(files)} reference files uploaded"}

@router.post("/check")
def check_pdf(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    from backend.engine import check_plagiarism
    from backend.report_gen import generate_report

    # 1. SAVE UPLOADED FILE
    file_path = f"data/user_uploads/{file.filename}"
    with open(file_path, "wb") as f:
        f.write(file.file.read())

    # 2. GET REFERENCE PDFs FROM ADMIN DB
    ref_rows = supabase_db.list_reference_pdfs()
    reference_pdfs = [f"data/reference_pdfs/{r['filename']}" for r in ref_rows]

    # 3. RUN PLAGIARISM CHECK
    results = check_plagiarism(file_path, reference_pdfs)

    # 4. GENERATE RESULT PDF
    output_pdf = f"data/result_pdfs/result_{file.filename}.pdf"
    generate_report(output_pdf, results)

    # 5. SAVE TO DB
    save_result(user['username'], user['role'], file.filename, output_pdf, results)

    # 6. RETURN RESPONSE
    return {
        "results": results,
        "report": output_pdf
    }

@router.post("/check_existing")
def check_existing(
    req: CheckRequest,
    user=Depends(get_current_user),
):
    from backend.engine import check_plagiarism
    from backend.report_gen import generate_report

    file_path = f"data/user_uploads/{req.filename}"

    # get reference PDFs
    ref_rows = supabase_db.list_reference_pdfs()
    reference_pdfs = [f"data/reference_pdfs/{r['filename']}" for r in ref_rows]

    # run check
    results = check_plagiarism(file_path, reference_pdfs)

    output_pdf = f"data/result_pdfs/result_{req.filename}.pdf"
    generate_report(output_pdf, results)

    # save to DB
    save_result(user['username'], user['role'], req.filename, output_pdf, results)

    return {
        "report": output_pdf,
        "results": results
    }