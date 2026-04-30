import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

BASE_URL = "https://www.cl.cam.ac.uk/teaching/exams/pastpapers/"
INDEX_URL = urljoin(BASE_URL, "index.csv")
USER_AGENT = "rag-exam-tool/0.1 (+https://github.com/)"
DEFAULT_DELAY = 0.5
TIMEOUT_SECONDS = 30
MAX_RETRIES = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Cambridge CS Tripos past paper question PDFs."
    )
    parser.add_argument(
        "--years",
        help="Year filter. Examples: 2022-2025, 2024, 2022,2024,2025",
    )
    parser.add_argument(
        "--papers",
        help="Comma-separated paper numbers to download. Example: 1,2,3",
    )
    parser.add_argument(
        "--data-dir",
        default="local/corpora/cam-cs-tripos/source-pdfs",
        help="Directory to store downloaded PDFs and metadata.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned downloads without writing files.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="Delay in seconds between requests.",
    )
    return parser.parse_args()


def parse_years(value: str | None) -> set[int] | None:
    if not value:
        return None

    years: set[int] = set()
    for part in value.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_str, end_str = token.split("-", 1)
            start = int(start_str)
            end = int(end_str)
            if end < start:
                raise ValueError(f"Invalid year range: {token}")
            years.update(range(start, end + 1))
        else:
            years.add(int(token))

    return years


def parse_papers(value: str | None) -> set[int] | None:
    if not value:
        return None
    return {int(token.strip()) for token in value.split(",") if token.strip()}


def clean_key(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def first_value(row: dict[str, str], *aliases: str) -> str | None:
    normalized = {clean_key(key): value for key, value in row.items()}
    for alias in aliases:
        value = normalized.get(clean_key(alias))
        if value is not None and value != "":
            return value.strip()
    return None


def require_int(row: dict[str, str], *aliases: str) -> int:
    value = first_value(row, *aliases)
    if value is None:
        alias_list = ", ".join(aliases)
        raise ValueError(f"Missing required field: {alias_list}")
    return int(value)


def resolve_pdf_url(row: dict[str, str]) -> str:
    direct_url = first_value(row, "url", "pdf", "pdf_url", "question_pdf", "link")
    if direct_url:
        return urljoin(BASE_URL, direct_url)

    path = first_value(row, "path", "file", "filename", "pdf_path", "relative_url")
    if path:
        return urljoin(BASE_URL, path)

    year = require_int(row, "year")
    paper = require_int(row, "paper")
    question = require_int(row, "question", "q")
    filename = f"y{year}p{paper}q{question}.pdf"
    return urljoin(BASE_URL, filename)


def fetch_index(session: requests.Session) -> list[dict[str, str]]:
    response = session.get(INDEX_URL, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    reader = csv.DictReader(response.text.splitlines())
    return [dict(row) for row in reader]


def build_download_plan(
    rows: list[dict[str, str]],
    years: set[int] | None,
    papers: set[int] | None,
    data_dir: Path,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for row in rows:
        try:
            year = require_int(row, "year")
            paper = require_int(row, "paper")
            question = require_int(row, "question", "q")
        except ValueError as exc:
            print(f"Skipping malformed row: {exc}", file=sys.stderr)
            continue

        if years is not None and year not in years:
            continue
        if papers is not None and paper not in papers:
            continue

        output_dir = data_dir / str(year)
        filename = f"y{year}p{paper}q{question}.pdf"
        output_path = output_dir / filename
        metadata = {
            "year": year,
            "paper": paper,
            "question": question,
            "topic": first_value(row, "topic", "subject", "section"),
            "author": first_value(row, "author", "setter"),
            "source_url": resolve_pdf_url(row),
        }
        plan.append(
            {
                "url": metadata["source_url"],
                "output_path": output_path,
                "filename": filename,
                "metadata": metadata,
            }
        )

    return sorted(
        plan,
        key=lambda item: (
            item["metadata"]["year"],
            item["metadata"]["paper"],
            item["metadata"]["question"],
        ),
    )


def download_file(
    session: requests.Session,
    url: str,
    output_path: Path,
    delay_seconds: float,
) -> None:
    attempts = 0
    while True:
        attempts += 1
        response = session.get(url, timeout=TIMEOUT_SECONDS)
        if response.status_code == 429 and attempts < MAX_RETRIES:
            retry_after = response.headers.get("Retry-After")
            backoff = (
                float(retry_after) if retry_after else delay_seconds * attempts * 2
            )
            print(
                f"Rate limited for {output_path.name}, retrying in {backoff:.1f}s",
                file=sys.stderr,
            )
            time.sleep(backoff)
            continue

        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        return


def write_metadata(
    data_dir: Path, metadata_by_filename: dict[str, dict[str, Any]]
) -> None:
    metadata_path = data_dir / "metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata_by_filename, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    try:
        args = parse_args()
        years = parse_years(args.years)
        papers = parse_papers(args.papers)
    except ValueError as exc:
        print(f"Invalid arguments: {exc}", file=sys.stderr)
        return 2

    data_dir = Path(args.data_dir)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    try:
        rows = fetch_index(session)
    except requests.RequestException as exc:
        print(f"Failed to fetch CSV index: {exc}", file=sys.stderr)
        return 1

    plan = build_download_plan(rows, years, papers, data_dir)
    if not plan:
        print("No papers matched the requested filters.")
        return 0

    print(f"Matched {len(plan)} question PDFs from {INDEX_URL}")

    downloaded = 0
    skipped = 0
    errors = 0
    metadata_by_filename: dict[str, dict[str, Any]] = {}

    for item in plan:
        output_path = item["output_path"]
        metadata = item["metadata"]
        metadata_by_filename[item["filename"]] = metadata

        if output_path.exists():
            skipped += 1
            print(f"Skip existing {output_path}")
            continue

        if args.dry_run:
            print(f"Would download {item['url']} -> {output_path}")
            continue

        try:
            download_file(session, item["url"], output_path, args.delay)
            downloaded += 1
            print(f"Downloaded {output_path}")
        except requests.RequestException as exc:
            errors += 1
            print(f"Failed {item['url']}: {exc}", file=sys.stderr)

    if not args.dry_run:
        write_metadata(data_dir, metadata_by_filename)
        print(f"Wrote metadata to {data_dir / 'metadata.json'}")

    print(
        f"Summary: downloaded={downloaded} skipped={skipped} "
        f"errors={errors} total={len(plan)}"
    )
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
