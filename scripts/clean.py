"""An allowlist protects canonical JSON, backups and unrelated workspace files."""

import shutil
from pathlib import Path

for name in (
    "dist",
    "build",
    "htmlcov",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".coverage",
):
    path = Path(name)
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
for root in (Path("src"), Path("tests"), Path("scripts"), Path("skills")):
    for path in root.rglob("__pycache__"):
        if not path.is_symlink():
            shutil.rmtree(path)
