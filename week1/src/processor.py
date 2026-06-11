import json
import logging
from pathlib import Path

from bs4 import BeautifulSoup
from pydantic import BaseModel, field_validator, ValidationError

logger = logging.getLogger(__name__)


class JobListing(BaseModel):
    source_id: str
    job_title: str
    company: str
    description: str

    @field_validator("source_id", "job_title", "company", "description")
    @classmethod
    def cannot_be_empty(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Field cannot be empty")
        return value


def _read_html(html_path: Path) -> str:
    return html_path.read_text(encoding="utf-8")


def _extract_meta(soup: BeautifulSoup, name: str, attr: str = "property") -> str | None:
    tag = soup.find("meta", attrs={attr: name})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None


def _extract_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    og_url = _extract_meta(soup, "og:url") or ""
    source_id = og_url.rstrip("/").split("/")[-1] if og_url else ""

    descriptions_tag = soup.find(attrs={"data-automation": "jobAdDetails"})
    description = (
        descriptions_tag.get_text(separator=" ", strip=True) if descriptions_tag else ""
    )

    title_tag = soup.find(attrs={"data-automation": "job-detail-title"})
    job_title = title_tag.get_text(separator=" ", strip=True) if title_tag else ""

    company_tag = soup.find(attrs={"data-automation": "advertiser-name"})
    company = company_tag.get_text(separator=" ", strip=True) if company_tag else ""

    return {
        "source_id": source_id,
        "job_title": job_title,
        "company": company,
        "description": description,
    }


def _validate_record(fields: dict) -> tuple[JobListing | None, str | None]:
    try:
        record = JobListing(**fields)
        return record, None
    except ValidationError as e:
        error_str = str(e).lower()
        for field_name in ["source_id", "job_title", "company", "description"]:
            if field_name in error_str:
                return None, field_name
        return None, "unknown"


def _save_json(output_path: Path, record: JobListing) -> None:
    output_path.write_text(
        json.dumps(record.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def process_all_html(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print("🥈 Silver: Cleaning and validating HTML to JSON")

    html_files = sorted(input_dir.glob("*.html"))
    total = len(html_files)
    processed = 0
    skipped = 0

    if total == 0:
        logger.warning("No HTML files found to process.")
        print("\n📊 Silver Summary:")
        print(f"Total: 0 | Processed: 0 | Skipped: 0")
        return

    for html_path in html_files:
        html = _read_html(html_path)
        fields = _extract_fields(html)
        record, error_field = _validate_record(fields)
        output_path = output_dir / f"{html_path.stem}.json"

        if record is None:
            skipped += 1
            if output_path.exists():
                output_path.unlink()
            logger.warning(f"Missing {error_field} in: {html_path.name}")
            continue

        _save_json(output_path, record)
        processed += 1
        logger.info(f"Processed file: {html_path.name}")

    print("\n📊 Silver Summary:")
    print(f"Total: {total} | Processed: {processed} | Skipped: {skipped}")
    print()
