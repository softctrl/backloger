"""Sprint summaries use the project's status categories and the full sprint scope."""

from datetime import date
from typing import Any

from backloger.models import Backlog, Iteration, WorkItem


def overview(backlog: Backlog, analysis: dict[str, Any], today: date) -> dict[str, Any]:
    categories = {status.id: status.category for status in backlog.project.statuses}
    grouped: dict[str | None, list[WorkItem]] = {None: []}
    grouped.update({iteration.id: [] for iteration in backlog.iterations})
    for item in backlog.work_items:
        grouped[item.iteration_id].append(item)

    def summarize(iteration: Iteration | None) -> dict[str, Any]:
        items = grouped[iteration.id if iteration else None]
        counts = {key: 0 for key in ("pending", "active", "done", "cancelled")}
        estimates: dict[str, float] = {}
        blocked = overdue = 0
        for item in items:
            category = categories[item.status]
            counts[category] += 1
            if category not in {"done", "cancelled"}:
                blocked += bool(analysis["blocker_counts"].get(item.id, 0))
                overdue += bool(item.due_date and item.due_date < today)
                if item.estimate:
                    unit = item.estimate.unit
                    estimates[unit] = estimates.get(unit, 0) + item.estimate.value
        applicable = len(items) - counts["cancelled"]
        phase = "unplanned" if iteration is None else "undated"
        if iteration:
            if iteration.start_date and iteration.start_date > today:
                phase = "upcoming"
            elif iteration.due_date and iteration.due_date < today:
                phase = "past"
            elif iteration.start_date and iteration.due_date:
                phase = "current"
        return {
            "id": iteration.id if iteration else None,
            "name": iteration.name if iteration else "Atividades sem sprint",
            "start_date": iteration.start_date.isoformat()
            if iteration and iteration.start_date
            else None,
            "due_date": iteration.due_date.isoformat()
            if iteration and iteration.due_date
            else None,
            "phase": phase,
            "total": len(items),
            **counts,
            "remaining": counts["pending"] + counts["active"],
            "blocked": blocked,
            "overdue": overdue,
            "progress": round(100 * counts["done"] / applicable, 1) if applicable else None,
            "open_estimates": {unit: round(value, 6) for unit, value in estimates.items()},
        }

    return {
        "today": today.isoformat(),
        "iterations": [summarize(iteration) for iteration in backlog.iterations],
        "unassigned": summarize(None),
    }
