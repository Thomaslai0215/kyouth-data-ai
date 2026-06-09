from email import policy
from email.parser import BytesParser
from pathlib import Path

def _extract_html_from_mhtml(mhtml_path: Path) -> str:
    with open(mhtml_path, "rb") as file:
        msg = BytesParser(policy=policy.default).parse(file)

    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)  # always returns bytes
            if payload:
                charset = part.get_content_charset("utf-8") or "utf-8"
                return payload.decode(charset, errors="replace")

    raise ValueError(f"No HTML content found in: {mhtml_path.name}")


def ingest_all_mhtml(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print("🥉 Bronze: Extracting HTML from MHTML files")

    mhtml_files = sorted(input_dir.glob("*.mhtml"))
    total = len(mhtml_files)
    extracted = 0
    failed = 0

    if total == 0:
        print("⚠️ No MHTML files found to ingest.")
        print("\n📊 Bronze Summary:")
        print(f"Total: 0 | Extracted: 0 | Failed: 0")
        return

    for mhtml_path in mhtml_files:
        try:
            html = _extract_html_from_mhtml(mhtml_path)
            output_path = output_dir / f"{mhtml_path.stem}.html"
            output_path.write_text(html, encoding="utf-8")
            extracted += 1
            print(f"✅ Extracted: {mhtml_path.name}")
        except Exception as exc:
            failed += 1
            # Prefer the standardized message when HTML part is missing
            msg = str(exc)
            if "No HTML content found" in msg:
                print(f"⚠️ No HTML content found in: {mhtml_path.name}")
            else:
                print(f"⚠️ Failed to extract {mhtml_path.name}: {exc}")

    print("\n📊 Bronze Summary:")
    print(f"Total: {total} | Extracted: {extracted} | Failed: {failed}")
