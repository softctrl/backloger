# Execução e recuperação

Instalação, requisitos de PDF, atualização e pacote ZIP estão em
[INSTALL.md](../INSTALL.md). `make package` gera wheel, fonte, instalador, SBOM
e checksums. Make/Compose são usados a partir do checkout ou do arquivo fonte
extraído; a CLI instalada por wheel opera projetos sem copiar o código-fonte.

Projetos com acompanhamento anterior devem seguir o
[runbook de instalação do comando e da skill](RUNBOOK_ADOPTION.md). A skill cuida
da integração, importação e rotina futura de acompanhamento pelo agente; seus
detalhes técnicos e exemplos acompanham o ZIP.

## Dashboard, burndown e documento

Em **Sprints**, escolha um ciclo para acompanhar A fazer, Em andamento e
Concluídas, com progresso, restantes e bloqueios do escopo completo. É possível
criar/editar sprints, adicionar atividades existentes e cadastrar novas já
associadas ao ciclo. A opção Sem sprint mostra o backlog não alocado. Veja
[SPRINTS.md](SPRINTS.md) para planejamento, filtros e burndown.

A página inicial abre o dashboard. Os gráficos de estado, prioridade e
responsável permitem abrir as atividades correspondentes no Kanban. Ritmo de
entrega admite janelas de 7/14/30 dias e tabela alternativa acessível. Animações
respeitam a preferência do sistema por movimento reduzido. O grafo permite busca,
recortes de vizinhança/pré-requisitos/impactos, tela inteira, três organizações e
exportação da visão em SVG/PDF paginado. Caminho crítico distingue estimativas
de cadeias estruturais sem duração; veja [DEPENDENCIES.md](DEPENDENCIES.md).

O burndown usa quantidade de atividades restantes, com seleção de projeto ou
iteração. Gravações registram checkpoints reais; datas anteriores ao histórico
disponível ficam vazias, e intervalos sem registro são pontilhados. A leitura
atual mostra o saldo canônico de hoje. A referência ideal exige uma iteração com
start_date/due_date e uma linha de base registrada durante o período. Novas
atividades, cancelamentos e reaberturas podem alterar o saldo. Não se inferem
estimativas em pontos/horas ou histórico a partir de timestamps de edição.

Em **Documento**, alterne entre a prévia renderizada e o Markdown original,
copie o texto, abra uma versão para imprimir ou baixe PDF. O documento completo
usa exatamente o mesmo Markdown da CLI; filtros do quadro não recortam o relatório.
Notas e mudanças dos cards aparecem também nos relatórios. O campo **Nota de
andamento**, no editor de cada card, acrescenta registros ao salvar.

A prévia agora é um **relatório gerencial**: resumo executivo, indicadores,
alertas, gráficos, marcos, burndown, próximas ações e descrição completa de cada
atividade. **Atualizar relatório** força nova leitura. A mesma fonte é usada nos
três formatos e na action de CI. Veja [REPORTS.md](REPORTS.md) para definições e
tratamento de dados ausentes. Depois de atualizar o código, reinicie o processo
Python para carregar o novo gerador e recarregue a página.

```sh
backloger export markdown --output docs/BACKLOG.md
backloger export html --output dist/BACKLOG.html
backloger export pdf --output dist/BACKLOG.pdf
make export-pdf
```

PDF usa WeasyPrint e bibliotecas Pango. No Debian/Ubuntu, prepare
`libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core`; Docker e a action de
relatórios já incluem essa preparação. O renderizador roda em processo isolado,
sem buscar URLs/arquivos externos e com limites de recursos. Relatórios grandes
são renderizados em partes e reunidos com paginação contínua, preservando todas
as atividades. Cada parte admite 30 segundos; o trabalho completo admite até
300 segundos. O PDF pode levar alguns minutos em projetos com centenas de cards.
Documentos acima de 2 MiB devem ser exportados em Markdown para processamento
local. A prévia fica em iframe sem permissão de executar scripts.

Se a exportação falhar, a mensagem distingue dependências ausentes, memória,
tempo e limites de saída. Os logs registram a categoria e o código de saída,
sem publicar o texto dos cards ou o stderr bruto do renderizador. Reinstalar
Pango não resolve uma mensagem de memória ou timeout. HTML/Markdown continuam
disponíveis para os casos que excedem os limites do PDF.

Para testar gráficos e interações sem navegador: instale Node 22.12+,
execute `npm install --ignore-scripts` e `make test-ui`. Node é uma ferramenta de
teste e não é necessário para servir a aplicação. A CI executa esses testes;
o teste Playwright continua responsável pela homologação em navegador real.

Para reutilizar a CI em outro projeto, consulte [GITHUB_ACTION.md](GITHUB_ACTION.md).

