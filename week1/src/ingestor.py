import logging
from email import policy
from email.parser import BytesParser
from pathlib import Path

logger = logging.getLogger(__name__)


def _extract_html_from_mhtml(mhtml_path: Path) -> str:
    """Read one MHTML file and return the HTML text inside it."""
    with open(mhtml_path, "rb") as file:
        msg = BytesParser(policy=policy.default).parse(file)

    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset("utf-8") or "utf-8"
                return payload.decode(charset, errors="replace")

    raise ValueError(f"No HTML content found in: {mhtml_path.name}")


def ingest_all_mhtml(input_dir: Path, output_dir: Path) -> None:
    """Convert every MHTML file in input_dir to HTML files in output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    print("🥉 Bronze: Extracting HTML from MHTML files")

    mhtml_files = sorted(input_dir.glob("*.mhtml"))
    total = len(mhtml_files)
    extracted = 0
    failed = 0

    if total == 0:
        logger.warning("No MHTML files found to ingest.")
        print("\n📊 Bronze Summary:")
        print(f"Total: 0 | Extracted: 0 | Failed: 0")
        return

    for mhtml_path in mhtml_files:
        try:
            html = _extract_html_from_mhtml(mhtml_path)
            output_path = output_dir / f"{mhtml_path.stem}.html"
            output_path.write_text(html, encoding="utf-8")
            extracted += 1
            logger.info(f"Extracted: {mhtml_path.name}")
        except Exception as exc:
            failed += 1
            msg = str(exc)
            if "No HTML content found" in msg:
                logger.warning(f"No HTML content found in: {mhtml_path.name}")
            else:
                logger.error(f"Failed to extract {mhtml_path.name} | Reason: {exc}")

    print("\n📊 Bronze Summary:")
    print(f"Total: {total} | Extracted: {extracted} | Failed: {failed}")
    print()
