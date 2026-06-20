"""Day 1-2: Tag jobs.tech_stack using Gemini via batched prompts and MCP for SQL.

Pipeline overview:
  1. MCP loads jobs with empty tech_stack
  2. Jobs with bad descriptions → tagged from title/company (no LLM)
  3. Other jobs → batched Gemini prompts (size from rate limits)
  4. Each job's tech_stack saved to SQLite via MCP
  5. Return token/time stats and quality metrics
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from google import genai
from google.genai import types

load_dotenv(Path(__file__).resolve().parent / ".env")

WEEK2_DIR = Path(__file__).resolve().parent
DB_SERVER_PATH = WEEK2_DIR / "db_server.py"
DEFAULT_DB_PATH = WEEK2_DIR / "data" / "jobs_d1.db"
RATE_LIMITS_PATH = WEEK2_DIR / "rate_limits.txt"
DEFAULT_MODEL = "gemini-3.1-flash-lite"
FALLBACK_MODELS = (
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
)


def _mcp_client(db_url: str) -> Client:
    """Start the MCP SQLite server subprocess pointed at the given database file."""
    env = os.environ.copy()
    env["DB_PATH"] = str(Path(db_url).resolve())
    return Client(
        PythonStdioTransport(
            script_path=DB_SERVER_PATH,
            env=env,
            cwd=str(WEEK2_DIR),
        )
    )


BASELINE_PROMPT_TEMPLATE = """You are a technical recruiter assistant.
Read each job description below and extract the technical stack (programming languages,
frameworks, databases, cloud platforms, tools, and relevant technical skills).

Return ONLY a JSON array. Each item must have:
- "id": the job id exactly as given
- "tech_stack": a comma-separated string of skills (e.g. "Python, SQL, AWS")

Do not include markdown fences or extra commentary.

Jobs:
{jobs_block}
"""

OPTIMIZED_PROMPT_TEMPLATE = """Extract tech stack per job. JSON array only:
[{{"id":"<id>","tech_stack":"skill1, skill2"}}]

Include all languages, frameworks, databases, cloud, and tools from title and description.
Always return real skills — never placeholders (e.g. N/A, not specified, unknown).

