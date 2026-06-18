# Week 2 — LLM Setup & Tagging

## Project structure

```
week2/
├── data/
│   ├── jobs_d1.db      # Day 1-2 tagging database (from resources.zip)
│   └── resume.db       # Day 3-4 skill gaps (from resources.zip)
├── queries/            # SQL scripts used by MCP db_server.py
├── db_server.py        # FastMCP SQLite server (bonus)
├── tag_data.py         # Day 1-2 tagging
├── prompt_model.py     # Day 0 LLM setup
├── rate_limits.txt
├── pyproject.toml
├── .env.example        # Template for reviewers (safe to commit)
└── .env                # GOOGLE_API_KEY, TAG_OPTIMIZED (do not commit)
```

## Where to put database files from `resources.zip`

Extract `resources.zip` and place the SQLite files in **`week2/data/`**:

| File from zip | Put here | Used in |
|---|---|---|
| `jobs_d1.db` (or `job1.db`) | `week2/data/jobs_d1.db` | Day 1-2 `tag_data.py` |
| `resume.db` | `week2/data/resume.db` | Day 3-4 `find_skil_gaps.py` (later) |

You can also use your Week 1 database instead of `jobs_d1.db`:

```text
week1/data/3_gold/jobs.db
```

Run tagging with an explicit path:

```bash
uv run tag_data.py ../week1/data/3_gold/jobs.db
```

## Setup

```bash
cd week2
uv sync
cp .env.example .env   # Windows: copy .env.example .env
```

Edit `week2/.env`:

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) |
| `TAG_OPTIMIZED` | No | Set to `1` to use the shorter optimized prompt (recommended for normal runs) |

`.env` is gitignored. Commit `.env.example` only — it has no secrets and shows reviewers what to configure.

Install Ollama models (Day 0) and update `rate_limits.txt` from AI Studio.

## Day 1-2: Tagging

```bash
cd week2

# Default: data/jobs_d1.db (uses TAG_OPTIMIZED from .env if set)
uv run tag_data.py

# Custom database path
uv run tag_data.py data/jobs_d1.db

# One-off optimized run without editing .env (PowerShell)
$env:TAG_OPTIMIZED=1; uv run tag_data.py

# Bonus benchmark: baseline vs optimized (>5% improvement proof)
uv run tag_data.py --benchmark
```

**Prompt modes:** With `TAG_OPTIMIZED=1` in `.env`, normal runs use the optimized prompt automatically. Without it, the baseline (longer) prompt is used. Use `--benchmark` to compare both and print token/time savings.

## Day 0: prompt_model.py

```bash
uv run prompt_model.py llama3.1 "tell me one malaysian joke"
uv run prompt_model.py gemini-2.5-flash "hello"
cat rate_limits.txt
```

## Requirements checklist (Day 1-2)

| Requirement | Implementation |
|---|---|
| `tag_data(db_url: str)` | `tag_data.py` |
| Read `jobs`, fill empty `tech_stack` | MCP + `select_untagged_jobs.sql` |
| Batch updates (not whole table in one prompt) | `calculate_batch_settings()` from `rate_limits.txt` |
| Log each job: `Analyzed Job {id}: ...` | `process_batch()` |
| Retry on batch mismatch | `[Batch N] Attempt X failed: ...` |
| Graceful errors (no stack traces) | try/except throughout |
| Gemini models only (bonus MCP path) | `gemini-2.5-flash` default |
| MCP for SQL (bonus) | `db_server.py` + `queries/*.sql` |
| Return tokens + time (bonus) | `tag_data()` return dict + summary print |
| Quality metrics (bonus) | duplicate rate, avg skills, short tags |
| Prompt optimization proof (bonus) | `--benchmark` + `OPTIMIZED_PROMPT_TEMPLATE` |
| Time optimization (bonus) | description truncation + batch pacing |
