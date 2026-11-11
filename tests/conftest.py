from pathlib import Path

import pytest

from backloger.models import Project
from backloger.repository import Repository
from backloger.service import BacklogService


@pytest.fixture(params=["split", "single"])
def service(tmp_path: Path, request: pytest.FixtureRequest) -> BacklogService:
    repository = Repository(tmp_path)
    repository.initialize(Project(name="Projeto de teste", key="SYS"), request.param)
    return BacklogService(repository)