{jobs_block}
"""

MAX_BATCH_ATTEMPTS = 5
DESCRIPTION_CHAR_LIMIT = 1200
BATCH_QUALITY_CAP = 8
TPM_BUDGET_FRACTION = 0.35
PROMPT_OVERHEAD_TOKENS = 120
DEFAULT_TOKENS_PER_JOB = 600
MIN_MEANINGFUL_CHARS = 40
MIN_LLM_SKILLS = 2

# Whole-stack or per-skill values that mean the model found nothing useful.
VAGUE_SKILL_TERMS: tuple[str, ...] = (
    "n/a",
    "na",
    "none",
    "null",
    "nil",
    "unknown",
    "unspecified",
    "not specified",
    "not available",
    "not applicable",
    "not mentioned",
    "no information",
    "no stack",
    "no tech",
    "no skills",
    "no technology",
    "no technologies",
    "tbd",
    "tba",
    "missing",
    "empty",
    "unclear",
    "various",
)

# Known technologies/tools — matched anywhere in title or company (longer names first).
TECH_TERMS: tuple[tuple[str, str], ...] = (
    ("machine learning", "Machine Learning"),
    ("node.js", "Node.js"),
    ("power bi", "Power BI"),
    ("spring boot", "Spring Boot"),
    ("google cloud", "Google Cloud"),
    ("alibaba cloud", "Alibaba Cloud"),
    ("javascript", "JavaScript"),
    ("typescript", "TypeScript"),
    ("postgresql", "PostgreSQL"),
    ("kubernetes", "Kubernetes"),
    ("tensorflow", "TensorFlow"),
    ("pytorch", "PyTorch"),
    ("mongodb", "MongoDB"),
    ("docker", "Docker"),
    ("python", "Python"),
    ("java", "Java"),
    ("php", "PHP"),
    ("node", "Node.js"),
    ("react", "React"),
    ("angular", "Angular"),
    ("vue", "Vue"),
    ("aws", "AWS"),
    ("azure", "Azure"),
    ("gcp", "Google Cloud"),
    ("sql", "SQL"),
    ("mysql", "MySQL"),
    ("linux", "Linux"),
    ("git", "Git"),
    ("api", "API"),
    ("rag", "RAG"),
    ("ai", "AI"),
    ("ml", "Machine Learning"),
    ("etl", "ETL"),
    ("ci/cd", "CI/CD"),
)

# Generic role/domain hints when few explicit tech terms are found.
ROLE_TERMS: tuple[tuple[str, str], ...] = (
    ("full stack", "Full Stack Development"),
    ("data engineer", "Data Engineering"),
    ("data analyst", "Data Analysis"),
    ("software engineer", "Software Engineering"),
    ("backend", "Backend Development"),
    ("frontend", "Frontend Development"),
    ("devops", "DevOps"),
    ("programmer", "Programming"),
    ("developer", "Software Development"),
    ("engineer", "Engineering"),
    ("analyst", "Analysis"),
    ("automation", "Automation"),
)

BOILERPLATE_PHRASES: tuple[str, ...] = (
    "job description",
    "key responsibilities",
    "qualifications",
    "requirements",
    "about the role",
    "about us",
    "responsibilities",
)


@dataclass
class RateLimitConfig:
    """RPM, TPM, and RPD limits for one Gemini model (from rate_limits.txt)."""

    rpm: int
    tpm: int
    rpd: int


@dataclass
class BatchSettings:
    """Computed batch size, wait time between calls, and optional RPD warning."""

    batch_size: int
    retry_delay_seconds: float
    formula_note: str
    api_calls: int = 0
    rpd_warning: str | None = None


@dataclass
class TokenUsage:
    """Running total of input/output tokens across Gemini calls."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        """Input plus output tokens."""
        return self.input_tokens + self.output_tokens

    def add(self, other: TokenUsage) -> None:
        """Add another TokenUsage into this running total."""
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens


@dataclass
class TaggingResult:
    """Internal result from one tagging run: tokens, time, count, and quality metrics."""

    tokens: TokenUsage = field(default_factory=TokenUsage)
    time_ms: float = 0.0
    jobs_tagged: int = 0
    quality: dict[str, float | int] = field(default_factory=dict)


def load_rate_limits(
    model: str = DEFAULT_MODEL, path: Path = RATE_LIMITS_PATH
) -> RateLimitConfig:
    """Read RPM/TPM/RPD for a model from rate_limits.txt (or use safe defaults)."""
    defaults = RateLimitConfig(rpm=10, tpm=250_000, rpd=250)
    if not path.exists():
        return defaults

    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) >= 4 and parts[0] == model:
            return RateLimitConfig(
                rpm=int(float(parts[1])),
                tpm=_parse_limit_value(parts[2]),
                rpd=_parse_limit_value(parts[3]),
            )
    return defaults


def _parse_limit_value(raw: str) -> int:
    """Parse a limit like 250000, 250K, or 1M into an integer."""
    raw = raw.upper().strip()
    if raw.endswith("K"):
        return int(float(raw[:-1]) * 1_000)
    if raw.endswith("M"):
        return int(float(raw[:-1]) * 1_000_000)
    if raw.endswith("B"):
        return int(float(raw[:-1]) * 1_000_000_000)
    return int(float(raw))


def estimate_avg_tokens_per_job(
    jobs: list[dict[str, str]] | None = None,
    fallback: int = DEFAULT_TOKENS_PER_JOB,
) -> int:
    """Estimate average prompt tokens per job from description/metadata size."""
    if not jobs:
        return fallback

    per_job_tokens: list[int] = []
    for job in jobs:
        text = " ".join(
            str(job.get(key, "") or "") for key in ("title", "company", "description")
        )
        per_job_tokens.append(estimate_tokens(text) + 80)

    return max(100, sum(per_job_tokens) // len(per_job_tokens))


def calculate_batch_settings(
    limits: RateLimitConfig,
    *,
    total_jobs: int = 1,
    avg_tokens_per_job: int | None = None,
) -> BatchSettings:
    """
    Work out how many jobs per Gemini call and how long to wait between calls.

    Uses TPM (token budget), RPD (daily request limit), job count, and a quality cap.
    retry_delay = 60 / RPM seconds between batches.
    """
    retry_delay = 60.0 / max(limits.rpm, 1)
    tokens_per_job = max(avg_tokens_per_job or DEFAULT_TOKENS_PER_JOB, 100)
    total = max(total_jobs, 1)

    tpm_budget = int(limits.tpm * TPM_BUDGET_FRACTION)
    tpm_batch = max(1, (tpm_budget - PROMPT_OVERHEAD_TOKENS) // tokens_per_job)
    rpd_floor = math.ceil(total / max(limits.rpd, 1))

    preferred = min(tpm_batch, total, BATCH_QUALITY_CAP)
    batch_size = max(1, rpd_floor, preferred)
    batch_size = min(batch_size, tpm_batch, total)

    api_calls = math.ceil(total / batch_size)
    rpd_warning: str | None = None
    if limits.rpd > 0 and api_calls > limits.rpd:
        rpd_warning = (
            f"Estimated API calls ({api_calls}) exceed RPD ({limits.rpd}). "
            "Increase batch size, use a higher-RPD model, or split tagging across runs."
        )
    elif rpd_floor > BATCH_QUALITY_CAP:
        rpd_warning = (
            f"RPD floor ({rpd_floor}) exceeds quality cap ({BATCH_QUALITY_CAP}); "
            f"using batch_size={batch_size} to stay within daily request limits."
        )

    formula = (
        f"retry_delay=60/RPM={retry_delay:.1f}s; "
        f"tpm_batch={tpm_batch}; rpd_floor={rpd_floor}; "
        f"batch_size=max(1, rpd_floor, min(tpm_batch, jobs={total}, cap={BATCH_QUALITY_CAP}))="
        f"{batch_size}; api_calls=ceil({total}/{batch_size})={api_calls}"
    )
    return BatchSettings(
        batch_size=batch_size,
        retry_delay_seconds=retry_delay,
        formula_note=formula,
        api_calls=api_calls,
        rpd_warning=rpd_warning,
    )


def estimate_tokens(text: str) -> int:
    """Rough token count: about 4 tokens per word."""
    return max(1, len(text.split()) * 4)


def truncate_description(description: str, limit: int = DESCRIPTION_CHAR_LIMIT) -> str:
    """Cut long job descriptions so prompts stay within token budget."""
    description = (description or "").strip()
    if len(description) <= limit:
        return description
    return description[:limit] + "..."


def _strip_boilerplate(text: str) -> str:
    """Remove generic HR phrases like 'job description' to measure real content length."""
    cleaned = re.sub(r"\s+", " ", text.lower()).strip()
    for phrase in BOILERPLATE_PHRASES:
        cleaned = cleaned.replace(phrase, " ")
    return re.sub(r"\s+", " ", cleaned).strip(" :;")


def is_insufficient_description(description: str) -> bool:
    """True when description is empty or mostly boilerplate — not usable for LLM tagging."""
    text = (description or "").strip()
    if not text:
        return True

    meaningful = _strip_boilerplate(text)
    return len(meaningful) < MIN_MEANINGFUL_CHARS


def _metadata_text(job: dict[str, str]) -> str:
    """Join title, company, and description into one string for keyword matching."""
    title = (job.get("job_title") or "").strip()
    company = (job.get("company") or "").strip()
    description = _strip_boilerplate((job.get("description") or "").strip())
    title_parts = re.split(r"[/,|&\-–()]+", title)
    parts = [title, company, *title_parts]
    if description:
        parts.append(description)
    return " ".join(part.strip() for part in parts if part.strip())


def _extract_terms(text: str, term_map: tuple[tuple[str, str], ...]) -> list[str]:
    """Find known tech or role keywords in text and return their display labels."""
    lowered = text.lower()
    found: list[str] = []
    seen: set[str] = set()
    for needle, label in sorted(term_map, key=lambda item: -len(item[0])):
        if needle in lowered:
            key = label.lower()
            if key not in seen:
                seen.add(key)
                found.append(label)
    return found


def infer_tech_stack_from_metadata(job: dict[str, str]) -> str:
    """Infer a best-effort tech stack from job title and company when description is unusable."""
    text = _metadata_text(job)
    skills = _extract_terms(text, TECH_TERMS)
    if len(skills) < 3:
        for label in _extract_terms(text, ROLE_TERMS):
            if label.lower() not in {skill.lower() for skill in skills}:
                skills.append(label)

    if not skills:
        return "software development"
    return ", ".join(skills[:8])


def _normalize_skill_text(text: str) -> str:
    """Lowercase and trim punctuation from one skill token."""
    return re.sub(r"\s+", " ", (text or "").lower().strip(" .,;:-"))


def _compact_skill_text(text: str) -> str:
    """Strip skill text down to letters/numbers only for fuzzy placeholder checks."""
    return re.sub(r"[^a-z0-9/+]", "", _normalize_skill_text(text))


def is_vague_skill(skill: str) -> bool:
    """True when a single skill token is a placeholder, not a real technology."""
    normalized = _normalize_skill_text(skill)
    if not normalized:
        return True
    compact = _compact_skill_text(skill)
    if compact in {"na", "n/a", "tbd", "tba", "nil", "null", "none"}:
        return True
    if normalized in VAGUE_SKILL_TERMS:
        return True
    if compact in {
        term.replace(" ", "").replace("/", "") for term in VAGUE_SKILL_TERMS
    }:
        return True
    for term in VAGUE_SKILL_TERMS:
        if normalized == term or normalized.startswith(f"{term} "):
            return True
    return False


def parse_meaningful_skills(tech_stack: str) -> list[str]:
    """Split a comma-separated stack and drop vague placeholders like N/A."""
    return [
        skill.strip()
        for skill in tech_stack.split(",")
        if skill.strip() and not is_vague_skill(skill.strip())
    ]


def is_vague_tech_stack(tech_stack: str) -> bool:
    """True when the full LLM tech_stack is empty or only placeholder text."""
    if not (tech_stack or "").strip():
        return True
    skills = parse_meaningful_skills(tech_stack)
    return len(skills) == 0


def merge_tech_stacks(*stacks: str, limit: int = 8) -> str:
    """Combine multiple skill lists into one deduplicated comma-separated string."""
    merged: list[str] = []
    seen: set[str] = set()
    for stack in stacks:
        for skill in parse_meaningful_skills(stack):
            key = skill.lower()
            if key not in seen:
                seen.add(key)
                merged.append(skill)
    return ", ".join(merged[:limit])


def resolve_tech_stack(job: dict[str, str], llm_stack: str) -> tuple[str, str | None]:
    """
    Pick the final tech_stack for a job.

    If the LLM answer is vague or too short, fill in from title/company metadata.
    Returns (final_stack, optional note for the log).
    """
    llm_stack = (llm_stack or "").strip()
    metadata_stack = infer_tech_stack_from_metadata(job)

    if is_vague_tech_stack(llm_stack):
        return metadata_stack, "inferred from metadata (vague LLM response)"

    if len(parse_meaningful_skills(llm_stack)) < MIN_LLM_SKILLS:
        enriched = merge_tech_stacks(llm_stack, metadata_stack)
        if enriched and enriched != llm_stack:
            return enriched, "enriched from metadata (sparse LLM response)"
        if enriched:
            return enriched, None

    return llm_stack, None


def split_jobs_for_tagging(
    jobs: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Separate unusual jobs (thin descriptions) from jobs suitable for LLM batch tagging."""
    metadata_jobs: list[dict[str, str]] = []
    llm_jobs: list[dict[str, str]] = []
    for job in jobs:
        if is_insufficient_description(job.get("description") or ""):
            metadata_jobs.append(job)
        else:
            llm_jobs.append(job)
    return metadata_jobs, llm_jobs


