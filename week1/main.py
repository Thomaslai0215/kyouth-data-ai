from pathlib import Path

from src.ingestor import ingest_all_mhtml

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = DATA_DIR / "0_source"
BRONZE_DIR = DATA_DIR / "1_bronze"
SILVER_DIR = DATA_DIR / "2_silver"
GOLD_DIR = DATA_DIR / "3_gold"
DB_NAME = "jobs.db"


# def run_profiler() -> None:

# def run_gold() -> None:
    

# def run_silver() -> None:


def run_bronze() -> None:
    input_dir = SOURCE_DIR
    output_dir = BRONZE_DIR
    ingest_all_mhtml(input_dir, output_dir)


def main() -> None:
    run_bronze()
    # run_silver()
    # run_gold()
    # run_profiler()


if __name__ == "__main__":
    main()
