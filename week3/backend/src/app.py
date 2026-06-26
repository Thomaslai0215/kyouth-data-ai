import os
import sys
import tempfile
import json
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WEEK3_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parent.parent
WEEK2_DIR = Path(__file__).resolve().parent / "week_2"
DB_PATH = BACKEND_DIR / "data" / "jobs.db"

load_dotenv(WEEK3_DIR / ".env")
FRONTEND_PORT = os.getenv("FRONTEND_PORT", "8000")

from secrets_util import apply_docker_secrets

apply_docker_secrets()

sys.path.insert(0, str(WEEK2_DIR))
from find_skill_gaps import (  # noqa: E402
    SkillGapResult,
    find_skill_gaps,
    format_skill_gap_result,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{FRONTEND_PORT}",
        f"http://127.0.0.1:{FRONTEND_PORT}",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = ""
    pdf_text: str = ""


class ChatResponse(BaseModel):
    reply: str


def chat_with_model(message: str) -> str:
    model = os.getenv("CHAT_MODEL", "llama3.1")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    prompt = message.strip() or "Say hello briefly."
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    request = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode())
        text = data.get("response", "").strip()
        return text or "I could not generate a reply right now."
    except urllib.error.HTTPError as exc:
        return f"[Chat model error] {exc.code} {exc.reason}"
    except urllib.error.URLError as exc:
        return f"[Chat model error] {exc.reason}"
    except Exception as exc:
        return f"[Chat model error] {exc}"


def run_skill_gap_analysis(resume_text: str) -> SkillGapResult:
    if not DB_PATH.is_file():
        return SkillGapResult(gaps=[], demand_statistics={}, total_tokens=0, time_ms=0.0)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(resume_text)
        tmp_path = tmp.name

    try:
        return find_skill_gaps(tmp_path, str(DB_PATH))
    finally:
        os.unlink(tmp_path)


def wants_skill_gap(message: str) -> bool:
    """Empty message or explicit analysis request → run find_skill_gaps."""
    if not message:
        return True
    text = message.lower()
    return "start analysis" in text or "skill gap" in text or text == "analyze"


def chat_about_resume(resume_text: str, message: str) -> str:
    question = message or "Summarize this resume briefly."
    prompt = (
        f"Resume text:\n{resume_text[:3000]}\n\n"
        f"User question: {question}\n\n"
        "Answer using only the resume above."
    )
    return chat_with_model(prompt)


def handle_chat(request: ChatRequest) -> ChatResponse:
    resume_text = request.pdf_text.strip()
    message = request.message.strip()

    if not resume_text and not message:
        return ChatResponse(
            reply="Send a message to chat, or upload a resume PDF."
        )

    if not resume_text:
        return ChatResponse(reply=chat_with_model(message))

    if wants_skill_gap(message):
        result = run_skill_gap_analysis(resume_text)
        if not result.gaps:
            return ChatResponse(
                reply=(
                    "No skill gaps found. Make sure the jobs database has tagged tech_stack values."
                )
            )
        return ChatResponse(reply=format_skill_gap_result(result))

    return ChatResponse(reply=chat_about_resume(resume_text, message))


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return handle_chat(request)


@app.post("/api/chat", response_model=ChatResponse)
def chat_api_alias(request: ChatRequest) -> ChatResponse:
    return handle_chat(request)
