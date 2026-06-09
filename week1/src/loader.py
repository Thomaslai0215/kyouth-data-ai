from pathlib import Path


def load_all_jsons(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Loading JSON files from {input_dir} to {output_dir}")
    # TODO: Load cleaned JSON data into the gold warehouse (SQLite DB)
