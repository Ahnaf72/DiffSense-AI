from fastapi import FastAPI, UploadFile, File
import os

from backend.pdf_utils import extract_text
from backend.nlp_utils import remove_citations, sentence_split
from .faiss_index import FaissIndex
from .plagiarism import similarity_score, classify

app = FastAPI()
faiss_db = FaissIndex()

os.makedirs("data/reference_pdfs", exist_ok=True)
os.makedirs("data/user_uploads", exist_ok=True)

@app.post("/upload/reference")
async def upload_reference(file: UploadFile = File(...)):
    path = f"data/reference_pdfs/{file.filename}"
    with open(path, "wb") as f:
        f.write(await file.read())

    text = remove_citations(extract_text(path))
    sentences = sentence_split(text)
    faiss_db.add(sentences, file.filename)
    return {"message": "Reference PDF added"}

@app.post("/check")
async def check_pdf(file: UploadFile = File(...)):
    path = f"data/user_uploads/{file.filename}"
    with open(path, "wb") as f:
        f.write(await file.read())

    text = remove_citations(extract_text(path))
    sentences = sentence_split(text)

    report = []
    for s in sentences:
        matches = faiss_db.search(s)
        for m, src in matches:
            score = similarity_score(s, m)
            label = classify(score)
            if label != "Original":
                report.append({
                    "sentence": s,
                    "source": src,
                    "score": round(score * 100, 2),
                    "type": label
                })
    return report
