"""Real domain data and template for the independent Node DOM tests."""

import json
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from backloger.models import Dependency, Estimate, Project
from backloger.repository import Repository
from backloger.service import BacklogService, CreateItem, UpdateItem

with tempfile.TemporaryDirectory(prefix="backloger-ui-") as directory:
    root = Path(directory)
    repo = Repository(root)
    repo.initialize(Project(name="Projeto de interface", key="SYS"))
    service = BacklogService(repo)
    for index, (title, priority, owner) in enumerate(
        [
            ("Autenticação", "critical", "backend"),
            ("Contrato da API", "high", "backend"),
            ("Interface", "medium", "frontend"),
            ("Testes", "medium", "quality"),
            ('<img src=x onerror="alert(1)">', "low", None),
        ],
        1,
    ):
        # The prerequisite may be introduced in a later file; create first,
        # then establish the graph through the same service as the application.
        service.add(
            CreateItem(
                title=title,
                priority=priority,
                owner=owner,
                estimate=Estimate(unit="hours", value=index),
            )
        )
    for item_id, target in [("SYS-001", "SYS-002"), ("SYS-003", "SYS-001"), ("SYS-004", "SYS-003")]:
        service.update(
            item_id, UpdateItem(expected_version=1, dependencies=[Dependency(target_id=target)])
        )
    service.update("SYS-002", UpdateItem(expected_version=1, status="done"))
    env = Environment(
        loader=FileSystemLoader("src/backloger/templates"), autoescape=select_autoescape()
    )
    template = env.get_template("index.html")
    project = repo.snapshot().backlog.project
    print(
        json.dumps(
            {
                "html": template.render(project=project, token="test-token", read_only=False),
                "readonly_html": template.render(
                    project=project, token="test-token", read_only=True
                ),
                "state": service.state(),
                "markdown": service.report()[1],
            }
        )
    )
