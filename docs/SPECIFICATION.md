# Backloger — Plataforma Universal de Gestão de Backlogs

Especificação técnica e funcional · versão 1.0 · 11 de novembro de 2026
Projeto SoftCtrl.COM

Este documento registra a especificação-base do produto. O andamento da
implementação está em [BACKLOG.md](BACKLOG.md); resultados executados ficam em
[VALIDATION.md](VALIDATION.md). A versão do produto inicial é 0.1.0; a versão do
contrato é 1.0.0. Esses números não indicam que toda a evolução abaixo foi entregue.

## Propósito e princípio arquitetural

Plataforma open source em Python para padronizar atividades de desenvolvimento,
manutenção, evolução e operação. Qualquer projeto, seja Python, Go, C++, Kotlin,
React ou outra tecnologia, adota um contrato JSON independente de linguagem.
Não exige servidor central, serviço externo ou gerenciador específico por sistema.

**Projetos compartilham o padrão de backlog e mantêm seus próprios dados,
histórico e ciclo de vida.** O produto é independente e reutilizável, sem ser
incorporado como módulo a cada aplicação. CLI e web consomem o mesmo núcleo.

## Decisões tecnológicas

| Componente | Tecnologia |
| --- | --- |
| Linguagem | Python 3.12+ |
| API | FastAPI |
| Validação | Pydantic v2 e JSON Schema |
| Interface | HTML, Jinja2, HTMX e JavaScript |
| Kanban | JavaScript com drag-and-drop |
| Grafos | Cytoscape.js |
| CLI | Typer e Rich |
| Análise | NetworkX |
| Persistência canônica | JSON versionado em Git |
| Persistência auxiliar futura | SQLite, quando necessário |
| Implantação | Docker Compose |
| Automação | Makefile |
| Qualidade | pytest, Ruff, Mypy |
| Distribuição | Pacote Python e imagem OCI |

## Modos de uso

1. **CLI:** instalado uma vez, preferencialmente com pipx; funciona em qualquer
   repositório sem servidor. Cria/edita atividades, valida arquivos, identifica
   bloqueios, analisa dependências e exporta relatórios.
2. **Web local:** Python ou Compose, com Kanban, grafo, dashboard, tabela e
   roadmap. Alterações feitas em JSON aparecem automaticamente e alterações da
   interface retornam aos dados canônicos.
3. **Centralizado, evolução:** múltiplos projetos, autenticação, permissões,
   dashboards consolidados e integração Git, preservando contratos independentes.

Sincronização deve detectar conflitos, preservar informações e impedir
sobrescrita silenciosa de modificações concorrentes. Limites de garantias com
editores não cooperativos devem ser explicitados.

## Contrato

Dois modelos: `backlog.json` único ou `.backloger/project.json`,
`.backloger/work-items/ID.json`, `milestones.json`, `iterations.json`, `views.json`.
Arquivos por atividade são o padrão para facilitar revisões e merges Git.
`docs/BACKLOG.md` é um relatório derivado.

Exemplo de atividade:

```json
{
  "schema_version": "1.0.0",
  "id": "SYS-001",
  "title": "Implementar autenticação",
  "description": "Criar autenticação segura para a API",
  "type": "feature",
  "status": "in_progress",
  "priority": "critical",
  "component": "authentication",
  "owner": "backend-team",
  "labels": ["security", "backend", "p0"],
  "milestone_id": "M1",
  "estimate": {"unit": "hours", "value": 16},
  "dependencies": [{"target_id": "SYS-002", "relation": "blocked_by"}],
  "acceptance_criteria": [
    {"id": "AC-001", "text": "Validar credenciais", "done": true},
    {"id": "AC-002", "text": "Implementar testes de segurança", "done": false}
  ],
  "created_at": "2026-11-11T09:00:00-03:00",
  "updated_at": "2026-11-11T09:00:00-03:00",
  "version": 1,
  "extensions": {}
}
```

`schema_version` controla compatibilidade do formato; `version` controla
concorrência por atividade. O projeto deve conter as referências usadas no
exemplo. O contrato implementado e os limites constam em [CONTRACT.md](CONTRACT.md).

| Tipo | Uso |
| --- | --- |
| Epic | Grande iniciativa |
| Feature | Nova funcionalidade |
| Story | Necessidade funcional do usuário |
| Task | Atividade técnica |
| Bug | Correção de defeito |
| Maintenance | Manutenção preventiva/corretiva |
| Security | Correção ou melhoria de segurança |
| Documentation | Documentação |
| Spike | Investigação técnica |
| Incident | Incidente operacional |

