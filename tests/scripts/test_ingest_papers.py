"""Tests for the bulk operator ingest CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.ingest_papers import (
    PaperAction,
    PaperResult,
    PreflightError,
    discover_pdfs,
    execute_actions,
    main,
    plan_actions,
    render_summary,
    resolve_region,
)
from src.jobs.queue import InMemoryIngestJobQueue


class FakeStorage:
    """Dict-backed ObjectStorage stand-in (exists/put_file only)."""

    def __init__(self, existing: tuple[str, ...] = ()) -> None:
        self.existing = set(existing)
        self.uploaded: dict[str, Path] = {}

    def exists(self, key: str) -> bool:
        return key in self.existing

    def put_file(
        self, *, key: str, path: Path, content_type: str | None = None
    ) -> None:
        self.uploaded[key] = Path(path)
        self.existing.add(key)


def _make_pdfs(root: Path, names_by_subdir: dict[str, list[str]]) -> None:
    for subdir, names in names_by_subdir.items():
        directory = root / subdir if subdir else root
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            (directory / name).write_bytes(b"%PDF-1.4 test")


class TestDiscoverPdfs:
    def test_recursive_and_sorted_by_basename(self, tmp_path: Path) -> None:
        _make_pdfs(tmp_path, {"2023": ["y2023p7q8.pdf"], "2019": ["y2019p8q6.pdf"]})
        result = discover_pdfs(tmp_path, only=None)
        assert [p.name for p in result] == ["y2019p8q6.pdf", "y2023p7q8.pdf"]

    def test_ignores_non_pdf_files(self, tmp_path: Path) -> None:
        _make_pdfs(tmp_path, {"": ["y2019p8q6.pdf"]})
        (tmp_path / "metadata.json").write_text("{}")
        result = discover_pdfs(tmp_path, only=None)
        assert [p.name for p in result] == ["y2019p8q6.pdf"]

    def test_empty_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PreflightError, match="no PDFs"):
            discover_pdfs(tmp_path, only=None)

    def test_duplicate_basenames_across_subdirs_raise(self, tmp_path: Path) -> None:
        _make_pdfs(tmp_path, {"2019": ["y2019p8q6.pdf"], "extra": ["y2019p8q6.pdf"]})
        with pytest.raises(PreflightError, match="duplicate basename"):
            discover_pdfs(tmp_path, only=None)

    def test_only_filters_by_basename(self, tmp_path: Path) -> None:
        _make_pdfs(tmp_path, {"2019": ["y2019p8q6.pdf"], "2023": ["y2023p7q8.pdf"]})
        result = discover_pdfs(tmp_path, only=["y2023p7q8.pdf"])
        assert [p.name for p in result] == ["y2023p7q8.pdf"]

    def test_only_with_unmatched_name_raises(self, tmp_path: Path) -> None:
        _make_pdfs(tmp_path, {"2019": ["y2019p8q6.pdf"]})
        with pytest.raises(PreflightError, match="nope.pdf"):
            discover_pdfs(tmp_path, only=["nope.pdf"])


class TestResolveRegion:
    def test_parses_region_from_standard_queue_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AWS_REGION", raising=False)
        url = "https://sqs.eu-west-2.amazonaws.com/757706350311/lexicon-ingest"
        assert resolve_region(url) == "eu-west-2"

    def test_falls_back_to_aws_region_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        assert resolve_region("https://example.com/queue") == "eu-west-1"

    def test_no_region_anywhere_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AWS_REGION", raising=False)
        with pytest.raises(PreflightError, match="region"):
            resolve_region("https://example.com/queue")


class TestPlanActions:
    def test_missing_keys_planned_as_submit(self, tmp_path: Path) -> None:
        _make_pdfs(tmp_path, {"": ["y2019p8q6.pdf"]})
        pdfs = discover_pdfs(tmp_path, only=None)
        actions = plan_actions(
            pdfs, collection="cam-test", storage=FakeStorage(), force=False
        )
        assert actions == [
            PaperAction(
                pdf_path=pdfs[0],
                object_key="source-pdfs/cam-test/y2019p8q6.pdf",
                action="submit",
            )
        ]

    def test_existing_keys_planned_as_skip(self, tmp_path: Path) -> None:
        _make_pdfs(tmp_path, {"": ["y2019p8q6.pdf"]})
        pdfs = discover_pdfs(tmp_path, only=None)
        storage = FakeStorage(existing=("source-pdfs/cam-test/y2019p8q6.pdf",))
        actions = plan_actions(
            pdfs, collection="cam-test", storage=storage, force=False
        )
        assert actions[0].action == "skip"

    def test_force_overrides_skip(self, tmp_path: Path) -> None:
        _make_pdfs(tmp_path, {"": ["y2019p8q6.pdf"]})
        pdfs = discover_pdfs(tmp_path, only=None)
        storage = FakeStorage(existing=("source-pdfs/cam-test/y2019p8q6.pdf",))
        actions = plan_actions(pdfs, collection="cam-test", storage=storage, force=True)
        assert actions[0].action == "submit"

    def test_invalid_collection_raises(self, tmp_path: Path) -> None:
        _make_pdfs(tmp_path, {"": ["y2019p8q6.pdf"]})
        pdfs = discover_pdfs(tmp_path, only=None)
        with pytest.raises(PreflightError, match="invalid object key"):
            plan_actions(pdfs, collection="../evil", storage=FakeStorage(), force=False)


class FailingStorage(FakeStorage):
    """put_file raises for keys in `fail_keys`."""

    def __init__(self, fail_keys: tuple[str, ...]) -> None:
        super().__init__()
        self.fail_keys = set(fail_keys)

    def put_file(
        self, *, key: str, path: Path, content_type: str | None = None
    ) -> None:
        if key in self.fail_keys:
            raise RuntimeError("upload exploded")
        super().put_file(key=key, path=path, content_type=content_type)


def _actions_for(tmp_path: Path, names: list[str]) -> list[PaperAction]:
    _make_pdfs(tmp_path, {"": names})
    pdfs = discover_pdfs(tmp_path, only=None)
    return plan_actions(pdfs, collection="cam-test", storage=FakeStorage(), force=False)


class TestExecuteActions:
    def test_submits_stage_then_enqueue(self, tmp_path: Path) -> None:
        actions = _actions_for(tmp_path, ["y2019p8q6.pdf"])
        storage = FakeStorage()
        queue = InMemoryIngestJobQueue()
        results = execute_actions(
            actions,
            storage=storage,
            queue=queue,
            collection="cam-test",
            parser="cambridge",
            university="cam",
        )
        assert results[0].status == "enqueued"
        assert results[0].job_id
        assert "source-pdfs/cam-test/y2019p8q6.pdf" in storage.uploaded
        received = queue.receive()
        assert received is not None
        assert received.message.paper_object_key == (
            "source-pdfs/cam-test/y2019p8q6.pdf"
        )
        assert received.message.parser == "cambridge"
        assert received.message.collection == "cam-test"
        assert received.message.job_id == results[0].job_id

    def test_skip_actions_touch_nothing(self, tmp_path: Path) -> None:
        actions = [
            PaperAction(
                pdf_path=tmp_path / "y2019p8q6.pdf",
                object_key="source-pdfs/cam-test/y2019p8q6.pdf",
                action="skip",
            )
        ]
        storage = FakeStorage()
        queue = InMemoryIngestJobQueue()
        results = execute_actions(
            actions,
            storage=storage,
            queue=queue,
            collection="cam-test",
            parser="cambridge",
            university="cam",
        )
        assert results[0].status == "skipped"
        assert not storage.uploaded
        assert queue.receive() is None

    def test_one_failure_does_not_stop_batch(self, tmp_path: Path) -> None:
        actions = _actions_for(tmp_path, ["a-fail.pdf", "b-ok.pdf"])
        storage = FailingStorage(fail_keys=("source-pdfs/cam-test/a-fail.pdf",))
        queue = InMemoryIngestJobQueue()
        results = execute_actions(
            actions,
            storage=storage,
            queue=queue,
            collection="cam-test",
            parser="cambridge",
            university="cam",
        )
        by_name = {r.pdf_path.name: r for r in results}
        assert by_name["a-fail.pdf"].status == "failed"
        assert "upload exploded" in (by_name["a-fail.pdf"].error or "")
        assert by_name["b-ok.pdf"].status == "enqueued"

    def test_enqueue_failure_recorded_as_failed(self, tmp_path: Path) -> None:
        class ExplodingQueue(InMemoryIngestJobQueue):
            def enqueue(self, message: object) -> None:
                raise RuntimeError("sqs exploded")

        actions = _actions_for(tmp_path, ["y2019p8q6.pdf"])
        results = execute_actions(
            actions,
            storage=FakeStorage(),
            queue=ExplodingQueue(),
            collection="cam-test",
            parser="cambridge",
            university="cam",
        )
        assert results[0].status == "failed"
        assert "sqs exploded" in (results[0].error or "")


class TestRenderSummary:
    def test_summary_lists_counts_jobids_and_retry_commands(
        self, tmp_path: Path
    ) -> None:
        results = [
            PaperResult(
                pdf_path=tmp_path / "a.pdf",
                object_key="source-pdfs/c/a.pdf",
                status="enqueued",
                job_id="job-123",
            ),
            PaperResult(
                pdf_path=tmp_path / "b.pdf",
                object_key="source-pdfs/c/b.pdf",
                status="skipped",
            ),
            PaperResult(
                pdf_path=tmp_path / "f.pdf",
                object_key="source-pdfs/c/f.pdf",
                status="failed",
                error="boom",
            ),
        ]
        text = render_summary(
            results,
            pdf_dir=tmp_path,
            collection="c",
            parser="cambridge",
            university="cam",
        )
        assert "job-123" in text
        assert "1 enqueued, 1 skipped, 1 failed" in text
        assert "--only f.pdf --force" in text
        assert "aws logs tail /ecs/lexicon-worker" in text


class TestMain:
    def _argv(self, tmp_path: Path, *extra: str) -> list[str]:
        return [
            str(tmp_path),
            "--collection",
            "cam-test",
            "--parser",
            "cambridge",
            *extra,
        ]

    def test_happy_path_exits_zero_and_enqueues(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _make_pdfs(tmp_path, {"2019": ["y2019p8q6.pdf"]})
        storage = FakeStorage()
        queue = InMemoryIngestJobQueue()
        code = main(self._argv(tmp_path), storage=storage, queue=queue)
        assert code == 0
        assert queue.receive() is not None
        out = capsys.readouterr().out
        assert "1 enqueued, 0 skipped, 0 failed" in out

    def test_university_defaults_to_cam(self, tmp_path: Path) -> None:
        _make_pdfs(tmp_path, {"": ["y2019p8q6.pdf"]})
        queue = InMemoryIngestJobQueue()
        main(self._argv(tmp_path), storage=FakeStorage(), queue=queue)
        received = queue.receive()
        assert received is not None
        assert received.message.university == "cam"

    def test_dry_run_has_no_side_effects(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _make_pdfs(tmp_path, {"": ["y2019p8q6.pdf"]})
        storage = FakeStorage()
        queue = InMemoryIngestJobQueue()
        code = main(self._argv(tmp_path, "--dry-run"), storage=storage, queue=queue)
        assert code == 0
        assert not storage.uploaded
        assert queue.receive() is None
        out = capsys.readouterr().out
        assert "stage+enqueue" in out

    def test_failure_exits_one(self, tmp_path: Path) -> None:
        _make_pdfs(tmp_path, {"": ["y2019p8q6.pdf"]})
        storage = FailingStorage(fail_keys=("source-pdfs/cam-test/y2019p8q6.pdf",))
        code = main(
            self._argv(tmp_path), storage=storage, queue=InMemoryIngestJobQueue()
        )
        assert code == 1

    def test_preflight_error_exits_two_before_side_effects(
        self, tmp_path: Path
    ) -> None:
        # empty dir -> discovery preflight failure
        storage = FakeStorage()
        queue = InMemoryIngestJobQueue()
        code = main(self._argv(tmp_path), storage=storage, queue=queue)
        assert code == 2
        assert not storage.uploaded

    def test_unknown_parser_rejected_by_argparse(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(
                [str(tmp_path), "--collection", "c", "--parser", "nonsense"],
                storage=FakeStorage(),
                queue=InMemoryIngestJobQueue(),
            )
        assert excinfo.value.code == 2
