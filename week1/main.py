from pathlib import Path

from src.ingestor import ingest_all_mhtml
from src.loader import load_all_jsons
from src.profiler import run_data_profile
from src.processor import process_all_html

SOURCE_DIR = Path("data/0_source")
BRONZE_DIR = Path("data/1_bronze")
SILVER_DIR = Path("data/2_silver")
GOLD_DIR = Path("data/3_gold")
DB_NAME = "jobs.db"


def run_profiler() -> None:
    db_path = GOLD_DIR / DB_NAME
    run_data_profile(db_path)


def run_gold() -> None:
    load_all_jsons(SILVER_DIR, GOLD_DIR)


def run_silver() -> None:
    input_dir = BRONZE_DIR
    output_dir = SILVER_DIR
    process_all_html(input_dir, output_dir)


def run_bronze() -> None:
    input_dir = SOURCE_DIR
    output_dir = BRONZE_DIR
    ingest_all_mhtml(input_dir, output_dir)


def main() -> None:
    run_bronze()
    run_silver()
    run_gold()
    run_profiler()


if __name__ == "__main__":
    main()
