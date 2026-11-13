"""Real domain data and template for the independent Node DOM tests."""

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from backloger.models import Dependency, Estimate, Project
from backloger.repository import Repository
from backloger.service import BacklogService, CreateItem, IterationRequest, UpdateItem

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
    basic_state = service.state()
    basic_markdown = service.report()[1]
    today = datetime.now(UTC).date()
    first, _ = service.save_iteration(
        IterationRequest(
            name="Sprint atual",
            start_date=today - timedelta(days=3),
            due_date=today + timedelta(days=10),
        )
    )
    service.save_iteration(
        IterationRequest(
            name="Próxima sprint",
            start_date=today + timedelta(days=11),
            due_date=today + timedelta(days=24),
        )
    )
    for item_id in ["SYS-001", "SYS-002", "SYS-003"]:
        snapshot = service.snapshot()
        item = service.item(snapshot, item_id)
        service.update(item_id, UpdateItem(expected_version=item.version, iteration_id=first.id))
    print(
        json.dumps(
            {
                "html": template.render(project=project, token="test-token", read_only=False),
                "readonly_html": template.render(
                    project=project, token="test-token", read_only=True
                ),
                "state": basic_state,
                "sprint_state": service.state(),
                "markdown": basic_markdown,
            }
        )
    )
