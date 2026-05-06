from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FLYCTL_ACTION_SHA = "ed8efb33836e8b2096c7fd3ba1c8afe303ebbff1"


def _load_workflow(name: str) -> dict[str, Any]:
    workflow_path = REPO_ROOT / ".github" / "workflows" / name
    assert workflow_path.exists(), f"{workflow_path} does not exist"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    return workflow


def test_backend_cd_waits_for_main_ci_or_manual_dispatch() -> None:
    workflow = _load_workflow("deploy-backend.yml")

    triggers = workflow.get(True) or workflow.get("on")
    assert triggers == {
        "workflow_run": {
            "workflows": ["CI"],
            "types": ["completed"],
            "branches": ["main"],
        },
        "workflow_dispatch": {},
    }

    deploy_job = workflow["jobs"]["deploy"]
    assert "workflow_run.conclusion == 'success'" in deploy_job["if"]
    assert "workflow_run.event == 'push'" in deploy_job["if"]
    assert "github.ref == 'refs/heads/main'" in deploy_job["if"]
    assert workflow["concurrency"]["group"] == "backend-production"


def test_ci_lints_github_actions_workflows() -> None:
    workflow = _load_workflow("ci.yml")
    actionlint_job = workflow["jobs"]["actionlint"]

    assert actionlint_job["runs-on"] == "ubuntu-latest"
    assert actionlint_job["permissions"] == {"contents": "read"}

    steps = actionlint_job["steps"]
    assert any(step.get("uses") == "actions/checkout@v4" for step in steps)
    assert any(step.get("uses") == "actions/setup-go@v5" for step in steps)
    assert {
        "name": "Install actionlint",
        "run": "go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.12",
    } in steps
    assert {
        "name": "Lint GitHub Actions workflows",
        "run": '"$(go env GOPATH)/bin/actionlint"',
    } in steps


def test_backend_cd_records_production_environment_and_deploys_fly() -> None:
    workflow = _load_workflow("deploy-backend.yml")
    deploy_job = workflow["jobs"]["deploy"]

    assert workflow["permissions"] == {"contents": "read"}
    assert deploy_job["permissions"] == {"contents": "read", "deployments": "write"}
    assert deploy_job["environment"] == {
        "name": "production",
        "url": "https://lexiconrevision.uk",
    }

    steps = deploy_job["steps"]
    assert any(step.get("uses") == "actions/checkout@v4" for step in steps)
    assert any(
        step.get("uses") == f"superfly/flyctl-actions/setup-flyctl@{FLYCTL_ACTION_SHA}"
        for step in steps
    )
    deploy_steps = [
        step for step in steps if step.get("run") == "flyctl deploy --remote-only"
    ]
    assert deploy_steps == [
        {
            "name": "Deploy Fly backend",
            "run": "flyctl deploy --remote-only",
            "env": {"FLY_API_TOKEN": "${{ secrets.FLY_API_TOKEN }}"},
        }
    ]


def test_backend_cd_smokes_live_frontend_and_backend_after_deploy() -> None:
    workflow = _load_workflow("deploy-backend.yml")
    smoke_job = workflow["jobs"]["smoke"]

    assert smoke_job["needs"] == "deploy"
    assert smoke_job["env"] == {
        "API_ORIGIN": "https://lexicon-revision-api.fly.dev",
        "FRONTEND_ORIGIN": "https://lexiconrevision.uk",
    }

    smoke_script = "\n".join(
        step["run"] for step in smoke_job["steps"] if "run" in step
    )
    for expected in [
        "--retry 3",
        "--retry-all-errors",
        "/healthz",
        "/readyz",
        "/collections",
        "access-control-allow-origin: https://lexiconrevision.uk",
        "cambridge-cs-tripos",
        "edinburgh-mece10017",
        "paper_count",
        "locked_requires_signin",
        "/assets/index-",
    ]:
        assert expected in smoke_script
    assert "744" not in smoke_script
