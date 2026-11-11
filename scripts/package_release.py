"""Assemble an explicit installation bundle, without copying the workspace."""

import hashlib
import json
import tomllib
import zipfile
from pathlib import Path


def build_release(root: Path, output: Path) -> Path:
    config = tomllib.loads((root / "pyproject.toml").read_text())
    version = config["project"]["version"]
    if not version or any(c not in "0123456789abcdefghijklmnopqrstuvwxyz.+-" for c in version):
        raise ValueError("Versão inválida para o nome do pacote")
    artifacts = [
        f"backloger-{version}-py3-none-any.whl",
        f"backloger-{version}.tar.gz",
        "sbom.spdx.json",
        "requirements-runtime.txt",
    ]
    files = {name: (output / name).read_bytes() for name in artifacts}
    for name in ("README.md", "INSTALL.md", "CHANGELOG.md", "LICENSE", ".gitignore", "action.yml"):
        files[name] = (root / name).read_bytes()
    files["install.py"] = (root / "scripts/install_release.py").read_bytes()
    for directory, extensions in (
        ("docs", {".md", ".svg"}),
        ("schemas", {".json"}),
        ("examples", {".json", ".yml", ".md", ".csv"}),
        ("skills", {".md", ".py", ".yaml", ".json"}),
    ):
        for path in sorted((root / directory).rglob("*")):
            if path.is_file() and path.suffix in extensions:
                relative = path.relative_to(root)
                if ".runtime" in relative.parts or "__pycache__" in relative.parts:
                    continue
                if any(part.is_symlink() for part in [path, *path.parents] if part != root):
                    raise ValueError(f"Link simbólico não permitido no pacote: {relative}")
                files[relative.as_posix()] = path.read_bytes()
    manifest = {
        "name": "backloger",
        "version": version,
        "requires_python": config["project"]["requires-python"],
        "schema_version": "1.0.0",
        "dependency_wheels_included": False,
        "artifact_signature": None,
        "sha256": {name: hashlib.sha256(files[name]).hexdigest() for name in artifacts},
    }
    files["release.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    files["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in sorted(files.items())
    ).encode()
    archive = output / f"backloger-{version}-install.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in sorted(files.items()):
            bundle.writestr(f"backloger-{version}/{name}", content)
    (output / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((output / name).read_bytes()).hexdigest()}  {name}\n"
            for name in [*artifacts, archive.name]
        )
    )
    print(f"Instalador: {archive} ({archive.stat().st_size} bytes)")
    print(f"Integridade: {output / 'SHA256SUMS'}")
    return archive


if __name__ == "__main__":
    build_release(Path.cwd().resolve(), Path("dist"))