```sh
make install-dev
make check
make serve
# Outro repositório:
backloger --project /caminho/projeto init --name "Meu Sistema" --key SYS
backloger --project /caminho/projeto add --type feature --title "Criar API"
backloger --project /caminho/projeto move SYS-001 --to review
backloger --project /caminho/projeto export markdown --output docs/BACKLOG.md
```

`pipx install .` instala a CLI isoladamente. Até a publicação no PyPI, use o
checkout ou wheel de `make package`. Runtime não requer rede. O instalador dev
lê o grupo de dependências de `pyproject.toml`.

Atualizações estruturadas usam JSON parcial com campos editáveis:

```sh
backloger --project /repo show SYS-001
backloger --project /repo update SYS-001 --file alteracao.json --version 1 --revision HASH
```

`alteracao.json` pode conter description, owner, labels, estimate,
acceptance_criteria etc. `move` aceita versão/revisão. A documentação HTTP está em
`/api/docs`; mutações exigem X-Backloger-Token da página e If-Match.

## Docker

O projeto precisa estar inicializado; o container não inicializa ou apaga dados.

```sh
cp .env.example .env
# Ajuste diretório e identidade no .env.
make docker-config
make docker-up PROJECT=/caminho/projeto
make docker-ps
make docker-down
# Desenvolvimento com reload:
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

Abra `http://127.0.0.1:8765`.

| Variável | Padrão | Uso |
| --- | --- | --- |
| BACKLOGER_PROJECT | . | Raiz autorizada; no container é /project |
| BACKLOGER_PORT | 8765 | Porta publicada em 127.0.0.1 |
| BACKLOGER_READ_ONLY | false | Bloqueia app e torna o volume somente leitura |
| LOCAL_UID / LOCAL_GID | 1000 / 1000 | Identidade não privilegiada Compose |
| PYTHONPATH | /workspace/src no override dev | Código montado para reload |

Make aceita PROJECT e PORT; configura LOCAL_UID/GID com a identidade atual e
BACKLOGER_PROJECT a partir de PROJECT. Para usar o path do `.env`, invoque
Compose diretamente ou passe o mesmo path em PROJECT. O Dockerfile isolado
usa usuário 10001:10001.

```sh
BACKLOGER_READ_ONLY=true make docker-restart PROJECT=/caminho/projeto
backloger --project /caminho/projeto --read-only serve
```

No host, `--read-only` protege o repositório; permissões de filesystem devem ser
configuradas pelo operador para impedir também outros programas. Compose
configura o volume ro automaticamente. O wrapper `--read-only docker up`
mantém ambas as proteções.

## Backup e recuperação

```sh
backloger doctor
backloger recover
backloger backups
backloger restore SYS-001 --backup ID_DO_BACKUP --version VERSAO_ATUAL
```

Restore recupera uma atividade validada, incrementa sua versão e gera outro
backup/auditoria. No modo único extrai somente essa atividade, mantendo as
demais. O arquivo anterior de views também é guardado; sua restauração é
manual nesta versão.

Em conflito de recuperação, copie todo o projeto, incluindo `.runtime`, antes
de resolver. Compare o alvo, os hashes/conteúdo no diário e o backup. Não apague
diários para ocultar conflitos. Recovery mantém qualquer terceiro conteúdo.

Preserve `.runtime` fora do Git em seu plano de backup externo. Não há expurgo
automático. Arquive auditoria antes de 20.000 eventos e monitore o disco.
`make clean` preserva JSONs, backups, diários e ambiente virtual.

O `.gitignore` mantém arquivos canônicos de `.backloger/`, `backlog.json`,
schemas, exemplos e documentação gerencial versionáveis. Exclui somente o
subdiretório operacional `.backloger/.runtime/`, além de ambientes, caches,
artefatos, relatórios temporários e configurações/credenciais locais. Arquivos
de lock das dependências não são ignorados. Regras de ignore não retiram do
Git arquivos já rastreados; revise o índice ao incorporar essas regras a um
repositório existente.

## Verificação

`make check` executa Ruff, parser JS quando Node existe, hashes de assets, Mypy,
testes sem navegador e validação do backlog. `make coverage` gera htmlcov/.

Para navegador: `.venv/bin/python -m playwright install chromium`, seguido de
`make test-e2e`. CHROMIUM_EXECUTABLE_PATH seleciona outro Chromium instalado;
BACKLOGER_SCREENSHOT=/tmp/backloger.png salva uma imagem após o teste. O teste
encaminha requisições do navegador à aplicação ASGI real em processo, sem porta
de teste. O smoke Docker exercita HTTP no container.

`make test-docker` verifica os dois formatos, criação HTTP, edição externa,
Markdown e somente leitura na API e no volume. `make security-scan` consulta
vulnerabilidades da árvore runtime instalada e requer rede; `make sbom`
funciona offline. A CI inclui Python 3.12/3.14, Chromium, Compose e auditoria.
Resultados efetivamente obtidos estão em [VALIDATION.md](VALIDATION.md).
