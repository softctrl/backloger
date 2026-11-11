import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from backloger.repository import Repository
from backloger.schema import reject_unknown

pytestmark = pytest.mark.integration


def test_all_example_backlogs_are_valid() -> None:
    for path in (Path("."), Path("examples/demo"), Path("examples/single")):
        snapshot = Repository(path).snapshot()
        reject_unknown(snapshot.backlog)
        assert snapshot.backlog.work_items


def test_make_targets_and_compose_security() -> None:
    targets = [
        "install",
        "install-dev",
        "build",
        "package",
        "lint",
        "format",
        "typecheck",
        "test",
        "test-unit",
        "test-integration",
        "test-e2e",
        "test-security",
        "coverage",
        "check",
        "validate",
        "serve",
        "export-md",
        "graph",
        "doctor",
        "docker-build",
        "docker-up",
        "docker-down",
        "docker-restart",
        "docker-logs",
        "docker-ps",
        "docker-config",
        "security-scan",
        "sbom",
        "clean",
        "help",
    ]
    for target in targets:
        result = subprocess.run(["make", "--dry-run", target], capture_output=True, text=True)
        assert result.returncode == 0, (target, result.stderr)
        assert result.stdout.strip(), target
    service = yaml.safe_load(Path("compose.yaml").read_text())["services"]["backloger"]
    assert all(port.startswith("127.0.0.1:") for port in service["ports"])
    assert service["read_only"] is True
    assert service["volumes"][0]["read_only"] == "${BACKLOGER_READ_ONLY:-false}"
    assert service["environment"]["BACKLOGER_READ_ONLY"] == service["volumes"][0]["read_only"]
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]


def test_sbom_excludes_dev_dependencies() -> None:
    subprocess.run([sys.executable, "scripts/sbom.py"], check=True, capture_output=True)
    data = json.loads(Path("dist/sbom.spdx.json").read_text())
    names = {p["name"] for p in data["packages"]}
    assert {"backloger", "pydantic", "fastapi", "networkx", "portalocker"} <= names
    assert not names & {"pytest", "ruff", "mypy", "playwright"}
    assert data["spdxVersion"] == "SPDX-2.3"
