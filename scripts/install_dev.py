"""Install the single dev dependency group without duplicating its definition."""

import subprocess
import sys
import tomllib
from pathlib import Path

data = tomllib.loads(Path("pyproject.toml").read_text())
subprocess.run(
    [sys.executable, "-m", "pip", "install", *data["dependency-groups"]["dev"]], check=True
)
