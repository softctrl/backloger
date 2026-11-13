"""Complete management document, shared by CLI, web, PDF and CI."""

import html
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from backloger.models import Backlog, Milestone, WorkItem
from backloger.report_charts import Chart, Series, chart_markdown
from backloger.report_data import PRIORITIES, RELATIONS, TYPES, UNITS, ReportData, progress


def markdown_text(text: str) -> str:
    value = html.escape(text).replace("\n", " ").replace("\r", " ")
    for character in ("\\", "|", "*", "_", "[", "]", "`", "#", "!", "~"):
        value = value.replace(character, "\\" + character)
    return value


def table(headers: list[str], rows: Iterable[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(markdown_text(cell) for cell in row) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def _chart(
    title: str,
    labels: list[str],
    values: list[float],
    *,
    kind: str = "bar",
    colors: list[str] | None = None,
) -> str:
    return chart_markdown(
        Chart.model_validate(
            {
                "kind": kind,
                "title": title,
                "labels": labels,
                "series": [{"name": "Atividades", "values": values}],
                "colors": colors or [],
            }
        )
    )


def _summary(data: ReportData) -> str:
    items, counts = data.backlog.work_items, data.counts
    criteria = [criterion for item in items for criterion in item.acceptance_criteria]
    acceptance = f"{sum(c.done for c in criteria)}/{len(criteria)}" if criteria else "Não definidos"
    throughput = str(data.throughput) if data.history["observed_since"] else "Não disponível"
    lines = [
        "## 1. Resumo executivo",
        "",
        f"**Situação geral: {data.assessment}.** O projeto reúne {len(items)} atividades: "
        f"{counts['done']} concluídas, {counts['active']} em execução/revisão, "
        f"{counts['pending']} aguardando início e {counts['cancelled']} canceladas. "
        f"O avanço do escopo válido é de **{progress(items, data.categories)}**.",
        "",
        table(
            ["Indicador", "Resultado", "Leitura gerencial"],
            [
                [
                    "Conclusão do escopo",
                    progress(items, data.categories),
                    "Concluídas ÷ total não cancelado",
                ],
                [
                    "Atividades abertas",
                    str(len(data.open_items)),
                    "Aguardando início ou em execução/revisão",
                ],
                ["Bloqueadas", str(len(data.blocked)), "Dependem de pré-requisitos ainda abertos"],
                [
                    "Prazos vencidos",
                    str(len(data.overdue)),
                    "Abertas com data anterior à referência",
                ],
                [
                    "Entregas nos últimos 7 dias",
                    throughput,
                    "Atividades distintas concluídas em eventos observados; não é previsão",
                ],
                [
                    "Critérios de aceite",
                    acceptance,
                    "Critérios marcados como atendidos ÷ cadastrados",
                ],
            ],
        ),
        "### Pontos de atenção e encaminhamentos",
        "",
    ]
    if data.overdue:
        lines.append(
            "- **Tratar atrasos:** revisar prazo e plano de entrega de "
            + ", ".join(i.id for i in data.overdue[:10])
            + "."
        )
    if data.blocked:
        lines.append(
            f"- **Desbloquear o fluxo:** {len(data.blocked)} atividades aguardam "
            "pré-requisitos; priorizar os bloqueadores apresentados na seção de dependências."
        )
    if data.wip_exceeded:
        lines.append(
            "- **Rever capacidade:** limite WIP excedido em "
            + markdown_text(", ".join(data.wip_exceeded))
            + "."
        )
    if not data.overdue and not data.blocked and not data.wip_exceeded:
        lines.append("- Nenhum atraso com prazo cadastrado, bloqueio ou excesso de WIP detectado.")
    for missing, text in [
        ([i for i in data.open_items if not i.owner], "Definir responsáveis"),
        ([i for i in data.open_items if not i.due_date], "Definir datas de entrega"),
        (
            [i for i in data.open_items if not i.acceptance_criteria],
            "Completar critérios de aceite",
        ),
    ]:
        if missing:
            lines.append(f"- **{text}:** {len(missing)} atividades abertas sem essa informação.")
    lines.extend(
        [
            "",
            "> Percentual por quantidade de atividades, sem ponderação por esforço. "
            "Ausência de prazo não comprova que uma atividade esteja dentro do prazo.",
            "",
        ]
    )
    return "\n".join(lines)


def _distribution(data: ReportData) -> str:
    items = data.backlog.work_items
    counts = Counter(i.status for i in items)
    statuses = data.backlog.project.statuses
    lines = ["## 2. Distribuição e capacidade", "", "### Situação das atividades", ""]
    if items:
        lines.append(
            _chart(
                "Distribuição por estado",
                [s.name for s in statuses],
                [float(counts[s.id]) for s in statuses],
                kind="donut",
                colors=[
                    {
                        "pending": "#929b8f",
                        "active": "#df8853",
                        "done": "#286856",
                        "cancelled": "#c2c9c0",
                    }[s.category]
                    for s in statuses
                ],
            )
        )
    lines.append(
        table(
            ["Estado", "Quantidade", "% do total", "Limite WIP"],
            [
                [
                    s.name,
                    str(counts[s.id]),
                    f"{counts[s.id] / len(items):.0%}" if items else "—",
                    str(s.wip_limit) if s.wip_limit else "Não definido",
                ]
                for s in statuses
            ],
        )
    )
    priority: Counter[str] = Counter(i.priority for i in data.open_items)
    lines.extend(
        [
            "### Prioridade do trabalho aberto",
            "",
            _chart(
                "Atividades abertas por prioridade",
                list(PRIORITIES.values()),
                [float(priority[p]) for p in PRIORITIES],
            ),
            table(
                ["Prioridade", "Abertas", "Bloqueadas", "Vencidas"],
                [
                    [
                        label,
                        str(priority[key]),
                        str(sum(i.priority == key for i in data.blocked)),
                        str(sum(i.priority == key for i in data.overdue)),
                    ]
                    for key, label in PRIORITIES.items()
                ],
            ),
            "### Distribuição por responsável",
            "",
        ]
    )
    owners = sorted({i.owner or "Sem responsável" for i in items})
    lines.append(
        table(
            ["Responsável", "Total", "Abertas", "Concluídas", "Bloqueadas"],
            [
                [
                    owner,
                    str(sum((i.owner or "Sem responsável") == owner for i in items)),
                    str(sum((i.owner or "Sem responsável") == owner for i in data.open_items)),
                    str(
                        sum(
                            (i.owner or "Sem responsável") == owner
                            and data.categories[i.status] == "done"
                            for i in items
                        )
                    ),
                    str(sum((i.owner or "Sem responsável") == owner for i in data.blocked)),
                ]
                for owner in owners
            ],
        )
        if owners
        else "Nenhuma atividade cadastrada.\n"
    )
    return "\n".join(lines)


def _timeline(data: ReportData) -> str:
    lines = ["## 3. Evolução e burndown", "", "### Burndown do projeto — últimos 30 dias", ""]
    points = data.burndown["scopes"][0]["points"]
    remaining = [p["remaining"] for p in points]
    lines.append(
        chart_markdown(
            Chart(
                kind="line",
                title="Burndown · atividades restantes",
                labels=[p["date"][5:] for p in points],
                series=[Series(name="Restantes", values=remaining)],
            )
        )
    )
    observations = [p for p in points if p["remaining"] is not None]
    lines.extend(
        [
            f"**Saldo atual: {remaining[-1]} atividades abertas.** "
            f"Há {len(observations)} dia(s) com observação nesta janela. "
            "Dias sem checkpoint ficam sem valor; não há reconstrução retroativa. "
            "Novas atividades, reaberturas e cancelamentos podem alterar a curva.",
            "",
            table(
                ["Data observada (UTC)", "Restantes", "Escopo total"],
                [[p["date"], str(p["remaining"]), str(p["total"])] for p in observations],
            ),
            "### Ritmo de entrega — últimos 7 dias",
            "",
        ]
    )
    days = data.history["days"][-7:]
    lines.append(
        chart_markdown(
            Chart(
                kind="bar",
                title="Entradas e conclusões observadas",
                labels=[day["date"][5:] for day in days],
                series=[
                    Series(name="Criadas", values=[day["created"] for day in days]),
                    Series(name="Concluídas", values=[day["completed"] for day in days]),
                ],
            )
        )
    )
    lines.extend(
        [
            table(
                ["Data (UTC)", "Criadas", "Concluídas"],
                [[d["date"], str(d["created"]), str(d["completed"])] for d in days],
            ),
            "> " + data.history["note"],
            "",
        ]
    )
    if not data.history["observed_since"]:
        lines.extend(
            [
                "Não há auditoria operacional disponível nesta cópia do projeto. "
                "Os zeros de eventos representam ausência de registros, "
                "não uma medição de produtividade.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"Auditoria observada desde {data.history['observed_since']}. "
                f"Eventos na janela de 30 dias: {data.history['event_count']}. "
                "Períodos anteriores ao início dos registros não comprovam ausência de atividade.",
                "",
            ]
        )
    return "\n".join(lines)


def _roadmap(data: ReportData) -> str:
    lines = ["## 4. Marcos e iterações", ""]
    if data.backlog.milestones:
        milestones = data.backlog.milestones[:20]
        groups = [
            [i for i in data.backlog.work_items if i.milestone_id == m.id] for m in milestones
        ]
        lines.extend(
            [
                "### Entregas por marco",
                "",
                chart_markdown(
                    Chart(
                        kind="bar",
                        title="Conclusões e pendências por marco",
                        labels=[m.id for m in milestones],
                        series=[
                            Series(
                                name="Concluídas",
                                values=[
                                    sum(data.categories[i.status] == "done" for i in group)
                                    for group in groups
                                ],
                            ),
                            Series(
                                name="Abertas",
                                values=[
                                    sum(
                                        data.categories[i.status] not in {"done", "cancelled"}
                                        for i in group
                                    )
                                    for group in groups
                                ],
                            ),
                        ],
                    )
                ),
                "O gráfico considera até 20 marcos, na ordem cadastrada, e exclui cancelados. "
                "A tabela apresenta todos os marcos.",
                "",
            ]
        )
    sections: list[tuple[str, Sequence[Milestone], str]] = [
        ("Marcos de entrega", data.backlog.milestones, "milestone_id"),
        ("Iterações", data.backlog.iterations, "iteration_id"),
    ]
    for title, entities, field in sections:
        lines.extend([f"### {title}", ""])
        rows = []
        for entity in entities:
            items = [i for i in data.backlog.work_items if getattr(i, field) == entity.id]
            opened = [i for i in items if data.categories[i.status] not in {"done", "cancelled"}]
            rows.append(
                [
                    f"{entity.id} · {entity.name}",
                    str(entity.due_date or "Não definido"),
                    str(len(items)),
                    progress(items, data.categories),
                    "Vencido com pendências"
                    if entity.due_date and opened and entity.due_date < data.at.date()
                    else "Em aberto"
                    if opened
                    else "Sem atividades"
                    if not items
                    else "Encerrado",
                ]
            )
        lines.append(
            table(["Entrega", "Prazo", "Atividades", "Conclusão", "Situação"], rows)
            if rows
            else "Nenhum registro cadastrado.\n"
        )
        unassigned = sum(getattr(i, field) is None for i in data.open_items)
        if unassigned:
            lines.append(
                f"{unassigned} atividades abertas ainda sem vínculo com {title.lower()}.\n"
            )
    scopes = [
        scope
        for scope in data.burndown["scopes"][1:]
        if scope["baseline_date"] and scope["points"][-1]["total"]
    ]
    for scope in scopes[:5]:
        points = [point for point in scope["points"] if point["date"] >= scope["baseline_date"]]
        lines.extend(
            [
                f"### Burndown da iteração — {markdown_text(scope['name'])}",
                "",
                chart_markdown(
                    Chart(
                        kind="line",
                        title=f"Burndown · {scope['name']}",
                        labels=[point["date"][5:] for point in points],
                        series=[
                            Series(name="Restantes", values=[p["remaining"] for p in points]),
                            Series(name="Referência ideal", values=[p["ideal"] for p in points]),
                        ],
                    )
                ),
                f"Linha de base observada: {scope['baseline_date']}. Prazo: {scope['due_date']}. "
                "A referência ideal é linear e não representa previsão de entrega.",
                "",
                table(
                    ["Data observada (UTC)", "Restantes", "Referência ideal"],
                    [
                        [p["date"], str(p["remaining"]), str(p["ideal"])]
                        for p in points
                        if p["remaining"] is not None
                    ],
                ),
            ]
        )
    if len(scopes) > 5:
        lines.append(
            "Gráficos limitados às cinco primeiras iterações com linha de base; "
            "consulte as demais no dashboard.\n"
        )
    return "\n".join(lines)


def _dependencies(data: ReportData) -> str:
    by_id = {i.id: i for i in data.backlog.work_items}
    lines = ["## 5. Dependências e próximas ações", "", "### Bloqueios que exigem atuação", ""]
    if data.blocked:
        lines.append(
            table(
                ["Atividade bloqueada", "Responsável", "Pré-requisitos ainda abertos"],
                [
                    [
                        f"{i.id} · {i.title}",
                        i.owner or "Não definido",
                        "; ".join(
                            f"{key} · {by_id[key].title}" for key in data.analysis["blockers"][i.id]
                        ),
                    ]
                    for i in data.blocked
                ],
            )
        )
    else:
        lines.append("Nenhum bloqueio de precedência detectado.\n")
    bottlenecks = [
        row
        for row in data.analysis["bottlenecks"]
        if row["affected"] and by_id[row["id"]] in data.open_items
    ]
    if bottlenecks:
        lines.extend(
            [
                "### Maiores impactos potenciais",
                "",
                table(
                    ["Pré-requisito", "Estado", "Atividades alcançadas"],
                    [
                        [
                            f"{row['id']} · {by_id[row['id']].title}",
                            data.statuses[by_id[row["id"]].status],
                            str(row["affected"]),
                        ]
                        for row in bottlenecks
                    ],
                ),
                "Impacto considera todos os sucessores do grafo, inclusive itens já encerrados.\n",
            ]
        )
    critical = data.analysis["critical_paths"]["remaining"]
    if critical["method"] == "estimate":
        lines.append(
            "**Caminho crítico técnico restante:** "
            + " → ".join(critical["path"])
            + f" · {critical['duration']:g} {UNITS[critical['unit']]}. "
            "Estimativa de esforço/precedência; não é uma previsão de calendário.\n"
        )
    elif critical["method"] == "structure":
        lines.append(
            "**Maior cadeia de precedência restante:** "
            + " → ".join(critical["path"])
            + f" · {critical['length']} atividades. {critical['reason']} "
            "Não é uma previsão de duração; complete estimativas na mesma unidade "
            "para calcular o caminho crítico técnico.\n"
        )
    else:
        lines.append("**Caminho crítico restante:** nenhuma atividade pendente.\n")
    ready = [i for i in data.open_items if i.id in data.analysis["ready"]][:8]
    lines.extend(
        [
            "### Próximas ações sem bloqueio de dependência",
            "",
            "Seleção por prioridade, prazo e ID. Confirme capacidade e contexto antes de iniciar.",
            "",
        ]
    )
    lines.append(
        table(
            ["Atividade", "Prioridade", "Estado", "Responsável", "Prazo"],
            [
                [
                    f"{i.id} · {i.title}",
                    PRIORITIES[i.priority],
                    data.statuses[i.status],
                    i.owner or "Não definido",
                    str(i.due_date or "Não definido"),
                ]
                for i in ready
            ],
        )
        if ready
        else "Nenhuma atividade aberta elegível.\n"
    )
    return "\n".join(lines)


def _item_detail(item: WorkItem, data: ReportData) -> str:
    milestones = {m.id: m.name for m in data.backlog.milestones}
    iterations = {i.id: i.name for i in data.backlog.iterations}
    estimate = (
        f"{item.estimate.value:g} {UNITS[item.estimate.unit]}" if item.estimate else "Não definida"
    )
    rows = [
        ["Estado", data.statuses[item.status], "Prioridade", PRIORITIES[item.priority]],
        ["Tipo", TYPES[item.type], "Responsável", item.owner or "Não definido"],
        [
            "Componente",
            item.component or "Não definido",
            "Prazo",
            str(item.due_date or "Não definido"),
        ],
        [
            "Marco",
            milestones.get(item.milestone_id or "", "Não definido"),
            "Iteração",
            iterations.get(item.iteration_id or "", "Não definida"),
        ],
        ["Estimativa", estimate, "Versão", str(item.version)],
        [
            "Criação (UTC)",
            item.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M"),
            "Atualização (UTC)",
            item.updated_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M"),
        ],
    ]
    lines = [
        f"### {item.id} — {markdown_text(item.title)}",
        "",
        table(["Campo", "Informação", "Campo", "Informação"], rows),
        "**Leitura de acompanhamento:** " + markdown_text(data.attention(item)) + ".",
        "",
        "**Descrição e escopo**",
        "",
    ]
    if item.description.strip():
        # Quote and escape each physical line: descriptions cannot inject report
        # sections, HTML, Mermaid metadata or external resource references.
        lines.extend("> " + markdown_text(line) for line in item.description.splitlines())
    else:
        lines.append(
            "Descrição não cadastrada. Complementar o escopo para permitir acompanhamento."
        )
    lines.extend(["", "**Critérios de aceite**", ""])
    if item.acceptance_criteria:
        lines.extend(
            f"- {'[x]' if c.done else '[ ]'} {c.id} · {markdown_text(c.text)}"
            for c in item.acceptance_criteria
        )
    else:
        lines.append("Nenhum critério de aceite cadastrado.")
    lines.extend(["", "**Dependências e relações**", ""])
    if item.dependencies:
        by_id = {i.id: i for i in data.backlog.work_items}
        lines.extend(
            f"- {RELATIONS[d.relation]} **{d.target_id}** · "
            + markdown_text(by_id[d.target_id].title)
            for d in item.dependencies
        )
    else:
        lines.append("Nenhuma relação declarada neste card.")
    if item.labels:
        lines.extend(
            ["", "**Etiquetas:** " + ", ".join(markdown_text(label) for label in item.labels)]
        )
    lines.extend(["", "**Último registro de acompanhamento**", ""])
    if item.history:
        latest = max(item.history, key=lambda entry: entry.at)
        lines.append(f"{latest.at.isoformat()} · v{latest.version} · {markdown_text(latest.text)}")
    else:
        lines.append("Sem histórico registrado no card.")
    return "\n".join([*lines, ""])


def markdown(
    backlog: Backlog, *, events: list[dict[str, Any]] | None = None, at: datetime | None = None
) -> str:
    data = ReportData.build(backlog, events, at)
    items = sorted(backlog.work_items, key=lambda item: item.id)
    lines = [
        f"# Backlog — {markdown_text(backlog.project.name)}",
        "",
        "Relatório gerencial de acompanhamento de status",
        "",
        f"**Projeto:** {backlog.project.key} · **Referência:** {data.at.date().isoformat()} (UTC) "
        f"· **Contrato:** {backlog.schema_version}",
        "",
        "Dados canônicos do projeto, consolidados para acompanhamento de execução, "
        "priorização e decisões de entrega.",
        "",
        "**Conteúdo:** Resumo executivo · Distribuição e capacidade · Evolução e burndown · "
        "Marcos e iterações · Dependências e próximas ações · Inventário · "
        "Detalhamento das atividades · Histórico · Critérios de leitura",
        "",
        _summary(data),
        _distribution(data),
        _timeline(data),
        _roadmap(data),
        _dependencies(data),
        "## 6. Inventário de atividades",
        "",
        table(
            ["ID", "Atividade", "Estado", "Prioridade", "Responsável", "Prazo"],
            [
                [
                    i.id,
                    i.title,
                    data.statuses[i.status],
                    PRIORITIES[i.priority],
                    i.owner or "Não definido",
                    str(i.due_date or "Não definido"),
                ]
                for i in items
            ],
        )
        if items
        else "Nenhuma atividade cadastrada.\n",
        "## 7. Detalhamento das atividades",
        "",
    ]
    lines.extend(_item_detail(item, data) for item in items)
    lines.extend(["## 8. Histórico das atividades", ""])
    history = sorted(
        [(entry.at, item.id, entry) for item in items for entry in item.history],
        key=lambda row: (row[0], row[1], row[2].id),
        reverse=True,
    )
    if history:
        lines.append(
            table(
                ["Data/hora", "Atividade", "Versão", "Registro"],
                [
                    [at.isoformat(), item_id, str(entry.version), entry.text]
                    for at, item_id, entry in history
                ],
            )
        )
    else:
        lines.append("Nenhuma nota ou alteração registrada nos cards.\n")
    lines.extend(
        [
            "## 9. Critérios de leitura e qualidade dos dados",
            "",
            "- Status respeitam a configuração do projeto. "
            "Conclusão exclui cancelamentos do denominador.",
            "- Bloqueios incluem pré-requisitos transitivos abertos; "
            "datas de referência e métricas são UTC.",
            "- Histórico dos cards acompanha os JSONs. "
            "Séries temporais usam a auditoria local disponível; "
            "ela pode não acompanhar um clone Git ou uma edição externa.",
            "- Burndown usa quantidade de atividades. Dias sem observação não equivalem a zero; "
            "no Mermaid, a linha liga somente as datas observadas. Não há previsão de término.",
            "- Estimativas não são convertidas entre horas, dias e pontos. "
            "Critérios marcados como atendidos "
            "não comprovam, isoladamente, a validação técnica da entrega.",
            "- Campos não informados são indicados no documento. "
            "Filtros da interface não recortam este relatório.",
            "",
        ]
    )
    return "\n".join(lines)
