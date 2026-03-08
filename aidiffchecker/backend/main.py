import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import List
from fastapi.responses import JSONResponse
from backend.pdf_routes import router as pdf_router

# ---------- Authentication Setup ----------
SECRET_KEY = "YOUR_SECRET_KEY"  # change this
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

fake_users_db = {
    "karima": {
        "username": "karima",
        "full_name": "Karima Jaman",
        "hashed_password": pwd_context.hash("adminpass"[:72]),  # truncate to 72 chars
        "role": "admin",
        "disabled": False,
    },
    "teacher1": {
        "username": "teacher1",
        "full_name": "Teacher One",
        "hashed_password": pwd_context.hash("teacherpass"[:72]),
        "role": "teacher",
        "disabled": False,
    },
    "student1": {
        "username": "student1",
        "full_name": "Student One",
        "hashed_password": pwd_context.hash("studentpass"[:72]),
        "role": "student",
        "disabled": False,
    },
}


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def authenticate_user(username: str, password: str):
    user = fake_users_db.get(username)
    if not user or not verify_password(password, user["hashed_password"]):
        return False
    return user

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        user = fake_users_db.get(username)
        if user is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return user

# ---------- App & Directories ----------
app = FastAPI()
origins = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "file://",
]
app.include_router(pdf_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_DIR = "backend/data/user_uploads"
REFERENCE_DIR = "backend/data/reference_pdf"
TEACHER_DIR = "backend/data/teacher_uploads"

os.makedirs(USER_DIR, exist_ok=True)
os.makedirs(REFERENCE_DIR, exist_ok=True)
os.makedirs(TEACHER_DIR, exist_ok=True)

# ---------- Auth Token Endpoint ----------
@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token = create_access_token(
        data={"sub": user["username"]}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user["role"]
    }

# ---------- Admin: Upload Reference PDFs (multiple allowed) ----------
@app.post("/upload_reference")
async def upload_reference(files: List[UploadFile] = File(...), user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can upload reference PDFs")
    saved_files = []
    
    for file in files:
        filename = file.filename
    base, ext = os.path.splitext(filename)

    counter = 1
    file_path = os.path.join(REFERENCE_DIR, filename)

    while os.path.exists(file_path):
        filename = f"{base}({counter}){ext}"
        file_path = os.path.join(REFERENCE_DIR, filename)
        counter += 1

    with open(file_path, "wb") as f:
        f.write(await file.read())

    saved_files.append(filename)
        
    
    return {"message": f"Reference PDFs uploaded: {saved_files}"}

# ---------- Teacher: Upload PDFs (multiple allowed) ----------
@app.post("/upload_teacher")
async def upload_teacher_pdfs(files: List[UploadFile] = File(...), user: dict = Depends(get_current_user)):
    if user["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can upload PDFs here")
    saved_files = []
    for file in files:
        file_path = os.path.join(TEACHER_DIR, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        saved_files.append(file.filename)
    return {"message": f"Teacher PDFs uploaded: {saved_files}"}

# ---------- Student: Upload PDF (only one allowed) ----------
@app.post("/upload_student_pdf")
async def upload_student_pdf(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can upload PDFs here")
    file_path = os.path.join(USER_DIR, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())
    return {"message": f"Student PDF uploaded: {file.filename}"}

@app.get("/admin/dashboard-stats")
def dashboard_stats():

    total_users = len(fake_users_db)

    reference_pdfs = len(os.listdir(REFERENCE_DIR))
    teacher_uploads = len(os.listdir(TEACHER_DIR))
    student_uploads = len(os.listdir(USER_DIR))

    return {
        "total_users": total_users,
        "reference_pdfs": reference_pdfs,
        "teacher_uploads": teacher_uploads,
        "student_uploads": student_uploads,
        "comparisons": 0
    }

@app.get("/admin/users")
def get_users():
    return {
        "teachers": [
            {"username": "t1", "full_name": "Teacher One"}
        ],
        "students": [
            {"username": "s1", "full_name": "Student One"}
        ],
        "admins": [
            {"username": "admin", "full_name": "Main Admin"}
        ]
    }

@app.get("/admin/pdfs")
def get_pdfs():
    files = os.listdir(REFERENCE_DIR)

    pdfs = []
    for f in files:
        path = os.path.join(REFERENCE_DIR, f)
        created = datetime.fromtimestamp(os.path.getctime(path)).strftime("%Y-%m-%d")
        pdfs.append({
            "name": f,
            "uploaded_at": created
        })

    return pdfs

@app.post("/admin/users/add")
def add_user(user: dict):
    if user["username"] == "admin":
        return {"exists": True}
    return {"success": True}

@app.delete("/admin/users/delete/{username}")
def delete_user(username: str):
    return {"deleted": username}
@app.delete("/admin/pdfs/delete/{filename}")
def delete_pdf(filename: str):

    file_path = os.path.join(REFERENCE_DIR, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    os.remove(file_path)

    return {"message": f"{filename} deleted"}
@app.get("/student/uploads/{username}")
def student_uploads(username: str):
    files = os.listdir(USER_DIR)
    return {"files": files}


@app.get("/student/result_pdfs/{username}")
def result_pdfs(username: str):
    return {"files": []}                                                                                                   