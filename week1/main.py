import logging
import sys
from pathlib import Path

from src.ingestor import ingest_all_mhtml
from src.processor import process_all_html
from src.loader import load_all_jsons
from src.profiler import run_data_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = DATA_DIR / "0_source"
BRONZE_DIR = DATA_DIR / "1_bronze"
SILVER_DIR = DATA_DIR / "2_silver"
GOLD_DIR = DATA_DIR / "3_gold"
DB_PATH = GOLD_DIR / "jobs.db"


def run_profiler() -> None:
    """Run the data quality check on the gold database."""
    run_data_profile(DB_PATH)


def run_gold() -> None:
    """Load silver JSON files into the gold SQLite database."""
    input_dir = SILVER_DIR
    output_dir = GOLD_DIR
    load_all_jsons(input_dir, output_dir)


def run_silver() -> None:
    """Clean bronze HTML files and save them as silver JSON files."""
    input_dir = BRONZE_DIR
    output_dir = SILVER_DIR
    process_all_html(input_dir, output_dir)


def run_bronze() -> None:
    """Extract HTML from source MHTML files into the bronze folder."""
    input_dir = SOURCE_DIR
    output_dir = BRONZE_DIR
    ingest_all_mhtml(input_dir, output_dir)


def main() -> None:
    """Run one pipeline step based on the command given on the command line."""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "ingest":
            run_bronze()
        elif command == "process":
            run_silver()
        elif command == "load":
            run_gold()
        elif command == "profile":
            run_profiler()
        elif command == "all":
            run_bronze()
            run_silver()
            run_gold()
            run_profiler()
        else:
            print(f"Unknown command: {command}")
            print_usage()
            sys.exit(1)
    else:
        print_usage()
        sys.exit(1)


def print_usage() -> None:
    """Show the list of valid commands."""
    print("Usage: python main.py [ingest|process|load|profile|all]")


if __name__ == "__main__":
    main()
