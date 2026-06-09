import json
import sqlite3
import sys
from pathlib import Path

# Force UTF-8 output encoding
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def load_all_jsons(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create database path
    db_path = output_dir / "jobs.db"
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Drop existing table if it exists (to ensure clean schema)
    cursor.execute("DROP TABLE IF EXISTS jobs")
    
    # Create table with schema
    cursor.execute("""
        CREATE TABLE jobs (
            source_id TEXT PRIMARY KEY,
            job_title TEXT,
            company TEXT,
            description TEXT,
            tech_stack TEXT
        )
    """)
    conn.commit()
    
    print("🥇 Gold: Loading Silver JSON data into SQLite")
    
    json_files = sorted(input_dir.glob("*.json"))
    total = len(json_files)
    inserted = 0
    skipped = 0
    
    if total == 0:
        print("⚠️ No JSON files found to load.")
        print("\n📊 Gold Summary:")
        print(f"Total: 0 | Inserted: 0 | Skipped: 0")
        conn.close()
        return
    
    for json_path in json_files:
        try:
            # Read JSON file
            json_content = json_path.read_text(encoding="utf-8")
            data = json.loads(json_content)
            
            # Insert with OR IGNORE for idempotency
            cursor.execute(
                """
                INSERT OR IGNORE INTO jobs 
                (source_id, job_title, company, description, tech_stack)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    data["source_id"],
                    data["job_title"],
                    data["company"],
                    data["description"],
                    None,  # tech_stack will be populated in week 2/3
                ),
            )
            
            # Check if row was actually inserted
            if cursor.rowcount > 0:
                inserted += 1
                print(f"✅ Inserted: {json_path.name}")
            else:
                skipped += 1
                print(f"⏭️ Skipped (duplicate): {json_path.name}")
                
        except Exception as e:
            skipped += 1
            print(f"❌ Failed to load {json_path.name}: {type(e).__name__}: {str(e)}")
    
    conn.commit()
    conn.close()
    
    print("\n📊 Gold Summary:")
    print(f"Total: {total} | Inserted: {inserted} | Skipped: {skipped}")
