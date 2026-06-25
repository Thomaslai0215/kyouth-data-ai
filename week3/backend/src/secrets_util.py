import os
from pathlib import Path

SECRETS_DIR = Path("/run/secrets")


def read_secret(name: str) -> str:
    path = SECRETS_DIR / name
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def apply_docker_secrets() -> None:
    """Load sensitive values from Docker secrets mounted at /run/secrets."""
    api_key = read_secret("google_api_key")
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
