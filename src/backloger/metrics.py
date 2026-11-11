"""Historical charts use observed audit events, never inferred past snapshots."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from backloger.models import Backlog, Project, WorkItem


def completion_count(project: Project, events: list[dict[str, Any]], at: datetime) -> int:
    """Unique work items observed entering done during the preceding seven days."""
    end = at.astimezone(UTC)
    start = end - timedelta(days=7)
    done = {status.id for status in project.statuses if status.category == "done"}
    completed = set()
    for event in events:
        if not isinstance(event.get("at"), str) or not isinstance(event.get("item_id"), str):
            continue
        try:
            timestamp = datetime.fromisoformat(event["at"])
        except ValueError:
            continue
        if (
            timestamp.tzinfo is not None
            and start <= timestamp <= end
            and event.get("status") in done
            and event.get("previous_status") not in done
        ):
            completed.add(event["item_id"])
    return len(completed)


def activity_history(
    project: Project, events: list[dict[str, Any]], at: datetime, days: int = 30
) -> dict[str, Any]:
    end = at.astimezone(UTC)
    start = end.date() - timedelta(days=days - 1)
    buckets: dict[str, dict[str, set[str]]] = {
        (start + timedelta(days=i)).isoformat(): {"created": set(), "completed": set()}
        for i in range(days)
    }
    done = {s.id for s in project.statuses if s.category == "done"}
    first: datetime | None = None
    observed = 0
    for event in events:
        item_id = event.get("item_id")
        if not isinstance(item_id, str) or not isinstance(event.get("at"), str):
            continue
        try:
            timestamp = datetime.fromisoformat(event["at"])
        except ValueError:
            continue
        if timestamp.tzinfo is None or timestamp > end:
            continue
        timestamp = timestamp.astimezone(UTC)
        first = min(first, timestamp) if first else timestamp
        bucket = buckets.get(timestamp.date().isoformat())
        if bucket is None:
            continue
        observed += 1
        if event.get("action") == "create":
            bucket["created"].add(item_id)
        if event.get("status") in done and event.get("previous_status") not in done:
            bucket["completed"].add(item_id)
    return {
        "timezone": "UTC",
        "observed_since": first.isoformat() if first else None,
        "event_count": observed,
        "days": [
            {"date": day, "created": len(values["created"]), "completed": len(values["completed"])}
            for day, values in buckets.items()
        ],
        "note": (
            "Somente eventos registrados pelo Backloger. Edições externas não são "
            "reconstruídas. Datas em UTC."
        ),
    }


def burndown_history(
    backlog: Backlog, events: list[dict[str, Any]], at: datetime, days: int = 30
) -> dict[str, Any]:
    """Keep actual checkpoints; unknown dates remain null, with no backfilled history."""
    end = at.astimezone(UTC)
    start = end.date() - timedelta(days=days - 1)
    categories = {s.id: s.category for s in backlog.project.statuses}
    scopes: list[tuple[str, str, list[WorkItem], date | None, date | None]] = [
        ("project", backlog.project.name, backlog.work_items, None, None)
    ]
    scopes.extend(
        (
            f"iteration:{iteration.id}",
            iteration.name,
            [i for i in backlog.work_items if i.iteration_id == iteration.id],
            iteration.start_date,
            iteration.due_date,
        )
        for iteration in backlog.iterations
    )
    checkpoints: dict[str, list[tuple[datetime, int, int]]] = {scope[0]: [] for scope in scopes}
    for event in events:
        burn = event.get("burn")
        if not isinstance(burn, dict) or not isinstance(event.get("at"), str):
            continue
        try:
            timestamp = datetime.fromisoformat(event["at"])
        except ValueError:
            continue
        if timestamp.tzinfo is None or timestamp > end:
            continue
        timestamp = timestamp.astimezone(UTC)
        iterations = burn.get("iterations", {})
        values = (
            {"project": burn, **{f"iteration:{key}": value for key, value in iterations.items()}}
            if isinstance(iterations, dict)
            else {"project": burn}
        )
        for scope_id, counts in values.items():
            if scope_id not in checkpoints or not isinstance(counts, dict):
                continue
            remaining, total = counts.get("remaining"), counts.get("total")
            if type(remaining) is int and type(total) is int and 0 <= remaining <= total <= 2000:
                checkpoints[scope_id].append((timestamp, remaining, total))
    result = []
    for scope_id, name, items, planned_start, due in scopes:
        observations = list(checkpoints[scope_id])
        observations.sort(key=lambda row: row[0])
        baseline = next(
            (
                row
                for row in observations
                if planned_start and due and planned_start <= row[0].date() < due
            ),
            None,
        )
        observations.append(
            (end, sum(categories[i.status] not in {"done", "cancelled"} for i in items), len(items))
        )
        observed = {
            timestamp.date().isoformat(): (remaining, total)
            for timestamp, remaining, total in observations
        }
        points = []
        for index in range(days):
            day = start + timedelta(days=index)
            counts = observed.get(day.isoformat())
            ideal = None
            if baseline and due and day >= baseline[0].date():
                duration = (due - baseline[0].date()).days
                ideal = round(
                    max(0, baseline[1] * (1 - (day - baseline[0].date()).days / duration)), 2
                )
            points.append(
                {
                    "date": day.isoformat(),
                    "remaining": counts[0] if counts else None,
                    "total": counts[1] if counts else None,
                    "ideal": ideal,
                }
            )
        result.append(
            {
                "id": scope_id,
                "name": name,
                "points": points,
                "start_date": planned_start.isoformat() if planned_start else None,
                "due_date": due.isoformat() if due else None,
                "baseline_date": baseline[0].date().isoformat() if baseline else None,
            }
        )
    return {
        "scopes": result,
        "unit": "work_items",
        "timezone": "UTC",
        "note": (
            "Pontos observados em gravações do Backloger e na leitura atual. "
            "Datas sem registro ficam em aberto. Novas atividades e reaberturas "
            "podem elevar a curva."
        ),
    }