Estados são configuráveis por projeto com categorias padronizadas para métricas.

## Dependências e análise

Setas expressam precedência: SYS-001 → SYS-002 e SYS-003 → SYS-004, onde
SYS-004 depende de SYS-002 e SYS-003, e ambos dependem de SYS-001.
O motor deve detectar ciclos, referências inexistentes, atividades isoladas,
bloqueadores transitivos, gargalos e impacto de atrasos. Selecionar uma atividade
deve expor seus pré-requisitos e itens potencialmente afetados. Caminho crítico
depende de dados suficientes e deve distinguir estimativa técnica de calendário.

## Interface

Cinco visualizações: dashboard executivo, Kanban editável, grafo de dependências,
tabela detalhada e roadmap de milestones. Kanban deve permitir drag-and-drop,
edição, limites WIP, filtros por responsável, prioridade, etiqueta, componente,
iteração e bloqueio, além de visões salvas. Dashboard deve exibir totais por
status, vencidas, bloqueadas, progresso e throughput/histórico quando disponíveis.
Mudanças externas dos JSONs devem atualizar a interface automaticamente.

## CLI

```sh
backloger init --name "Meu Sistema" --key SYS
backloger validate --strict
backloger list --status in_progress
backloger add --type feature --title "Criar API"
backloger move SYS-001 --to review
backloger link SYS-003 --blocked-by SYS-001
backloger export markdown --output docs/BACKLOG.md
backloger graph --format svg --output docs/graph.svg
backloger serve --port 8765
backloger docker up
backloger doctor
```

Deve oferecer --project, saídas JSON, códigos de retorno documentados e
autocompletar. Exportações incluem Markdown, CSV e Mermaid.

## Docker e automação

Entregáveis obrigatórios: Dockerfile, compose.yaml, compose.dev.yaml,
.dockerignore, .env.example e Makefile. Compose deve executar sem privilégios,
montar apenas o diretório autorizado e publicar a porta em 127.0.0.1 por padrão.
Somente leitura deve valer na aplicação e no volume.

Alvos Make funcionais e verificáveis: install, install-dev, build, package, lint,
format, typecheck, test, test-unit, test-integration, test-e2e, test-security,
coverage, check, validate, serve, export-md, graph, doctor, docker-build,
docker-up, docker-down, docker-restart, docker-logs, docker-ps, docker-config,
security-scan, sbom, clean, help.

## Segurança e integridade

Escrita atômica, locks, versão otimista, backups, recuperação, auditoria,
referências validadas e conflitos explícitos. Proteger XSS/Markdown, CSRF,
traversal, acesso entre projetos, grafos malformados e exposição HTTP acidental.
Autenticação e colaboração remota entram em evolução própria.

## Backlog do produto

| ID | Prioridade | Entrega |
| --- | --- | --- |
| BKL-001 | P0 | Estrutura e empacotamento Python |
| BKL-002 | P0 | JSON Schema oficial e exemplos |
| BKL-003 | P0 | Modelos de domínio e validação |
| BKL-004 | P0 | Persistência JSON e escrita atômica |
| BKL-005 | P0 | CLI completo |
| BKL-006 | P0 | Dependências e análise de grafos |
| BKL-007 | P0 | Markdown, CSV e Mermaid |
| BKL-008 | P0 | API FastAPI |
| BKL-009 | P0 | Dashboard e Kanban |
| BKL-010 | P0 | Visualizador de grafos |
| BKL-011 | P0 | Sincronização de alterações externas |
| BKL-012 | P0 | Segurança web local |
| BKL-013 | P0 | Docker Compose e Makefile |
| BKL-014 | P0 | Testes, CI e documentação |
| BKL-015 | P1 | Roadmap, timeline e relatórios avançados |
| BKL-016 | P1 | GitHub e GitLab |
| BKL-017 | P1 | Autenticação e colaboração multiusuário |
| BKL-018 | P1 | Importadores e plugins |
| BKL-019 | P2 | Centralização multiprojeto |
| BKL-020 | P2 | Dependências entre projetos |

**Primeira versão utilizável:** inicializar um projeto, cadastrar atividades,
editar Kanban, visualizar dependências, refletir alterações externas, gerar
Markdown e executar tudo em Compose sem perda de dados.

## Evolução

Preparar integrações com agentes de IA: consulta, propostas de atividades e
dependências e sugestão de próxima atividade pronta. Propostas passam pelas
mesmas validações e por revisão antes da persistência. Dependências globais
entre projetos devem preservar a independência dos dados de cada projeto.
