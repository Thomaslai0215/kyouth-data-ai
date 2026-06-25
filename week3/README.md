# Week 3 — Resume Helper Chatbot (Docker)

Technical manual for the full-stack Resume Helper: a containerized chat app with a FastAPI frontend, FastAPI backend, Ollama for general chat, and Week 2 `find_skill_gaps` for resume analysis.

## Project overview

This project builds and containerizes a full-stack chat application:

| Service | Port | Role |
|---|---|---|
| `frontend` | 8000 | Chat UI, PDF upload, PDF-to-text extraction |
| `backend` | 8001 | Chat API, skill-gap analysis, Ollama routing |
| `ollama` | 11434 | Local LLM for normal chat (bonus) |

**Two modes in one UI:**

1. **Normal chat** — user sends a text message → backend calls Ollama (`CHAT_MODEL`, e.g. `llama3.1`).
2. **Skill-gap analysis** — user uploads a resume PDF → frontend extracts text → backend runs Week 2 `find_skill_gaps` against `backend/data/jobs.db` using Gemini.

### Project structure

```
week3/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── secrets/
│   └── google_api_key.txt.example
├── frontend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/
│       ├── app.py
│       ├── static/          # chat.js, chat.css
│       └── templates/       # chat_page.html
└── backend/
    ├── Dockerfile
    ├── data/
    │   └── jobs.db          # tagged jobs DB (built into Docker image)
    ├── pyproject.toml
    └── src/
        ├── app.py
        ├── secrets_util.py
        └── week_2/
            └── find_skill_gaps.py
```

---

## Setup instructions

### Prerequisites

