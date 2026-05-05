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
    ObjectStorageConfigError,
    build_object_storage,
    conversion_run_id_from_stem,
    discover_converted_paper_artifacts,
    load_object_storage_settings,
    local_manifest_path,
    mineru_artifact_key,
    upload_converted_paper_artifacts,
)
from src.storage.base import ObjectStorage  # noqa: E402
from src.storage.manifest import ArtifactManifest, ManifestArtifact  # noqa: E402

logger = logging.getLogger(__name__)
MINERU_VERSION = "mineru-cli"
ContentListSnapshot = dict[Path, tuple[int, int]]


def find_content_list(output_dir: Path, stem: str) -> Path | None:
    """Find the content_list.json produced by MinerU for a given PDF stem."""
    # MinerU outputs to <output>/<stem>/<method>/<stem>_content_list.json
    candidates = list(output_dir.glob(f"{stem}/**/{stem}_content_list.json"))
    return candidates[0] if candidates else None


def snapshot_content_list_state(output_dir: Path, stem: str) -> ContentListSnapshot:
    """Capture existing content_list file identity before a forced conversion."""
    snapshot: ContentListSnapshot = {}
    for path in sorted(output_dir.glob(f"{stem}/**/{stem}_content_list.json")):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        snapshot[path] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def content_list_refreshed_since_snapshot(
    content_list_path: Path | None,
    snapshot: ContentListSnapshot,
) -> bool:
    """Return whether a content_list is new or rewritten after the snapshot."""
    if content_list_path is None:
        return False
    try:
        stat = content_list_path.stat()
    except FileNotFoundError:
        return False
    previous_stat = snapshot.get(content_list_path)
    if previous_stat is None:
        return True
    return previous_stat != (stat.st_mtime_ns, stat.st_size)


def _find_unique_content_list_for_manifest(output_dir: Path, stem: str) -> Path | None:
    candidates = sorted(output_dir.glob(f"{stem}/**/{stem}_content_list.json"))
    if not candidates:
        return None
    if len(candidates) > 1:
        logger.warning(
            "Ignoring reusable artifact manifest for %s because multiple "
            "content_list outputs exist: %s",
            stem,
            ", ".join(str(path) for path in candidates),
        )
        return None
    return candidates[0]


