# Integração e rotina para o agente

Esta referência é executada pelo agente. O usuário precisa apenas instalar o
comando, copiar a skill e solicitar a integração.

## Identificar armazenamento e fontes

Use a raiz real do projeto. Preserve nome/chave, estados e convenções existentes
quando já houver Backloger. Selecione estados pelas categorias configuradas,
sem presumir que todo projeto usa `todo`, `in_progress` e `done`.

Sem backlog anterior, use `backloger --project CAMINHO init --name NOME --key CHAVE`.
Com legado, leia as fontes, normalize pelo [mapeamento](mapping.md) e gere um
candidato completo antes da entrada em uso. Preserve fontes, alterações locais e
um backup suficiente para reverter. O mapa estável de IDs evita duplicações.

O armazenamento normalmente fica na raiz. Se um `backlog.json` legado também é
consumido pela aplicação, investigue seus usos antes de renomear qualquer coisa.
Você pode adotar uma subpasta dedicada para o Backloger e registrar esse caminho
nas instruções do projeto. Não modifique o build da aplicação por necessidade
artificial da integração.

## Usar o helper com a instalação disponível

`stage_backlog.py` precisa do Python que tem Backloger instalado. Em instalações
por pipx/venv no Linux, resolva o comando e confira o Python do mesmo ambiente:

```sh
BACKLOGER_PYTHON="$(dirname "$(readlink -f "$(command -v backloger)")")/python"
"$BACKLOGER_PYTHON" -c 'import backloger; print(backloger.__version__)'
```

Se o comando usar outro tipo de launcher, identifique seu ambiente em vez de
presumir que o Python global contém o pacote. Resolva o caminho do helper em
relação à skill carregada. Prepare `proposal.json` e execute:

```sh
"$BACKLOGER_PYTHON" /caminho/da/skill/scripts/stage_backlog.py \
  --input /pasta-de-trabalho/proposal.json \
  --output /pasta-de-trabalho/candidate \
  --storage split --expected-count QUANTIDADE_RECONCILIADA \
  --source /caminho/fonte-legada.md
```

O helper aceita uma proposta no contrato Backlog, não faz extração automática de
formatos legados. Use os modelos/schemas instalados como contrato. O candidato
inclui canônicos, `id-map.json`, `migration-manifest.json` e `BACKLOG.md`. O
manifesto identifica datas atribuídas ao instante da importação; datas parciais
precisam ser resolvidas e documentadas. Leia o relatório e reconcilie contagens,
status, conteúdo, aceite, notas e relações. Não fabrique `.runtime/audit`.

## Aplicar a primeira adoção

Não encerre uma solicitação de integração com apenas o candidato. Dentro da
autorização recebida, publique o armazenamento validado e configure a rotina.
Congele os escritores durante a transferência e confira se as fontes mudaram.
O destino precisa estar livre de outro armazenamento, inclusive links simbólicos.

Uma transferência pode usar o Python do Backloger e os bytes do snapshot:

```python
from pathlib import Path
import json
from backloger.filesystem import atomic_create
from backloger.repository import Repository
from backloger.schema import reject_unknown

source = Path("/pasta-de-trabalho/candidate")
target = Path("/caminho/do/armazenamento-no-projeto")
snapshot = Repository(source, read_only=True).snapshot()
reject_unknown(snapshot.backlog)
manifest = json.loads((source / "migration-manifest.json").read_text())
if snapshot.revision != manifest["revision"]:
    raise RuntimeError("Candidato mudou; reconcilie novamente")
if any(path.exists() or path.is_symlink()
       for path in (target / ".backloger", target / "backlog.json")):
    raise RuntimeError("Destino já possui armazenamento; não sobrescrever")
if snapshot.storage == "single":
    atomic_create(target / "backlog.json", snapshot.raw["backlog.json"])
else:
    (target / ".backloger").mkdir()
    for name, content in snapshot.raw.items():
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_create(destination, content)
after = Repository(target, read_only=True).snapshot()
if after.revision != snapshot.revision:
    raise RuntimeError("Revisão divergente; preserve o destino e investigue")
```

A pasta do projeto/armazenamento deve existir. Uma interrupção pode deixar a
primeira cópia incompleta: preserve-a, mantenha escritores parados e restaure a
referência anterior antes de tentar outra entrada em uso. Nunca mescle uma
segunda cópia sobre um destino incompleto. Copie somente dados canônicos, não a
auditoria do candidato. Guarde mapa/manifesto em um local versionável com nome
único, por exemplo `docs/migrations/backloger/`, sem apagar registros anteriores.

## Integrar a continuidade ao projeto

Escolha o caminho do relatório: respeite a convenção já existente; se o Markdown
legado ocupa `docs/BACKLOG.md`, use outro nome, como `docs/BACKLOGER.md`, até
resolver seu arquivamento. Gere o relatório a partir dos JSONs e identifique a
fonte anterior como histórica, preservando seu conteúdo.

Mescle estas regras ao `.gitignore`, sem substituir regras de outras linguagens:

```gitignore
**/.backloger/.runtime/
backloger-reports/
```

Os JSONs canônicos, o histórico dos cards e a skill devem permanecer versionáveis.
Backups operacionais `.runtime` ficam fora do Git e precisam de preservação local.

Mescle [o bloco de AGENTS.md](../assets/AGENTS.backloger.md) às instruções do
projeto. Substitua `{{PROJECT_PATH}}` pelo caminho relativo do armazenamento
(normalmente `.`) e `{{REPORT_PATH}}` pelo relatório escolhido. Não substitua o
arquivo inteiro e não duplique o bloco. Registre também particularidades reais,
como estados customizados ou uma rotina de relatórios já existente. Ao terminar,
valide e confira o relatório e o diff; não faça commit/push automaticamente.

## Usar um backlog já ativo e mantê-lo atualizado

Reutilize os IDs e o mapa de origem. Consulte os cards antes de criar outros.
Use `add`, `move`, `link` e `update`; uma nova importação não substitui a pasta
ativa. Os exemplos abaixo assumem os estados padrão e devem ser adaptados ao
projeto:

```sh
backloger --project . list --status in_progress
backloger --project . show SYS-001
backloger --project . move SYS-001 --to in_progress --version VERSAO_LIDA --revision REVISAO_LIDA
backloger --project . update SYS-001 --file /pasta-de-trabalho/andamento.json --version VERSAO_LIDA --revision REVISAO_LIDA
```

Leia `show` novamente após uma gravação; versão e revisão mudam. `andamento.json`
é um JSON parcial de campos editáveis, por exemplo:

```json
{
  "history_note": "Critério de expiração implementado. Testes da sessão passaram; revisão ainda pendente."
}
```

Troque a nota pelo que realmente ocorreu. Atualize critérios quando verificados,
registre novas pendências e mantenha explícito o trabalho restante. Preserve as
extensões ao editar esse objeto; não substitua `history`. Em conflito, releia e
reconcilie antes de reaplicar. Não repita uma mutação com revisão antiga.

No encerramento do trabalho:

```sh
backloger --project . validate --strict
backloger --project . export markdown --output docs/BACKLOGER.md
```

Use os caminhos registrados no projeto, não obrigatoriamente esses exemplos.
Outputs são relativos ao diretório de execução. HTML/PDF e jobs de CI entram
quando solicitados ou já adotados pelo projeto. Sem agente executando tarefas,
a skill não roda em segundo plano; pessoas também podem atualizar os cards
pela CLI/web. Serviços externos não recebem mudanças sem autorização própria.
