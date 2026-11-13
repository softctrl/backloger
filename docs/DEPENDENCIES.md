# Dependências e caminho crítico

Abra **Dependências** na interface web. As setas sempre seguem **pré-requisito
→ dependente**. Somente `blocked_by` e `blocks` impõem precedência;
`relates_to` e `child_of` não entram no cálculo.

## Ler projetos grandes

- **Pendências** mostra atividades fora das categorias concluída e cancelada.
  **Projeto completo** inclui também o trabalho encerrado.
- A visão **Automática** começa pelo conjunto filtrado. Acima de 120 atividades,
  abre uma vizinhança de até 180 nós, com aviso do recorte e contagem do escopo.
  **Panorama completo** mostra todas as atividades do escopo e dos filtros.
- **Localizar atividade** procura por ID ou título no escopo inteiro. Digite para
  refinar a lista e pressione Enter ou selecione um resultado. A busca encontra
  atividades fora do recorte inicial e dos filtros gerais.
- Selecione **Vizinhança**, **Pré-requisitos** ou **Impactos** para explorar uma
  atividade. As duas últimas visões incluem relações transitivas. O painel
  inferior lista todas as relações do projeto, 30 por vez; clicar em um item
  muda o foco. Consultar um pré-requisito encerrado abre o escopo completo.
- A organização **Hierárquica** respeita a maior cadeia de precedência e agrupa
  componentes independentes. Troque a direção para cima/baixo ou use as
  organizações concêntrica/circular. Rótulos automáticos usam somente IDs em
  desenhos com mais de 80 nós; o painel inferior mantém os títulos completos.
- **Tela inteira** amplia a área do grafo, com alternativa por CSS quando o
  navegador não permite fullscreen. O mesmo botão ou Esc retorna à página.
  Use zoom e **Enquadrar** para navegar. Atualizações sem mudança de topologia
  preservam a posição e o zoom.

A contagem junto à legenda informa quantas atividades e relações estão
desenhadas. Os totais de análise continuam referentes ao projeto ou ao escopo
de cálculo indicado. Um recorte visual não remove dependências canônicas.

## Calcular o caminho crítico

O motor faz passagens de ida e volta sobre o DAG para calcular início/fim
técnicos, início mais tarde e folga. Destaca **todas as rotas empatadas sem
folga**, além de fornecer um caminho representativo determinístico.

Para calcular duração, todas as atividades do escopo precisam de estimativa
na **mesma unidade**: horas, dias ou pontos. Abra os cards e preencha
**Estimativa** e **Unidade**. Valores zero são válidos. Não há conversão implícita
entre unidades.

O escopo **Pendências** calcula o trabalho ainda aberto; estimativas ausentes
em cards concluídos não impedem esse cálculo. **Projeto completo** considera as
atividades não canceladas, inclusive concluídas. Esses cálculos usam as
estimativas cadastradas, sem descontar percentuais de execução de atividades
em andamento. Não são previsões de calendário nem consideram disponibilidade
de pessoas, paralelismo limitado ou feriados.

Sem estimativas suficientes, o motor mostra a **maior cadeia de precedência
por quantidade de atividades**, declara o motivo e mantém a duração ausente.
O botão **Completar estimativas** abre os cards sem estimativa no escopo. Unidades
misturadas exigem revisão dos valores nos cards. **Ver rotas** isola as rotas
calculadas; filtros gerais não cortam esse resultado. A seção de dependências
do relatório gerencial usa a mesma análise do trabalho restante.

## Exportar o desenho

**SVG** e **PDF da visão** exportam os nós e as posições da visão atual, incluindo
os nós alcançáveis por pan/zoom. Zoom e deslocamento não recortam o arquivo. A
exportação usa títulos, estados e relações canônicas da revisão exibida.

SVG permite ampliar sem perda. PDF usa A4 paisagem, com panorama, regiões em
páginas separadas para desenhos grandes e inventário com títulos completos,
estados e pré-requisitos diretos. Dependências de fora do desenho recebem a
indicação **fora da visão** no inventário. O cálculo de duração sempre identifica
seu escopo; ele não é recalculado somente sobre o recorte exportado.

O PDF admite até 36 regiões de grafo e 2 MiB de conteúdo intermediário. Se a
visão exceder esses limites, reduza o recorte ou exporte SVG. Requer a mesma
instalação WeasyPrint/Pango do [PDF gerencial](OPERATIONS.md). Exportar funciona
em modo somente leitura e não altera os JSONs. Se houver uma edição concorrente,
a API recusa a revisão antiga; aguarde a atualização e exporte novamente.

## Automação

```sh
backloger --project /repo --json analyze SYS-003
backloger --project /repo graph --format svg --output docs/graph.svg
```

O SVG da CLI usa a organização do exportador de relatórios. Para preservar a
organização interativa e gerar o PDF do grafo, use os botões da web ou a API
descrita em [CONTRACT.md](CONTRACT.md). A exportação Markdown/HTML/PDF do documento
gerencial continua disponível separadamente na web, CLI e action.
