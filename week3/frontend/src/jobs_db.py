"""Read job listings from the Week 1 SQLite database."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "jobs.db"


def _connect() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise FileNotFoundError(
            f"jobs.db not found at {DB_PATH}. Copy week1/data/3_gold/jobs.db into frontend/data/."
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def total_jobs() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()
        return int(row["count"])


TOP_COMPANIES = 8


def _company_rows() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            """
            SELECT company, COUNT(*) AS count
            FROM jobs
            WHERE company IS NOT NULL AND company != ''
            GROUP BY company
            ORDER BY count DESC
            """
        ).fetchall()


def _top_company_names(top_n: int = TOP_COMPANIES) -> list[str]:
    return [row["company"] for row in _company_rows()[:top_n]]


def company_counts(top_n: int = TOP_COMPANIES) -> list[dict]:
    """Top companies for the pie chart; remaining jobs are grouped as Other."""
    rows = _company_rows()
    top = rows[:top_n]
    other_count = sum(row["count"] for row in rows[top_n:])
    other_employers = len(rows) - top_n

    result = [{"label": row["company"], "count": row["count"]} for row in top]
    if other_count:
        label = f"Other ({other_count} jobs, {other_employers} employers)"
        result.append({"label": label, "count": other_count, "group": "other"})
    return result


def jobs_from_other_companies(limit: int = 100, offset: int = 0) -> tuple[list[dict], int]:
    """Jobs from companies outside the top N shown individually on the pie chart."""
    top_names = _top_company_names()
    placeholders = ",".join("?" * len(top_names))
    with _connect() as conn:
        total = conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM jobs
            WHERE company NOT IN ({placeholders})
            """,
            top_names,
        ).fetchone()["count"]
        rows = conn.execute(
            f"""
            SELECT job_title, company, description
            FROM jobs
            WHERE company NOT IN ({placeholders})
            ORDER BY company, job_title
            LIMIT ? OFFSET ?
            """,
            (*top_names, limit, offset),
        ).fetchall()
    results = [
        {
            "job_title": row["job_title"] or "",
            "company": row["company"] or "",
            "description": (row["description"] or "")[:200],
        }
        for row in rows
    ]
    return results, int(total)


def title_counts(top_n: int = 10) -> list[dict]:
    """Most common job titles for the bar chart."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT job_title, COUNT(*) AS count
            FROM jobs
            WHERE job_title IS NOT NULL AND job_title != ''
            GROUP BY job_title
            ORDER BY count DESC
            LIMIT ?
            """,
            (top_n,),
        ).fetchall()
    return [{"label": row["job_title"], "count": row["count"]} for row in rows]


def search_jobs(query: str, limit: int = 100) -> tuple[list[dict], int]:
    """Search job title, company, and description. Returns (rows, total_matches)."""
    cleaned = query.strip()
    if cleaned.lower() in ("other", "others"):
        return jobs_from_other_companies(limit=limit)

    pattern = f"%{cleaned}%"
    with _connect() as conn:
        total = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM jobs
            WHERE job_title LIKE ?
               OR company LIKE ?
               OR description LIKE ?
            """,
            (pattern, pattern, pattern),
        ).fetchone()["count"]
        rows = conn.execute(
            """
            SELECT job_title, company, description
            FROM jobs
            WHERE job_title LIKE ?
               OR company LIKE ?
               OR description LIKE ?
            ORDER BY job_title
            LIMIT ?
            """,
            (pattern, pattern, pattern, limit),
        ).fetchall()
    results = [
        {
            "job_title": row["job_title"] or "",
            "company": row["company"] or "",
            "description": (row["description"] or "")[:200],
        }
        for row in rows
    ]
    return results, int(total)
