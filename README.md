# kyouth-data-ai

Technical manual for the **KYOUTH Data & AI** program: a three-week project that moves from raw job data ingestion, through LLM-powered tagging and skill-gap analysis, to a containerized full-stack Resume Helper chatbot.

> **Submission:** Push all work to your **public** Git repository. Only committed files are evaluated. Do not commit secrets (`.env`, API keys). Each week has its own detailed README.

| Week | Focus | Quick start |
|---|---|---|
| [Week 1](week1/README.md) | Job data pipeline (Medallion → SQLite) | `cd week1 && uv sync && uv run python main.py all` |
| [Week 2](week2/README.md) | LLM setup, job tagging, skill gaps | `cd week2 && uv sync && uv run find_skill_gaps.py` |
| [Week 3](week3/README.md) | Dockerized chat app (frontend + backend + AI) | `cd week3 && docker compose up --build` |

---

## Project overview

This repository tells one end-to-end story:

```
Week 1: Scrape & clean job data → jobs.db
Week 2: Tag jobs with LLM → tech_stack in DB → find_skill_gaps(resume, db)
Week 3: Chat UI → upload resume → same skill-gap logic in a Docker app
```

### Week 1 — Job data pipeline

Builds a **Medallion Architecture** pipeline that turns Jobstreet MHTML pages into a SQLite gold database.

| Layer | Folder | Output |
|---|---|---|
| Source | `week1/data/0_source/` | Original `.mhtml` files |
| Bronze | `week1/data/1_bronze/` | Extracted HTML |
| Silver | `week1/data/2_silver/` | Clean JSON (one job per file) |
| Gold | `week1/data/3_gold/` | `jobs.db` |

**Key modules:** `ingestor.py`, `processor.py`, `loader.py`, `profiler.py` — orchestrated by `main.py`.

### Week 2 — LLM setup & tagging

Adds AI on top of the job database:

| Script | Purpose |
|---|---|
| `prompt_model.py` | Route prompts to Gemini (cloud) or Ollama (local) |
| `tag_data.py` | Tag untagged jobs with `tech_stack` via Gemini |
| `find_skill_gaps.py` | Extract resume skills (Gemini), compare to job demand (deterministic set math) |

**Flow:** tagged `tech_stack` values define market demand → resume is parsed → missing skills (`gaps`) are computed reproducibly.

### Week 3 — Resume Helper chatbot (Docker)

Containerizes a full-stack chat application:

| Service | Port | Role |
|---|---|---|
| `frontend` | 8000 | Chat UI, PDF upload, PDF-to-text |
| `backend` | 8001 | `POST /chat`, skill-gap analysis, Ollama chat |
| `ollama` | 11434 | Local LLM for general chat (bonus) |

**Two modes:** normal chat (Ollama) and resume skill-gap analysis (Week 2 `find_skill_gaps` + Gemini).

### Repository structure

```
kyouth-data-ai/
├── README.md                 # This file — whole-project manual
├── week1/                    # Data pipeline
│   ├── main.py
│   ├── src/
│   ├── queries/
│   └── data/                 # gitignored — local data layers
├── week2/                    # LLM tagging & skill gaps
│   ├── prompt_model.py
│   ├── tag_data.py
│   ├── find_skill_gaps.py
│   ├── db_server.py          # MCP bonus
│   └── data/                 # gitignored
└── week3/                    # Docker chat app
    ├── docker-compose.yml
    ├── .env.example
    ├── secrets/
    ├── frontend/
    └── backend/
```

---

## Setup instructions

### Prerequisites

