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
import hashlib
import logging
import sys
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.conversion import (  # noqa: E402,F401
    MINERU_VERSION,
    find_content_list,
    logger,
    run_mineru_batch,
    upload_batch_artifacts,
    write_manifest_atomic,
)
from src.storage import (  # noqa: E402
    ObjectStorageConfigError,
    build_object_storage,
    conversion_run_id_from_stem,
    load_object_storage_settings,
    local_manifest_path,
    mineru_artifact_key,
    sha256_blob_key,
)
from src.storage.base import ObjectStorage  # noqa: E402
from src.storage.manifest import ArtifactManifest, ManifestArtifact  # noqa: E402

ContentListSnapshot = dict[Path, tuple[int, int]]
ManifestReuseStatus = Literal["reuse", "upload", "convert"]


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
    status, manifest_path = _classify_artifact_manifest_reuse(
        output_dir,
        stem=stem,
    )
    if status != "reuse":
        return None
    return manifest_path


def _classify_artifact_manifest_reuse(
    output_dir: Path,
    *,
    stem: str,
    pdf_path: Path | None = None,
    storage: ObjectStorage | None = None,
) -> tuple[ManifestReuseStatus, Path | None]:
    """Return whether a converted output can reuse its local manifest.

    ``convert`` means the source PDF bytes differ from the manifest, so the
    local MinerU output may also be stale. Other invalid or missing manifests
    can be repaired by uploading the current local artifacts.
    """
    content_list_path = _find_unique_content_list_for_manifest(output_dir, stem)
    if content_list_path is None:
        return "upload", None
    manifest_path = local_manifest_path(content_list_path, pdf_stem=stem)
    if not manifest_path.is_file():
        return "upload", None
    try:
        manifest = ArtifactManifest.from_json(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning(
            "Ignoring invalid artifact manifest for %s: %s",
            stem,
            manifest_path,
        )
        return "upload", None
    expected_run_id = conversion_run_id_from_stem(stem)
    if manifest.paper_id != stem:
        logger.warning(
            "Ignoring artifact manifest for %s with paper_id=%s: %s",
            stem,
            manifest.paper_id,
            manifest_path,
        )
        return "upload", None
    if manifest.conversion_run_id != expected_run_id:
        logger.warning(
            "Ignoring artifact manifest for %s with conversion_run_id=%s "
            "(expected %s): %s",
            stem,
            manifest.conversion_run_id,
            expected_run_id,
            manifest_path,
        )
        return "upload", None
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
        return "upload", None
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
        return "upload", None
    if pdf_path is not None and not _manifest_source_pdf_matches(manifest, pdf_path):
        logger.warning(
            "Ignoring artifact manifest for %s because source_pdf_key does not "
            "match current PDF bytes: %s",
            stem,
            manifest_path,
        )
        return "convert", None
    if storage is not None and not _manifest_storage_objects_exist(manifest, storage):
        logger.warning(
            "Ignoring artifact manifest for %s because referenced object storage "
            "keys are missing: %s",
            stem,
            manifest_path,
        )
        return "upload", None
    return "reuse", manifest_path


def _manifest_source_pdf_matches(
    manifest: ArtifactManifest,
    pdf_path: Path,
) -> bool:
    pdf_sha256_hex = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    expected_key = sha256_blob_key(sha256_hex=pdf_sha256_hex, extension="pdf")
    return manifest.source_pdf_key == expected_key


def _manifest_storage_objects_exist(
    manifest: ArtifactManifest,
    storage: ObjectStorage,
) -> bool:
    keys = [
        manifest.source_pdf_key,
        *[artifact.key for artifact in manifest.artifacts],
        mineru_artifact_key(
            conversion_run_id=manifest.conversion_run_id,
            kind="manifest",
            filename="",
        ),
    ]
    for key in keys:
        try:
            if not storage.exists(key):
                return False
        except Exception:
            logger.warning(
                "Unable to verify artifact object exists in storage: %s",
                key,
                exc_info=True,
            )
            return False
    return True


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

    to_convert: list[Path] = []
    skipped_missing_manifest: list[Path] = []
    skipped = 0

    for pdf_path in pdf_files:
        stem = pdf_path.stem
        content_list_path = find_content_list(output_dir, stem)
        if not args.force and content_list_path is not None:
            if args.strict_upload:
                manifest_status, _manifest_path = _classify_artifact_manifest_reuse(
                    output_dir,
                    stem=stem,
                    pdf_path=pdf_path,
                    storage=storage,
                )
                if manifest_status == "reuse":
                    logger.info("Skipping %s (already converted and uploaded)", stem)
                    skipped += 1
                elif manifest_status == "convert":
                    logger.info(
                        "Re-converting %s (source PDF differs from manifest)",
                        stem,
                    )
                    to_convert.append(pdf_path)
                else:
                    logger.info(
                        "Re-uploading artifacts for %s (manifest not reusable)",
                        stem,
                    )
                    skipped_missing_manifest.append(pdf_path)
            else:
                logger.info("Skipping %s (already converted)", stem)
                skipped += 1
        else:
            to_convert.append(pdf_path)

    if not to_convert and not skipped_missing_manifest:
        logger.info("Nothing to convert (%d skipped)", skipped)
        if not args.strict_upload:
            return

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