def build_jobs_block(jobs: list[dict[str, str]]) -> str:
    """Format a batch of jobs as text (id, title, company, description) for the prompt."""
    lines: list[str] = []
    for job in jobs:
        job_id = job["source_id"]
        job_title = (job.get("job_title") or "").strip()
        company = (job.get("company") or "").strip()
        description = truncate_description(job.get("description") or "")
        lines.append(
            f"ID: {job_id}\nTitle: {job_title}\nCompany: {company}\nDescription: {description}\n"
        )
    return "\n".join(lines)


def build_prompt(jobs: list[dict[str, str]], optimized: bool) -> str:
    """Build the full Gemini prompt (baseline or optimized template + job block)."""
    jobs_block = build_jobs_block(jobs)
    template = OPTIMIZED_PROMPT_TEMPLATE if optimized else BASELINE_PROMPT_TEMPLATE
    prompt = template.format(jobs_block=jobs_block)
    return f"Return exactly {len(jobs)} JSON objects (one per job id).\n{prompt}"


def extract_json_array(text: str) -> list[dict]:
    """Pull a JSON array out of the model response (handles markdown fences)."""
    text = text.strip()
    if not text:
        raise ValueError("Empty model response")
    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            obj_start = text.find("{")
            obj_end = text.rfind("}")
            if obj_start != -1 and obj_end != -1:
                text = text[obj_start : obj_end + 1]
        else:
            text = text[start : end + 1]
    data = json.loads(text)
    if isinstance(data, dict):
        for key in ("results", "jobs", "data", "items", "responses"):
            nested = data.get(key)
            if isinstance(nested, list):
                return nested
        raise ValueError("Response JSON object does not contain a results array")
    if not isinstance(data, list):
        raise ValueError("Response is not a JSON array")
    return data


