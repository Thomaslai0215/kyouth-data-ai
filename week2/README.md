# Week 2 — LLM Setup & Tagging

Technical manual for Day 0–4: local/cloud LLM setup, job tech-stack tagging, and resume skill-gap analysis.

## General submission notes

- Push all work into your **public** Git repository — only files in the repo are evaluated.
- Double-check file names and paths match the assignment spec.
- Submit before the cutoff; early submission is encouraged.
- Do **not** commit secrets (`.env` is gitignored). Commit `.env.example` instead.

---

## Project overview

This project builds a small LLM-powered data pipeline in three stages:

| Day | Script | Goal |
|---|---|---|
| Day 0 | `prompt_model.py` | Route prompts to Gemini (cloud) or Ollama (local); record rate limits |
| Day 1–2 | `tag_data.py` | Read untagged jobs from SQLite, infer `tech_stack` with Gemini, write back via MCP |
| Day 3–4 | `find_skill_gaps.py` | Extract resume skills with Gemini, compare against job demand, return deterministic gaps |

**End-to-end flow:** jobs are tagged in the database → tagged `tech_stack` values define market demand → a resume is parsed → missing skills (`gaps`) are computed with plain set math so results are reproducible.

### Project structure

```
week2/
├── data/
│   ├── jobs_d1.db      # Day 1-2 tagging database (from resources.zip)
│   └── resume_d3.txt   # Day 3-4 resume input (from resources.zip)
├── queries/            # SQL scripts used by MCP db_server.py
├── db_server.py        # FastMCP SQLite server (bonus)
├── tag_data.py         # Day 1-2 tagging
├── find_skill_gaps.py  # Day 3-4 skill gaps
├── prompt_model.py     # Day 0 LLM setup
├── rate_limits.txt
├── pyproject.toml
├── .env.example        # Template for reviewers (safe to commit)
└── .env                # GOOGLE_API_KEY, TAG_OPTIMIZED (do not commit)
```

---

## Setup instructions

### Prerequisites

