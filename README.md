# kyouth-data-ai

This repository is organized for Week 1 of the data engineering workflow.

## Project Structure

week1/
├── data/
│   ├── 0_source/          # Vendor Data: Unedited MHTML
│   ├── 1_bronze/          # Raw Data: Decoded HTML
│   ├── 2_silver/          # Clean Data: Removed HTML tags
│   └── 3_gold/            # Final Warehouse: SQLite DB
├── src/
│   ├── ingestor.py        # Day 1: Extracts to data/1_bronze/
│   ├── processor.py       # Day 2: Cleans/Validates to data/2_silver/
│   ├── loader.py          # Day 3: Loads to data/3_gold/
│   └── profiler.py        # Day 4: Quality checks on Gold layer
├── main.py                # CLI Orchestrator
├── pyproject.toml         # Environment & Dependencies
├── uv.lock

## Usage

Run the orchestrator from the repository root:

```bash
python main.py ingest
python main.py process
python main.py load
python main.py profile
python main.py all
```

## Notes

- The root `data/` and `src/` directories were moved into `week1/` to align with the required folder layout.
- The module files currently contain starter scaffolding and TODO placeholders.
