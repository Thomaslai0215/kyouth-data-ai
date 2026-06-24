import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WEEK3_DIR = Path(__file__).resolve().parents[2]
WEEK2_DIR = Path(__file__).resolve().parent / "week_2"

load_dotenv(WEEK3_DIR / ".env")

sys.path.insert(0, str(WEEK2_DIR))
from prompt_model import prompt_model  # noqa: E402

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = ""
    pdf_text: str = ""


class ChatResponse(BaseModel):
    reply: str


def build_prompt(message: str, pdf_text: str) -> str:
    parts: list[str] = []

    if pdf_text.strip():
        parts.append(f"Resume text:\n{pdf_text.strip()}")

    if message.strip():
        parts.append(f"User message:\n{message.strip()}")

    if not parts:
        return "Say hello briefly as a resume helper chatbot."

    return (
        "\n\n".join(parts)
        + "\n\nReply helpfully as a resume assistant. Keep the answer concise."
    )


def handle_chat(request: ChatRequest) -> ChatResponse:
    prompt = build_prompt(request.message, request.pdf_text)
    model = os.getenv("CHAT_MODEL", "gemini-2.5-flash")
    reply = prompt_model(model, prompt)
    return ChatResponse(reply=reply)


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return handle_chat(request)


@app.post("/api/chat", response_model=ChatResponse)
def chat_api_alias(request: ChatRequest) -> ChatResponse:
    """Alias so existing BACKEND_URL values still work."""
    return handle_chat(request)
