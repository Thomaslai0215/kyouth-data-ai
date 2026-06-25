import sqlite3
import sys
import time
import json
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_MODEL = "gemini-3.1-flash-lite"
# DB_PATH = "resources_eval_test/jobs_d3_eval.db"
# DB_PATH = "resources/jobs_d1.db"
DB_PATH = "data/jobs_d1.db"

def tag_data(db_url: str):
    start_time = time.time()
    total_tokens = 0
    
    BATCH_SIZE = 5  
    INTER_BATCH_DELAY = 5 
    MAX_RETRIES = 3
    RETRY_WAIT = 5
    
    try:
        conn = sqlite3.connect(db_url)
        cursor = conn.cursor()
        
        try:
            cursor.execute("ALTER TABLE jobs ADD COLUMN tech_stack TEXT")
        except sqlite3.OperationalError:
            pass
            
        cursor.execute("SELECT source_id, description FROM jobs WHERE tech_stack IS NULL OR tech_stack = ''")
        rows = cursor.fetchall()
        
        if not rows:
            print("No data to tag")
            elapsed = (time.time() - start_time) * 1000
            print(f"Total tokens used: {total_tokens}, took {elapsed:.3f}ms")
            return total_tokens, elapsed
            
        client = genai.Client()
        
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            
            prompt_data = {str(row[0]): row[1][:1000] for row in batch} 
            
            prompt = (
                "Extract technical stacks from the following job descriptions. "
                "Return strictly a JSON object where keys are the job IDs and values "
                "are comma-separated strings of the tech stack.\n"
                f"{json.dumps(prompt_data)}"
            )
            
            success = False
            attempts = 0
            
            while not success and attempts < MAX_RETRIES:
                try:
                    attempts += 1
                    
                    response = client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                        ),
                    )
                    
                    if response.usage_metadata:
                        total_tokens += response.usage_metadata.total_token_count
                    else:
                        total_tokens += len(prompt.split()) * 4
                        
                    extracted_tags = json.loads(response.text)
                    
                    update_payload = []
                    for job_id, tech_stack in extracted_tags.items():
                        update_payload.append((tech_stack, str(job_id)))
                        
                        print(f"Analyzed Job {job_id}: {tech_stack}")
                        
                    cursor.executemany("UPDATE jobs SET tech_stack = ? WHERE source_id = ?", update_payload)
                    conn.commit()
                    success = True
                    
                    time.sleep(INTER_BATCH_DELAY)
                    
                except Exception as e:
                    if attempts == MAX_RETRIES:
                        print(f"[Batch {i//BATCH_SIZE}] Failed after {MAX_RETRIES} attempts. Error: {str(e)[:100]}...")
                    else:
                        time.sleep(RETRY_WAIT)
                        
        conn.close()
        
        elapsed_ms = (time.time() - start_time) * 1000
        print(f"Total tokens used: {total_tokens}, took {elapsed_ms:.3f}ms")
        
        return total_tokens, elapsed_ms
        
    except Exception as e:
        print(f"A critical error occurred, but was handled gracefully: {e}")
        return 0, 0.0

if __name__ == "__main__":
    db_path = DB_PATH
    
    if not os.path.exists(db_path):
        print(f"Database file '{db_path}' not found. Please ensure it is in the same directory.")
    else:
        tag_data(db_path)