| Tool | Weeks | Notes |
|---|---|---|
| Python 3.14+ | 1, 2, 3 | Managed with [uv](https://docs.astral.sh/uv/) |
| [uv](https://docs.astral.sh/uv/) | 1, 2, 3 | `uv sync` per week folder |
| Git | All | Clone this public repository |
| Gemini API key | 2, 3 | [Google AI Studio](https://aistudio.google.com/apikey) |
| Ollama | 2 (Day 0), 3 (chat) | Local models e.g. `llama3.1` |
| Docker Desktop | 3 | Docker Compose for the chat app |
| NVIDIA GPU (optional) | 3 | For Ollama in Docker |

### Clone the repository

```bash
git clone https://github.com/Thomaslai0215/kyouth-data-ai.git
cd kyouth-data-ai
```

### Week 1 — no secrets required

```bash
cd week1
uv sync
```

Place MHTML files in `week1/data/0_source/`. See [week1/README.md](week1/README.md).

### Week 2 — Gemini API key

```bash
cd week2
cp .env.example .env    # Windows: copy .env.example .env
uv sync
```

Edit `week2/.env` with `GOOGLE_API_KEY`. Place data files in `week2/data/` (from course `resources.zip`). See [week2/README.md](week2/README.md).

### Week 3 — env + Docker secrets

```bash
cd week3
cp .env.example .env
cp secrets/google_api_key.txt.example secrets/google_api_key.txt
```

- `week3/.env` — `BACKEND_URL`, `CHAT_MODEL`, etc. (see `.env.example`)
- `secrets/google_api_key.txt` — Gemini key for Docker (paste key only, no variable name)

```bash
docker compose up --build
docker compose exec ollama ollama pull llama3.1   # first time only
```

See [week3/README.md](week3/README.md) for full Docker setup.

---

## Usage

### Week 1 — run the pipeline

```bash
cd week1
uv run python main.py all
```

Or step by step: `ingest` → `process` → `load` → `profile`.

**Output:** `week1/data/3_gold/jobs.db` with ~83 quality jobs.

### Week 2 — tag jobs and find skill gaps

```bash
cd week2
uv run tag_data.py
uv run find_skill_gaps.py
```

**Output:** updated `tech_stack` in DB; terminal gaps list + Top 5 demand stats.

### Week 3 — run the chat app

```bash
cd week3
docker compose up --build
```

Open **http://localhost:8000**.

| Action | Input | Output |
|---|---|---|
| Normal chat | Type a message, click Send | Ollama reply |
| Skill-gap analysis | Upload PDF → Send (or type `start analysis`) | Gaps list + Top 5 missing skills |

**Expected skill-gap output:**

```text
gaps=['ai', 'aws', 'mysql', ...] time=2056 tokens=425

--- BONUS: Top 5 Most In-Demand Missing Skills ---
Skill: aws                  | Missing from resume, but required by 2 job(s)
...
```

---

## API / function reference

Detailed Week 3 API docs are in [week3/README.md](week3/README.md). Summary:

### Week 3 backend — `POST /chat`

**Request:**

```json
{
  "message": "who are you?",
  "pdf_text": ""
}
```

**Response:**

```json
{
  "reply": "..."
}
```

| `pdf_text` | `message` | Behavior |
|---|---|---|
| empty | present | Normal chat via Ollama |
| present | any | Skill-gap analysis via `find_skill_gaps` |
| empty | empty | Guidance message |

### Week 3 frontend — key endpoints & JS

| Endpoint / function | Purpose |
|---|---|
| `GET /` | Chat page; injects `BACKEND_URL` |
| `POST /api/pdf-to-text` | Extract text from uploaded PDF |
| `loadPdfFile()` | Store resume text client-side |
| `sendToBackend()` | POST JSON to backend |
| `appendMessage()` | Render chat bubbles |

### Week 2 — key scripts

| Script | Inputs | Output |
|---|---|---|
| `prompt_model.py` | model name, prompt string | LLM text response |
| `tag_data.py` | SQLite DB path | Updates `jobs.tech_stack` |
| `find_skill_gaps.py` | resume file, DB path | `SkillGapResult` (gaps, demand stats, tokens, time) |

### Docker networking (Week 3)

| From | To | URL |
|---|---|---|
| Browser | Frontend | `http://localhost:8000` |
| Browser | Backend | `http://localhost:8001/chat` (`BACKEND_URL`) |
| Backend container | Ollama | `http://ollama:11434` |

The browser must use `localhost`, not Docker service names.

---

## Data / assumptions

### How the weeks connect

```
MHTML files
  → Week 1 pipeline → jobs.db
  → Week 2 tag_data.py → jobs with tech_stack
  → Week 2 find_skill_gaps.py → gaps vs resume
  → Week 3 chat UI → same find_skill_gaps logic in backend
```

### Data files (local, mostly gitignored)

| Path | Week | Purpose |
|---|---|---|
| `week1/data/3_gold/jobs.db` | 1 | Gold job database |
| `week2/data/jobs_d1.db` | 2 | Tagging + skill-gap DB |
| `week2/data/resume_d3.txt` | 2 | Sample resume for CLI |
| `week3/backend/data/jobs.db` | 3 | Tagged DB baked into backend image |

### Assumptions

- **Week 1:** MHTML/HTML files are valid Jobstreet saves; bad records are skipped or quarantined.
- **Week 2:** Jobs must be tagged before skill-gap analysis; Gemini extracts resume skills (`temperature=0`); gap math is deterministic.
- **Week 3:** PDFs must be text-based; resume truncated to 3000 chars; chat history is not persisted; `BACKEND_URL` uses host `localhost`.

### Environment variables

| Variable | Week | Description |
|---|---|---|
| `GOOGLE_API_KEY` | 2, 3 | Gemini API (Week 3 Docker: use `secrets/google_api_key.txt`) |
| `BACKEND_URL` | 3 | Browser → backend URL |
| `CHAT_MODEL` | 3 | Ollama model for normal chat |
| `OLLAMA_BASE_URL` | 3 | Ollama endpoint |

Never commit `.env` or `secrets/google_api_key.txt`. Commit `.env.example` files only.

---

## Testing

### Week 1

```bash
cd week1
uv run python main.py all
```

Verify: Bronze/Silver/Gold summaries; `jobs.db` exists; profiler reports quarantine count.

### Week 2

```bash
cd week2
uv run tag_data.py
uv run find_skill_gaps.py
```

Verify: `Analyzed Job {id}:` lines; deterministic `gaps` on two consecutive runs.

### Week 3 — frontend (manual)

| Test | Expected |
|---|---|
| Send message without resume | Ollama chat reply |
| Upload PDF | Filename chip appears; bot prompts to analyze |
| Click × on chip | Resume cleared |
| Send after upload | Skill-gap formatted output |

### Week 3 — backend (`curl`)

```bash
# Normal chat
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"who are you?\",\"pdf_text\":\"\"}"

# Skill-gap
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"\",\"pdf_text\":\"Skills: Python, SQL\"}"
```

### Docker integration

```bash
cd week3
docker compose up --build
docker compose ps
```

All three services (`frontend`, `backend`, `ollama`) should be **Up**.

---

## Limitations

### Week 1

- Sequential file processing — slow at very large scale.
- Quality rules may quarantine valid but short job posts.
- Data folders are local and not committed to Git.

### Week 2

- Tagging depends on Gemini API availability and rate limits.
- Skill extraction quality varies with resume wording.
- `jobs_d1.db` / resume files must be provided locally.

### Week 3

- No user authentication or persistent chat history.
- PDF extraction fails on scanned/image-only PDFs.
- Skill-gap uses Gemini; normal chat uses Ollama — two separate model paths.
- Ollama in Docker needs sufficient RAM/VRAM; first response can be slow.
- Port `8000` / `8001` conflicts require manual compose changes.
- Long gap lists appear as plain text in the chat UI.

---

## Architecture reflection

### Design choices

**Medallion pipeline (Week 1)** keeps raw, cleaned, and warehouse layers separate. Raw data can be reprocessed without re-scraping — the same pattern used in industry data lakes and warehouses.

**LLM + deterministic logic (Week 2)** uses AI only where judgment is needed (skill extraction, tagging) and plain set math for gaps. That makes gap results reproducible across runs.

**Microservices + Docker (Week 3)** splits frontend, backend, and Ollama into isolated containers. Each service has its own `Dockerfile` and dependencies. Docker Compose provides one-command deployment; environment variables and secrets keep configuration out of code.

**Reusing Week 2 in Week 3** avoids duplicating business logic. The backend writes uploaded resume text to a temp file and calls the same `find_skill_gaps` function — consistent behavior between CLI and chat UI.

### Trade-offs

| Prioritized | Sacrificed |
|---|---|
| Learning clarity (separate weeks, simple scripts) | Single unified production codebase |
| Docker Compose ease of use | Cloud-native orchestration |
| Plain HTML/JS chat UI | Rich frontend framework |
| Config via `.env` + secrets | Zero-setup for reviewers (secrets file required) |

### Improvements (given more time)

- Root-level orchestration script that runs Week 1 → 2 → 3 in sequence.
- Parameterize Docker ports via `.env`.
- Deploy Week 3 to Railway / Docker Hub with a landing page.
- Persist chat history in a database.
- Structured skill-gap UI (table or chart) instead of raw text.
- Automated integration tests across all three weeks.
- Streaming responses for Ollama chat.

---

## Week-specific documentation

For step-by-step instructions, expected outputs, and deeper technical detail:

- [Week 1 README](week1/README.md) — Medallion pipeline, SQL queries, Day 1–4 reflections
- [Week 2 README](week2/README.md) — LLM setup, tagging, skill gaps, MCP bonus
- [Week 3 README](week3/README.md) — Docker setup, API reference, secrets, testing
