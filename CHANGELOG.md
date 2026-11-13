# Changelog

## Em desenvolvimento

Visão de Sprints com seleção de ciclo, colunas por categoria de estado, progresso,
restantes, bloqueios, prazos e burndown. Criação/edição de sprints e inclusão de
atividades existentes pela web; novas atividades herdam a sprint selecionada.
Filtros não alteram os indicadores do escopo completo, canceladas ficam separadas
e listas grandes carregam mais cards sob demanda. As entidades reutilizam
`iterations`/`iteration_id`, com concorrência, backup, auditoria e somente leitura.

Correção da exportação PDF para relatórios com centenas de atividades: layout em
partes menores, metadados dos cards em blocos de texto, memória liberada entre
partes e reunião em arquivo único com paginação global. Limites de recursos e
bloqueio de recursos externos são mantidos. Falhas de memória, dependências,
CPU, tempo e tamanho agora têm diagnósticos distintos. `pypdf` passa a ser uma
dependência de runtime. Instalação inclui orientação para Fedora.

Dependências com tela inteira, busca por ID/título, escopo de pendências/projeto,
recortes de vizinhança/pré-requisitos/impactos, rótulos adaptáveis e layout
hierárquico por maior precedência. Exportação SVG e PDF da visão com panorama,
regiões legíveis e inventário. Motor com alcance transitivo por bitsets, folgas
e todas as rotas críticas empatadas. Estimativas ausentes/incompatíveis são
declaradas; a maior cadeia estrutural fica navegável sem inventar duração.
Relatório gerencial passa a usar o caminho restante, com explicação dos dados
necessários. Documentação de uso e contrato da nova exportação incluídos.

Runbook simplificado para instalar comando/skill e solicitar a integração ao
agente. A skill `backloger-adoption` orienta importação e entrada em uso, incorpora
a rotina ao `AGENTS.md` e mantém cards, histórico e relatórios durante os próximos
trabalhos. Referências técnicas e exemplo CSV/Markdown ficam dentro da skill e
do pacote. O helper recusa destinos existentes e valida o candidato normalizado.

Distribuição local em ZIP com instalador Python, wheel, código-fonte,
documentação, exemplos, schemas, SBOM e checksums. Guia de instalação e
atualização, validação de integridade antes da instalação e suporte a
wheelhouse sem índice remoto. `.gitignore` ampliado para Python, testes,
artefatos, arquivos locais e dados operacionais, preservando JSONs canônicos.

Relatório gerencial completo em Markdown, HTML e PDF: resumo executivo,
indicadores de conclusão, alertas de atraso/bloqueio/WIP, gráficos de status,
prioridades, entregas por marco e ritmo de entrega, burndown real e referência
ideal por iteração quando há linha de base. Inclui inventário, escopo completo,
responsáveis, prazos, estimativas, critérios de aceite, dependências e histórico
das atividades. PDF em A4 retrato com gráficos vetoriais, tabelas específicas,
fichas agrupadas e paginação; atualização manual do documento na web.

Dashboard com gráficos SVG interativos, burndown por projeto/iteração,
animações acessíveis e controles de grafo. Documento renderizado a partir do
Markdown canônico, HTML autocontido e PDF paginado. Histórico por card com notas
e registro automático de mudanças. Composite action para gerar/publicar somente
os relatórios Markdown, HTML e PDF solicitados por outro projeto GitHub.

## 0.1.0 — 2026-11-11

Fundação local do Backloger: contrato 1.0.0, dois formatos JSON, CLI, persistência
atômica com controle de concorrência e recuperação, análise de dependências,
exportadores e API compartilhando o núcleo. Interface com dashboard, Kanban,
grafo, tabela e milestones. Assets locais, segurança HTTP, Compose, Makefile,
testes e documentação.

Esta versão ainda aguarda homologação em navegador real e Docker, auditoria
online e fechamento da distribuição reproduzível. Veja
[o relatório de validação](docs/VALIDATION.md) e [o backlog](docs/BACKLOG.md).
