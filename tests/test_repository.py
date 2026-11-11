import json
import multiprocessing
from pathlib import Path

import pytest

from backloger import transactions
from backloger.errors import BacklogError, ConflictError, ReadOnlyError
from backloger.filesystem import atomic_write, decode
from backloger.models import WorkItem
from backloger.repository import Repository
from backloger.service import BacklogService, CreateItem, UpdateItem

pytestmark = pytest.mark.integration


def item_path(service: BacklogService, item_id: str) -> Path:
    snapshot = service.snapshot()
    return service.repository.root / (
        "backlog.json" if snapshot.storage == "single" else f".backloger/work-items/{item_id}.json"
    )


def external_edit(service: BacklogService, item_id: str, **changes: object) -> None:
    path = item_path(service, item_id)
    data = json.loads(path.read_text())
    item = (
        next(i for i in data["work_items"] if i["id"] == item_id) if "work_items" in data else data
    )
    item.update(changes)
    path.write_text(json.dumps(data))


def test_external_edit_without_version_change_conflicts_and_preserves_unknown_fields(
    service: BacklogService,
) -> None:
    item, original = service.add(CreateItem(title="Original"))
    external_edit(
        service,
        item.id,
        title="Editor externo",
        custom={"keep": [1, 2]},
        extensions={"vendor": {"a": True}},
    )
    with pytest.raises(ConflictError):
        service.update(item.id, UpdateItem(expected_version=1, status="review"), original.revision)
    assert service.snapshot().backlog.work_items[0].title == "Editor externo"
    changed, snapshot = service.update(item.id, UpdateItem(expected_version=1, status="review"))
    assert changed.version == 2
    assert snapshot.backlog.work_items[0].model_extra == {"custom": {"keep": [1, 2]}}
    assert changed.extensions == {"vendor": {"a": True}}
    with pytest.raises(ConflictError):
        service.update(item.id, UpdateItem(expected_version=1, title="Stale"))


