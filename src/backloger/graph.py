"""Bounded dependency analysis; edges always point prerequisite → dependent."""

from math import isclose
from typing import Any

import networkx as nx

from backloger.errors import BacklogError
from backloger.models import Backlog


def critical_schedule(backlog: Backlog, graph: nx.DiGraph, *, remaining: bool) -> dict[str, Any]:
    """Forward/backward DAG passes, including every tied zero-float route."""
    categories = {status.id: status.category for status in backlog.project.statuses}
    items = {
        item.id: item
        for item in backlog.work_items
        if categories[item.status] != "cancelled"
        and (not remaining or categories[item.status] != "done")
    }
    active = graph.subgraph(items)
    order = list(nx.lexicographical_topological_sort(active, key=str))
    missing = sorted(item.id for item in items.values() if item.estimate is None)
    units = sorted({item.estimate.unit for item in items.values() if item.estimate is not None})
    estimated = bool(items) and not missing and len(units) == 1
    reason = ""
    if missing:
        reason = f"{len(missing)} atividades sem estimativa neste escopo."
    if len(units) > 1:
        reason += " Estimativas em unidades diferentes; não há conversão automática."
    if not items:
        reason = (
            "Nenhuma atividade pendente neste escopo."
            if remaining
            else "Nenhuma atividade não cancelada neste escopo."
        )
    weights = {
        key: item.estimate.value if estimated and item.estimate else 1.0
        for key, item in items.items()
    }
    starts: dict[str, float] = {}
    finishes: dict[str, float] = {}
    predecessors: dict[str, str | None] = {}
    depth: dict[str, int] = {}
    for node in order:
        previous = max(
            sorted(active.predecessors(node)),
            key=lambda key: (finishes[key], depth[key]),
            default=None,
        )
        predecessors[node] = previous
        depth[node] = depth[previous] + 1 if previous else 1
        starts[node] = finishes[previous] if previous else 0.0
        finishes[node] = starts[node] + weights[node]
    last = max(sorted(order), key=lambda key: (finishes[key], depth[key]), default=None)
    span = finishes[last] if last else 0.0
    latest: dict[str, float] = {}
    timings = {}
    for node in reversed(order):
        end = min((latest[child] for child in active.successors(node)), default=span)
        latest[node] = end - weights[node]
        slack = max(0.0, latest[node] - starts[node])
        if isclose(slack, 0.0, abs_tol=1e-7):
            slack = 0.0
        timings[node] = {
            "start": starts[node],
            "finish": finishes[node],
            "latest_start": latest[node],
            "slack": slack,
        }
    critical_nodes = sorted(node for node in order if timings[node]["slack"] == 0)
    critical_ids = set(critical_nodes)
    critical_edges = [
        {"source": a, "target": b}
        for a, b in sorted(active.edges)
        if a in critical_ids
        and b in critical_ids
        and isclose(finishes[a], starts[b], rel_tol=0, abs_tol=1e-7)
    ]
    path = []
    current = last
    while current is not None:
        path.append(current)
        current = predecessors[current]
    return {
        "path": list(reversed(path)),
        "duration": span if estimated else None,
        "unit": units[0] if estimated else None,
        "method": "estimate" if estimated else "structure" if items else "empty",
        "reason": reason.strip(),
        "missing_estimates": missing,
        "units": units,
        "nodes": critical_nodes,
        "edges": critical_edges,
        "timings": timings,
        "length": len(path),
        "scope": "remaining" if remaining else "project",
        "note": "Estimativa técnica; não representa previsão de calendário."
        if estimated
        else "Maior cadeia de precedência por quantidade de atividades; não estima duração.",
    }


def reachability(graph: nx.DiGraph) -> tuple[list[str], dict[str, int], dict[str, int]]:
    """Bitsets avoid a separate ancestors/descendants traversal for every node."""
    nodes = sorted(graph)
    masks = {node: 1 << index for index, node in enumerate(nodes)}
    before = dict.fromkeys(nodes, 0)
    after = dict.fromkeys(nodes, 0)
    order = list(nx.topological_sort(graph))
    for node in order:
        for target in graph.successors(node):
            before[target] |= before[node] | masks[node]
    for node in reversed(order):
        for target in graph.successors(node):
            after[node] |= after[target] | masks[target]
    return nodes, before, after


