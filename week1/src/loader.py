import hashlib
import json
import logging
import sqlite3
import sys
from pathlib import Path

from src.sql_utils import load_sql

logger = logging.getLogger(__name__)

if sys.stdout.encoding != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def _compute_content_hash(job_title: str, company: str, description: str) -> str:
    hash_input = f"{job_title}|{company}|{description}"
    return hashlib.sha256(hash_input.encode()).hexdigest()


def load_all_jsons(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = output_dir / "jobs.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(load_sql("drop_jobs_quarantine.sql"))
    cursor.execute(load_sql("drop_jobs.sql"))
    cursor.execute(load_sql("create_jobs.sql"))
    conn.commit()

    print("🥇 Gold: Loading Silver JSON data into SQLite")

    json_files = sorted(input_dir.glob("*.json"))
    total = len(json_files)
    inserted = 0
    updated = 0
    skipped = 0

    insert_query = load_sql("insert_job.sql")
    select_hash_query = load_sql("select_content_hash.sql")
    update_query = load_sql("update_job.sql")

    if total == 0:
        logger.warning("No JSON files found to load.")
        print("\n📊 Gold Summary:")
        print(f"Total: 0 | Inserted: 0 | Updated: 0 | Skipped: 0")
        conn.close()
        return

    for json_path in json_files:
        try:
            json_content = json_path.read_text(encoding="utf-8")
            data = json.loads(json_content)

            job_title = data["job_title"]
            company = data["company"]
            description = data["description"]
            content_hash = _compute_content_hash(job_title, company, description)

            cursor.execute(
                insert_query,
                (
                    data["source_id"],
                    job_title,
                    company,
                    description,
                    None,
                    content_hash,
                ),
            )

            if cursor.rowcount > 0:
                inserted += 1
                logger.info(f"Inserted: {json_path.name}")
            else:
                cursor.execute(select_hash_query, (data["source_id"],))
                row = cursor.fetchone()
                if row and row[0] != content_hash:
                    cursor.execute(
                        update_query,
                        (
                            job_title,
                            company,
                            description,
                            None,
                            content_hash,
                            data["source_id"],
                        ),
                    )
                    updated += 1
                    logger.info(f"Updated (content changed): {json_path.name}")
                else:
                    skipped += 1
                    logger.info(f"Skipped (duplicate): {json_path.name}")

        except Exception as e:
            skipped += 1
            logger.error(f"Failed to load {json_path.name} | Reason: {e}")

    conn.commit()
    conn.close()

    print("\n📊 Gold Summary:")
    print(f"Total: {total} | Inserted: {inserted} | Updated: {updated} | Skipped: {skipped}")
    print()