def normalize_tag_item(item: dict) -> tuple[str, str] | None:
    """Accept common Gemini key variants for job id and tech stack."""
    job_id = ""
    for key in ("id", "job_id", "source_id", "ID", "jobId"):
        if key in item and item[key] not in (None, ""):
            job_id = str(item[key]).strip()
            break

    stack = ""
    for key in ("tech_stack", "techStack", "skills", "stack", "technical_stack"):
        if key not in item or item[key] in (None, ""):
            continue
        value = item[key]
        if isinstance(value, list):
            stack = ", ".join(
                str(skill).strip() for skill in value if str(skill).strip()
            )
        else:
            stack = str(value).strip()
        break

    if job_id and stack:
        return job_id, stack
    return None


def map_parsed_items(parsed: list, jobs: list[dict[str, str]]) -> dict[str, str]:
    """Map Gemini JSON items to {job_id: tech_stack}. Falls back to list order if ids missing."""
    id_to_stack: dict[str, str] = {}
    for item in parsed:
        if isinstance(item, dict):
            normalized = normalize_tag_item(item)
            if normalized:
                job_id, stack = normalized
                id_to_stack[job_id] = stack
        elif isinstance(item, str) and item.strip():
            continue

    expected_ids = {str(job["source_id"]) for job in jobs}
    if expected_ids.issubset(id_to_stack.keys()):
        return id_to_stack

    # Positional fallback when model returns stacks in order but wrong/missing ids.
    if len(parsed) == len(jobs):
        for job, item in zip(jobs, parsed):
            source_id = str(job["source_id"])
            if source_id in id_to_stack:
                continue
            if isinstance(item, dict):
                for key in ("tech_stack", "techStack", "skills", "stack"):
                    if key in item and item[key]:
                        value = item[key]
                        if isinstance(value, list):
                            stack = ", ".join(
                                str(v).strip() for v in value if str(v).strip()
                            )
                        else:
                            stack = str(value).strip()
                        if stack:
                            id_to_stack[source_id] = stack
                            break
            elif isinstance(item, str) and item.strip():
                id_to_stack[source_id] = item.strip()

    return id_to_stack


