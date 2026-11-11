"""Append-only application history stored with the work item and versioned in Git."""

from uuid import uuid4

from backloger.models import HistoryEntry, HistoryKind, Project, WorkItem, now


def entry(
    kind: HistoryKind, text: str, version: int, changed_fields: list[str] | None = None
) -> HistoryEntry:
    return HistoryEntry(
        id=f"H-{uuid4().hex}",
        at=now(),
        kind=kind,
        text=text,
        version=version,
        changed_fields=changed_fields or [],
    )


def comment(note: str | None, version: int) -> list[HistoryEntry]:
    return [entry("comment", note.strip(), version)] if note and note.strip() else []


def updated(old: WorkItem, new: WorkItem, project: Project, note: str | None) -> list[HistoryEntry]:
    labels = {
        "title": "Título",
        "description": "Descrição",
        "type": "Tipo",
        "status": "Estado",
        "priority": "Prioridade",
        "owner": "Responsável",
        "component": "Componente",
        "labels": "Etiquetas",
        "milestone_id": "Milestone",
        "iteration_id": "Iteração",
        "due_date": "Prazo",
        "estimate": "Estimativa",
        "dependencies": "Dependências",
        "acceptance_criteria": "Critérios de aceite",
        "extensions": "Extensões",
    }
    before, after = old.model_dump(mode="json"), new.model_dump(mode="json")
    changed = [key for key in labels if before.get(key) != after.get(key)]
    history = list(old.history)
    if changed:
        text = "Atualizados: " + ", ".join(labels[key] for key in changed) + "."
        if "status" in changed:
            names = {status.id: status.name for status in project.statuses}
            text = f"Estado: {names[old.status]} → {names[new.status]}. " + text
        history.append(entry("updated", text, new.version, changed))
    elif not (note and note.strip()):
        history.append(entry("updated", "Atividade salva sem alteração de campos.", new.version))
    return history + comment(note, new.version)
