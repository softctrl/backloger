"""Create the product backlog once. Existing projects are never overwritten."""

import json
from pathlib import Path

from backloger.filesystem import atomic_write, encode
from backloger.models import Backlog, Dependency, Milestone, Project, SavedView, WorkItem
from backloger.repository import Repository


def main() -> None:
    titles = [
        "Estrutura do projeto e empacotamento Python",
        "JSON Schema oficial e exemplos",
        "Modelos de domínio e validação",
        "Persistência JSON e escrita atômica",
        "CLI completo",
        "Motor de dependências e análise de grafos",
        "Geradores Markdown, CSV e Mermaid",
        "API FastAPI",
        "Dashboard e Kanban",
        "Visualizador de grafos",
        "Sincronização de alterações externas",
        "Segurança web local",
        "Docker Compose e Makefile",
        "Testes, CI e documentação",
        "Roadmap, timeline e relatórios avançados",
        "Integrações GitHub e GitLab",
        "Autenticação e colaboração multiusuário",
        "Importadores e plugins",
        "Instância centralizada multiprojeto",
        "Dependências entre projetos",
    ]
    dependencies = {
        2: [1],
        3: [2],
        4: [3],
        5: [4],
        6: [3],
        7: [6],
        8: [4],
        9: [8],
        10: [6, 8],
        11: [4, 8],
        12: [8],
        13: [1],
        14: [5, 6, 7, 8],
        15: [9],
        16: [5],
        17: [12],
        18: [3],
        19: [17],
        20: [19],
    }
    pending_validation = {9, 10, 11, 13, 14}
    descriptions = json.loads(Path(__file__).with_name("product-scope.json").read_text())
    items = []
    for n, title in enumerate(titles, 1):
        tier = "p0" if n <= 14 else "p1" if n <= 18 else "p2"
        status = "in_progress" if n in pending_validation else "done" if n <= 14 else "todo"
        description = descriptions[f"BKL-{n:03}"]
        items.append(
            WorkItem(
                id=f"BKL-{n:03}",
                title=title,
                type="feature",
                status=status,
                description=description,
                priority="critical" if tier == "p0" else "high" if tier == "p1" else "medium",
                labels=[tier],
                milestone_id="M1" if n <= 14 else "M2" if n <= 18 else "M3",
                dependencies=[Dependency(target_id=f"BKL-{d:03}") for d in dependencies.get(n, [])],
                extensions={"delivery_priority": tier.upper()},
            )
        )
    root = Path(".").resolve()
    Repository(root).initialize(Project(name="Backloger", key="BKL"))
    milestones = [
        Milestone(id="M1", name="Primeira versão utilizável"),
        Milestone(id="M2", name="Integrações e colaboração"),
        Milestone(id="M3", name="Múltiplos projetos"),
    ]
    views = [SavedView(id="p0", name="Primeira versão · P0", filters={"filter-label": "p0"})]
    for name, value in (("milestones", milestones), ("views", views)):
        atomic_write(
            root / f".backloger/{name}.json", encode([v.model_dump(mode="json") for v in value])
        )
    for item in items:
        atomic_write(
            root / f".backloger/work-items/{item.id}.json", encode(item.model_dump(mode="json"))
        )
    Repository(root).snapshot()

    demo_root = root / "examples/demo"
    Repository(demo_root).initialize(Project(name="Meu Sistema", key="SYS"))
    demo_items = [
        WorkItem(
            id="SYS-001",
            title="Implementar autenticação",
            type="feature",
            status="in_progress",
            priority="critical",
            owner="backend-team",
            component="authentication",
            labels=["security", "backend", "p0"],
            milestone_id="M1",
            estimate={"unit": "hours", "value": 16},
            dependencies=[Dependency(target_id="SYS-002")],
            acceptance_criteria=[
                {"id": "AC-001", "text": "Validar credenciais", "done": True},
                {"id": "AC-002", "text": "Implementar testes de segurança", "done": False},
            ],
        ),
        WorkItem(
            id="SYS-002",
            title="Definir contrato da API",
            type="task",
            status="done",
            priority="high",
            owner="backend-team",
            labels=["backend"],
            milestone_id="M1",
            estimate={"unit": "hours", "value": 4},
        ),
        WorkItem(
            id="SYS-003",
            title="Criar interface de acesso",
            type="story",
            owner="frontend-team",
            labels=["frontend"],
            milestone_id="M1",
            estimate={"unit": "hours", "value": 8},
            dependencies=[Dependency(target_id="SYS-001")],
        ),
        WorkItem(
            id="SYS-004",
            title="Validar fluxo completo",
            type="task",
            priority="high",
            owner="quality-team",
            labels=["quality"],
            milestone_id="M1",
            estimate={"unit": "hours", "value": 4},
            dependencies=[Dependency(target_id="SYS-001"), Dependency(target_id="SYS-003")],
        ),
        WorkItem(
            id="SYS-005",
            title="Documentar instalação",
            type="documentation",
            priority="low",
            labels=["docs"],
            estimate={"unit": "hours", "value": 2},
        ),
    ]
    demo_milestones = [Milestone(id="M1", name="Primeira entrega")]
    atomic_write(
        demo_root / ".backloger/milestones.json",
        encode([m.model_dump(mode="json") for m in demo_milestones]),
    )
    for item in demo_items:
        atomic_write(
            demo_root / f".backloger/work-items/{item.id}.json",
            encode(item.model_dump(mode="json")),
        )
    demo = Repository(demo_root).snapshot().backlog
    single = root / "examples/single"
    single.mkdir(parents=True, exist_ok=False)
    atomic_write(
        single / "backlog.json",
        encode(Backlog.model_validate(demo.model_dump(mode="json")).model_dump(mode="json")),
    )
    print("Backlog do produto e exemplos criados sem substituir projetos existentes.")


if __name__ == "__main__":
    main()