def is_transient_gemini_error(exc: Exception) -> bool:
    """True if the error is a rate limit or overload (worth retrying)."""
    message = str(exc).upper()
    return any(
        token in message
        for token in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "OVERLOADED")
    )


def retry_wait_seconds(retry_delay: float, attempt: int, exc: Exception) -> float:
    """How long to sleep before retrying; longer waits for rate-limit errors."""
    if is_transient_gemini_error(exc):
        return max(retry_delay * attempt, 15.0)
    return retry_delay * attempt


def count_usage(response, prompt_text: str, response_text: str) -> TokenUsage:
    """Read token counts from the API response, or estimate from text if missing."""
    usage = TokenUsage()
    metadata = getattr(response, "usage_metadata", None)
    if metadata:
        usage.input_tokens = int(getattr(metadata, "prompt_token_count", 0) or 0)
        usage.output_tokens = int(getattr(metadata, "candidates_token_count", 0) or 0)
        if usage.total == 0:
            usage.input_tokens = int(getattr(metadata, "total_token_count", 0) or 0)
    if usage.total == 0:
        usage.input_tokens = estimate_tokens(prompt_text)
        usage.output_tokens = estimate_tokens(response_text)
    return usage


async def call_gemini(
    client: genai.Client, model: str, prompt: str
) -> tuple[str, TokenUsage]:
    """Send one prompt to Gemini and return the text response plus token usage."""
    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"[Gemini Error] {exc}") from exc

    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("[Gemini Error] Empty response from model.")
    usage = count_usage(response, prompt, text)
    return text, usage


async def call_gemini_with_fallback(
    client: genai.Client, models: tuple[str, ...], prompt: str
) -> tuple[str, TokenUsage, str]:
    """Try Gemini models in order until one succeeds; return text, usage, and model used."""
    last_error: Exception | None = None
    for model in models:
        try:
            text, usage = await call_gemini(client, model, prompt)
            return text, usage, model
        except Exception as exc:
            last_error = exc
            if is_transient_gemini_error(exc):
                continue
            raise
    raise RuntimeError(str(last_error or "All Gemini models failed"))


async def mcp_run_script(
    mcp_client: Client, script_name: str, params: list | None = None
) -> dict | list:
    """Run a SQL file from queries/ via the MCP server and return parsed JSON."""
    raw = await mcp_client.call_tool(
        "run_sql_script",
        {"script_name": script_name, "params_json": json.dumps(params or [])},
    )
    payload = raw.data if hasattr(raw, "data") and raw.data is not None else raw
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


async def fetch_untagged_jobs(mcp_client: Client) -> list[dict[str, str]]:
    """Load all jobs whose tech_stack column is still empty."""
    result = await mcp_run_script(mcp_client, "select_untagged_jobs.sql")
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(result["error"])
    return result


async def update_job_stack(mcp_client: Client, source_id: str, tech_stack: str) -> None:
    """Write one job's tech_stack back to SQLite through MCP."""
    result = await mcp_run_script(
        mcp_client,
        "update_tech_stack.sql",
        [tech_stack, source_id],
    )
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(result["error"])


