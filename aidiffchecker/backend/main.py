"""
main.py  ─  FastAPI Application
================================
Key design decisions
─────────────────────
• Role is read from admin_db.users — never trusted from the frontend.
• /token  returns { access_token, token_type, role } so the
  frontend can redirect to the right page.
• Uploads are stored in per-user sub-folders:
      data/user_uploads/{username}/
      data/teacher_uploads/{username}/
• Result PDFs land in:
      data/result_pdfs/{username}/
• /my/uploads   → returns ONLY the authenticated user's files (from DB)
• /my/results   → returns ONLY the authenticated user's result PDFs
• /run_check    → runs the AI plagiarism engine and returns result PDF URL
"""

import os
from datetime import datetime, timedelta
from typing import List
from fastapi.responses import FileResponse

from fastapi import (
    FastAPI, UploadFile, File, Depends,
    HTTPException, status, Form, BackgroundTasks
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from fastapi.responses import HTMLResponse
from backend.highlight_utils import get_highlight_positions, get_page_dimensions
from jose import JWTError, jwt
from pydantic import BaseModel
from backend.admin_db import get_admin_db, db as supabase_db
from backend.user_db import save_upload, create_user_db, get_uploads, get_results
from backend.config import config

# ──────────────────────────────────────────────────────────────────────────
# AUTH SETUP (loaded from config.py / environment)
# ──────────────────────────────────────────────────────────────────────────
SECRET_KEY                  = config.SECRET_KEY
ALGORITHM                   = config.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = config.ACCESS_TOKEN_EXPIRE_MINUTES

pwd_context    = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme  = OAuth2PasswordBearer(tokenUrl="token")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate_user(username: str, password: str, db):
    row = db.get_user_by_username(username)

    if not row:
        return None
    if not verify_password(password, row.get("hashed_password", "")):
        return None
    return row


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    payload = data.copy()
    expire  = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    payload.update({"exp": expire})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db = Depends(get_admin_db),
) -> dict:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload  = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise exc
        row = db.get_user_by_username(username)
        if row is None:
            raise exc
        return row
    except JWTError:
        raise exc


# ──────────────────────────────────────────────────────────────────────────
# DIRECTORY SETUP (loaded from config.py / environment)
# ──────────────────────────────────────────────────────────────────────────
REFERENCE_DIR  = config.REFERENCE_DIR
STUDENT_ROOT   = config.STUDENT_ROOT
TEACHER_ROOT   = config.TEACHER_ROOT
RESULT_ROOT    = config.RESULT_ROOT

# Ensure all directories exist
config.ensure_directories()


def student_dir(username: str) -> str:
    p = os.path.join(STUDENT_ROOT, username)
    os.makedirs(p, exist_ok=True)
    return p


def teacher_dir(username: str) -> str:
    p = os.path.join(TEACHER_ROOT, username)
    os.makedirs(p, exist_ok=True)
    return p


def result_dir(username: str) -> str:
    p = os.path.join(RESULT_ROOT, username)
    os.makedirs(p, exist_ok=True)
    return p