def test_interrupted_write_and_recovery(
    service: BacklogService, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, _ = service.add(CreateItem(title="Antes"))
    original = transactions.atomic_write

    def fail_target(path: Path, value: bytes) -> None:
        if path == item_path(service, item.id):
            raise OSError("Simulated disk failure")
        original(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(transactions, "atomic_write", fail_target)
        with pytest.raises(OSError):
            service.update(item.id, UpdateItem(expected_version=1, title="Depois"))
    assert service.snapshot().backlog.work_items[0].title == "Antes"
    assert transactions.pending(service.repository.root)
    with pytest.raises(ConflictError):
        service.add(CreateItem(title="Pending"))
    assert service.repository.recover() == 1
    assert service.snapshot().backlog.work_items[0].title == "Depois"
    assert len(service.repository.events()) == 2
    assert service.repository.recover() == 0


def test_recovery_after_target_commit_and_before_audit(
    service: BacklogService, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, _ = service.add(CreateItem(title="Antes"))
    with monkeypatch.context() as patch:

        def fail(*args: object) -> None:
            raise OSError("Interrupted audit")

        patch.setattr(transactions, "_finalize", fail)
        with pytest.raises(OSError):
            service.update(item.id, UpdateItem(expected_version=1, title="Depois"))
    assert service.snapshot().backlog.work_items[0].title == "Depois"
    assert service.repository.recover() == 1
    assert len(service.repository.events()) == 2


def test_recovery_never_overwrites_external_edit(
    service: BacklogService, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, _ = service.add(CreateItem(title="Antes"))
    with monkeypatch.context() as patch:
        patch.setattr(
            transactions, "_finalize", lambda *args: (_ for _ in ()).throw(OSError("Crash"))
        )
        with pytest.raises(OSError):
            service.update(item.id, UpdateItem(expected_version=1, title="Depois"))
    external_edit(service, item.id, title="Edição externa")
    with pytest.raises(ConflictError):
        service.repository.recover()
    assert service.snapshot().backlog.work_items[0].title == "Edição externa"


def test_restore_backup_increments_version(service: BacklogService) -> None:
    item, _ = service.add(CreateItem(title="Antes"))
    service.update(item.id, UpdateItem(expected_version=1, title="Depois"))
    backup = next((service.repository.root / ".backloger/.runtime/backups").glob("*.json"))
    restored, _ = service.restore(item.id, backup.stem, 2)
    assert restored.title == "Antes"
    assert restored.version == 3


def test_lock_timeout(service: BacklogService) -> None:
    service.add(CreateItem(title="A"))
    # A second file description cannot acquire the same advisory lock.
    with service.repository.lock(), pytest.raises(ConflictError), service.repository.lock():
        pass


def concurrent_writer(root: str, barrier: object, queue: object) -> None:
    repository = Repository(Path(root))
    snapshot = repository.snapshot()
    candidate = snapshot.backlog.model_copy(deep=True)
    candidate.work_items.append(WorkItem(id="SYS-001", title="Concorrente"))
    barrier.wait()
    try:
        repository.commit(snapshot, candidate, item_id="SYS-001", action="create")
        queue.put("saved")
    except ConflictError:
        queue.put("conflict")


def test_concurrent_processes_one_wins(service: BacklogService) -> None:
    ctx = multiprocessing.get_context("fork")
    barrier, queue = ctx.Barrier(2), ctx.Queue()
    processes = [
        ctx.Process(target=concurrent_writer, args=(str(service.repository.root), barrier, queue))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0
    assert sorted(queue.get(timeout=2) for _ in processes) == ["conflict", "saved"]
    assert len(service.snapshot().backlog.work_items) == 1


@pytest.mark.security
def test_read_only_does_not_create_runtime(service: BacklogService) -> None:
    repository = Repository(service.repository.root, read_only=True)
    readonly = BacklogService(repository)
    before = {
        p.relative_to(repository.root): p.read_bytes()
        for p in repository.root.rglob("*")
        if p.is_file()
    }
    readonly.state()
    with pytest.raises(ReadOnlyError):
        readonly.add(CreateItem(title="Denied"))
    after = {
        p.relative_to(repository.root): p.read_bytes()
        for p in repository.root.rglob("*")
        if p.is_file()
    }
    assert before == after


@pytest.mark.security
def test_symlink_json_rejected(service: BacklogService, tmp_path: Path) -> None:
    item, _ = service.add(CreateItem(title="A"))
    path = item_path(service, item.id)
    target = tmp_path / "outside.json"
    path.rename(target)
    path.symlink_to(target)
    with pytest.raises(BacklogError):
        service.snapshot()


@pytest.mark.security
def test_atomic_replace_failure_leaves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "data.json"
    path.write_bytes(b"original")
    import backloger.filesystem as fs

    def fail(*args: object) -> None:
        raise OSError("No space")

    monkeypatch.setattr(fs.os, "replace", fail)
    with pytest.raises(OSError):
        atomic_write(path, b"new")
    assert path.read_bytes() == b"original"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data.json"]


@pytest.mark.security
@pytest.mark.parametrize("content", [b'{"a":1,"a":2}', b'{"x":NaN}', b"\xff", b"{"])
def test_bad_json_rejected(content: bytes) -> None:
    with pytest.raises(BacklogError):
        decode(content)


def test_wip_limit_enforced(service: BacklogService) -> None:
    snapshot = service.snapshot()
    if snapshot.storage == "single":
        path = service.repository.root / "backlog.json"
        data = json.loads(path.read_text())
        data["project"]["statuses"][1]["wip_limit"] = 1
    else:
        path = service.repository.root / ".backloger/project.json"
        data = json.loads(path.read_text())
        data["statuses"][1]["wip_limit"] = 1
    path.write_text(json.dumps(data))
    service.add(CreateItem(title="Active", status="in_progress"))
    with pytest.raises(ConflictError):
        service.add(CreateItem(title="Over limit", status="in_progress"))
