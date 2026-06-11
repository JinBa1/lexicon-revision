"""Reusable PDF -> MinerU -> artifact upload conversion flow."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from src.storage import (
    conversion_run_id_from_stem,
    discover_converted_paper_artifacts,
    upload_converted_paper_artifacts,
)
from src.storage.base import ObjectStorage
from src.storage.manifest import ArtifactManifest

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


class ConversionFailedError(Exception):
    """MinerU conversion or artifact upload failed for a paper."""


def convert_single_pdf(
    *,
    pdf_path: Path,
    output_dir: Path,
    storage: ObjectStorage,
    method: str = "auto",
    backend: str = "pipeline",
    lang: str = "en",
) -> ArtifactManifest:
    """Convert one PDF and upload its artifacts. Worker entry point.

    `backend` defaults to MinerU's CPU-capable `pipeline` backend; the
    GPU-oriented `hybrid-auto-engine` default stays in the batch CLI.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ok = run_mineru_batch([pdf_path], output_dir, method, backend, lang)
    if not ok:
        raise ConversionFailedError(f"MinerU failed for {pdf_path.name}")
    manifests = upload_batch_artifacts(
        pdf_paths=[pdf_path],
        output_dir=output_dir,
        storage=storage,
        mineru_version=MINERU_VERSION,
        strict=True,
    )
    if not manifests:
        raise ConversionFailedError(
            f"artifact upload produced no manifest for {pdf_path.name}"
        )
    return manifests[0]