# ──────────────────────────────────────────────────────────────────────────
# APP
# ──────────────────────────────────────────────────────────────────────────
app = FastAPI(title="AI Diff Checker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _load_models_on_startup():
    """Eagerly load embedding model on startup so status is accurate."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        from backend.nlp_utils import get_embeddings
        logger.info("Pre-loading embedding model on startup...")
        test = get_embeddings(["system startup probe"])
        if test is not None:
            logger.info("Embedding model loaded successfully on startup")
        else:
            logger.warning("Embedding model unavailable - system will run in degraded mode")
    except Exception as e:
        logger.error(f"Failed to pre-load embedding model: {e}")

# Serve generated result PDFs as static files
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
app.mount("/data", StaticFiles(directory="data"), name="data")
app.mount("/student_files", StaticFiles(directory=STUDENT_ROOT), name="student_files")
app.mount("/teacher_files", StaticFiles(directory=TEACHER_ROOT), name="teacher_files")
app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="frontend_assets")


# ──────────────────────────────────────────────────────────────────────────
# FRONTEND HTML ROUTES
# ──────────────────────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────────────────
# AUTH ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────
@app.post("/token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db = Depends(get_admin_db),
):
    """
    Returns { access_token, token_type, role }.
    Frontend uses `role` to decide which dashboard to load.
    """
    user = authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    token = create_access_token(
        {"sub": user["username"]},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": token, "token_type": "bearer", "role": user["role"]}


@app.post("/admin/change-password")
def change_password(
    current_password: str = Form(...),
    new_password:     str = Form(...),
    db               = Depends(get_admin_db),
    current_user:     dict    = Depends(get_current_user),
):
    user = db.get_user_by_username(current_user["username"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not pwd_context.verify(current_password, user.get("hashed_password", "")):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    new_hash = pwd_context.hash(new_password)
    # Update password via REST API
    import httpx
    headers = {"apikey": config.SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}", "Content-Type": "application/json"}
    r = httpx.patch(f"{config.SUPABASE_URL}/rest/v1/users?username=eq.{current_user['username']}", headers=headers, json={"hashed_password": new_hash})
    if r.status_code >= 400:
        raise HTTPException(status_code=500, detail="Failed to update password")
    return {"message": "Password updated successfully"}


# ──────────────────────────────────────────────────────────────────────────
# FILE UPLOAD ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────
@app.post("/upload_student_pdf")
async def upload_student_pdf(
    file: UploadFile = File(...),
    user: dict       = Depends(get_current_user),
):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can use this endpoint")

    username  = user["username"]
    dest_dir  = student_dir(username)

    # Handle duplicate filenames
    filename  = file.filename
    base, ext = os.path.splitext(filename)
    counter   = 1
    file_path = os.path.join(dest_dir, filename)
    while os.path.exists(file_path):
        filename  = f"{base}({counter}){ext}"
        file_path = os.path.join(dest_dir, filename)
        counter  += 1

    with open(file_path, "wb") as f:
        f.write(await file.read())

    save_upload(username, "student", filename)

    return {"success": True, "message": f"{filename} uploaded successfully!"}


@app.post("/upload_teacher_pdf")
async def upload_teacher_pdf(
    files: List[UploadFile] = File(...),
    user:  dict             = Depends(get_current_user),
):
    if user["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can use this endpoint")

    username = user["username"]
    dest_dir = teacher_dir(username)
    saved    = []

    for file in files:
        filename  = file.filename
        base, ext = os.path.splitext(filename)
        counter   = 1
        file_path = os.path.join(dest_dir, filename)
        while os.path.exists(file_path):
            filename  = f"{base}({counter}){ext}"
            file_path = os.path.join(dest_dir, filename)
            counter  += 1

        with open(file_path, "wb") as f:
            f.write(await file.read())

        save_upload(username, "teacher", filename)
        saved.append(filename)

    return {"success": True, "message": f"{len(saved)} PDF(s) uploaded successfully"}


# ──────────────────────────────────────────────────────────────────────────
# LIST UPLOADS  (token-authenticated — no username in URL)
# ──────────────────────────────────────────────────────────────────────────
@app.get("/my/uploads")
def my_uploads(user: dict = Depends(get_current_user)):
    """Return file list for the logged-in user only (from their dynamic DB)."""
    role     = user["role"]
    username = user["username"]
    files    = get_uploads(username, role)
    return {"files": files}


@app.get("/my/results")
def my_results(user: dict = Depends(get_current_user)):
    """Return comparison results for the logged-in user."""
    username = user["username"]
    role     = user["role"]
    rows     = get_results(username, role)

    # Convert datetime objects to strings for JSON
    serialized = []
    for r in rows:
        r2 = dict(r)
        if hasattr(r2.get("created_at"), "strftime"):
            r2["created_at"] = r2["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        serialized.append(r2)
    return {"results": serialized}


# ──────────────────────────────────────────────────────────────────────────
# DELETE UPLOADS
# ──────────────────────────────────────────────────────────────────────────
@app.delete("/upload_student_pdf/delete/{filename}")
def delete_student_pdf(
    filename: str,
    user:     dict = Depends(get_current_user),
):
    if user["role"] != "student":
        raise HTTPException(status_code=403)

    file_path = os.path.join(student_dir(user["username"]), filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    save_upload(user["username"], "student", filename, delete=True)
    return {"message": f"{filename} deleted"}


@app.delete("/upload_teacher_pdf/delete/{filename}")
def delete_teacher_pdf(
    filename: str,
    user:     dict = Depends(get_current_user),
):
    if user["role"] != "teacher":
        raise HTTPException(status_code=403)

    file_path = os.path.join(teacher_dir(user["username"]), filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    save_upload(user["username"], "teacher", filename, delete=True)
    return {"message": f"{filename} deleted"}


# ──────────────────────────────────────────────────────────────────────────
# RUN PLAGIARISM CHECK
# ──────────────────────────────────────────────────────────────────────────
class CheckRequest(BaseModel):
    filename: str  # just the filename, not the full path


@app.post("/run_check")
def run_check(
    req:  CheckRequest,
    user: dict = Depends(get_current_user),
):
    """
    Runs the AI plagiarism engine on an already-uploaded file.
    Returns the URL of the result PDF (downloadable).
    """
    from backend.engine import run_engine

    username = user["username"]
    role     = user["role"]

    if role == "student":
        pdf_path = os.path.join(student_dir(username), req.filename)
    elif role == "teacher":
        pdf_path = os.path.join(teacher_dir(username), req.filename)
    else:
        raise HTTPException(status_code=403, detail="Admins cannot run checks")

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail=f"{req.filename} not found")

    try:
        # run_engine() calls _build_report() internally — DO NOT call
        # generate_report() after this; it would overwrite the finished report.
        result_pdf_path, results, details = run_engine(username, role, pdf_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Engine error: {e}")

    result_url    = "/" + result_pdf_path.replace("\\", "/")
    overall       = max((r.get("similarity", 0) for r in results), default=0)
    uncited_total = max((r.get("uncited_total", 1) for r in results), default=1)

    return {
        "success":            True,
        "result_url":         result_url,
        "overall_similarity": round(overall, 2),
        "per_reference": [
            {
                "reference":          r["reference"],
                "similarity":         r.get("similarity", 0),
                "direct_percent":     round(r.get("match_types", {}).get("direct",     0) / max(r.get("uncited_total", uncited_total), 1) * 100, 1),
                "paraphrase_percent": round(r.get("match_types", {}).get("paraphrase", 0) / max(r.get("uncited_total", uncited_total), 1) * 100, 1),
                "semantic_percent":   round(r.get("match_types", {}).get("semantic",   0) / max(r.get("uncited_total", uncited_total), 1) * 100, 1),
            }
            for r in results
        ],
    }


@app.get("/download_report/{username}/{filename}")
def download_report(
    username: str,
    filename: str,
    user: dict = Depends(get_current_user),
):
    """
    Stream the result PDF to the browser as a downloadable file.
 
    The frontend should call this URL when the user clicks "Download Report".
    The browser will show a Save-As dialog (or auto-save) rather than
    opening the file inline.
 
    Security: only the owner (or an admin) may download their own reports.
    """
    # Only allow the owner or an admin to download
    if user["username"] != username and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
 
    file_path = os.path.join(RESULT_ROOT, username, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report not found")
 
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=filename,                       # triggers Save-As dialog
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/viewer", response_class=HTMLResponse)
def serve_viewer():
    """
    Serve the interactive plagiarism viewer.
    Place viewer.html in  backend/static/viewer.html
    """
    viewer_path = os.path.join("backend", "static", "viewer.html")
    if not os.path.exists(viewer_path):
        raise HTTPException(status_code=404,
                            detail="viewer.html not found in backend/static/")
    with open(viewer_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
 
 
@app.post("/viewer_data")
def get_viewer_data(
    req:  CheckRequest,               # same model already used by /run_check
    user: dict = Depends(get_current_user),
):
    """
    Re-run (or cache-hit) the plagiarism engine and return all data the
    interactive viewer needs:
      • pdf_url      : URL to stream the original student PDF to the browser
      • highlights   : per-chunk coloured rectangles (PyMuPDF coordinates)
      • page_dims    : width + height of every page (in PDF points)
      • sources      : per-reference summary stats + palette colours
      • overall      : max similarity across all references (0–100)
 
    The viewer calls this endpoint on load, then overlays the highlights
    on top of the PDF.js-rendered original document.
    """
    from backend.engine          import run_engine, check_plagiarism, REFERENCE_DIR
    from backend.highlight_utils import get_highlight_positions, get_page_dimensions
 
    username = user["username"]
    role     = user["role"]
 
    # ── resolve PDF path ──────────────────────────────────────────────────
    if role == "student":
        pdf_path = os.path.join(student_dir(username), req.filename)
    elif role == "teacher":
        pdf_path = os.path.join(teacher_dir(username), req.filename)
    else:
        raise HTTPException(status_code=403,
                            detail="Admins do not submit documents for checking")
 
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404,
                            detail=f"'{req.filename}' not found for user '{username}'")
 
    # ── collect reference PDFs ────────────────────────────────────────────
    reference_pdfs = [
        os.path.join(REFERENCE_DIR, f)
        for f in sorted(os.listdir(REFERENCE_DIR))
        if f.lower().endswith(".pdf")
    ]
    if not reference_pdfs:
        raise HTTPException(status_code=400,
                            detail="No reference PDFs available. Ask your admin to upload some.")
 
    # ── run detection engine ──────────────────────────────────────────────
    try:
        results, details, user_chunks, uncited_mask = check_plagiarism(
            pdf_path, reference_pdfs
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Engine error: {exc}")
 
    # ── build source order (descending by similarity) ─────────────────────
    matched = [r for r in results if sum(r["match_types"].values()) > 0]
    matched.sort(key=lambda r: r["similarity"], reverse=True)
    source_order = [r["reference"] for r in matched]
 
    # ── highlight positions via PyMuPDF ───────────────────────────────────
    try:
        highlights = get_highlight_positions(pdf_path, details, source_order)
    except Exception as exc:
        # Non-fatal: viewer still works, just without highlights
        highlights = []
 
    # ── page dimensions for canvas pre-sizing ────────────────────────────
    try:
        page_dims = get_page_dimensions(pdf_path)
    except Exception:
        page_dims = []
 
    # ── source summary rows ───────────────────────────────────────────────
    _PALETTE_FG = [
        "#1a6a8a","#c0622b","#2e7d32","#8e1c3e",
        "#1a237e","#4a148c","#bf360c","#004d40",
    ]
    _PALETTE_BG = [
        "#d4eaf5","#fbe8da","#dcedc8","#fce4ec",
        "#e8eaf6","#f3e5f5","#fbe9e7","#e0f2f1",
    ]
 
    uncited_total = max(sum(uncited_mask), 1)
    sources = []
    for i, r in enumerate(matched):
        mt = r["match_types"]
        sources.append({
            "name":       r["reference"],
            "similarity": r["similarity"],
            "direct":     round(mt["direct"]     / uncited_total * 100, 1),
            "paraphrase": round(mt["paraphrase"] / uncited_total * 100, 1),
            "semantic":   round(mt["semantic"]   / uncited_total * 100, 1),
            "table_hits": r.get("table_matches", 0),
            "image_hits": r.get("image_matches", 0),
            "color_fg":   _PALETTE_FG[i % len(_PALETTE_FG)],
            "color_bg":   _PALETTE_BG[i % len(_PALETTE_BG)],
        })
 
    overall = max((r["similarity"] for r in results), default=0.0)
 
    # Build the URL the browser can use to fetch the original PDF.
    # main.py mounts  /data  →  "data/"  as StaticFiles.
    # We replicate a similar pattern for the user upload directories.
    # Adjust the URL scheme if your static mount differs.
    pdf_url = (
        f"/student_files/{username}/{req.filename}"
        if role == "student"
        else f"/teacher_files/{username}/{req.filename}"
    )
 
    return {
        "filename":   req.filename,
        "pdf_url":    pdf_url,
        "overall":    round(overall, 1),
        "highlights": highlights,
        "page_dims":  page_dims,
        "sources":    sources,
        "total_chunks": len(user_chunks),
        "uncited":    int(uncited_total),
    }
 
# ──────────────────────────────────────────────────────────────────────────
# ADMIN ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────
@app.post("/upload_reference")
async def upload_reference(
    files: List[UploadFile] = File(...),
    user:  dict             = Depends(get_current_user),
    db    = Depends(get_admin_db),
):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can upload reference PDFs")

    saved_files  = []
    failed_files = []

    for file in files:
        filename  = file.filename
        base, ext = os.path.splitext(filename)
        counter   = 1
        file_path = os.path.join(REFERENCE_DIR, filename)
        while os.path.exists(file_path):
            filename  = f"{base}({counter}){ext}"
            file_path = os.path.join(REFERENCE_DIR, filename)
            counter  += 1

        try:
            with open(file_path, "wb") as f:
                f.write(await file.read())

            user_row = db.get_user_by_username(user["username"])

            db.insert_reference_pdf(filename, user_row["id"])
            saved_files.append(filename)

        except Exception as e:
            failed_files.append({"filename": filename, "error": str(e)})

    msg = ""
    if saved_files:
        msg += f"Uploaded: {', '.join(saved_files)}. "
    if failed_files:
        msg += "Failed: " + ", ".join(f["filename"] for f in failed_files)

    return {"message": msg}


@app.get("/admin/dashboard-stats")
def dashboard_stats(
    db   = Depends(get_admin_db),
    user: dict    = Depends(get_current_user),
):
    if user["role"] != "admin":
        raise HTTPException(status_code=403)

    ref_count   = db.count_reference_pdfs()
    total_users = db.count_users()

    def count_uploads_by_role(role):
        users = db.list_users(role=role)
        total = 0
        for u in users:
            files = get_uploads(u["username"], role)
            total += len(files)
        return total

    return {
        "total_users":     total_users,
        "reference_pdfs":  ref_count,
        "teacher_uploads": count_uploads_by_role("teacher"),
        "student_uploads": count_uploads_by_role("student"),
        "comparisons":     0,
    }


@app.get("/admin/users")
def get_users(
    db   = Depends(get_admin_db),
    user: dict    = Depends(get_current_user),
):
    if user["role"] != "admin":
        raise HTTPException(status_code=403)

    rows = db.list_users()
    teachers = [u for u in rows if u["role"] == "teacher"]
    students = [u for u in rows if u["role"] == "student"]
    admins   = [u for u in rows if u["role"] == "admin"]
    return {"teachers": teachers, "students": students, "admins": admins}


@app.get("/admin/pdfs")
def get_reference_pdfs(
    user: dict    = Depends(get_current_user),
    db   = Depends(get_admin_db),
):
    if user["role"] != "admin":
        raise HTTPException(status_code=403)

    rows = db.list_reference_pdfs()

    return [
        {
            "name":        r["filename"],
            "uploaded_by": r["uploaded_by"],
            "uploaded_at": r["uploaded_at"][:19].replace("T", " ") if isinstance(r["uploaded_at"], str) else str(r["uploaded_at"])[:19],
        }
        for r in rows
    ]


@app.post("/admin/users/add")
def add_user(
    username:     str = Form(...),
    full_name:    str = Form(...),
    password:     str = Form(...),
    role:         str = Form(...),
    db           = Depends(get_admin_db),
    current_user: dict    = Depends(get_current_user),
):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can add users")

    existing = db.get_user_by_username(username)
    if existing:
        return {"exists": True}

    hashed = pwd_context.hash(password)
    result = db.insert_user(username, full_name, hashed, role)
    new_id = result["id"] if isinstance(result, dict) else result[0]["id"] if isinstance(result, list) else None

    create_user_db(username, role)
    return {"success": True, "user_id": new_id}


@app.delete("/admin/users/delete/{username}")
def delete_user(
    username:     str,
    db           = Depends(get_admin_db),
    current_user: dict    = Depends(get_current_user),
):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete users")

    user_obj = db.get_user_by_username(username)
    if not user_obj:
        raise HTTPException(status_code=404, detail="User not found")
    if user_obj["role"] == "admin":
        raise HTTPException(status_code=403, detail="Cannot delete admin accounts")

    from backend.user_db import drop_user_db
    drop_user_db(username, user_obj["role"])

    db.delete_user(username)
    return {"deleted": username}


@app.delete("/admin/pdfs/delete/{filename}")
def delete_pdf(
    filename: str,
    user:     dict    = Depends(get_current_user),
    db       = Depends(get_admin_db),
):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete PDFs")

    file_path = os.path.join(REFERENCE_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    db.delete_reference_pdf(filename)
    return {"message": f"{filename} deleted successfully"}


# ──────────────────────────────────────────────────────────────────────────
# SYSTEM STATUS ENDPOINTS (for offline mode monitoring)
# ──────────────────────────────────────────────────────────────────────────
@app.get("/api/system/status")
def system_status(db = Depends(get_admin_db)):
    """
    Return comprehensive system status for frontend offline badge.

    Response includes:
    - models: status of each embedding model (ok/unavailable/not_attempted)
    - database: connection status
    - offline_mode: whether OFFLINE_MODE is enabled
    - degraded: whether system is running in degraded (BM25-only) mode
    - missing_models: list of model names that failed to load
    """
    import logging
    logger = logging.getLogger(__name__)

    # Import model manager and nlp_utils for status checks
    try:
        from backend.model_manager import model_manager
        from backend.nlp_utils import check_offline_readiness, _model_type, _cached_model

        # Trigger model load if not yet attempted
        if _cached_model is None:
            from backend.nlp_utils import get_embeddings
            get_embeddings(["status probe"])

        # Get model status
        offline_status = check_offline_readiness()
        model_status = model_manager.get_model_status()

        fastembed_status = "not_attempted"
        if offline_status.get("fastembed_attempted"):
            fastembed_status = "ok" if offline_status.get("fastembed_available") else "unavailable"

        st_status = "not_attempted"
        if model_status.get("sentence_transformer", {}).get("attempted"):
            st_status = "ok" if model_status.get("sentence_transformer", {}).get("loaded") else "unavailable"

        # Also check nlp_utils fallback
        if _model_type == "sentence_transformer":
            st_status = "ok"

        fully_ready = offline_status.get("fully_offline_ready", False)

    except Exception as e:
        logger.error(f"Error checking model status: {e}")
        fastembed_status = "error"
        st_status = "error"
        fully_ready = False
        offline_status = {"missing_models": []}

    # Check database connection
    db_status = "ok"
    try:
        db.health_check()
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "error"

    # Determine if we're in degraded mode
    degraded = not fully_ready

    return {
        "models": {
            "fastembed": fastembed_status,
            "sentence_transformer": st_status
        },
        "database": db_status,
        "offline_mode": config.OFFLINE_MODE,
        "degraded": degraded,
        "missing_models": offline_status.get("missing_models", []),
        "uptime": "ok"
    }


@app.get("/api/system/health")
def health_check():
    """
    Simple health check endpoint for Docker healthcheck.
    Returns minimal JSON response.
    """
    return {
        "status": "ok",
        "offline": config.OFFLINE_MODE
    }