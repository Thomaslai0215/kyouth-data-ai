from pathlib import Path

QUERIES_DIR = Path(__file__).resolve().parent.parent / "queries"


def load_sql(name: str) -> str:
    """Read an SQL file from the queries folder and return its text."""
    return (QUERIES_DIR / name).read_text(encoding="utf-8").strip()
