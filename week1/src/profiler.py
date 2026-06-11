import sqlite3
import sys
from pathlib import Path

# Force UTF-8 output encoding
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def run_data_profile(db_path: Path) -> None:
    """
    Profile the jobs database and output data quality metrics.
    """
    # Check if database exists
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Total records
        cursor.execute("SELECT COUNT(*) FROM jobs")
        total_records = cursor.fetchone()[0]
        
        # Null values count
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE job_title IS NULL OR job_title = ''")
        null_job_title = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE company IS NULL OR company = ''")
        null_company = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE description IS NULL OR description = ''")
        null_description = cursor.fetchone()[0]
        
        # Average description length
        cursor.execute("SELECT AVG(LENGTH(description)) FROM jobs WHERE description IS NOT NULL")
        avg_desc_length = cursor.fetchone()[0]
        if avg_desc_length is None:
            avg_desc_length = 0
        else:
            avg_desc_length = int(avg_desc_length)
        
        # Shortest description
        cursor.execute(
            "SELECT LENGTH(description) as desc_len, source_id, job_title FROM jobs "
            "WHERE description IS NOT NULL ORDER BY desc_len ASC LIMIT 1"
        )
        shortest_result = cursor.fetchone()
        shortest_len = shortest_result[0] if shortest_result else 0
        shortest_source_id = shortest_result[1] if shortest_result else "N/A"
        shortest_job_title = shortest_result[2] if shortest_result else "N/A"
        
        # Longest description
        cursor.execute(
            "SELECT LENGTH(description) as desc_len, source_id, job_title FROM jobs "
            "WHERE description IS NOT NULL ORDER BY desc_len DESC LIMIT 1"
        )
        longest_result = cursor.fetchone()
        longest_len = longest_result[0] if longest_result else 0
        longest_source_id = longest_result[1] if longest_result else "N/A"
        longest_job_title = longest_result[2] if longest_result else "N/A"
        
        conn.close()
        
        # Print formatted report
        print("\n--- 🔍 DATA QUALITY REPORT ---")
        print(f"📈 Total Records: {total_records}")
        print(f"❓ Missing Values -> job_title: {null_job_title}, company: {null_company}, description: {null_description}")
        print(f"📝 Avg Description Length: {avg_desc_length} chars")
        print(f"⚠️ Shortest Description: {shortest_len} chars ↳ source_id: {shortest_source_id} | job_title: {shortest_job_title}")
        print(f"🚨 Longest Description: {longest_len} chars ↳ source_id: {longest_source_id} | job_title: {longest_job_title}")
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {str(e)}")
        return
