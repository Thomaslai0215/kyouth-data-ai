# kyouth-data-ai

## Project Description

This project builds a small **job data pipeline** for Week 1. It reads Jobstreet job pages saved as MHTML files, cleans them step by step, loads them into a SQLite database, and checks data quality.

The pipeline uses a **Medallion Architecture** with four data folders:

| Layer | Folder | What it holds |
|-------|--------|----------------|
| Source | `week1/data/0_source/` | Original `.mhtml` files from the browser |
| Bronze | `week1/data/1_bronze/` | Raw HTML extracted from MHTML |
| Silver | `week1/data/2_silver/` | Clean JSON files (one job per file) |
| Gold | `week1/data/3_gold/` | SQLite database (`jobs.db`) |

Each step is a separate Python module. `main.py` runs them in order, like a simple pipeline controller.

**Bonus features included:**
- **Logging** — per-file progress uses Python `logging`; summaries still use `print()`
- **Content hashing** — detects when job text changes even if `source_id` stays the same
- **SQL files** — database queries live in `week1/queries/`
- **Quality labels** — LOW quality jobs are moved to a `jobs_quarantine` table

---

## Setup Instructions

### Prerequisites

- **Python** 3.14 or newer (see `week1/pyproject.toml`)
- **[uv](https://docs.astral.sh/uv/)** — used to install dependencies
- **Git** — to clone this repository

No API keys or `.env` file are needed for this project. All data comes from local MHTML/HTML files.

### Install dependencies

1. Clone the repository and go into the Week 1 folder:

```bash
git clone https://github.com/Thomaslai0215/kyouth-data-ai.git
cd kyouth-data-ai/week1
```

2. Install packages with uv:

```bash
uv sync
```

This creates a virtual environment and installs `beautifulsoup4`, `pydantic`, and other packages listed in `pyproject.toml`.

### Environment variables

This project does **not** use secret API keys. You do not need to set any environment variables to run the pipeline.

If you add your own `.env` file later, keep it out of Git (it is already listed in `.gitignore`).

---

## Usage

All commands are run from the **`week1/`** folder.

### Run one step at a time

```bash
uv run python main.py ingest    # Day 1: MHTML → HTML (Bronze)
uv run python main.py process   # Day 2: HTML → JSON (Silver)
uv run python main.py load      # Day 3: JSON → SQLite (Gold)
uv run python main.py profile   # Day 4: Data quality report
```

### Run the full pipeline

```bash
uv run python main.py all
```

This runs all four steps in order: ingest → process → load → profile.

### Expected results (with the provided dataset)

After a full run, you should see summary lines like these:

**Bronze (ingest)**
```
📊 Bronze Summary:
Total: 100 | Extracted: 100 | Failed: 0
```

**Silver (process)**
```
📊 Silver Summary:
Total: 100 | Processed: 84 | Skipped: 16
```
Some HTML files are missing required fields (job title, company, or description) and are skipped on purpose.

**Gold (load)**
```
📊 Gold Summary:
Total: 84 | Inserted: 84 | Updated: 0 | Skipped: 0
```

**Profile**
```
--- 🔍 DATA QUALITY REPORT ---
📈 Total Records (jobs): 83
🚫 Quarantined (LOW quality): 1
```

After profiling, **83 jobs** stay in the `jobs` table and **1 LOW-quality job** is moved to `jobs_quarantine`. This is expected — one job has a very short description and fails the quality rules.

### Where to find outputs

- Bronze HTML: `week1/data/1_bronze/*.html`
- Silver JSON: `week1/data/2_silver/*.json`
- Gold database: `week1/data/3_gold/jobs.db` (created when you run `load`)

---

## Project Structure

```
kyouth-data-ai/
├── README.md
└── week1/
    ├── main.py              # CLI — runs each pipeline step
    ├── pyproject.toml       # Python version and dependencies
    ├── uv.lock
    ├── data/
    │   ├── 0_source/        # Input MHTML files
    │   ├── 1_bronze/        # Extracted HTML
    │   ├── 2_silver/        # Clean JSON
    │   └── 3_gold/          # jobs.db
    ├── queries/             # SQL files used by loader and profiler
    └── src/
        ├── ingestor.py      # Day 1 — Bronze layer
        ├── processor.py     # Day 2 — Silver layer
        ├── loader.py        # Day 3 — Gold layer
        ├── profiler.py      # Day 4 — Quality checks
        └── sql_utils.py     # Loads SQL from queries/
```

---

## Technical Reflections

### Day 1: The Extractor (Medallion & Lakehouses)

**Why is it useful to keep the original raw HTML files instead of directly inserting processed data into the database? What problems become easier to debug or recover from?**

- **Answer:** Keeping raw files in `0_source` and `1_bronze` means we always have the original data to go back to. If our cleaning logic in `processor.py` has a bug, we can fix the code and re-run `process` without downloading the job pages again. In industry, this is similar to a **Data Lake** — cheap storage for raw files before they are cleaned for a **Data Warehouse**. Raw layers make it easier to debug bad extracts, compare old vs new runs, and recover when a later step fails.

### Day 2: Treatment Plant (ETL vs ELT & Scale)

**Why do cloud systems prefer loading raw data first before cleaning it (ELT)? What problems happen when processing files sequentially, and how does distributed processing help?**

- **Answer:** In **ELT**, raw data is loaded first and transformed later inside the warehouse (e.g. Snowflake, BigQuery). This is flexible because you can re-run transforms without re-ingesting data. Our project uses **ETL** (transform in Silver, then load to Gold), which is fine at small scale. Processing files one-by-one in a loop is simple but slow for large datasets — if one file takes 2 seconds, 100,000 files take days. Tools like **Apache Spark** split work across many machines so many files are processed in parallel, which cuts total runtime sharply.

### Day 3: The Blueprint & The Vault (Storage & Contracts)

**What should happen if an important field like `job_title` disappears? Why fail early instead of silently inserting nulls into DB? How does `INSERT OR IGNORE` help prevent duplicate records?**

- **Answer:** If `job_title` is missing, the record should be **rejected in Silver** (Pydantic validation in `processor.py`) before it reaches the database. Failing early stops bad data from breaking reports and dashboards later — empty or null job titles are hard to spot once thousands of rows are loaded. In Gold, `source_id` is the primary key and `INSERT OR IGNORE` skips rows that already exist, so re-running `load` does not create duplicate jobs. **Content hashing** (bonus) goes further: if the same `source_id` appears again but the job text changed, the loader updates the row instead of silently ignoring it.

### Day 4: The QA Inspector & Orchestrator (Orchestration & DAGs)

**What happens if `processor.py` crashes halfway? How are automated orchestration tools more reliable than manual retries with Python scripts?**

- **Answer:** If `processor.py` stops halfway, only some HTML files become JSON — the summary shows how many were processed vs skipped, and files already written to `2_silver/` stay there. Files not yet reached are unchanged. You must fix the error and run `process` again; idempotent overwrites handle the rest. Running steps manually with `main.py` works for learning, but in production teams use tools like **Apache Airflow** to schedule jobs, retry failed tasks automatically, track which step failed, alert the team, and run steps in the correct order (a DAG) without someone re-running scripts by hand.
