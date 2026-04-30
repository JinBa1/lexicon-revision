"""Batch-convert PDFs to MinerU output (markdown + content_list.json + images).

Calls `mineru` once per directory of PDFs to leverage GPU batching (the pipeline
backend streams pages from multiple documents through a single inference window).

Usage:
    python scripts/convert_papers.py \
        local/corpora/cam-cs-tripos/source-pdfs/2025 \
        local/corpora/cam-cs-tripos/mineru-output/
    python scripts/convert_papers.py \
        local/test-inputs/pdfs tests/fixtures/mineru/cambridge/ --force
    python scripts/convert_papers.py \
        local/corpora/cam-cs-tripos/source-pdfs/ \
        local/corpora/cam-cs-tripos/mineru-output/ \
        --method auto --backend hybrid-auto-engine
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.storage import (  # noqa: E402
    build_object_storage,
    conversion_run_id_from_stem,
    discover_converted_paper_artifacts,
    load_object_storage_settings,
    upload_converted_paper_artifacts,
)
from src.storage.base import ObjectStorage  # noqa: E402
from src.storage.manifest import ArtifactManifest  # noqa: E402

logger = logging.getLogger(__name__)
MINERU_VERSION = "mineru-cli"


def find_content_list(output_dir: Path, stem: str) -> Path | None:
    """Find the content_list.json produced by MinerU for a given PDF stem."""
    # MinerU outputs to <output>/<stem>/<method>/<stem>_content_list.json
    candidates = list(output_dir.glob(f"{stem}/**/{stem}_content_list.json"))
    return candidates[0] if candidates else None


def run_mineru_batch(
    pdf_paths: list[Path],
    output_dir: Path,
    method: str = "auto",
    backend: str = "hybrid-auto-engine",
    lang: str = "en",
) -> bool:
    """Run MinerU on a batch of PDFs by staging them in a temp directory.

    MinerU's -p flag accepts a directory but only globs one level deep.
    We symlink the selected PDFs into a flat temp directory so MinerU
    processes them all in a single GPU session.

    Returns True if MinerU exited successfully, False otherwise.
    """
    with tempfile.TemporaryDirectory(prefix="mineru_batch_") as tmp:
        tmp_dir = Path(tmp)
        for pdf_path in pdf_paths:
            link = tmp_dir / pdf_path.name
            if not link.exists():
                link.symlink_to(pdf_path.resolve())

        cmd = [
            "mineru",
            "-p",
            str(tmp_dir),
            "-o",
            str(output_dir),
            "-m",
            method,
            "-b",
            backend,
            "-l",
            lang,
        ]
        logger.info(
            "Running MinerU on %d PDFs (backend=%s, method=%s)",
            len(pdf_paths),
            backend,
            method,
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("MinerU batch failed: %s", result.stderr[-500:])
            return False
    return True


def upload_batch_artifacts(
    *,
    pdf_paths: list[Path],
    output_dir: Path,
    storage: ObjectStorage,
    mineru_version: str,
) -> list[ArtifactManifest]:
    manifests: list[ArtifactManifest] = []
    for pdf_path in pdf_paths:
        try:
            discovered = discover_converted_paper_artifacts(
                pdf_path=pdf_path,
                output_dir=output_dir,
            )
            manifest = upload_converted_paper_artifacts(
                storage=storage,
                artifacts=discovered,
                conversion_run_id=conversion_run_id_from_stem(pdf_path.stem),
                mineru_version=mineru_version,
            )
            discovered.manifest_local_path.write_text(
                manifest.to_json() + "\n",
                encoding="utf-8",
            )
            manifests.append(manifest)
        except Exception:
            logger.exception(
                "Failed to upload converted artifacts for %s",
                pdf_path.name,
            )
    return manifests


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-convert PDFs using MinerU CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/convert_papers.py "
            "local/corpora/cam-cs-tripos/source-pdfs/2025 "
            "local/corpora/cam-cs-tripos/mineru-output/\n"
            "  python scripts/convert_papers.py local/test-inputs/pdfs "
            "tests/fixtures/mineru/cambridge/"
            " --force\n"
        ),
    )
    parser.add_argument(
        "pdf_dir", help="Directory containing PDFs (searched recursively)"
    )
    parser.add_argument("output_dir", help="Directory for MinerU output")
    parser.add_argument(
        "--force", action="store_true", help="Re-convert even if output exists"
    )
    parser.add_argument(
        "--method",
        choices=["auto", "txt", "ocr"],
        default="auto",
        help="MinerU parse method (default: auto)",
    )
    _backend_choices = [
        "pipeline",
        "vlm-http-client",
        "hybrid-http-client",
        "vlm-auto-engine",
        "hybrid-auto-engine",
    ]
    parser.add_argument(
        "--backend",
        choices=_backend_choices,
        default="hybrid-auto-engine",
        help="MinerU backend (default: hybrid-auto-engine)",
    )
    parser.add_argument(
        "--lang",
        default="en",
        help="PDF language for OCR (default: en)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    pdf_dir = Path(args.pdf_dir)
    output_dir = Path(args.output_dir)

    if not pdf_dir.exists():
        logger.error("PDF directory not found: %s", pdf_dir)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(pdf_dir.glob("**/*.pdf"))
    if not pdf_files:
        logger.warning("No PDF files found in %s", pdf_dir)
        sys.exit(0)

    # Partition into to-convert vs skip
    to_convert: list[Path] = []
    skipped = 0

    for pdf_path in pdf_files:
        stem = pdf_path.stem
        if not args.force and find_content_list(output_dir, stem) is not None:
            logger.info("Skipping %s (already converted)", stem)
            skipped += 1
        else:
            to_convert.append(pdf_path)

    if not to_convert:
        logger.info("Nothing to convert (%d skipped)", skipped)
        return

    # Run MinerU in a single batch for GPU efficiency
    success = run_mineru_batch(
        to_convert, output_dir, args.method, args.backend, args.lang
    )

    # Count results
    converted = 0
    failed = 0
    converted_pdf_paths: list[Path] = []
    for pdf_path in to_convert:
        if find_content_list(output_dir, pdf_path.stem) is not None:
            converted += 1
            converted_pdf_paths.append(pdf_path)
        else:
            failed += 1

    uploaded = 0
    if converted > 0:
        try:
            storage = build_object_storage(load_object_storage_settings())
            manifests = upload_batch_artifacts(
                pdf_paths=converted_pdf_paths,
                output_dir=output_dir,
                storage=storage,
                mineru_version=MINERU_VERSION,
            )
            uploaded = len(manifests)
            logger.info("Uploaded artifacts for %d PDFs", uploaded)
        except Exception:
            logger.exception(
                "Storage upload unavailable; leaving converted outputs in place"
            )

    if not success and failed == len(to_convert):
        logger.error("MinerU batch failed for all %d PDFs", failed)
    else:
        logger.info(
            "Done: %d converted, %d skipped, %d failed, %d uploaded (of %d total)",
            converted,
            skipped,
            failed,
            uploaded,
            len(pdf_files),
        )


if __name__ == "__main__":
    main()
