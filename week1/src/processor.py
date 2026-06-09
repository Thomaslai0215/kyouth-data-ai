from pathlib import Path


def process_all_html(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Processing files from {input_dir} to {output_dir}")
    # TODO: Clean HTML files and write cleaned JSON output to the output directory
