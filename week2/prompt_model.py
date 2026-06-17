import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

# Required models from the project setup document.
GEMINI_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
}

OLLAMA_MODELS = {
    "llama3.1",
    "phi3",
    "deepseek-r1:1.5b",
}

OLLAMA_BASE_URL = "http://127.0.0.1:11434"


def _print_available_models() -> None:
    print("\n--- AVAILABLE MODELS ---")
    print("Gemini:", ", ".join(sorted(GEMINI_MODELS)))
    print("Ollama:", ", ".join(sorted(OLLAMA_MODELS)))


def prompt_model(model: str, prompt: str) -> str:
    """Route to Gemini (cloud) or Ollama (local) based on model name."""
    if model in GEMINI_MODELS or model.startswith("gemini-"):
        return _prompt_gemini(model, prompt)
    # Bonus: any other name is treated as an Ollama model (e.g. mistral, qwen2.5).
    return _prompt_ollama(model, prompt)


def _prompt_ollama(model: str, prompt: str) -> str:
    payload = json.dumps(
        {"model": model, "prompt": prompt, "stream": False}
    ).encode()
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode())
        text = data.get("response", "").strip()
        if text:
            return text
        return "[Ollama Error] Empty response from model."
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        return f"[Ollama Error] {exc.code} {exc.reason}. {body}"
    except urllib.error.URLError as exc:
        return f"[Ollama Error] {exc.reason}"
    except Exception as exc:
        return f"[Ollama Error] {exc}"


def _prompt_gemini(model: str, prompt: str) -> str:
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return (
            "[Gemini Error] Missing GOOGLE_API_KEY or GEMINI_API_KEY environment variable."
        )

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model, contents=prompt)
        text = (response.text or "").strip()
        if text:
            return text
        return "[Gemini Error] Empty response from model."
    except Exception as exc:
        return f"[Gemini Error] {exc}"


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: uv run prompt_model.py <model> <prompt>")
        sys.exit(1)

    model = sys.argv[1]
    prompt = sys.argv[2]

    print("--- RESPONSE ---")
    response = prompt_model(model, prompt)
    print(response)
    if response.startswith("[Gemini Error]") or response.startswith("[Ollama Error]"):
        _print_available_models()


if __name__ == "__main__":
    main()
