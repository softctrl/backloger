# Instalação do Backloger 0.1.0

O pacote instala a CLI e a aplicação web local. Requer **Python 3.12+** e um
ambiente virtual; não requer Node, servidor central ou banco de dados. A
instalação inicial baixa dependências Python, salvo se você fornecer um
diretório local com todos os wheels compatíveis. Depois de instalado, o fluxo
local funciona sem rede.

Para incorporar em um projeto que já possui backlogs ou outros acompanhamentos,
siga o [runbook de instalação do comando e da skill](docs/RUNBOOK_ADOPTION.md).
A skill `backloger-adoption` orienta o agente a integrar o Backloger, importar o
acompanhamento anterior e registrar no projeto a rotina de atualização dos cards
e relatórios durante os próximos trabalhos.

## Instalar pelo pacote ZIP

Extraia `backloger-0.1.0-install.zip` e entre em `backloger-0.1.0/`:

```sh
python3 install.py --check
python3 install.py
.venv/bin/backloger --version
```

Pode usar outro executável Python 3.12 ou mais recente, como `python3.14`.
O instalador verifica os checksums, cria `.venv`, instala o wheel com suas
dependências e executa `pip check`. Ele não instala pacotes no Python global,
não pede privilégios administrativos e não inicializa nem altera um backlog.

Para escolher um destino fora da pasta extraída:

```sh
python3 install.py --venv "$HOME/.local/share/backloger/venv"
"$HOME/.local/share/backloger/venv/bin/backloger" --version
```

Para instalar sem consultar um índice, prepare previamente os wheels das
dependências para o mesmo Python/sistema operacional e use:

```sh
python3 install.py --wheelhouse /caminho/wheelhouse
```

O ZIP não inclui o interpretador Python nem os wheels das dependências.
`requirements-runtime.txt` e o SBOM registram o ambiente de construção; esse
inventário não substitui um lock com hashes nem um wheelhouse completo.

## Instalar diretamente o wheel

Com pipx já disponível:

```sh
pipx install --python python3 ./backloger-0.1.0-py3-none-any.whl
backloger --version
```

Ou em um ambiente virtual criado manualmente:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install ./backloger-0.1.0-py3-none-any.whl
.venv/bin/python -m pip check
.venv/bin/backloger --version
```

O wheel contém CLI, API, interface, gráficos, assets locais, licenças e JSON
Schemas. A instalação pelo wheel não precisa do checkout do código-fonte.

## Preparar PDF no Linux

Markdown e HTML não exigem bibliotecas nativas de renderização. Para PDF no
Debian/Ubuntu, prepare Pango e fontes:

```sh
sudo apt-get update
sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core
```

No Fedora:

```sh
sudo dnf install pango fontconfig dejavu-sans-fonts
```

O pacote instala também `pypdf`, usado para reunir relatórios grandes em um
único arquivo com numeração contínua. Instale/atualize o pacote completo para
manter essas dependências disponíveis no mesmo ambiente do comando.

Se o Python da distribuição não oferecer `venv`/`ensurepip`, instale também o
pacote `python3-venv` correspondente ao interpretador escolhido. Docker e a
action de relatórios já incluem a preparação de Pango/fontes. O renderizador
PDF usa limites de recursos do Linux; Windows/macOS não foram homologados
nesta entrega. Veja [validação](docs/VALIDATION.md).

## Inicializar e usar em qualquer repositório

Depois de instalar, ative o venv ou use o caminho completo do executável. Com
pipx, `backloger` já fica no PATH configurado pelo pipx.

```sh
. .venv/bin/activate
backloger --project /caminho/meu-projeto init --name "Meu Sistema" --key SYS
backloger --project /caminho/meu-projeto add --type feature --title "Criar API"
backloger --project /caminho/meu-projeto validate --strict
backloger --project /caminho/meu-projeto serve --port 8765
```

Abra `http://127.0.0.1:8765`. Em **Documento**, consulte o relatório gerencial,
atualize a prévia e baixe Markdown, HTML ou PDF. A CLI também exporta:

```sh
backloger --project /caminho/meu-projeto export markdown --output docs/BACKLOG.md
backloger --project /caminho/meu-projeto export html --output dist/BACKLOG.html
backloger --project /caminho/meu-projeto export pdf --output dist/BACKLOG.pdf
```

Os caminhos de saída são relativos ao diretório de onde o comando foi
executado; `--project` seleciona a origem dos dados, não o destino dos relatórios.
Para um projeto existente, omita `init`. Use `doctor` para diagnóstico.

## Atualizar ou remover a instalação

Pare o servidor antes de atualizar. Com pipx, instale o novo wheel:

```sh
pipx install --force ./backloger-0.1.0-py3-none-any.whl
```

Em venv existente, substitua o pacote mesmo quando for uma nova construção da
mesma versão local:

```sh
.venv/bin/python -m pip install --upgrade --force-reinstall ./backloger-0.1.0-py3-none-any.whl
.venv/bin/python -m pip check
```

Reinicie o servidor e recarregue a página. Os dados continuam no diretório de
cada projeto; mantenha seu backup, incluindo `.backloger/.runtime` para
recuperação. Para remover com pipx: `pipx uninstall backloger`. Em venv, use
`python -m pip uninstall backloger` pelo Python desse ambiente.

## Código-fonte, desenvolvimento e Docker

Extraia `backloger-0.1.0.tar.gz` para obter código, testes, Makefile, Compose,
exemplos e action. Dentro do diretório extraído:

```sh
make install-dev
make check
make serve PROJECT=/caminho/meu-projeto
make docker-up PROJECT=/caminho/meu-projeto
```

Docker exige daemon e Compose. O wrapper `backloger docker` depende desses
arquivos do código-fonte; uma instalação isolada do wheel não os inclui.
Detalhes em [operação](docs/OPERATIONS.md) e [action reutilizável](docs/GITHUB_ACTION.md).

## Conteúdo e integridade

O ZIP inclui instalador, wheel, fonte, guias, skill de migração, exemplos, schemas, inventário SPDX,
versões observadas e checksums. O arquivo `dist/SHA256SUMS` confere os artefatos
distribuídos; o `SHA256SUMS` interno confere os arquivos extraídos.

```sh
sha256sum --check SHA256SUMS
```

Essa construção local não foi publicada no PyPI/registry e não possui assinatura
digital. Checksum detecta alteração em relação ao manifesto, mas não autentica
o distribuidor. Homologação completa e pendências estão em
[VALIDATION.md](docs/VALIDATION.md).