| Tool | Version / notes |
|---|---|
| Python | 3.12+ (managed by `uv`) |
| [uv](https://docs.astral.sh/uv/) | Package manager — installs deps and runs scripts |
| Gemini API key | From [Google AI Studio](https://aistudio.google.com/apikey) |
| Ollama (Day 0 only) | Local models: `llama3.1`, `phi3`, `deepseek-r1:1.5b` |

### Install dependencies

```bash
cd week2
uv sync
```

### Configure environment variables

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

Edit `week2/.env`:

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | Gemini API key |
| `TAG_OPTIMIZED` | No | Set to `1` for the shorter optimized tagging prompt (recommended) |

`.env` is gitignored. Commit `.env.example` only — it has no secrets and shows reviewers what to configure.

### Data files

Extract `resources.zip` and place files in **`week2/data/`**:

| File from zip | Put here | Used in |
|---|---|---|
| `jobs_d1.db` (or `job1.db`) | `week2/data/jobs_d1.db` | Day 1–2 `tag_data.py` |
| `resume_d3.txt` | `week2/data/resume_d3.txt` | Day 3–4 `find_skill_gaps.py` |

You can also use your Week 1 database:

```text
week1/data/3_gold/jobs.db
```

Run tagging with an explicit path:

```bash
uv run tag_data.py ../week1/data/3_gold/jobs.db
```

### Day 0 extras

Install Ollama models and update `rate_limits.txt` from AI Studio (RPM/TPM for your chosen Gemini model).

---

## Usage

All commands assume you are in the `week2/` directory.

### Day 0: `prompt_model.py`

```bash
uv run prompt_model.py llama3.1 "tell me one malaysian joke"
uv run prompt_model.py gemini-2.5-flash "hello"
cat rate_limits.txt
```

**Expected output:** model response text printed to stdout; `rate_limits.txt` holds RPM/TPM values used by later scripts.

### Day 1–2: `tag_data.py`

```bash
# Default: data/jobs_d1.db (uses TAG_OPTIMIZED from .env if set)
uv run tag_data.py

# Custom database path
uv run tag_data.py data/jobs_d1.db

# One-off optimized run without editing .env (PowerShell)
$env:TAG_OPTIMIZED=1; uv run tag_data.py

# Bonus benchmark: baseline vs optimized (>5% improvement proof)
uv run tag_data.py --benchmark
```

**Prompt modes:** With `TAG_OPTIMIZED=1` in `.env`, normal runs use the optimized prompt. Without it, the baseline (longer) prompt is used. `--benchmark` runs both and prints per-run summaries plus a comparison block.

**Expected output (normal run):**

```text
Analyzed Job 91347112: Python, Java, Spring Framework, ...
Total tokens used: 2416, took 8548.573ms
--- TAGGING QUALITY ---
jobs_measured: 8
avg_skills_per_job: 6.75
...
```

**Expected output (`--benchmark`):** `=== BASELINE RUN ===` → full tagging log + summary → `=== OPTIMIZED RUN ===` → full log + summary → `=== COMPARISON SUMMARY ===` with token/time deltas.

### Day 3–4: `find_skill_gaps.py`

```bash
# Default: data/resume_d3.txt + data/jobs_d1.db
uv run find_skill_gaps.py

# Resume by name in data/ (.txt or .pdf)
uv run find_skill_gaps.py my_resume
uv run find_skill_gaps.py my_resume.pdf

# Custom resume + database
uv run find_skill_gaps.py data/resume_d3.txt data/jobs_d1.db

# Bonus benchmark: baseline vs optimized (>5% token/time proof)
uv run find_skill_gaps.py --benchmark
```

**Expected output (normal run):**

```text
--- SKILL GAPS ---
gaps=['ai', 'api', 'aws', ...]

--- USAGE ---
time=754.097
tokens=266

--- DEMAND STATISTICS ---
Skills in job market (unique): 43
Skills on resume: 6
Skill gaps (missing): 41
...
```

**Determinism:** two consecutive runs return the **same** `gaps` list. The LLM only extracts resume skills (`temperature=0`); gap logic is `sorted(job_skills - resume_skills)`.

**Expected output (`--benchmark`):** baseline summary → optimized summary → comparison with `Gaps identical: True/False`.

---

## API / function reference

### `prompt_model.py`

#### `prompt_model(model: str, prompt: str) -> str`

| | |
|---|---|
| **Purpose** | Send a prompt to Gemini (cloud) or Ollama (local) based on model name |
| **Inputs** | `model` — e.g. `gemini-2.5-flash`, `llama3.1`; `prompt` — user text |
| **Outputs** | Model response string |

### `tag_data.py`

#### `tag_data(db_url: str) -> dict[str, float | int]`

| | |
|---|---|
| **Purpose** | Tag all jobs with empty `tech_stack` in the SQLite database via Gemini + MCP |
| **Inputs** | `db_url` — path to SQLite file (e.g. `data/jobs_d1.db`) |
| **Outputs** | Dict with `input_tokens`, `output_tokens`, `total_tokens`, `time_ms`, `jobs_tagged`, and `quality_*` metrics |

**Module interactions:** `tag_data.py` spawns `db_server.py` as an MCP subprocess, runs SQL from `queries/`, batches jobs according to `rate_limits.txt`, and calls Gemini with retry on transient errors.

**Key helpers:**

| Function | Purpose |
|---|---|
| `calculate_batch_settings()` | Derive batch size and retry delay from RPM/TPM |
| `infer_tech_stack_from_metadata()` | Tag unusual jobs (empty/boilerplate descriptions) without LLM |
| `resolve_tech_stack()` | Enrich vague LLM answers (N/A, single skill) |
| `process_batch()` | One Gemini call + MCP update for a job batch |

### `find_skill_gaps.py`

#### `find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult`

| | |
|---|---|
| **Purpose** | Compare resume skills against tagged job demand; return missing skills |
| **Inputs** | `input_file_path` — resume path or bare name under `data/`; `db_url` — tagged jobs DB |
| **Outputs** | `SkillGapResult` (Pydantic `BaseModel`) |

#### `SkillGapResult`

| Field | Type | Description |
|---|---|---|
| `gaps` | `list[str]` | Sorted, lowercase skills demanded by jobs but absent from resume |
| `tokens` | `int` | Total LLM tokens used for resume extraction |
| `time` | `float` | Elapsed time in milliseconds |
| `stats` | `dict` | Demand statistics (top gaps, counts, min/max demand) |

**Key helpers:**

| Function | Purpose |
|---|---|
| `split_skills()` | Split comma/`/` delimited stacks; preserves `A/B testing` and `CI/CD` |
| `sanitize_resume_text()` | Strip prompt-injection lines before LLM |
| `is_plausible_skill()` | Reject sentence-like or injected model output |
| `_load_job_demand()` | Fetch all `tech_stack` values via MCP |

### `db_server.py` (MCP bonus)

#### `run_sql_script(script_name: str, params_json: str = "[]") -> str`

| | |
|---|---|
| **Purpose** | Execute a named SQL file from `queries/` against `DB_PATH` |
| **Inputs** | `script_name` — e.g. `select_untagged_jobs.sql`; `params_json` — JSON param list |
| **Outputs** | JSON string of rows (SELECT) or `{"rows_affected": N}` (UPDATE) |

---

## Data / assumptions

### Database schema (jobs table)

Scripts expect a SQLite `jobs` table with at least:

- `id` — job identifier (logged in output)
- `tech_stack` — comma-separated skills (empty = untagged)
- `description` — job text used for LLM tagging
- Additional metadata columns used when descriptions are insufficient (title, company, etc.)

### Input files

| File | Format | Notes |
|---|---|---|
| `data/jobs_d1.db` | SQLite | Must be tagged before skill-gap analysis |
| Resume (`.txt` / `.pdf`) | Plain text or PDF | Bare names resolve under `data/`; PDF needs `pypdf` |

### Assumptions

- **Tagging:** job descriptions are mostly English; very short or boilerplate descriptions fall back to metadata inference.
- **Skill gaps:** resume extraction is the only non-deterministic step; gap list is always reproducible given the same extracted skills.
- **Skill splitting:** `/` splits compound skills except `A/B testing` and `CI/CD`; output is lowercased.
- **Direct match:** `C/C++` on a resume removes `c`, `c++`, and `c/c++` from gaps (split + set logic).
- **Non-technical skills:** certifications, spoken languages, and soft skills are excluded by prompt rules.
- **Rate limits:** `rate_limits.txt` reflects the active Gemini model; batch size stays within TPM/RPM budgets.

### Data flow

```text
jobs_d1.db ──MCP──► tag_data.py ──Gemini──► updated tech_stack
                                              │
resume (.txt/.pdf) ──Gemini──► resume skills  │
                                              ▼
                              find_skill_gaps.py ──set math──► SkillGapResult.gaps
```

---

## Testing

### How the system was tested

| Area | Method |
|---|---|
| Tagging | Run `uv run tag_data.py` on `data/jobs_d1.db`; verify `Analyzed Job {id}:` lines and DB updates |
| Skill gaps | Run `uv run find_skill_gaps.py` twice; confirm identical `gaps` |
| Benchmarks | `uv run tag_data.py --benchmark` and `uv run find_skill_gaps.py --benchmark`; check >5% token/time savings |
| Error handling | Missing resume, bad DB path, empty PDF — scripts print messages and return gracefully (no stack traces) |
| Jailbreak safety | Injection phrases in resume text are stripped; implausible LLM skills are filtered |

### Reproduce tests

```bash
cd week2
uv sync

# Tagging
uv run tag_data.py

# Determinism check (gaps must match)
uv run find_skill_gaps.py > run1.txt
uv run find_skill_gaps.py > run2.txt
# Compare gaps= lines in run1.txt and run2.txt

# Optimization proof
uv run tag_data.py --benchmark
uv run find_skill_gaps.py --benchmark
```

### Requirements checklist (Day 1–2)

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

### Requirements checklist (Day 3–4)

| Requirement | Implementation |
|---|---|
| `find_skill_gaps(input_file_path, db_url) -> SkillGapResult` | `find_skill_gaps.py` |
| `SkillGapResult` is a Pydantic `BaseModel` with `gaps: list[str]` | `SkillGapResult` |
| Read `jobs` table + process resume | MCP `select_all_tech_stacks.sql` + resume file |
| Output sorted + lowercase | `sorted(job_skills - resume_skills)` |
| Deterministic across runs | LLM `temperature=0` for parsing only; gaps via set math |
| Split skills on `/` (except `A/B testing`, `CI/CD`) | `split_skills()` + `SPLIT_EXCEPTIONS` |
| Direct-match accuracy (C/C++ removes c, c++, c/c++) | `split_skills()` lowercases + splits both sides |
| Ignore certifications / non-technical skills | extraction prompt rules |
| Justifiable batch size + retry | batch = 1 (one resume); retry = `60/RPM` |
| Graceful errors (no crashes) | try/except, fallback to empty resume/jobs |
| Return tokens + time (bonus) | `tokens`, `time` fields |
| Jailbreak safety (bonus) | `sanitize_resume_text()` + hardened prompt + `is_plausible_skill()` |
| Statistics (bonus) | `stats`: top demand gaps, demand difference |
| MCP integration (bonus) | reuses `db_server.py` + new SQL script |
| Gemini models only (bonus) | `genai` with `DEFAULT_MODEL` + fallbacks |
| Prompt optimization proof (bonus) | `--benchmark` + `BASELINE_RESUME_PROMPT` vs `OPTIMIZED_RESUME_PROMPT` |
| Time optimization proof (bonus) | `--benchmark` + cached job demand + single parse pass |

---

## Limitations

| Area | What does not work well |
|---|---|
| **Tagging accuracy** | LLM may miss niche skills or over-tag generic terms; vague answers are partially handled by `resolve_tech_stack()` but not perfect |
| **Small datasets** | `--benchmark` on ~8 jobs may not always show >5% savings due to API latency variance |
| **PDF resumes** | Extraction quality depends on PDF layout; scanned images are not OCR'd |
| **Skill normalization** | No synonym map (e.g. `k8s` vs `kubernetes`); exact string match after lowercase split |
| **Jailbreak defense** | Pattern-based filtering only; sophisticated injections may still affect extraction |
| **Performance** | Sequential Gemini calls; no parallel batching across rate-limit windows |
| **Ollama** | Day 0 only; tagging and skill gaps require Gemini |

---

## Architecture reflection

### Design choices

- **MCP for SQL:** database access goes through `db_server.py` and versioned `.sql` files instead of inline queries — separates data access from LLM logic and matches the bonus MCP requirement.
- **LLM for unstructured input only:** tagging reads job descriptions; skill gaps read resumes. All aggregation, sorting, and gap math is deterministic Python — no LLM in the final gap decision.
- **Shared utilities in `tag_data.py`:** rate-limit math, MCP client, and token counting are reused by `find_skill_gaps.py` to avoid duplicating Day 0–2 infrastructure.
- **Baseline vs optimized prompts:** two explicit templates with `--benchmark` runs make optimization measurable without hidden env-dependent behavior.

### Trade-offs

| Prioritized | Sacrificed |
|---|---|
| Simplicity and reviewability | Scalability (no job queue, no caching layer) |
| Deterministic gap output | Richer semantic matching (synonyms, embeddings) |
| Graceful degradation | Strict fail-fast on bad inputs |
| Token savings (truncation, short prompts) | Occasional loss of context in very long descriptions/resumes |

### Improvements (given more time)

- Synonym / alias table for skills (`k8s` → `kubernetes`)
- Embedding-based gap ranking instead of raw string sets
- Persistent cache of tagged stacks to skip re-tagging unchanged jobs
- Structured logging and a small test suite with mocked Gemini responses
- OCR path for image-based PDF resumes
