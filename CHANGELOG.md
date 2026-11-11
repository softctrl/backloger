# Changelog

## Em desenvolvimento

Runbook para adoção em projetos existentes e skill `backloger-adoption`, com
inventário, mapeamento de campos/IDs, reconciliação, preparação validada em pasta
separada, entrada em uso, migração incremental e reversão. Exemplo fictício
reconcilia CSV/Markdown preservando critérios, notas e datas de origem. O helper
recusa destinos existentes e não é um importador universal de formatos legados.

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
