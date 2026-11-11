"""Bounded dependency analysis; edges always point prerequisite → dependent."""

from typing import Any

import networkx as nx

from backloger.errors import BacklogError
from backloger.models import Backlog


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


def analyze(backlog: Backlog, selected: str | None = None) -> dict[str, Any]:
    graph = dependency_graph(backlog)
    items = {item.id: item for item in backlog.work_items}
    categories = {s.id: s.category for s in backlog.project.statuses}
    unfinished = {i.id for i in items.values() if categories[i.status] not in {"done", "cancelled"}}
    blockers = {
        node: sorted(nx.ancestors(graph, node) & unfinished) for node in graph if node in unfinished
    }
    critical: dict[str, Any] = {"path": [], "duration": None, "unit": None}
    estimates = [i.estimate for i in items.values()]
    if estimates and all(e is not None for e in estimates):
        units = {e.unit for e in estimates if e is not None}
        if len(units) == 1:
            distances: dict[str, float] = {}
            paths: dict[str, list[str]] = {}
            for node in nx.topological_sort(graph):
                predecessor = max(
                    graph.predecessors(node), key=lambda n: distances[n], default=None
                )
                estimate = items[node].estimate
                assert estimate is not None
                distances[node] = (distances[predecessor] if predecessor else 0) + estimate.value
                paths[node] = (paths[predecessor] if predecessor else []) + [node]
            last = max(distances, key=lambda n: distances[n])
            critical = {"path": paths[last], "duration": distances[last], "unit": next(iter(units))}
    result: dict[str, Any] = {
        "edges": [{"source": a, "target": b} for a, b in sorted(graph.edges)],
        "isolated": sorted(node for node, degree in graph.degree if degree == 0),
        "blockers": blockers,
        "blocked_count": sum(bool(b) for b in blockers.values()),
        "ready": sorted(n for n in unfinished if not blockers.get(n)),
        "bottlenecks": sorted(
            [{"id": n, "affected": len(nx.descendants(graph, n))} for n in graph],
            key=lambda row: (-row["affected"], row["id"]),
        )[:10],
        "critical_path": critical,
        "critical_path_note": "Estimativa técnica; não representa previsão de calendário.",
    }
    if selected:
        if selected not in graph:
            raise BacklogError(f"Atividade inexistente: {selected}")
        result["selected"] = {
            "id": selected,
            "prerequisites": sorted(nx.ancestors(graph, selected)),
            "affected": sorted(nx.descendants(graph, selected)),
        }
    return result
