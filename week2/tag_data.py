"""Day 1-2: Tag jobs.tech_stack using Gemini via batched prompts and MCP for SQL."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from google import genai

load_dotenv(Path(__file__).resolve().parent / ".env")

WEEK2_DIR = Path(__file__).resolve().parent
DB_SERVER_PATH = WEEK2_DIR / "db_server.py"
DEFAULT_DB_PATH = WEEK2_DIR / "data" / "jobs_d1.db"
RATE_LIMITS_PATH = WEEK2_DIR / "rate_limits.txt"
DEFAULT_MODEL = "gemini-2.5-flash"


def _mcp_client(db_url: str) -> Client:
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

{jobs_block}
"""

MAX_BATCH_ATTEMPTS = 3
DESCRIPTION_CHAR_LIMIT = 1200


@dataclass
class RateLimitConfig:
    rpm: int
    tpm: int
    rpd: int


@dataclass
class BatchSettings:
    batch_size: int
    retry_delay_seconds: float
    formula_note: str


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, other: TokenUsage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens


@dataclass
class TaggingResult:
    tokens: TokenUsage = field(default_factory=TokenUsage)
    time_ms: float = 0.0
    jobs_tagged: int = 0
    quality: dict[str, float | int] = field(default_factory=dict)


def load_rate_limits(
    model: str = DEFAULT_MODEL, path: Path = RATE_LIMITS_PATH
) -> RateLimitConfig:
    """Load RPM/TPM/RPD for a Gemini model from rate_limits.txt."""
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
    raw = raw.upper().strip()
    if raw.endswith("K"):
        return int(float(raw[:-1]) * 1_000)
    if raw.endswith("M"):
        return int(float(raw[:-1]) * 1_000_000)
    if raw.endswith("B"):
        return int(float(raw[:-1]) * 1_000_000_000)
    return int(float(raw))


def calculate_batch_settings(
    limits: RateLimitConfig, avg_tokens_per_job: int = 600
) -> BatchSettings:
    """
    Derive batch size and retry delay from rate limits.

    - retry_delay = 60 / RPM (seconds between API calls)
    - batch_size from TPM budget: use ~35% of TPM per request, capped by RPM headroom
    """
    retry_delay = 60.0 / max(limits.rpm, 1)
    prompt_overhead = 120
    tokens_per_job = max(avg_tokens_per_job, 100)
    tpm_budget_per_request = int(limits.tpm * 0.35)
    batch_size = max(
        1, min(8, (tpm_budget_per_request - prompt_overhead) // tokens_per_job)
    )
    formula = (
        f"retry_delay=60/RPM={retry_delay:.1f}s; "
        f"batch_size=min(8, floor(TPM*0.35-{prompt_overhead})/{tokens_per_job})={batch_size}"
    )
    return BatchSettings(
        batch_size=batch_size,
        retry_delay_seconds=retry_delay,
        formula_note=formula,
    )


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()) * 4)


def truncate_description(description: str, limit: int = DESCRIPTION_CHAR_LIMIT) -> str:
    description = (description or "").strip()
    if len(description) <= limit:
        return description
    return description[:limit] + "..."