def mask_ids(nodes: list[str], mask: int, limit: int | None = None) -> list[str]:
    result = []
    while mask:
        bit = mask & -mask
        result.append(nodes[bit.bit_length() - 1])
        if limit is not None and len(result) >= limit:
            break
        mask ^= bit
    return result


def dependency_graph(backlog: Backlog) -> nx.DiGraph:
    items = {item.id: item for item in backlog.work_items}
    if len(items) != len(backlog.work_items):
        raise BacklogError("IDs de atividades duplicados")
    graph = nx.DiGraph()
    graph.add_nodes_from(items)
    count = 0
    statuses = {s.id for s in backlog.project.statuses}
    for field in ("milestones", "iterations", "views"):
        entities = getattr(backlog, field)
        if len({e.id for e in entities}) != len(entities):
            raise BacklogError(f"IDs duplicados em {field}")
    for item in items.values():
        if not item.id.startswith(backlog.project.key + "-"):
            raise BacklogError(f"{item.id}: prefixo diferente da chave do projeto")
        if item.status not in statuses:
            raise BacklogError(f"{item.id}: estado desconhecido: {item.status}")
        for field, entities in (
            ("milestone_id", backlog.milestones),
            ("iteration_id", backlog.iterations),
        ):
            ref = getattr(item, field)
            if ref and ref not in {e.id for e in entities}:
                raise BacklogError(f"{item.id}: referência inexistente: {ref}")
        for dep in item.dependencies:
            count += 1
            if count > 10_000:
                raise BacklogError("Limite de 10000 relações excedido")
            if dep.target_id not in items:
                raise BacklogError(f"{item.id}: dependência inexistente: {dep.target_id}")
            if dep.relation == "blocked_by":
                graph.add_edge(dep.target_id, item.id)
            elif dep.relation == "blocks":
                graph.add_edge(item.id, dep.target_id)
    if not nx.is_directed_acyclic_graph(graph):
        cycle = nx.find_cycle(graph)
        raise BacklogError("Ciclo de dependências: " + " → ".join(a for a, _ in cycle))
    return graph


def analyze(
    backlog: Backlog, selected: str | None = None, *, blocker_limit: int | None = None
) -> dict[str, Any]:
    graph = dependency_graph(backlog)
    items = {item.id: item for item in backlog.work_items}
    categories = {s.id: s.category for s in backlog.project.statuses}
    unfinished = {i.id for i in items.values() if categories[i.status] not in {"done", "cancelled"}}
    nodes, before, after = reachability(graph)
    unfinished_mask = sum(1 << index for index, node in enumerate(nodes) if node in unfinished)
    blockers = {
        node: mask_ids(nodes, before[node] & unfinished_mask, blocker_limit)
        for node in nodes
        if node in unfinished
    }
    blocker_counts = {node: (before[node] & unfinished_mask).bit_count() for node in unfinished}
    project_schedule = critical_schedule(backlog, graph, remaining=False)
    remaining_schedule = critical_schedule(backlog, graph, remaining=True)
    bottlenecks: list[dict[str, Any]] = [
        {"id": node, "affected": after[node].bit_count()} for node in nodes
    ]
    result: dict[str, Any] = {
        "edges": [{"source": a, "target": b} for a, b in sorted(graph.edges)],
        "isolated": sorted(node for node, degree in graph.degree if degree == 0),
        "blockers": blockers,
        "blocker_counts": blocker_counts,
        "blockers_truncated": any(
            len(blockers[node]) < count for node, count in blocker_counts.items()
        ),
        "blocked_count": sum(bool(count) for count in blocker_counts.values()),
        "ready": sorted(node for node in unfinished if not blocker_counts[node]),
        "bottlenecks": sorted(
            bottlenecks,
            key=lambda row: (-row["affected"], row["id"]),
        )[:10],
        "critical_path": {key: project_schedule[key] for key in ("path", "duration", "unit")},
        "critical_paths": {"project": project_schedule, "remaining": remaining_schedule},
        "critical_path_note": "Estimativa técnica; não representa previsão de calendário.",
    }
    # Keep the original API's unknown-duration path empty; the detailed schedules
    # explicitly distinguish structural chains from estimated critical paths.
    if project_schedule["method"] != "estimate":
        result["critical_path"]["path"] = []
    if selected:
        if selected not in graph:
            raise BacklogError(f"Atividade inexistente: {selected}")
        result["selected"] = {
            "id": selected,
            "prerequisites": mask_ids(nodes, before[selected]),
            "affected": mask_ids(nodes, after[selected]),
        }
    return result
