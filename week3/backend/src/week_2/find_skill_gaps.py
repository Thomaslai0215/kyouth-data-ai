import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List

from google import genai
from google.genai import types
from dotenv import load_dotenv
from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = str(DATA_DIR / "jobs.db")
RESUME_PATH = str(DATA_DIR / "resume_d3.txt")

load_dotenv(BACKEND_DIR.parent / ".env")

GEMINI_MODEL = "gemini-3.1-flash-lite"


class SkillGapResult(BaseModel):
    gaps: List[str]
    demand_statistics: Dict[str, int]
    total_tokens: int
    time_ms: float


class ResumeExtraction(BaseModel):
    technical_skills: List[str]


def parse_skills(skill_text: str) -> List[str]:
    if not skill_text:
        return []

    text = skill_text.lower()
    text = text.replace("a/b testing", "ab_testing_placeholder")
    text = text.replace("ci/cd", "cicd_placeholder")

    raw_skills = re.split(r"[,/]", text)
    cleaned_skills = set()
    for s in raw_skills:
        s = s.strip()
        s = s.replace("ab_testing_placeholder", "a/b testing")
        s = s.replace("cicd_placeholder", "ci/cd")
        if s:
            cleaned_skills.add(s)

    return list(cleaned_skills)


def is_jailbreak_attempt(text: str) -> bool:
    suspicious = [
        "ignore previous instructions",
        "disregard",
        "bypass",
        "system prompt",
        "you are now",
        "forget all",
        "developer mode",
    ]
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in suspicious)


def find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult:
    start_time = time.time()
    total_tokens = 0
    max_retries = 3
    retry_wait = 5

    try:
        with open(input_file_path, encoding="utf-8") as f:
            resume_text = f.read()

        resume_text = resume_text[:3000]

        if is_jailbreak_attempt(resume_text):
            print("[SECURITY WARNING] Potential prompt injection detected. Sanitizing input...")
            resume_text = "Extract technical skills only from this data: " + re.sub(
                r"[^a-zA-Z0-9.,/\s]", "", resume_text
            )

        client = genai.Client()
        prompt = f"""
        Extract only the hard technical skills (programming languages, frameworks, cloud platforms, tools) from the following resume.
        Ignore soft skills like 'leadership', 'management', and ignore certifications.
        <resume>
        {resume_text}
        </resume>
        """

        resume_skills_raw: list[str] = []
        attempts = 0
        while attempts < max_retries:
            try:
                attempts += 1
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ResumeExtraction,
                        temperature=0.0,
                    ),
                )

                if response.usage_metadata:
                    total_tokens += response.usage_metadata.total_token_count
                else:
                    total_tokens += len(prompt.split()) * 4

                result_dict = json.loads(response.text)
                resume_skills_raw = result_dict.get("technical_skills", [])
                break
            except Exception as e:
                if attempts == max_retries:
                    print(f"LLM extraction failed after {max_retries} attempts: {e}")
                time.sleep(retry_wait)

        conn = sqlite3.connect(db_url)
        cursor = conn.cursor()
        cursor.execute("SELECT tech_stack FROM jobs WHERE tech_stack IS NOT NULL")
        rows = cursor.fetchall()
        conn.close()

        db_skills_pool: list[str] = []
        for row in rows:
            db_skills_pool.extend(parse_skills(row[0]))

        resume_parsed: set[str] = set()
        for skill in resume_skills_raw:
            resume_parsed.update(parse_skills(skill))

        skill_demand: dict[str, int] = {}
        for skill in db_skills_pool:
            skill_demand[skill] = skill_demand.get(skill, 0) + 1

        db_unique_skills = set(skill_demand.keys())
        gap_set = db_unique_skills - resume_parsed
        sorted_gaps = sorted(gap_set)
        gap_stats = {skill: skill_demand[skill] for skill in sorted_gaps}
        gap_stats = dict(sorted(gap_stats.items(), key=lambda item: item[1], reverse=True))

        elapsed_ms = (time.time() - start_time) * 1000
        return SkillGapResult(
            gaps=sorted_gaps,
            demand_statistics=gap_stats,
            total_tokens=total_tokens,
            time_ms=elapsed_ms,
        )

    except Exception as e:
        print(f"Gracefully handled error: {e}")
        return SkillGapResult(gaps=[], demand_statistics={}, total_tokens=0, time_ms=0.0)


def format_skill_gap_result(result: SkillGapResult) -> str:
    """Same text format as running find_skill_gaps.py from the terminal."""
    lines = [
        f"gaps={result.gaps} time={result.time_ms:.0f} tokens={result.total_tokens}",
        "",
        "--- BONUS: Top 5 Most In-Demand Missing Skills ---",
    ]
    for skill, count in list(result.demand_statistics.items())[:5]:
        lines.append(
            f"Skill: {skill.ljust(20)} | Missing from resume, but required by {count} job(s)"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    db_path = DB_PATH
    resume_path = RESUME_PATH

    if not os.path.exists(db_path) or not os.path.exists(resume_path):
        print("Ensure jobs.db and resume_d3.txt exist in backend/data/.")
        sys.exit(1)

    final_result = find_skill_gaps(resume_path, db_path)
    print(format_skill_gap_result(final_result))
