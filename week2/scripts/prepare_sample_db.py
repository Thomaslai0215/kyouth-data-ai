"""Create a small sample jobs_d1.db for local testing (optional)."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs_d1.db"

SAMPLE_JOBS = [
    (
        "1",
        "Software Engineer",
        "Acme Corp",
        "Build APIs with Python, Django, PostgreSQL, Docker, and AWS.",
    ),
    (
        "2",
        "ML Engineer",
        "Beta Labs",
        "Train models with Python, PyTorch, TensorFlow, SQL, and Kubernetes.",
    ),
    (
        "3",
        "Data Analyst",
        "Gamma Inc",
        "Analyze data using SQL, Python, Excel, Tableau, and Power BI.",
    ),
]


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                source_id TEXT PRIMARY KEY,
                job_title TEXT,
                company TEXT,
                description TEXT,
                tech_stack TEXT,
                content_hash TEXT
            )
            """
        )
        cursor.executemany(
            """
            INSERT OR REPLACE INTO jobs
            (source_id, job_title, company, description, tech_stack, content_hash)
            VALUES (?, ?, ?, ?, NULL, NULL)
            """,
            SAMPLE_JOBS,
        )
        conn.commit()
    print(f"Created sample database at {DB_PATH}")


if __name__ == "__main__":
    main()
