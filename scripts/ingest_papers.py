"""Stage exam PDFs to object storage and enqueue production ingest jobs.

Bulk operator path onto the queue-backed ingestion pipeline: discovers PDFs
recursively, uploads each to ``source-pdfs/<collection>/<basename>``, then
enqueues one ``IngestJobMessage`` per staged paper. Already-staged papers
(R2 key exists) are skipped unless --force. SQS credentials come from the
boto3 default chain (use the admin SSO profile); R2 credentials come from
the standard OBJECT_STORAGE_* env vars.

Usage:
    AWS_PROFILE=dev python scripts/ingest_papers.py \
        local/corpora/cam-cs-tripos/source-pdfs \
        --collection cam-cs-tripos --parser cambridge
    # recover a single failed paper:
    AWS_PROFILE=dev python scripts/ingest_papers.py \
        local/corpora/cam-cs-tripos/source-pdfs \
        --collection cam-cs-tripos --parser cambridge \
        --only y2019p8q6.pdf --force
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.chunking.pipeline import PARSER_REGISTRY  # noqa: E402
from src.jobs.models import IngestJobMessage  # noqa: E402
from src.jobs.queue import IngestJobQueue  # noqa: E402
from src.storage.base import InvalidKeyError, ObjectStorage  # noqa: E402
from src.storage.keys import validate_key  # noqa: E402

logger = logging.getLogger(__name__)

WATCH_HINT = (
    "AWS_PROFILE=dev aws logs tail /ecs/lexicon-worker --region eu-west-2 --follow"
)

_SQS_URL_RE = re.compile(r"^https://sqs\.([a-z0-9-]+)\.amazonaws\.com/")


class PreflightError(Exception):
    """Raised for failures detected before any side effect."""


@dataclass(frozen=True)
class PaperAction:
    pdf_path: Path
    object_key: str
    action: Literal["submit", "skip"]


@dataclass(frozen=True)
class PaperResult:
    pdf_path: Path
    object_key: str
    status: Literal["enqueued", "skipped", "failed"]
    job_id: str | None = None
    error: str | None = None


def discover_pdfs(pdf_dir: Path, *, only: list[str] | None) -> list[Path]:
    """Recursively find PDFs, sorted by basename; enforce unique basenames."""
    pdfs = sorted(pdf_dir.rglob("*.pdf"), key=lambda p: p.name)
    if not pdfs:
        raise PreflightError(f"no PDFs found under {pdf_dir}")
    seen: dict[str, Path] = {}
    for pdf in pdfs:
        previous = seen.get(pdf.name)
        if previous is not None:
            raise PreflightError(
                f"duplicate basename {pdf.name!r}: {previous} and {pdf} "
                "(keys are flat per collection)"
            )
        seen[pdf.name] = pdf
    if only is not None:
        wanted = set(only)
        unmatched = wanted - seen.keys()
        if unmatched:
            raise PreflightError(
                f"--only names not found in {pdf_dir}: {sorted(unmatched)}"
            )
        pdfs = [pdf for pdf in pdfs if pdf.name in wanted]
    return pdfs


def resolve_region(queue_url: str) -> str:
    """SQS region from the queue URL host, falling back to AWS_REGION."""
    match = _SQS_URL_RE.match(queue_url)
    if match:
        return match.group(1)
    region = os.environ.get("AWS_REGION")
    if region:
        return region
    raise PreflightError(
        "cannot determine SQS region: queue URL is not a standard "
        "sqs.<region>.amazonaws.com URL and AWS_REGION is unset"
    )


def plan_actions(
    pdfs: list[Path],
    *,
    collection: str,
    storage: ObjectStorage,
    force: bool,
) -> list[PaperAction]:
    """Decide submit/skip per paper. Read-only (HEAD checks only)."""
    actions: list[PaperAction] = []
    for pdf in pdfs:
        key = f"source-pdfs/{collection}/{pdf.name}"
        try:
            validate_key(key)
        except InvalidKeyError as exc:
            raise PreflightError(f"invalid object key {key!r}: {exc}") from exc
        if not force and storage.exists(key):
            actions.append(PaperAction(pdf_path=pdf, object_key=key, action="skip"))
        else:
            actions.append(PaperAction(pdf_path=pdf, object_key=key, action="submit"))
    return actions


def execute_actions(
    actions: list[PaperAction],
    *,
    storage: ObjectStorage,
    queue: IngestJobQueue,
    collection: str,
    parser: str,
    university: str,
) -> list[PaperResult]:
    """Stage then enqueue each submit action; isolate per-paper failures.

    Enqueue happens only after that paper's upload succeeds, so every
    enqueued paper is guaranteed staged even if the batch dies midway.
    """
    results: list[PaperResult] = []
    for action in actions:
        if action.action == "skip":
            logger.info("skip (already staged): %s", action.object_key)
            results.append(
                PaperResult(
                    pdf_path=action.pdf_path,
                    object_key=action.object_key,
                    status="skipped",
                )
            )
            continue
        try:
            storage.put_file(
                key=action.object_key,
                path=action.pdf_path,
                content_type="application/pdf",
            )
            message = IngestJobMessage(
                collection=collection,
                paper_object_key=action.object_key,
                parser=parser,
                university=university,
            )
            queue.enqueue(message)
        except Exception as exc:
            logger.exception("failed: %s", action.pdf_path.name)
            results.append(
                PaperResult(
                    pdf_path=action.pdf_path,
                    object_key=action.object_key,
                    status="failed",
                    error=str(exc),
                )
            )
            continue
        logger.info("enqueued %s as job %s", action.pdf_path.name, message.job_id)
        results.append(
            PaperResult(
                pdf_path=action.pdf_path,
                object_key=action.object_key,
                status="enqueued",
                job_id=message.job_id,
            )
        )
    return results


def render_summary(
    results: list[PaperResult],
    *,
    pdf_dir: Path,
    collection: str,
    parser: str,
    university: str,
) -> str:
    """Human summary: per-paper lines, totals, retry commands, watch hint."""
    lines: list[str] = []
    for result in results:
        if result.status == "enqueued":
            lines.append(f"enqueued  {result.pdf_path.name}  job_id={result.job_id}")
        elif result.status == "skipped":
            lines.append(f"skipped   {result.pdf_path.name}  (already staged)")
        else:
            lines.append(f"FAILED    {result.pdf_path.name}  {result.error}")
    counts = {
        status: sum(1 for r in results if r.status == status)
        for status in ("enqueued", "skipped", "failed")
    }
    lines.append(
        f"{counts['enqueued']} enqueued, {counts['skipped']} skipped, "
        f"{counts['failed']} failed"
    )
    failed = [r for r in results if r.status == "failed"]
    if failed:
        lines.append("retry failed papers individually:")
        for result in failed:
            lines.append(
                f"  python scripts/ingest_papers.py {pdf_dir} "
                f"--collection {collection} --parser {parser} "
                f"--university {university} "
                f"--only {result.pdf_path.name} --force"
            )
    if counts["enqueued"]:
        lines.append(f"watch the worker: {WATCH_HINT}")
    return "\n".join(lines)


def _build_real_dependencies(
    queue_url: str | None,
) -> tuple[ObjectStorage, IngestJobQueue]:
    """Build prod storage + SQS queue from env; preflight both."""
    from src.jobs.sqs import SqsIngestJobQueue
    from src.storage import (
        ObjectStorageConfigError,
        build_object_storage,
        load_object_storage_settings,
    )

    resolved_url = queue_url or os.environ.get("INGEST_QUEUE_URL")
    if not resolved_url:
        raise PreflightError(
            "queue URL required: pass --queue-url or set INGEST_QUEUE_URL"
        )
    try:
        settings = load_object_storage_settings()
    except ObjectStorageConfigError as exc:
        raise PreflightError(f"object storage misconfigured: {exc}") from exc
    if settings.provider == "local":
        raise PreflightError(
            "OBJECT_STORAGE_PROVIDER=local refused: this CLI stages to the "
            "production bucket; export the prod s3 settings"
        )
    storage = build_object_storage(settings)

    region = resolve_region(resolved_url)
    import boto3

    client = boto3.client("sqs", region_name=region)
    try:
        client.get_queue_attributes(QueueUrl=resolved_url, AttributeNames=["QueueArn"])
    except Exception as exc:
        raise PreflightError(f"queue unreachable ({resolved_url}): {exc}") from exc
    queue = SqsIngestJobQueue(queue_url=resolved_url, client=client)
    return storage, queue


def main(
    argv: list[str] | None = None,
    *,
    storage: ObjectStorage | None = None,
    queue: IngestJobQueue | None = None,
) -> int:
    """Returns exit code: 0 success, 1 any paper failed, 2 preflight error.

    `storage` / `queue` are injectable for tests; both default to real
    env-built dependencies (including queue-reachability preflight).
    """
    arg_parser = argparse.ArgumentParser(
        description="Stage exam PDFs to R2 and enqueue production ingest jobs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  AWS_PROFILE=dev python scripts/ingest_papers.py "
            "local/corpora/cam-cs-tripos/source-pdfs "
            "--collection cam-cs-tripos --parser cambridge\n"
        ),
    )
    arg_parser.add_argument(
        "pdf_dir", help="Directory containing PDFs (searched recursively)"
    )
    arg_parser.add_argument("--collection", required=True)
    arg_parser.add_argument("--parser", required=True, choices=sorted(PARSER_REGISTRY))
    arg_parser.add_argument("--university", default="cam")
    arg_parser.add_argument(
        "--only",
        action="append",
        metavar="FILENAME",
        help="Restrict to these PDF basenames (repeatable)",
    )
    arg_parser.add_argument(
        "--queue-url", help="SQS queue URL (default: INGEST_QUEUE_URL env)"
    )
    arg_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions; no uploads or enqueues",
    )
    arg_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-stage and re-enqueue even if already staged",
    )
    args = arg_parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    pdf_dir = Path(args.pdf_dir)
    try:
        if not pdf_dir.is_dir():
            raise PreflightError(f"not a directory: {pdf_dir}")
        if storage is None or queue is None:
            storage, queue = _build_real_dependencies(args.queue_url)
        pdfs = discover_pdfs(pdf_dir, only=args.only)
        actions = plan_actions(
            pdfs,
            collection=args.collection,
            storage=storage,
            force=args.force,
        )
    except PreflightError as exc:
        logger.error("preflight failed: %s", exc)
        return 2

    if args.dry_run:
        for action in actions:
            verb = "stage+enqueue" if action.action == "submit" else "skip"
            print(f"{verb}  {action.pdf_path.name} -> {action.object_key}")
        return 0

    results = execute_actions(
        actions,
        storage=storage,
        queue=queue,
        collection=args.collection,
        parser=args.parser,
        university=args.university,
    )
    print(
        render_summary(
            results,
            pdf_dir=pdf_dir,
            collection=args.collection,
            parser=args.parser,
            university=args.university,
        )
    )
    return 1 if any(r.status == "failed" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