def find_artifact_manifest(output_dir: Path, stem: str) -> Path | None:
    """Find the local artifact manifest for a converted PDF stem."""
    content_list_path = _find_unique_content_list_for_manifest(output_dir, stem)
    if content_list_path is None:
        return None
    manifest_path = local_manifest_path(content_list_path, pdf_stem=stem)
    if not manifest_path.is_file():
        return None
    try:
        manifest = ArtifactManifest.from_json(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning(
            "Ignoring invalid artifact manifest for %s: %s",
            stem,
            manifest_path,
        )
        return None
    expected_run_id = conversion_run_id_from_stem(stem)
    if manifest.paper_id != stem:
        logger.warning(
            "Ignoring artifact manifest for %s with paper_id=%s: %s",
            stem,
            manifest.paper_id,
            manifest_path,
        )
        return None
    if manifest.conversion_run_id != expected_run_id:
        logger.warning(
            "Ignoring artifact manifest for %s with conversion_run_id=%s "
            "(expected %s): %s",
            stem,
            manifest.conversion_run_id,
            expected_run_id,
            manifest_path,
        )
        return None
    artifacts_match, mismatch_reason = _manifest_artifacts_match_run_namespace(
        manifest.artifacts,
        conversion_run_id=expected_run_id,
    )
    if not artifacts_match:
        logger.warning(
            "Ignoring artifact manifest for %s with invalid artifact namespace "
            "(%s): %s",
            stem,
            mismatch_reason,
            manifest_path,
        )
        return None
    expected_artifact_keys = _expected_local_artifact_keys(
        content_list_path,
        stem=stem,
        conversion_run_id=expected_run_id,
    )
    manifest_artifact_keys = {artifact.key for artifact in manifest.artifacts}
    if manifest_artifact_keys != expected_artifact_keys or len(
        manifest_artifact_keys
    ) != len(manifest.artifacts):
        logger.warning(
            "Ignoring artifact manifest for %s with incomplete artifact set "
            "(missing=%s extra=%s): %s",
            stem,
            sorted(expected_artifact_keys - manifest_artifact_keys),
            sorted(manifest_artifact_keys - expected_artifact_keys),
            manifest_path,
        )
        return None
    return manifest_path


def _expected_local_artifact_keys(
    content_list_path: Path,
    *,
    stem: str,
    conversion_run_id: str,
) -> set[str]:
    expected_keys = {
        mineru_artifact_key(
            conversion_run_id=conversion_run_id,
            kind="content_list",
            filename="",
        )
    }
    markdown_path = content_list_path.with_name(f"{stem}.md")
    if markdown_path.is_file():
        expected_keys.add(
            mineru_artifact_key(
                conversion_run_id=conversion_run_id,
                kind="markdown",
                filename="",
            )
        )

    images_dir = content_list_path.parent / "images"
    image_paths = sorted(path for path in images_dir.glob("**/*") if path.is_file())
    for image_path in image_paths:
        expected_keys.add(
            mineru_artifact_key(
                conversion_run_id=conversion_run_id,
                kind="image",
                filename=image_path.name,
            )
        )
    return expected_keys


def _manifest_artifacts_match_run_namespace(
    artifacts: tuple[ManifestArtifact, ...],
    *,
    conversion_run_id: str,
) -> tuple[bool, str]:
    if not artifacts:
        return False, "manifest has no artifacts"

    has_content_list = False
    image_prefix = f"artifacts/mineru/{conversion_run_id}/images/"
    for artifact in artifacts:
        if artifact.kind == "content_list":
            if artifact.key != mineru_artifact_key(
                conversion_run_id=conversion_run_id,
                kind="content_list",
                filename="",
            ):
                return False, f"content_list key {artifact.key!r} is not canonical"
            has_content_list = True
        elif artifact.kind == "markdown":
            if artifact.key != mineru_artifact_key(
                conversion_run_id=conversion_run_id,
                kind="markdown",
                filename="",
            ):
                return False, f"markdown key {artifact.key!r} is not canonical"
        elif artifact.kind == "image":
            if not artifact.key.startswith(image_prefix):
                return False, f"image key {artifact.key!r} is outside {image_prefix}"
            filename = artifact.key.removeprefix(image_prefix)
            if not filename or "/" in filename:
                return False, f"image key {artifact.key!r} has invalid filename"
        else:
            return False, f"unexpected artifact kind {artifact.kind!r}"
    if not has_content_list:
        return False, "missing content_list artifact"
    return True, ""


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


def write_manifest_atomic(path: Path, manifest: ArtifactManifest) -> None:
    """Atomically write a local artifact manifest JSON file."""
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(manifest.to_json() + "\n")
        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def upload_batch_artifacts(
    *,
    pdf_paths: list[Path],
    output_dir: Path,
    storage: ObjectStorage,
    mineru_version: str,
    strict: bool = False,
) -> list[ArtifactManifest]:
    manifests: list[ArtifactManifest] = []
    failures: list[tuple[Path, BaseException]] = []
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
            write_manifest_atomic(discovered.manifest_local_path, manifest)
            manifests.append(manifest)
        except Exception as exc:
            failures.append((pdf_path, exc))
            logger.exception(
                "Failed to upload converted artifacts for %s",
                pdf_path.name,
            )
    if failures and strict:
        failed_names = ", ".join(path.name for path, _ in failures)
        raise RuntimeError(
            f"artifact upload failed for {len(failures)} PDF(s): {failed_names}"
        ) from failures[0][1]
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
    parser.add_argument(
        "--strict-upload",
        action="store_true",
        help=(
            "Require production object-storage upload and exit nonzero on "
            "storage config, upload, or missing manifest failures"
        ),
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

    if args.strict_upload:
        seen_run_ids: dict[str, Path] = {}
        duplicate_run_ids: list[str] = []
        for pdf_path in pdf_files:
            try:
                run_id = conversion_run_id_from_stem(pdf_path.stem)
            except Exception as exc:
                logger.error(
                    "Invalid PDF stem for strict upload: %s (%s)",
                    pdf_path.stem,
                    exc,
                )
                sys.exit(1)
            existing_path = seen_run_ids.get(run_id)
            if existing_path is not None:
                duplicate_run_ids.append(run_id)
                logger.error(
                    "Duplicate conversion run ID for strict upload: %s (%s and %s)",
                    run_id,
                    existing_path,
                    pdf_path,
                )
            else:
                seen_run_ids[run_id] = pdf_path
        if duplicate_run_ids:
            sys.exit(1)

    to_convert: list[Path] = []
    skipped_missing_manifest: list[Path] = []
    skipped = 0

    for pdf_path in pdf_files:
        stem = pdf_path.stem
        if not args.force and find_content_list(output_dir, stem) is not None:
            logger.info("Skipping %s (already converted)", stem)
            if args.strict_upload and find_artifact_manifest(output_dir, stem) is None:
                skipped_missing_manifest.append(pdf_path)
            else:
                skipped += 1
        else:
            to_convert.append(pdf_path)

    if not to_convert and not skipped_missing_manifest:
        logger.info("Nothing to convert (%d skipped)", skipped)
        if not args.strict_upload:
            return

    storage: ObjectStorage | None = None
    if args.strict_upload:
        try:
            storage = build_object_storage(load_object_storage_settings())
        except ObjectStorageConfigError as exc:
            logger.error(
                "Storage upload required but object storage is misconfigured: %s",
                exc,
            )
            sys.exit(1)

    forced_content_list_snapshots: dict[str, ContentListSnapshot] = {}
    if args.force and to_convert:
        forced_content_list_snapshots = {
            pdf_path.stem: snapshot_content_list_state(output_dir, pdf_path.stem)
            for pdf_path in to_convert
        }

    success = True
    if to_convert:
        success = run_mineru_batch(
            to_convert, output_dir, args.method, args.backend, args.lang
        )

    converted = 0
    failed = 0
    converted_pdf_paths: list[Path] = []
    for pdf_path in to_convert:
        content_list_path = find_content_list(output_dir, pdf_path.stem)
        if content_list_path is not None:
            forced_content_list_is_stale = (
                args.strict_upload
                and args.force
                and not content_list_refreshed_since_snapshot(
                    content_list_path,
                    forced_content_list_snapshots.get(pdf_path.stem, {}),
                )
            )
            if forced_content_list_is_stale:
                logger.error(
                    "Strict upload failed because forced conversion did not refresh "
                    "content_list for %s",
                    pdf_path.name,
                )
                failed += 1
                continue
            converted += 1
            converted_pdf_paths.append(pdf_path)
        else:
            failed += 1

    uploaded = 0
    upload_candidates = converted_pdf_paths + skipped_missing_manifest
    if upload_candidates:
        try:
            if storage is None:
                storage = build_object_storage(load_object_storage_settings())
            manifests = upload_batch_artifacts(
                pdf_paths=upload_candidates,
                output_dir=output_dir,
                storage=storage,
                mineru_version=MINERU_VERSION,
                strict=args.strict_upload,
            )
            uploaded = len(manifests)
            logger.info("Uploaded artifacts for %d PDFs", uploaded)
        except ObjectStorageConfigError as exc:
            if args.strict_upload:
                logger.error(
                    "Storage upload required but object storage is misconfigured: %s",
                    exc,
                )
                sys.exit(1)
            logger.warning(
                "Storage upload skipped: %s. For local artifact upload, set "
                "OBJECT_STORAGE_DEV_PRESIGN_SECRET and optionally "
                "OBJECT_STORAGE_LOCAL_ROOT=./local/object-store.",
                exc,
            )
        except Exception:
            if args.strict_upload:
                logger.exception(
                    "Storage upload failed; strict upload requires all artifacts"
                )
                sys.exit(1)
            logger.exception(
                "Storage upload unavailable; leaving converted outputs in place"
            )
        if args.strict_upload and uploaded != len(upload_candidates):
            logger.error(
                "Strict upload incomplete: uploaded %d of %d PDFs",
                uploaded,
                len(upload_candidates),
            )
            sys.exit(1)

    if args.strict_upload and failed > 0:
        logger.error(
            "Strict upload failed because %d PDF(s) did not produce content_list",
            failed,
        )
        sys.exit(1)

    if args.strict_upload and args.force and not success:
        logger.error("Strict upload failed because MinerU batch returned failure")
        sys.exit(1)

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
