# Visão de sprints

Abra **Sprints** no menu lateral. Escolha um ciclo para ver **A fazer**,
**Em andamento** e **Concluídas**, com os estados configurados no projeto.
Revisão, teste e outros estados da categoria ativa aparecem em Em andamento,
mantendo o nome original no card.

## Começar

1. Clique em **Criar sprint**, informe nome e período e salve. As datas são
   opcionais; o fim não pode anteceder o início.
2. Use **Adicionar do backlog**, busque por ID ou título e clique em Adicionar.
   Essa lista reúne as atividades sem sprint e mostra até 50 resultados por
   busca. Cada inclusão é salva individualmente com controle de concorrência.
3. Use **Nova atividade na sprint** para cadastrar trabalho já associado ao ciclo.
   Abra qualquer card para atualizar estado, responsável, critérios ou notas.

O campo **Sprint** no editor também permite transferir uma atividade para outro
ciclo ou deixá-la sem sprint. A opção **Sem sprint** reúne o backlog não alocado,
incluindo o trabalho em andamento. Não são criados ciclos ou datas automaticamente
a partir de etiquetas, nomes de milestones ou descrições antigas.

## Acompanhar o que falta

- **Restantes** soma A fazer e Em andamento. **Bloqueadas** considera os
  pré-requisitos transitivos do projeto, inclusive fora da sprint.
- **Conclusão** é a quantidade concluída dividida pelo escopo não cancelado.
  Canceladas ficam em uma seção separada e fora desse cálculo. Escopo vazio ou
  inteiramente cancelado aparece como Sem atividades aplicáveis.
- Os filtros recortam os cards; os indicadores permanecem referentes à sprint
  completa. A contagem de cada coluna mostra resultados filtrados / total.
  O filtro geral de iteração não interfere na seleção local de sprint.
- As colunas mostram 24 cards inicialmente e permitem carregar mais. A busca
  encontra também os cards que ainda não foram exibidos. A ordenação usa
  prioridade, prazo e ID.
- Atrasos exigem prazo no próprio card. O período da sprint é apresentado
  separadamente: um ciclo encerrado com trabalho aberto continua mostrando suas
  pendências, sem concluir atividades automaticamente.
- Estimativas dos itens abertos são somadas por unidade, sem converter horas,
  dias e pontos ou descontar percentuais de execução presumidos.

O burndown da sprint fica em uma seção expansível, com os últimos 30 dias em UTC.
Usa os mesmos checkpoints observados do dashboard; não reconstrói histórico
anterior à adoção. A referência ideal só aparece quando existe linha de base
observada no período. Mudanças de escopo podem elevar o saldo restante.

Mudanças externas nos JSONs aparecem na atualização automática. Planejamento e
edição usam a revisão do projeto. Se outra alteração ocorrer durante a edição,
o formulário é preservado e a gravação antiga é recusada. Em somente leitura,
é possível consultar sprints e abrir cards, com ações de gravação desabilitadas.

## Dados e relatórios

Sprints utilizam as **iterações** já existentes no contrato 1.0.0:
`.backloger/iterations.json`, ou `iterations` no arquivo único. A associação
continua em `work_items[].iteration_id`. Campos desconhecidos existentes nas
iterações são preservados ao editar nome e período.

Os relatórios gerenciais continuam cobrindo o projeto inteiro e incluem as
iterações e a associação de cada atividade. Consulte [CONTRACT.md](CONTRACT.md)
para a API e [REPORTS.md](REPORTS.md) para as definições dos indicadores.