def measure_tagging_quality(tech_stacks: list[str]) -> dict[str, float | int]:
    """Bonus metrics: avg skills per job, duplicate rate, and very short tags."""
    if not tech_stacks:
        return {
            "jobs_measured": 0,
            "avg_skills_per_job": 0.0,
            "duplicate_skill_entries": 0,
            "duplicate_rate_percent": 0.0,
            "short_tag_count": 0,
        }

    duplicate_entries = 0
    short_tags = 0
    skill_counts: list[int] = []

    for stack in tech_stacks:
        skills = [s.strip().lower() for s in stack.split(",") if s.strip()]
        skill_counts.append(len(skills))
        if len(stack.strip()) < 5:
            short_tags += 1
        seen: set[str] = set()
        for skill in skills:
            if skill in seen:
                duplicate_entries += 1
            seen.add(skill)

    total_skills = sum(skill_counts) or 1
    return {
        "jobs_measured": len(tech_stacks),
        "avg_skills_per_job": round(sum(skill_counts) / len(tech_stacks), 2),
        "duplicate_skill_entries": duplicate_entries,
        "duplicate_rate_percent": round(duplicate_entries / total_skills * 100, 2),
        "short_tag_count": short_tags,
    }


async def tag_jobs_from_metadata(
    mcp_client: Client, jobs: list[dict[str, str]]
) -> list[str]:
    """Tag unusual jobs locally using title/company metadata when description is unusable."""
    tagged_stacks: list[str] = []
    for job in jobs:
        source_id = str(job["source_id"])
        tech_stack = infer_tech_stack_from_metadata(job)
        await update_job_stack(mcp_client, source_id, tech_stack)
        print(
            f"Analyzed Job {source_id}: {tech_stack} (inferred from metadata)",
            flush=True,
        )
        tagged_stacks.append(tech_stack)
    return tagged_stacks


async def process_batch(
    gemini_client: genai.Client,
    mcp_client: Client,
    batch_index: int,
    jobs: list[dict[str, str]],
    model: str,
    optimized: bool,
    retry_delay: float,
    usage: TokenUsage,
) -> list[str]:
    """
    Tag one batch of jobs with Gemini.

    On failure: split the batch in half, or fall back to metadata for a single job.
    """
    try:
        return await _process_batch_once(
            gemini_client,
            mcp_client,
            batch_index,
            jobs,
            model,
            optimized,
            retry_delay,
            usage,
        )
    except Exception as exc:
        if len(jobs) == 1:
            job = jobs[0]
            tech_stack = infer_tech_stack_from_metadata(job)
            await update_job_stack(mcp_client, str(job["source_id"]), tech_stack)
            print(
                f"Analyzed Job {job['source_id']}: {tech_stack} "
                f"(inferred from metadata after LLM failure: {exc})",
                flush=True,
            )
            return [tech_stack]
        if len(jobs) > 1:
            print(
                f"[Batch {batch_index}] Splitting batch of {len(jobs)} after failure: {exc}",
                flush=True,
            )
            mid = len(jobs) // 2
            left = await process_batch(
                gemini_client,
                mcp_client,
                batch_index,
                jobs[:mid],
                model,
                optimized,
                retry_delay,
                usage,
            )
            right = await process_batch(
                gemini_client,
                mcp_client,
                batch_index,
                jobs[mid:],
                model,
                optimized,
                retry_delay,
                usage,
            )
            return left + right
        raise


async def _process_batch_once(
    gemini_client: genai.Client,
    mcp_client: Client,
    batch_index: int,
    jobs: list[dict[str, str]],
    model: str,
    optimized: bool,
    retry_delay: float,
    usage: TokenUsage,
) -> list[str]:
    """One attempt to tag a batch: prompt Gemini, parse JSON, update DB, log each job."""
    tagged_stacks: list[str] = []
    expected = len(jobs)
    models = tuple(dict.fromkeys((model, *FALLBACK_MODELS)))

    for attempt in range(1, MAX_BATCH_ATTEMPTS + 1):
        try:
            prompt = build_prompt(jobs, optimized=optimized)
            response_text, batch_usage, model_used = await call_gemini_with_fallback(
                gemini_client, models, prompt
            )
            usage.add(batch_usage)
            if model_used != model:
                print(f"[Batch {batch_index}] Used fallback model: {model_used}")

            parsed = extract_json_array(response_text)
            if len(parsed) != expected:
                raise ValueError("Mismatch between batch size and response")

            id_to_stack = map_parsed_items(parsed, jobs)

            resolved: list[tuple[str, str, str | None]] = []
            for job in jobs:
                source_id = str(job["source_id"])
                tech_stack = id_to_stack.get(source_id)
                if not tech_stack:
                    for key, value in id_to_stack.items():
                        if str(key) == source_id:
                            tech_stack = value
                            break
                if not tech_stack:
                    raise ValueError(f"Missing tagged result for job {source_id}")
                final_stack, note = resolve_tech_stack(job, tech_stack)
                resolved.append((source_id, final_stack, note))

            for source_id, tech_stack, note in resolved:
                await update_job_stack(mcp_client, source_id, tech_stack)
                suffix = f" ({note})" if note else ""
                print(f"Analyzed Job {source_id}: {tech_stack}{suffix}")
                tagged_stacks.append(tech_stack)

            return tagged_stacks

        except Exception as exc:
            print(
                f"[Batch {batch_index}] Attempt {attempt} failed: {exc}",
                flush=True,
            )
            if attempt < MAX_BATCH_ATTEMPTS:
                await asyncio.sleep(retry_wait_seconds(retry_delay, attempt, exc))

    raise RuntimeError(
        f"Batch {batch_index} failed after {MAX_BATCH_ATTEMPTS} attempts"
    )


