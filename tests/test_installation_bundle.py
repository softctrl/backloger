import hashlib
import json
import runpy
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def build_fixture(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text('[project]\nversion="0.1.0"\nrequires-python=">=3.12"\n')
    for name in ("README.md", "INSTALL.md", "CHANGELOG.md", "LICENSE", ".gitignore", "action.yml"):
        shutil.copyfile(name, source / name)
    (source / "scripts").mkdir()
    shutil.copyfile("scripts/install_release.py", source / "scripts/install_release.py")
    for name in (
        "docs/REPORTS.md",
        "schemas/1.0.0/work-item.schema.json",
        "examples/demo/.backloger/project.json",
        "examples/migration/legacy-status.csv",
        "skills/backloger-adoption/SKILL.md",
        "skills/backloger-adoption/scripts/stage_backlog.py",
        "skills/backloger-adoption/agents/openai.yaml",
        "skills/backloger-adoption/references/integration.md",
        "skills/backloger-adoption/assets/AGENTS.backloger.md",
        "examples/demo/.backloger/.runtime/audit/secret.json",
        ".backloger/.runtime/audit/secret.json",
        ".env",
        ".aws/credentials",
        "unrelated.json",
    ):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("example fixture")
    output = source / "dist"
    output.mkdir()
    for name in (
        "backloger-0.1.0-py3-none-any.whl",
        "backloger-0.1.0.tar.gz",
        "sbom.spdx.json",
        "requirements-runtime.txt",
    ):
        (output / name).write_text(name)
    script = runpy.run_path("scripts/package_release.py")
    return script["build_release"](source, output)


def test_installation_bundle_checksums_and_selected_contents(tmp_path: Path) -> None:
    archive = build_fixture(tmp_path)
    with zipfile.ZipFile(archive) as bundle:
        names = {Path(name).relative_to("backloger-0.1.0").as_posix() for name in bundle.namelist()}
        assert {
            "install.py",
            "INSTALL.md",
            "SHA256SUMS",
            "release.json",
            ".gitignore",
            "action.yml",
            "backloger-0.1.0-py3-none-any.whl",
            "docs/REPORTS.md",
            "schemas/1.0.0/work-item.schema.json",
            "examples/demo/.backloger/project.json",
            "examples/migration/legacy-status.csv",
            "skills/backloger-adoption/SKILL.md",
            "skills/backloger-adoption/scripts/stage_backlog.py",
            "skills/backloger-adoption/references/integration.md",
            "skills/backloger-adoption/assets/AGENTS.backloger.md",
        } <= names
        assert not any(".runtime" in name or ".aws" in name or name == ".env" for name in names)
        assert "unrelated.json" not in names
        manifest = json.loads(bundle.read("backloger-0.1.0/release.json"))
        assert manifest["dependency_wheels_included"] is False
        assert manifest["artifact_signature"] is None
        for name, digest in manifest["sha256"].items():
            assert hashlib.sha256(bundle.read("backloger-0.1.0/" + name)).hexdigest() == digest
        bundle.extractall(tmp_path / "extracted")
    for line in (archive.parent / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert hashlib.sha256((archive.parent / name).read_bytes()).hexdigest() == expected
    installed = tmp_path / "extracted/backloger-0.1.0"
    result = subprocess.run(
        [sys.executable, str(installed / "install.py"), "--check"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert not (installed / ".venv").exists()
    (installed / "backloger-0.1.0-py3-none-any.whl").write_text("corrupted")
    result = subprocess.run(
        [sys.executable, str(installed / "install.py")], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 1 and "Integridade inválida" in result.stderr
    assert not (installed / ".venv").exists()


def test_gitignore_preserves_project_contract_docs_and_lockfiles(tmp_path: Path) -> None:
    shutil.copyfile(".gitignore", tmp_path / ".gitignore")
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    ignored = [
        ".venv/bin/python",
        "src/backloger/__pycache__/models.pyc",
        "dist/installer.zip",
        ".env",
        ".env.local",
        ".aws/credentials",
        "debug.log",
        "node_modules/jsdom/index.js",
        ".coverage.123",
        "playwright-report/index.html",
        ".vscode/local.json",
        ".backloger/.runtime/backups/item.json",
        "examples/demo/.backloger/.runtime/audit/x.json",
    ]
    tracked = [
        ".gitignore",
        ".env.example",
        ".env.local.example",
        ".env.template",
        "AGENTS.md",
        "pyproject.toml",
        "uv.lock",
        "package-lock.json",
        ".github/workflows/ci.yml",
        ".backloger/project.json",
        ".backloger/work-items/SYS-001.json",
        "backlog.json",
        "examples/demo/.backloger/project.json",
        "schemas/1.0.0/work-item.schema.json",
        "docs/BACKLOG.md",
        "docs/graph.svg",
        "INSTALL.md",
        ".vscode/extensions.json",
    ]
    result = subprocess.run(
        ["git", "-C", str(tmp_path), "check-ignore", "--stdin"],
        input="\n".join([*ignored, *tracked]) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    assert set(result.stdout.splitlines()) == set(ignored)
