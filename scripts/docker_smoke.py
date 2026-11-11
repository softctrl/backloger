"""Exercise the packaged service, external edits and a physically read-only mount."""

import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from backloger.models import Project
from backloger.repository import Repository

compose = ["docker", "compose", "-f", "compose.yaml", "-p", "backloger-smoke"]


def request(path, payload=None, headers=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        "http://127.0.0.1:18765" + path,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    return urllib.request.urlopen(req, timeout=5)


subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL)
for storage in ("split", "single"):
    with tempfile.TemporaryDirectory(prefix="backloger-compose-") as temporary:
        root = Path(temporary)
        Repository(root).initialize(Project(name="Compose smoke", key="SYS"), storage)
        environment = {
            **os.environ,
            "BACKLOGER_PROJECT": temporary,
            "BACKLOGER_PORT": "18765",
            "LOCAL_UID": str(os.getuid()),
            "LOCAL_GID": str(os.getgid()),
            "BACKLOGER_READ_ONLY": "false",
        }

        def run(*args, environment=environment, **kwargs):
            return subprocess.run([*compose, *args], env=environment, check=True, **kwargs)

        try:
            run("up", "--build", "-d")
            for _ in range(45):
                try:
                    with request("/health") as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    time.sleep(1)
            else:
                raise RuntimeError("Container did not become healthy")
            with request("/") as response:
                token = re.search(
                    r'name="backloger-token" content="([^"]+)"', response.read().decode()
                )[1]
            with request("/api/v1/state") as response:
                revision = response.headers["ETag"]
            with request(
                "/api/v1/items",
                {"title": "Criada no container"},
                {"X-Backloger-Token": token, "If-Match": revision},
            ) as response:
                assert response.status == 201
            path = root / (
                "backlog.json" if storage == "single" else ".backloger/work-items/SYS-001.json"
            )
            data = json.loads(path.read_text())
            item = data["work_items"][0] if storage == "single" else data
            item["title"] = "Edição externa"
            path.write_text(json.dumps(data))
            with request("/api/v1/state") as response:
                assert json.load(response)["work_items"][0]["title"] == "Edição externa"
            with request("/api/v1/export/markdown") as response:
                assert "Edição externa" in response.read().decode()
            environment["BACKLOGER_READ_ONLY"] = "true"
            run("up", "-d", "--force-recreate")
            # Docker healthcheck gives the restarted process time to initialize.
            for _ in range(45):
                try:
                    with request("/health") as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    time.sleep(1)
            with request("/") as response:
                token = re.search(
                    r'name="backloger-token" content="([^"]+)"', response.read().decode()
                )[1]
            try:
                request(
                    "/api/v1/items",
                    {"title": "Denied"},
                    {"X-Backloger-Token": token, "If-Match": revision},
                )
                raise AssertionError("Readonly API allowed a write")
            except urllib.error.HTTPError as error:
                assert error.code == 403
            command = [
                *compose,
                "exec",
                "-T",
                "backloger",
                "python",
                "-c",
                "from pathlib import Path; Path('/project/should-not-exist').write_text('denied')",
            ]
            assert subprocess.run(command, env=environment, capture_output=True).returncode != 0
            assert not (root / "should-not-exist").exists()
        finally:
            run("down")
print("Compose smoke: split, single, JSON externo e somente leitura OK")