async def _tag_data_async(
    db_url: str,
    model: str = DEFAULT_MODEL,
    optimized: bool = False,
) -> TaggingResult:
    """
    Main tagging pipeline: fetch untagged jobs, batch-call Gemini, write tech_stack via MCP.

    Jobs with bad descriptions are tagged from title/company metadata instead of the LLM.
    """
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[Gemini Error] Missing GOOGLE_API_KEY or GEMINI_API_KEY.")
        return TaggingResult()

    limits = load_rate_limits(model)
    gemini_client = genai.Client(api_key=api_key)
    usage = TokenUsage()
    tagged_stacks: list[str] = []
    start = time.perf_counter()

    mcp_client = _mcp_client(db_url)

    try:
        async with mcp_client:
            jobs = await fetch_untagged_jobs(mcp_client)
            if not jobs:
                print("No data to tag")
                elapsed_ms = (time.perf_counter() - start) * 1000
                return TaggingResult(tokens=usage, time_ms=elapsed_ms, jobs_tagged=0)

            metadata_jobs, llm_jobs = split_jobs_for_tagging(jobs)
            if metadata_jobs:
                print(
                    f"Tagging {len(metadata_jobs)} unusual job(s) from metadata "
                    f"(insufficient description)"
                )
                tagged_stacks.extend(
                    await tag_jobs_from_metadata(mcp_client, metadata_jobs)
                )

            if not llm_jobs:
                elapsed_ms = (time.perf_counter() - start) * 1000
                return TaggingResult(
                    tokens=usage,
                    time_ms=elapsed_ms,
                    jobs_tagged=len(tagged_stacks),
                    quality=measure_tagging_quality(tagged_stacks),
                )

            settings = calculate_batch_settings(
                limits,
                total_jobs=len(llm_jobs),
                avg_tokens_per_job=estimate_avg_tokens_per_job(llm_jobs),
            )

            print(
                f"Model: {model} | Batch size: {settings.batch_size} | "
                f"Retry delay: {settings.retry_delay_seconds:.1f}s | "
                f"LLM jobs: {len(llm_jobs)} | API calls: {settings.api_calls}"
            )
            print(f"Rate limit formula: {settings.formula_note}")
            if settings.rpd_warning:
                print(f"[Rate Limit Warning] {settings.rpd_warning}")

            batch_index = 0
            for offset in range(0, len(llm_jobs), settings.batch_size):
                batch = llm_jobs[offset : offset + settings.batch_size]
                stacks = await process_batch(
                    gemini_client,
                    mcp_client,
                    batch_index,
                    batch,
                    model,
                    optimized,
                    settings.retry_delay_seconds,
                    usage,
                )
                tagged_stacks.extend(stacks)
                batch_index += 1
                if offset + settings.batch_size < len(llm_jobs):
                    await asyncio.sleep(settings.retry_delay_seconds)

    except Exception as exc:
        print(f"[Tagging Error] {exc}")
        elapsed_ms = (time.perf_counter() - start) * 1000
        return TaggingResult(
            tokens=usage,
            time_ms=elapsed_ms,
            jobs_tagged=len(tagged_stacks),
            quality=measure_tagging_quality(tagged_stacks),
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    return TaggingResult(
        tokens=usage,
        time_ms=elapsed_ms,
        jobs_tagged=len(tagged_stacks),
        quality=measure_tagging_quality(tagged_stacks),
    )


def tag_data(db_url: str) -> dict[str, float | int]:
    """
    Public entry point for Day 1-2 tagging.

    Tags empty tech_stack rows, prints summary, returns token/time/quality stats.
    """
    optimized = os.environ.get("TAG_OPTIMIZED", "").lower() in {"1", "true", "yes"}
    model = os.environ.get("TAG_MODEL", DEFAULT_MODEL)
    result = asyncio.run(_tag_data_async(db_url, model=model, optimized=optimized))

    print(f"Total tokens used: {result.tokens.total}, took {result.time_ms:.3f}ms")
    if result.quality:
        print("--- TAGGING QUALITY ---")
        for key, value in result.quality.items():
            print(f"{key}: {value}")

    return {
        "input_tokens": result.tokens.input_tokens,
        "output_tokens": result.tokens.output_tokens,
        "total_tokens": result.tokens.total,
        "time_ms": round(result.time_ms, 3),
        "jobs_tagged": result.jobs_tagged,
        **{f"quality_{k}": v for k, v in result.quality.items()},
    }


async def _clear_tech_stack(db_url: str) -> None:
    """Empty all tech_stack values (used before benchmark re-runs)."""
    mcp_client = _mcp_client(db_url)
    async with mcp_client:
        await mcp_run_script(mcp_client, "clear_tech_stack.sql")


def _print_tagging_summary(label: str, result: TaggingResult) -> None:
    """Print the same style of summary as a normal tag_data() run."""
    print(f"--- {label} SUMMARY ---")
    print(f"Total tokens used: {result.tokens.total}, took {result.time_ms:.3f}ms")
    print(
        f"Input tokens: {result.tokens.input_tokens}, "
        f"Output tokens: {result.tokens.output_tokens}"
    )
    print(f"Jobs tagged: {result.jobs_tagged}")
    if result.quality:
        print("--- TAGGING QUALITY ---")
        for key, value in result.quality.items():
            print(f"{key}: {value}")


def _print_benchmark_comparison(
    baseline: TaggingResult, optimized: TaggingResult
) -> None:
    """Side-by-side comparison after both benchmark runs."""
    print("=== COMPARISON SUMMARY ===")
    print(f"Baseline tokens: {baseline.tokens.total}")
    print(f"Optimized tokens: {optimized.tokens.total}")
    print(f"Baseline time: {baseline.time_ms:.3f}ms")
    print(f"Optimized time: {optimized.time_ms:.3f}ms")
    print(f"Baseline jobs tagged: {baseline.jobs_tagged}")
    print(f"Optimized jobs tagged: {optimized.jobs_tagged}")

    if baseline.quality and optimized.quality:
        b_avg = baseline.quality.get("avg_skills_per_job", 0)
        o_avg = optimized.quality.get("avg_skills_per_job", 0)
        print(f"Baseline avg skills/job: {b_avg}")
        print(f"Optimized avg skills/job: {o_avg}")

    print("")
    if baseline.tokens.total > 0:
        token_saving = (
            (baseline.tokens.total - optimized.tokens.total) / baseline.tokens.total
        ) * 100
        token_delta = baseline.tokens.total - optimized.tokens.total
        print(
            f"Token change: {token_saving:.1f}% "
            f"({token_delta:+d} tokens, target >5% reduction)"
        )

    if baseline.time_ms > 0:
        time_saving = ((baseline.time_ms - optimized.time_ms) / baseline.time_ms) * 100
        time_delta = baseline.time_ms - optimized.time_ms
        print(
            f"Time change: {time_saving:.1f}% "
            f"({time_delta:+.3f}ms, target >5% reduction)"
        )


async def run_benchmark(db_url: str, model: str = DEFAULT_MODEL) -> None:
    """Compare baseline vs optimized prompts (bonus proof). Resets tech_stack between runs."""
    print("=== BENCHMARK: prompt optimization (baseline vs optimized) ===")
    print("Benchmark mode forces both runs explicitly:")
    print("- Baseline: optimized=False (long prompt)")
    print("- Optimized: optimized=True (short prompt)")
    print("TAG_OPTIMIZED env is ignored in this benchmark.")
    print("")

    await _clear_tech_stack(db_url)

    print("=== BASELINE RUN (optimized=False) ===")
    baseline = await _tag_data_async(db_url, model=model, optimized=False)
    print("")
    _print_tagging_summary("BASELINE", baseline)

    await _clear_tech_stack(db_url)

    print("")
    print("=== OPTIMIZED RUN (optimized=True) ===")
    optimized = await _tag_data_async(db_url, model=model, optimized=True)
    print("")
    _print_tagging_summary("OPTIMIZED", optimized)

    print("")
    _print_benchmark_comparison(baseline, optimized)


def main() -> None:
    """CLI: tag a database, or run --benchmark to compare baseline vs optimized prompts."""
    parser = argparse.ArgumentParser(description="Tag job tech stacks with Gemini.")
    parser.add_argument(
        "db_url",
        nargs="?",
        default=str(DEFAULT_DB_PATH),
        help="Path to SQLite database (default: data/jobs_d1.db)",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run baseline vs optimized comparison (bonus proof)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Gemini model name (default: gemini-3.1-flash-lite)",
    )
    args = parser.parse_args()

    if args.benchmark:
        asyncio.run(run_benchmark(args.db_url, model=args.model))
        return

    os.environ["TAG_MODEL"] = args.model
    tag_data(args.db_url)


if __name__ == "__main__":
    main()
