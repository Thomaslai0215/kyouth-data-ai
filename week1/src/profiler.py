import logging
import re
import sqlite3
import sys
from pathlib import Path

from src.sql_utils import load_sql

logger = logging.getLogger(__name__)

if sys.stdout.encoding != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SPECIAL_CHAR_PATTERN = re.compile(r"[!#@$%^&*]{4,}")


def _has_too_many_special_chars(description: str) -> bool:
    """Return True if the description has long runs of special characters."""
    return bool(SPECIAL_CHAR_PATTERN.search(description))


def _determine_quality(
    job_title: str | None,
    company: str | None,
    description: str | None,
) -> str:
    """Label a job as HIGH or LOW based on simple data quality rules."""
    if not job_title or not company or not description:
        return "LOW"
    if len(description) < 100:
        return "LOW"
    if _has_too_many_special_chars(description):
        return "LOW"
    return "HIGH"


def _ensure_quality_schema(cursor: sqlite3.Cursor) -> None:
    """Add the quality column and quarantine table if they do not exist yet."""
    cursor.execute(load_sql("table_info_jobs.sql"))
    columns = {row[1] for row in cursor.fetchall()}
    if "quality" not in columns:
        cursor.execute(load_sql("add_quality_column.sql"))
    cursor.execute(load_sql("create_jobs_quarantine.sql"))


def _label_and_quarantine(cursor: sqlite3.Cursor) -> tuple[int, int]:
    """Mark each job as HIGH or LOW, then move LOW jobs to jobs_quarantine."""
    select_query = load_sql("select_all_jobs.sql")
    update_query = load_sql("update_quality.sql")

    cursor.execute(select_query)
    rows = cursor.fetchall()

    high_count = 0
    low_count = 0

    for source_id, job_title, company, description, _tech_stack, _content_hash in rows:
        quality = _determine_quality(job_title, company, description)
        cursor.execute(update_query, (quality, source_id))
        if quality == "LOW":
            low_count += 1
        else:
            high_count += 1

    cursor.execute(load_sql("clear_jobs_quarantine.sql"))
    cursor.execute(load_sql("quarantine_low_quality.sql"))
    cursor.execute(load_sql("delete_low_quality.sql"))

    return high_count, low_count


def run_data_profile(db_path: Path) -> None:
    """Check job data quality in the database and print a summary report."""
    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        _ensure_quality_schema(cursor)
        high_count, low_count = _label_and_quarantine(cursor)
        conn.commit()

        cursor.execute(load_sql("count_jobs.sql"))
        total_records = cursor.fetchone()[0]

        cursor.execute(load_sql("count_quarantined.sql"))
        quarantined = cursor.fetchone()[0]

        cursor.execute(load_sql("count_null_job_title.sql"))
        null_job_title = cursor.fetchone()[0]

        cursor.execute(load_sql("count_null_company.sql"))
        null_company = cursor.fetchone()[0]

        cursor.execute(load_sql("count_null_description.sql"))
        null_description = cursor.fetchone()[0]

        cursor.execute(load_sql("avg_description_length.sql"))
        avg_desc_length = cursor.fetchone()[0]
        if avg_desc_length is None:
            avg_desc_length = 0
        else:
            avg_desc_length = int(avg_desc_length)

        cursor.execute(load_sql("shortest_description.sql"))
        shortest_result = cursor.fetchone()
        shortest_len = shortest_result[0] if shortest_result else 0
        shortest_source_id = shortest_result[1] if shortest_result else "N/A"
        shortest_job_title = shortest_result[2] if shortest_result else "N/A"

        cursor.execute(load_sql("longest_description.sql"))
        longest_result = cursor.fetchone()
        longest_len = longest_result[0] if longest_result else 0
        longest_source_id = longest_result[1] if longest_result else "N/A"
        longest_job_title = longest_result[2] if longest_result else "N/A"

        conn.close()

        logger.info(f"Quality labeling complete: HIGH={high_count}, LOW={low_count}, quarantined={quarantined}")

        print("\n--- 🔍 DATA QUALITY REPORT ---")
        print(f"📈 Total Records (jobs): {total_records}")
        print(f"🚫 Quarantined (LOW quality): {quarantined}")
        print(f"❓ Missing Values -> job_title: {null_job_title}, company: {null_company}, description: {null_description}")
        print(f"📝 Avg Description Length: {avg_desc_length} chars")
        print(f"⚠️ Shortest Description: {shortest_len} chars ↳ source_id: {shortest_source_id} | job_title: {shortest_job_title}")
        print(f"🚨 Longest Description: {longest_len} chars ↳ source_id: {longest_source_id} | job_title: {longest_job_title}")

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return
