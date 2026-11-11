# Relatórios em outros projetos via GitHub Action

O [action.yml](../action.yml) da raiz é uma composite action importável. Ela
valida o projeto e gera os formatos solicitados, sem iniciar servidor nem alterar
os JSONs. Cada execução usa um único snapshot, compartilhado por todos os
relatórios. Markdown é o padrão; HTML e PDF são opcionais.

No ZIP de instalação, `action.yml` é uma cópia para consulta. Para executar ou
publicar a action, use o checkout ou extraia o arquivo de código-fonte incluído:
ela também precisa de `src/`, `pyproject.toml` e `scripts/action_reports.py`.

Após publicar este repositório no GitHub, copie o exemplo de
[workflow consumidor](../examples/github-actions/reports.yml) para seu projeto e
substitua `OWNER/BACKLOGER_REPO@FULL_COMMIT_SHA` pela localização e pelo SHA
publicados. Esses valores são placeholders: o ambiente atual não tem remoto Git
configurado, portanto não se apresenta uma action já publicada.

```yaml
permissions:
  contents: read

jobs:
  backlog:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          persist-credentials: false
      - uses: OWNER/BACKLOGER_REPO@FULL_COMMIT_SHA
        with:
          project-dir: .
          formats: markdown,html,pdf
          output-dir: backloger-reports
          artifact-name: meu-backlog
```

Para gerar somente Markdown, use `formats: markdown` ou omita a opção. Para HTML
e Markdown, use `formats: markdown,html`. O formato PDF gera um arquivo real,
com paginação A4 retrato; não depende de abrir um navegador.

| Entrada | Padrão | Uso |
| --- | --- | --- |
| project-dir | . | Diretório inicializado, dentro do workspace |
| formats | markdown | markdown, html e/ou pdf, separados por vírgulas |
| output-dir | backloger-reports | Diretório autorizado para os relatórios |
| strict | true | Rejeitar campos fora do contrato; customizações ficam em extensions |
| python-version | 3.12 | Python 3.12+ para executar o Backloger |
| upload-artifact | true | Publicar somente os arquivos gerados como artefato do workflow |
| artifact-name | backloger-reports | Nome do artefato |

Saídas: `report-dir`, `markdown`, `html`, `pdf` e `manifest`. Formatos não
solicitados retornam caminho vazio. Os nomes são `BACKLOG.md`, `BACKLOG.html` e
`BACKLOG.pdf`. `manifest.json` registra revisão do backlog, quantidade de
atividades, formatos e SHA-256 dos arquivos. O upload usa caminhos individuais,
sem empacotar o restante do workspace.

O HTML é autocontido, com estilos locais embutidos, sem JavaScript ou recursos
externos. Markdown, HTML e PDF incluem os registros de histórico presentes nos
cards. Dados inválidos ou erro de renderização falham o job; não são publicados
relatórios parciais como sucesso.

O runner suportado é Linux com apt/sudo, como ubuntu-latest. A action cria um
venv isolado e instala o código da própria revisão importada. Bibliotecas Pango
e fontes são preparadas somente quando PDF é solicitado. Entradas são passadas
por variáveis de ambiente e validadas antes do processamento, sem interpolar
texto recebido em comandos de shell. Projeto e saídas ficam dentro do workspace.

A CI deste repositório contém um job `report-action` que exercita `uses: ./`
com os três formatos. A geração dos relatórios é testada localmente; a execução
remota e o upload no GitHub aguardam publicação e execução do workflow.

Os três formatos contêm o [relatório gerencial completo](REPORTS.md), com
gráficos, alertas, marcos e descrição das atividades. Os gráficos são Mermaid no
Markdown e SVG incorporado no HTML/PDF; não há dependência de CDN ou navegador.
Um clone que não contém `.backloger/.runtime/audit` mantém notas dos cards, mas
não reconstrói séries temporais de produtividade/burndown. Essa ausência é
explicitada no documento, junto ao saldo atual dos JSONs.

A estrutura segue a documentação oficial de
[composite actions](https://docs.github.com/en/actions/tutorials/create-actions/create-a-composite-action)
e de [artefatos](https://docs.github.com/en/actions/tutorials/store-and-share-data).
