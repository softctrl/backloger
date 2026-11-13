# Backloger

Backlogs locais, portáveis e versionados em Git. Python 3.12+ · SoftCtrl.COM.

Uma CLI e uma interface web usam o mesmo contrato e as mesmas regras. Cada
projeto mantém seus próprios dados. Não requer servidor central ou banco de
dados; depois de instalado, funciona sem rede.

Para começar, siga o [runbook de instalação do comando e da skill](docs/RUNBOOK_ADOPTION.md).
Você instala esses dois componentes e pede ao agente para integrar o Backloger,
importar o acompanhamento existente e manter cards e relatórios atualizados nos
próximos trabalhos. O [guia de instalação](INSTALL.md) reúne opções adicionais,
PDF e atualização. Node é usado somente nos testes de interface.

Para instalar a partir de um checkout ou do código-fonte extraído:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/backloger --project examples/demo serve --port 8765
```

Abra http://127.0.0.1:8765. Para explorar dados de exemplo:

```sh
.venv/bin/backloger --project examples/demo serve
.venv/bin/backloger --project examples/single --json list
```

Também é possível instalar com `pipx install .` ou com o wheel produzido por
`make package`. Esse alvo gera wheel, fonte, ZIP com instalador, SBOM SPDX e
checksums em `dist/`. A publicação em PyPI/registry ainda não foi realizada.

Uso direto da CLI para criar um backlog: `backloger --project /repo init --name "Meu Sistema" --key SYS`.

- JSON por atividade ou arquivo único; schemas oficiais 1.0.0 e campos de extensão.
- CLI de criação, consulta, edição, dependências, validação e diagnóstico.
- Escrita atômica, lock, revisão por conteúdo, backups, auditoria e recuperação.
- Análise de bloqueios transitivos, impacto, ciclos e caminho crítico técnico.
- Grafo com busca, recortes para grandes projetos, tela inteira e exportação SVG/PDF paginada.
- Dashboard com gráficos interativos e burndown, Kanban, grafo Cytoscape, tabela e roadmap.
- Histórico automático e notas de andamento em cada card, preservados no Git.
- Relatório gerencial com resumo executivo, gráficos, burndown, alertas e atividades detalhadas.
- Markdown renderizado e exportações HTML/PDF a partir da mesma fonte, disponíveis na web e CLI.
- GitHub Action reutilizável com relatórios Markdown, HTML e PDF opcionais.
- Filtros, visões salvas, WIP, critérios de aceite e detecção de alterações externas.
- Exportações Markdown, CSV, Mermaid e SVG; Compose e Makefile.

```sh
backloger add --type feature --title "Criar API"
backloger add --title "Validar integração"
backloger link SYS-002 --blocked-by SYS-001
backloger move SYS-001 --to review
backloger validate --strict
backloger analyze SYS-002
backloger export markdown --output docs/BACKLOG.md
backloger graph --format svg --output docs/graph.svg
```

O exemplo assume um projeto com chave SYS. Opções globais vêm antes do comando:
`backloger --project /repo --json list --status in_progress`.

Para desenvolver: `make install-dev`, `make check`, `make test-e2e`.
Para Docker: `make docker-config`, `make docker-up PROJECT=/repo`.
`make help` lista todos os alvos.

Esta fundação 0.1.0 implementa o fluxo local e tem um fluxo E2E validado em
Chromium. Docker, auditoria online e fechamento da distribuição permanecem
pendentes; portanto a primeira versão ainda não está totalmente homologada.
P1/P2 (colaboração, integrações, plugins e múltiplos projetos) seguem no backlog.

- [Especificação-base 1.0](docs/SPECIFICATION.md)
- [Instalação, atualização e pacote distribuível](INSTALL.md)
- [Instalar o comando e a skill](docs/RUNBOOK_ADOPTION.md)
- [Skill de integração e acompanhamento contínuo](skills/backloger-adoption/SKILL.md)
- [Contrato, API e códigos CLI](docs/CONTRACT.md)
- [Arquitetura e limites de concorrência](docs/ARCHITECTURE.md)
- [Execução, Compose e recuperação](docs/OPERATIONS.md)
- [Backlog do próprio produto](docs/BACKLOG.md)
- [Resultados de validação](docs/VALIDATION.md)
- [Importar a action de relatórios](docs/GITHUB_ACTION.md)
- [Conteúdo e leitura dos relatórios gerenciais](docs/REPORTS.md)
- [Explorar dependências, caminho crítico e exportar o grafo](docs/DEPENDENCIES.md)

Licença [Apache-2.0](LICENSE). Bibliotecas JavaScript incluem suas próprias licenças.
