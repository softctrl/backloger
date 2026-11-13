# Relatório gerencial de acompanhamento

Abra **Documento → Relatório gerencial** na aplicação. Use **Atualizar
relatório** para reler os dados, **Markdown** para consultar o texto ou os
botões de download para obter Markdown, HTML e PDF. A versão **Abrir / imprimir**
permite leitura em outra aba e impressão pelo navegador. Filtros do quadro não
recortam o relatório. Após atualizar o código, reinicie o servidor Python.

## Conteúdo

1. Resumo executivo: situação observada, conclusão, volume aberto, bloqueios,
   prazos vencidos, throughput e atendimento dos critérios de aceite.
2. Distribuição: gráficos e tabelas por status e prioridade; capacidade por
   responsável e limites WIP.
3. Evolução: burndown de 30 dias e entradas/conclusões observadas em 7 dias.
4. Marcos e iterações: progresso, pendências, prazos e burndown de iterações com
   linha de base e datas. O gráfico por marco mostra até 20 marcos; gráficos de
   iteração mostram até cinco linhas de base. As tabelas de marcos/iterações são
   completas.
5. Dependências: bloqueadores transitivos, impactos potenciais, caminho crítico
   técnico do trabalho restante quando calculável (ou maior cadeia estrutural
   com motivo da ausência de duração) e até oito ações sem bloqueio, ordenadas por
   prioridade, prazo e ID.
6. Inventário completo das atividades.
7. Ficha de cada atividade: descrição integral, tipo, status, prioridade,
   responsável, componente, prazo, marco, iteração, estimativa, versão, datas,
   critérios de aceite, relações, etiquetas e último registro de acompanhamento.
8. Histórico completo dos cards, ordenado do registro mais recente ao mais antigo.
9. Critérios de leitura e qualidade dos dados.

## Indicadores e dados ausentes

Conclusão é a quantidade de atividades em categoria `done` dividida pelo total
não cancelado. Não representa percentual de esforço consumido. Sem atividades
aplicáveis, apresenta `—`. Atraso exige uma atividade aberta com `due_date`
anterior à referência. Ausência de prazo nunca significa entrega pontual.

Throughput conta IDs distintos observados entrando em `done` nos sete dias
anteriores à geração. Uma reabertura/conclusão repetida não duplica esse indicador.
O gráfico diário conta IDs distintos em cada dia, portanto sua soma pode diferir
do indicador quando a mesma atividade é concluída em dias diferentes.

Datas e métricas são UTC. Descrições e histórico são apresentados como texto
seguro; HTML, imagens e links externos dos cards não são executados. Campos
ausentes são identificados e não recebem dados ou descrições inventados.

Burndown usa quantidade restante, com observações da auditoria e o saldo
canônico atual. Dias sem checkpoint permanecem desconhecidos. No SVG, as linhas
são interrompidas nessas lacunas; no Mermaid, o eixo contém somente datas
observadas. Uma iteração só recebe referência ideal se houver `start_date`,
`due_date` e baseline real registrada durante seu período. Essa referência é
linear, não uma previsão de término. Alterações de escopo podem elevar o saldo.

A auditoria operacional é local e normalmente não acompanha o Git; notas dos
cards acompanham os JSONs. Um clone sem auditoria não recupera séries passadas.
O documento declara essa limitação e mostra throughput indisponível quando não
há histórico observado. Zeros no gráfico de eventos não comprovam produtividade
nula. Edições externas não geram eventos retroativos.

O [grafo interativo](DEPENDENCIES.md) tem exportação própria em SVG/PDF da visão,
com páginas de regiões e inventário. Essa exportação é separada do documento
gerencial e usa a mesma análise de dependências.

## Arquivos e automação

```sh
backloger export markdown --output docs/BACKLOG.md
backloger export html --output dist/BACKLOG.html
backloger export pdf --output dist/BACKLOG.pdf
```

Markdown contém tabelas e diagramas Mermaid. Em leitores sem suporte a Mermaid,
as tabelas preservam os dados e os blocos de diagrama ficam como código. HTML e
PDF incluem gráficos SVG sem rede, scripts ou arquivos auxiliares. PDF usa A4
retrato, paginação, cabeçalhos repetidos nas tabelas e agrupamento das fichas
quando couberem na página. Descrições extensas podem ocupar várias páginas.

CLI, API e [GitHub Action](GITHUB_ACTION.md) usam esse mesmo conteúdo. PDF mantém
limite de 2 MiB de fonte e 32 MiB de saída. Relatórios grandes usam partes com
até 30 segundos de renderização cada e até 300 segundos para a geração completa;
o arquivo final mantém todas as atividades e paginação contínua. O processamento
admite até 128 partes e 2.000 páginas. Para projetos maiores que esses limites,
exporte Markdown/HTML para processamento local.
