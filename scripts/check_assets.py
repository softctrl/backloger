"""Check packaged assets; use Node's parser when Node is available."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

root = Path("src/backloger/static")
for name, expected in json.loads((root / "vendor/checksums.json").read_text()).items():
    actual = hashlib.sha256((root / "vendor" / name).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"Checksum inválido: {name}")
if shutil.which("node"):
    for path in [*root.glob("*.js"), root / "vendor/htmx.js", root / "vendor/cytoscape.min.js"]:
        subprocess.run(["node", "--check", str(path)], check=True)
print("Assets locais íntegros")
