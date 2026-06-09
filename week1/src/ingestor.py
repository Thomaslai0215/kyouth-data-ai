from pathlib import Path


def ingest_all_mhtml(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Ingesting files from {input_dir} to {output_dir}")
    # TODO: Extract MHTML files into HTML files in the output directory