| Tool | Version / notes |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | With Docker Compose |
| [uv](https://docs.astral.sh/uv/) | Optional — for local (non-Docker) development |
| Python | 3.14 (if using `uv` locally) |
| Gemini API key | For skill-gap analysis ([Google AI Studio](https://aistudio.google.com/apikey)) |
| NVIDIA GPU (optional) | For Ollama in Docker (`gpus: all` in compose) |

### 1. Configure environment variables

```bash
cd week3
cp .env.example .env          # Windows: copy .env.example .env
```

Edit `week3/.env`:

| Variable | Required | Description |
|---|---|---|
| `BACKEND_URL` | Yes | URL the **browser** uses to reach the backend (use `localhost`, not Docker service names) |
| `CHAT_MODEL` | For chat | Ollama model name, e.g. `llama3.1` |
| `GOOGLE_API_KEY` | Local dev | Gemini key when running backend with `uv` outside Docker |
| `OLLAMA_BASE_URL` | Local dev | Default `http://127.0.0.1:11434` when not using Docker |

Example:

```env
BACKEND_URL=http://localhost:8001/chat
CHAT_MODEL=llama3.1
GOOGLE_API_KEY=
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

### 2. Configure Docker secrets (Gemini API key)

For Docker, the backend reads the API key from a secret file — not from `.env` inside the container.

```bash
cd week3
cp secrets/google_api_key.txt.example secrets/google_api_key.txt
# Edit secrets/google_api_key.txt — paste only the key (no quotes, no variable name)
```

### 3. Run with Docker Compose

```bash
cd week3
docker compose up --build
```

First time with Ollama, pull a model inside the container:

```bash
docker compose exec ollama ollama pull llama3.1
```

Open the app: **http://localhost:8000**

### 4. Optional: run services locally with `uv`

**Frontend:**

```bash
cd week3/frontend
uv sync
uv run uvicorn --app-dir src --reload --port 8000 app:app
```

**Backend:**

```bash
cd week3/backend
uv sync
uv run uvicorn --app-dir src --reload --port 8001 app:app
```

Ensure `week3/.env` has `GOOGLE_API_KEY` set for skill-gap analysis when not using Docker secrets.

---

## Usage

### Start the stack

```bash
cd week3
docker compose up --build
```

### Access the frontend

Open **http://localhost:8000** in your browser.

### Normal chat

1. Type a message (e.g. `who are you?`).
2. Click **Send**.
3. Backend routes the message to Ollama and returns the reply.

### Skill-gap analysis

1. Click the upload button and select a **text-based PDF** resume.
2. The UI shows the filename in a chip below the input (use **×** to remove).
3. The bot prompts: *Type "start analysis" or press Send*.
4. Click **Send** (or type `start analysis` and send).
5. Backend runs `find_skill_gaps` and returns a formatted result.

**Expected output (skill-gap):**

```text
gaps=['ai', 'aws', 'mysql', ...] time=2056 tokens=425

--- BONUS: Top 5 Most In-Demand Missing Skills ---
Skill: aws                  | Missing from resume, but required by 2 job(s)
Skill: mysql                | Missing from resume, but required by 2 job(s)
...
```

### Run skill-gap from CLI (backend)

```bash
cd week3/backend
uv run python src/week_2/find_skill_gaps.py
```

Uses `backend/data/resume_d3.txt` and `backend/data/jobs.db` by default.

---

## API / function reference

### Backend — `POST /chat` (alias: `POST /api/chat`)

**Request JSON:**

```json
{
  "message": "who are you?",
  "pdf_text": ""
}
```

| Field | Type | Description |
|---|---|---|
| `message` | string | User text. Used for normal chat when `pdf_text` is empty. |
| `pdf_text` | string | Extracted resume text from the frontend. When present, triggers skill-gap analysis. |

**Response JSON:**

```json
{
  "reply": "..."
}
```

**Routing logic (`backend/src/app.py`):**

- `pdf_text` present → `find_skill_gaps()` → `format_skill_gap_result()`
- `pdf_text` empty + `message` present → Ollama chat via `chat_with_model()`
- both empty → guidance message

### Frontend — `GET /`

Serves `chat_page.html`. Injects `window.BACKEND_URL` from the `BACKEND_URL` environment variable.

### Frontend — `POST /api/pdf-to-text`

Accepts a PDF file (`multipart/form-data`, field name `file`).

**Response:**

```json
{
  "pdf_text": "extracted resume text..."
}
```

### Frontend JavaScript (`frontend/src/static/chat.js`)

| Function | Purpose |
|---|---|
| `loadPdfFile(file)` | Sends PDF to `/api/pdf-to-text`, stores extracted text |
| `showResumeChip(name)` | Shows uploaded filename with remove button |
| `clearResume()` | Clears stored resume text and resets UI |
| `sendToBackend(message, pdfText)` | `POST` to `BACKEND_URL` with JSON payload |
| `appendMessage(role, text)` | Adds a message bubble to the chat history |

### Docker networking

| From | To | URL |
|---|---|---|
| Browser | Frontend | `http://localhost:8000` |
| Browser | Backend | `http://localhost:8001/chat` (set in `BACKEND_URL`) |
| Backend container | Ollama container | `http://ollama:11434` |

The browser cannot use Docker service names (`http://backend:8001`) — it runs outside the Docker network. Inside Compose, the backend uses `http://ollama:11434` for Ollama.

### Secrets (`backend/src/secrets_util.py`)

| Function | Purpose |
|---|---|
| `read_secret(name)` | Read a file from `/run/secrets/<name>` |
| `apply_docker_secrets()` | Load `google_api_key` secret into `GOOGLE_API_KEY` |

---

## Data / assumptions

### Data files

| File | Purpose |
|---|---|
| `backend/data/jobs.db` | SQLite jobs database with tagged `tech_stack` values (from Week 2 tagging) |
| `backend/data/resume_d3.txt` | Sample resume for CLI testing only |
| `secrets/google_api_key.txt` | Gemini API key for Docker (not committed) |

### JSON message flow

```
Browser upload (PDF)
  → frontend POST /api/pdf-to-text
  → frontend stores pdf_text in memory
  → frontend POST BACKEND_URL { message, pdf_text }
  → backend writes pdf_text to temp file
  → find_skill_gaps(temp_file, jobs.db)
  → backend returns { reply }
  → frontend renders reply in chat
```

### Assumptions

- PDFs are **text-based** (scanned/image-only PDFs may return empty text).
- Resume text is truncated to **3000 characters** inside `find_skill_gaps`.
- Skill-gap analysis requires a **tagged** jobs database (`tech_stack` column populated).
- Skill-gap uses **Gemini** (`gemini-3.1-flash-lite`); normal chat uses **Ollama**.
- `BACKEND_URL` must use `localhost` (or your host IP), not Docker internal hostnames.
- Chat history is **in-memory only** (lost on page refresh).

---

## Testing

### Frontend (manual)

| Test | Steps | Expected |
|---|---|---|
| Normal chat | Send `who are you?` without uploading | Ollama reply |
| PDF upload | Upload a text-based PDF | Chip shows filename; bot prompts to start analysis |
| Remove resume | Click **×** on chip | Chip hidden; status resets |
| Skill-gap | Upload PDF → Send | Gaps list + Top 5 bonus section |
| Empty send | Click Send with no input | Bot asks for message or resume |

### Backend (`curl`)

**Normal chat:**

```bash
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"who are you?\",\"pdf_text\":\"\"}"
```

**Skill-gap analysis:**

```bash
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"\",\"pdf_text\":\"Skills: Python, SQL, Azure\"}"
```

**Missing input:**

```bash
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"\",\"pdf_text\":\"\"}"
```

### Docker integration

```bash
cd week3
docker compose up --build
docker compose ps          # all services should be Up
```

Verify:

- Frontend loads at `http://localhost:8000`
- Chat and skill-gap work end-to-end
- Backend can reach Ollama at `http://ollama:11434` inside the network

### CLI skill-gap

```bash
cd week3/backend
uv run python src/week_2/find_skill_gaps.py
```

---

## Limitations

- **No authentication** — anyone with access to the URL can use the chatbot.
- **No persistent chat history** — messages exist only in the browser session.
- **PDF extraction is basic** — `pypdf` text extraction; scanned PDFs often fail.
- **Skill-gap accuracy** depends on Gemini resume parsing and Week 2 job tagging quality.
- **Ollama performance** varies by hardware; GPU recommended for reasonable latency.
- **Large gap lists** can be long in the chat UI (full list is returned, not truncated).
- **Port conflicts** — if `8000` or `8001` is in use, change published ports in `docker-compose.yml` and update `BACKEND_URL` accordingly.
- **Secrets file required** — `docker compose up` fails if `secrets/google_api_key.txt` is missing (create from `.example`).

---

## Architecture reflection

### Design choices

**Microservices (frontend + backend + Ollama)** keeps each service focused: the frontend handles UI and PDF parsing; the backend handles AI routing and business logic; Ollama runs the local LLM in isolation. Each service has its own `Dockerfile` and `pyproject.toml`, which matches the Week 3 project structure and makes changes easier to reason about.

**Docker Compose** wires services together with one command (`docker compose up --build`). Environment variables and Docker secrets separate configuration from code — ports and API keys can change per machine without editing application logic.

**Week 2 integration** reuses `find_skill_gaps.py` instead of rewriting analysis logic. The backend writes uploaded resume text to a temporary file and calls the same function used in Week 2, keeping skill-gap math deterministic and consistent.

### Trade-offs

| Prioritized | Sacrificed |
|---|---|
| Simple deployment with Docker Compose | Production-grade orchestration (Kubernetes, load balancing) |
| Plain HTML/JS chat UI | Rich frontend framework (React, streaming responses) |
| Config via `.env` + secrets | Hardcoded URLs (more portable, slightly more setup) |
| Dual mode (chat + analysis) in one endpoint | Separate dedicated analysis API |

Using `localhost` in `BACKEND_URL` is a deliberate choice: the browser runs on the host, not inside Docker, so it must use the published host port.

### Improvements (given more time)

- Parameterize ports in `docker-compose.yml` via `.env` (`FRONTEND_PORT`, `BACKEND_PORT`).
- Add a landing page and deploy frontend/backend to Railway or Docker Hub.
- Persist chat history in a database.
- Add streaming responses for Ollama chat.
- Show skill gaps in a structured UI (table/chart) instead of raw text.
- Support `.txt` resume uploads in addition to PDF.
- Add health-check endpoints and automated integration tests.
