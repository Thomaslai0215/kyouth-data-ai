import os
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pypdf import PdfReader

from jobs_db import company_counts, search_jobs, title_counts, total_jobs

WEEK3_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = Path(__file__).resolve().parent

load_dotenv(WEEK3_DIR / ".env")

app = FastAPI()
templates = Jinja2Templates(directory=str(SRC_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(SRC_DIR / "static")), name="static")


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


@app.get("/")
def home(request: Request):
    backend_url = os.getenv("BACKEND_URL", "")
    return templates.TemplateResponse(
        request=request,
        name="chat_page.html",
        context={"backend_url": backend_url},
    )


@app.get("/dashboard")
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.get("/api/jobs/stats")
def jobs_stats():
    try:
        return {
            "total": total_jobs(),
            "companies": company_counts(),
            "titles": title_counts(),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/jobs/search")
def jobs_search(q: str = Query("", min_length=1)):
    try:
        results, total = search_jobs(q)
        return {"results": results, "total": total, "shown": len(results)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/pdf-to-text")
async def pdf_to_text(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")

    try:
        pdf_text = extract_pdf_text(file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read the PDF file.") from exc

    return {"pdf_text": pdf_text}