def build_jobs_block(jobs: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for job in jobs:
        job_id = job["source_id"]
        description = truncate_description(job.get("description") or "")
        lines.append(f"ID: {job_id}\nDescription: {description}\n")
    return "\n".join(lines)


def build_prompt(jobs: list[dict[str, str]], optimized: bool) -> str:
    jobs_block = build_jobs_block(jobs)
    template = OPTIMIZED_PROMPT_TEMPLATE if optimized else BASELINE_PROMPT_TEMPLATE
    return template.format(jobs_block=jobs_block)


def extract_json_array(text: str) -> list[dict]:
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("Response is not a JSON array")
    return data


def count_usage(response, prompt_text: str, response_text: str) -> TokenUsage:
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
    response = await client.aio.models.generate_content(model=model, contents=prompt)
    text = (response.text or "").strip()
    usage = count_usage(response, prompt, text)
    return text, usage


async def mcp_run_script(
    mcp_client: Client, script_name: str, params: list | None = None
) -> dict | list:
    raw = await mcp_client.call_tool(
        "run_sql_script",
        {"script_name": script_name, "params_json": json.dumps(params or [])},
    )
    payload = raw.data if hasattr(raw, "data") and raw.data is not None else raw
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


async def fetch_untagged_jobs(mcp_client: Client) -> list[dict[str, str]]:
    result = await mcp_run_script(mcp_client, "select_untagged_jobs.sql")
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(result["error"])
    return result


async def update_job_stack(
    mcp_client: Client, source_id: str, tech_stack: str
) -> None:
    result = await mcp_run_script(
        mcp_client,
        "update_tech_stack.sql",
        [tech_stack, source_id],
    )
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(result["error"])


def measure_tagging_quality(tech_stacks: list[str]) -> dict[str, float | int]:
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
    tagged_stacks: list[str] = []
    expected = len(jobs)

    for attempt in range(1, MAX_BATCH_ATTEMPTS + 1):
        try:
            prompt = build_prompt(jobs, optimized=optimized)
            response_text, batch_usage = await call_gemini(
                gemini_client, model, prompt
            )
            usage.add(batch_usage)

            parsed = extract_json_array(response_text)
            if len(parsed) != expected:
                raise ValueError("Mismatch between batch size and response")

            id_to_stack: dict[str, str] = {}
            for item in parsed:
                job_id = str(item.get("id", "")).strip()
                stack = str(item.get("tech_stack", "")).strip()
                if not job_id or not stack:
                    raise ValueError("Missing id or tech_stack in response item")
                id_to_stack[job_id] = stack

            for job in jobs:
                source_id = job["source_id"]
                if source_id not in id_to_stack:
                    raise ValueError(f"Missing tagged result for job {source_id}")
                tech_stack = id_to_stack[source_id]
                await update_job_stack(mcp_client, source_id, tech_stack)
                print(f"Analyzed Job {source_id}: {tech_stack}")
                tagged_stacks.append(tech_stack)

            return tagged_stacks

        except Exception as exc:
            print(
                f"[Batch {batch_index}] Attempt {attempt} failed: {exc}",
                flush=True,
            )
            if attempt < MAX_BATCH_ATTEMPTS:
                await asyncio.sleep(retry_delay * attempt)
            else:
                for job in jobs:
                    fallback = "general software development"
                    await update_job_stack(mcp_client, job["source_id"], fallback)
                    print(
                        f"Analyzed Job {job['source_id']}: {fallback} (fallback)",
                        flush=True,
                    )
                    tagged_stacks.append(fallback)
                return tagged_stacks

    return tagged_stacks


async def _tag_data_async(
    db_url: str,
    model: str = DEFAULT_MODEL,
    optimized: bool = False,
) -> TaggingResult:
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[Gemini Error] Missing GOOGLE_API_KEY or GEMINI_API_KEY.")
        return TaggingResult()

    limits = load_rate_limits(model)
    settings = calculate_batch_settings(limits)
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

            print(
                f"Model: {model} | Batch size: {settings.batch_size} | "
                f"Retry delay: {settings.retry_delay_seconds:.1f}s"
            )
            print(f"Rate limit formula: {settings.formula_note}")

            batch_index = 0
            for offset in range(0, len(jobs), settings.batch_size):
                batch = jobs[offset : offset + settings.batch_size]
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
                if offset + settings.batch_size < len(jobs):
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
    Read untagged jobs from SQLite via MCP, populate tech_stack with Gemini,
    and return token/time statistics.
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
    mcp_client = _mcp_client(db_url)
    async with mcp_client:
        await mcp_run_script(mcp_client, "clear_tech_stack.sql")


async def run_benchmark(db_url: str, model: str = DEFAULT_MODEL) -> None:
    """Compare baseline vs optimized prompts (bonus proof). Resets tech_stack between runs."""
    print("=== BENCHMARK: prompt optimization (baseline vs optimized) ===")
    await _clear_tech_stack(db_url)

    baseline = await _tag_data_async(db_url, model=model, optimized=False)
    print(
        f"Baseline -> tokens: {baseline.tokens.total}, time: {baseline.time_ms:.3f}ms"
    )

    await _clear_tech_stack(db_url)

    optimized = await _tag_data_async(db_url, model=model, optimized=True)
    print(
        f"Optimized -> tokens: {optimized.tokens.total}, time: {optimized.time_ms:.3f}ms"
    )

    if baseline.tokens.total > 0:
        token_saving = (
            (baseline.tokens.total - optimized.tokens.total) / baseline.tokens.total
        ) * 100
        print(f"Token change: {token_saving:.1f}% (target >5% reduction)")

    if baseline.time_ms > 0:
        time_saving = ((baseline.time_ms - optimized.time_ms) / baseline.time_ms) * 100
        print(f"Time change: {time_saving:.1f}% (target >5% reduction)")


def main() -> None:
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
        help="Gemini model name (default: gemini-2.5-flash)",
    )
    args = parser.parse_args()

    if args.benchmark:
        asyncio.run(run_benchmark(args.db_url, model=args.model))
        return

    os.environ["TAG_MODEL"] = args.model
    tag_data(args.db_url)


if __name__ == "__main__":
    main()
