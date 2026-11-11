# Runbook — adoção e migração em projetos existentes

Este procedimento adiciona o Backloger a um repositório Python, Go, Java, React
ou de outra tecnologia. A aplicação original não precisa importar uma biblioteca
Backloger nem mudar seu build. O contrato JSON do backlog fica no próprio projeto.

A migração é assistida pela skill `backloger-adoption`: ela lê o acompanhamento
existente, reconcilia os dados e prepara uma proposta. O helper valida uma
proposta já normalizada e cria um candidato separado. **Não existe um comando
universal `backloger import` nem sincronização automática com Jira/GitHub/GitLab
nesta versão.** Exportações dessas ferramentas podem ser usadas como fontes.

## Resultado esperado

- Fontes anteriores preservadas e identificadas por arquivo/ID/hash.
- Atividades, descrições, critérios, relações, marcos e histórico reconciliados.
- Mapa estável de IDs e decisões sobre estados, prioridades e datas.
- Contrato válido, sem referências inexistentes ou ciclos.
- Operação por CLI/web e relatórios Markdown, HTML e PDF quando habilitado.
- Entrada em uso e reversão documentadas, sem sobrescrita silenciosa.

## 1. Pré-requisitos e limites

Instale o pacote conforme [INSTALL.md](../INSTALL.md). Para executar os helpers,
use o Python do venv que contém `backloger`. Os exemplos abaixo usam o venv
criado pelo instalador do ZIP. Com pipx, a CLI funciona normalmente; para os
helpers, selecione o Python do ambiente que contém o pacote ou use o venv do ZIP.

No Linux/Bash, ajuste os caminhos para sua instalação e para o projeto real:

```sh
export ADOPTION_PACKAGE="/caminho/backloger-0.1.0"
export ADOPTION_PROJECT="/caminho/projeto-existente"
export ADOPTION_PYTHON="$ADOPTION_PACKAGE/.venv/bin/python"
export ADOPTION_CLI="$ADOPTION_PACKAGE/.venv/bin/backloger"
export ADOPTION_WORK="$(mktemp -d -t backloger-adoption.XXXXXX)"
"$ADOPTION_CLI" --version
```

O projeto deve existir e ser gravável. Trabalhe apenas no escopo autorizado,
respeitando instruções locais e alterações ainda não commitadas. A pasta
`ADOPTION_WORK` guarda a preparação; não é o backlog ativo. Não a apague antes
de preservar os registros de migração.

O formato admite 2.000 atividades, 10.000 relações, 100 dependências por card e
até 1.000 registros de histórico por card. O helper lê até 8 MiB por proposta ou
fonte indicada. Planeje divisão de escopo quando exceder esses limites; não
trunque nem descarte itens para fazer a validação passar. PDF tem limites
próprios descritos em [REPORTS.md](REPORTS.md).

## 2. Reconhecer o estado atual e preservar as fontes

```sh
cd "$ADOPTION_PROJECT"
git status --short
rg --files --hidden -g '!.git' -g '!.venv' -g '!node_modules' -g '!dist' \
  | rg -i 'backlog|roadmap|sprint|iteration|milestone|todo|kanban|issues|\.csv$'
```

Além dos nomes, procure listas de tarefas em README, documentação de releases,
atas, ADRs e acompanhamentos operacionais. Use os arquivos explicitamente
indicados pelo time mesmo se não aparecerem nessa busca. Para serviços externos,
use exportações ou acesso de leitura já autorizado, sem criar/fechar issues.

Verifique se existe `.backloger/project.json` ou `backlog.json` na raiz. O segundo
nome pode ser um arquivo legado com outro formato. **Não execute `init` sobre
um backlog existente e não o substitua.** Em monorepos, defina se o escopo é o
repositório inteiro ou um subprojeto. A CLI procura o projeto mais próximo nos
ancestrais: confirme nome/chave/caminho com `doctor` antes de alterar dados.

Faça backup das fontes e, quando já houver Backloger, de todo `.backloger`
incluindo `.runtime`, ou de `backlog.json` e do `.runtime` correspondente. Use
um destino separado, sem substituir backups anteriores. Git não preserva
arquivos ignorados nem alterações não commitadas por si só.

Registre um inventário em sua pasta de trabalho:

| Informação | O que registrar |
| --- | --- |
| Fonte | Caminho/exportação, hash e instante do levantamento |
| Identidade | Sistema/arquivo + ID original; referências entre documentos |
| Volume | Atividades únicas, subtarefas, critérios e notas |
| Estado | Vocabulário usado, concluídos, cancelados e ambiguidades |
| Planejamento | Marcos, iterações, prazos, estimativas e suas unidades |
| Relações | Pré-requisitos, referências externas e ciclos aparentes |
| Histórico | Notas datadas, autores, registros sem data e relatórios anteriores |

Não conte a mesma issue descrita em CSV e Markdown duas vezes. Não transforme
cada checkbox interno em atividade se ele representa um critério de aceite.

## 3. Instalar e invocar a skill

O ZIP e o código-fonte incluem [skills/backloger-adoption](../skills/backloger-adoption/SKILL.md).
Copie a pasta inteira para `.agents/skills/backloger-adoption` no projeto de
destino; scripts e referências fazem parte da skill:

```sh
"$ADOPTION_PYTHON" - <<'PY'
import os
import shutil
from pathlib import Path
source = Path(os.environ["ADOPTION_PACKAGE"]) / "skills/backloger-adoption"
target = Path(os.environ["ADOPTION_PROJECT"]) / ".agents/skills/backloger-adoption"
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(source, target)
PY
```

Esse comando recusa um destino já existente; revise uma atualização da skill
separadamente. Se o ambiente impedir escrita em `.agents`, mantenha a skill em
um diretório permitido e indique seu caminho ao agente, ou instale em uma
localização de skills autorizada. Não é necessário alterar permissões do sistema.

No Codex, skills de repositório são descobertas em `.agents/skills`; podem ser
invocadas com `$backloger-adoption`. Se não aparecerem, reinicie a sessão. Essa
convenção está documentada nas [OpenAI Docs sobre skills](https://learn.chatgpt.com/docs/build-skills).
A criação dessa pasta no seu projeto é uma etapa do operador: o instalador do
Backloger não modifica diretórios de configuração de agentes automaticamente.

Prompt para preparar a migração:

```text
Use $backloger-adoption para adotar o Backloger neste projeto.
Fontes: docs/BACKLOG.md, docs/ROADMAP.md e exports/issues.csv.
Preserve os originais, identifique duplicidades e proponha um mapa de IDs,
estados, critérios, dependências e histórico. Prepare um candidato separado,
valide-o e mostre a reconciliação. Nesta etapa, não altere o backlog ativo.
```

Para aplicar uma migração já revisada, explicite o projeto, o candidato e o
escopo da aplicação. Autorização já dada continua válida; a skill não deve pedir
novamente a mesma permissão. Um pedido de inventário/proposta não autoriza
publicar em serviços externos ou substituir um armazenamento ativo.

## 4. Mapear o acompanhamento anterior

Use a [referência de mapeamento da skill](../skills/backloger-adoption/references/mapping.md).
O agente deve produzir uma proposta no contrato `Backlog` contendo `project`,
`work_items`, `milestones`, `iterations` e `views`.

- Preserve IDs compatíveis com a chave do projeto; para os demais, crie um mapa
  estável. Mantenha `original_id` e `source_refs` em
  `extensions["backloger.migration"]`.
- Preserve estados humanos por configuração de projeto. Categorias são pending,
  active, done e cancelled. Cancelado/duplicado não deve virar entrega concluída.
- Prioridade admite critical/high/medium/low. P0/P1/P2 podem ser etiquetas ou um
  mapeamento documentado; não imponha equivalência universal entre ferramentas.
- Guarde a descrição integral, notas e critérios. Aceite atendido exige evidência
  declarada na origem; texto "testar" não comprova teste executado.
- Remapeie relações pelos novos IDs. Uma referência entre projetos ainda não é
  uma dependência executável. Preserve-a e declare a limitação, sem ocultar um
  bloqueio relevante no relatório de reconciliação.
- Use prazos reais e unidades conhecidas. Não converta pontos em horas/dias nem
  invente responsáveis, duração ou data de término.

Datas com horário precisam de fuso. Se ambas as datas de um card forem
inexistentes, o helper usa o instante de importação e registra essa origem;
isso não representa a idade do item. Se só uma existir, resolva a outra com
regra documentada antes de continuar. Notas sem data ficam preservadas em
metadados/descrição; não recebem uma data histórica fictícia.

Bloqueios sem um pré-requisito identificado podem ser preservados em estado,
etiqueta e motivo explícitos; eles não entram na contagem de bloqueios do grafo.
Registre essa diferença e não considere a lista de itens sem dependência como
autorização automática para iniciar trabalho.

Histórico conhecido pode ir para `history`, atribuído à origem. Autoria e campos
legados que não existem nesse contrato ficam nas extensões do item/projeto.
**Não gere `.runtime/audit` artificial:** comentários e timestamps de edição não
reconstituem throughput ou burndown diário. Arquive os gráficos antigos como
evidência e declare a continuidade/ruptura das métricas.

## 5. Ensaiar com um exemplo completo

O pacote inclui fontes fictícias em [examples/migration](../examples/migration):
um CSV e um Markdown descrevem os mesmos três itens; a proposta JSON demonstra
a reconciliação. Não use essa proposta como dados do seu projeto real.

```sh
"$ADOPTION_PYTHON" \
  "$ADOPTION_PACKAGE/skills/backloger-adoption/scripts/stage_backlog.py" \
  --input "$ADOPTION_PACKAGE/examples/migration/proposal.json" \
  --output "$ADOPTION_WORK/example-candidate" \
  --storage split --expected-count 3 \
  --source "$ADOPTION_PACKAGE/examples/migration/legacy-backlog.md" \
  --source "$ADOPTION_PACKAGE/examples/migration/legacy-status.csv"

"$ADOPTION_CLI" --project "$ADOPTION_WORK/example-candidate" validate --strict
"$ADOPTION_CLI" --project "$ADOPTION_WORK/example-candidate" analyze
"$ADOPTION_CLI" --project "$ADOPTION_WORK/example-candidate" --read-only serve --port 8766
```

Abra `http://127.0.0.1:8766` para conferir quadro, grafo e documento. Pare com
Ctrl+C. O candidato contém `.backloger/`, `id-map.json`,
`migration-manifest.json` e `BACKLOG.md`. O manifesto informa contagens por
estado, revisão, hash da proposta/fontes e IDs que receberam data de importação.
`--storage single` gera `backlog.json` em vez da estrutura dividida.

## 6. Preparar e reconciliar a migração real

Peça à skill uma proposta `proposal.json` na pasta de trabalho. Execute o mesmo
helper com um novo destino, as fontes reais e a contagem reconciliada. Não há
parser universal de CSV/Markdown: a extração/mapeamento é trabalho do agente,
verificado pelo operador e pelo núcleo.

Antes da entrada em uso, confira:

1. Total de atividades únicas e distribuição por estado/prioridade; explique
   qualquer diferença em relação ao inventário, incluindo fusões/desdobramentos.
2. Mapa de IDs, preservação de descrições, responsáveis, etiquetas e referências.
3. Critérios e notas, inclusive os não datados; diferencie conclusão declarada de
   verificação técnica efetivamente executada.
4. Direção das dependências, referências externas, ciclos e itens isolados.
5. Marcos/iterações, prazos, estimativas e campos mantidos em extensões.
6. `validate --strict`, análise do grafo, prévia somente leitura e exportações.

Guarde o mapa de IDs; ele é a base para uma importação posterior sem duplicação.
Registre dúvidas e campos omitidos com justificativa. Se uma dúvida impedir
reconciliação de identidade, conclusão, prazo ou precedência, resolva-a antes de
apresentar a migração como completa. Falha do helper não altera as fontes nem
publica um candidato parcialmente validado como sucesso.

## 7. Entrar em uso em projeto ainda sem Backloger

Congele alterações nas fontes pelo tempo necessário à transferência e pare os
processos que escrevam no projeto. Compare os hashes atuais com o levantamento;
se mudaram, atualize a proposta e valide outro candidato. Se `backlog.json` já
existe com formato legado, preserve-o em local acordado, com suas referências
atualizadas, antes de ativar outro armazenamento na raiz. Não execute os dois
formatos juntos.

Defina `ADOPTION_CANDIDATE` para o candidato REAL revisado; não o exemplo fictício.
A transferência abaixo aceita somente um projeto sem armazenamento Backloger:

```sh
export ADOPTION_CANDIDATE="/caminho/candidato-real-revisado"
"$ADOPTION_PYTHON" - <<'PY'
import json
import os
from pathlib import Path
from backloger.filesystem import atomic_create
from backloger.repository import Repository
from backloger.schema import reject_unknown

source = Path(os.environ["ADOPTION_CANDIDATE"]).resolve()
target = Path(os.environ["ADOPTION_PROJECT"]).resolve()
if source == target or not target.is_dir():
    raise SystemExit("Projeto deve existir e ser diferente do candidato")
if any(path.exists() or path.is_symlink()
       for path in (target / ".backloger", target / "backlog.json")):
    raise SystemExit("Destino já tem armazenamento; não mesclar nem sobrescrever")
snapshot = Repository(source, read_only=True).snapshot()
reject_unknown(snapshot.backlog)
manifest = json.loads((source / "migration-manifest.json").read_text())
if snapshot.revision != manifest["revision"]:
    raise SystemExit("Candidato mudou após a validação; reconcilie novamente")
if snapshot.storage == "split":
    (target / ".backloger").mkdir()
    for relative, content in snapshot.raw.items():
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_create(destination, content)
else:
    atomic_create(target / "backlog.json", snapshot.raw["backlog.json"])
after = Repository(target, read_only=True).snapshot()
if after.revision != snapshot.revision:
    raise SystemExit("Revisão divergente após cópia; mantenha escritores parados e investigue")
print("Transferido e conferido:", len(after.backlog.work_items), "atividades")
PY

"$ADOPTION_CLI" --project "$ADOPTION_PROJECT" validate --strict
"$ADOPTION_CLI" --project "$ADOPTION_PROJECT" doctor
"$ADOPTION_CLI" --project "$ADOPTION_PROJECT" --read-only serve --port 8765
```

A cópia dividida exige destino ausente. Se o processo for interrompido durante a
cópia, o destino pode estar incompleto: mantenha o servidor parado, preserve o
que foi criado para investigação e siga a reversão. Não force uma mesclagem.
Depois da conferência somente leitura, pare esse servidor e inicie `serve` sem
`--read-only` para habilitar edição. A revisão exata confirma os bytes canônicos,
mas não substitui a revisão semântica dos dados.

Preserve `id-map.json`, manifesto, inventário e decisões em um diretório de
migrações do projeto, com nome único, ou em seu sistema de evidências. Não copie
arquivos sobre registros de migração anteriores. Mantenha as fontes antigas
identificadas como arquivo histórico ou com um apontador para a nova fonte,
conforme o fluxo autorizado pelo time.

## 8. Quando o projeto já usa Backloger

Não copie o armazenamento inteiro do candidato sobre o projeto ativo. Faça
reconciliação incremental usando o mapa e as referências de origem:

- Origem já mapeada: consultar o card e comparar mudanças antes de atualizar.
- Origem nova: criar uma atividade e registrar seu novo ID no mapa.
- Item removido da origem: registrar a decisão; não apagar automaticamente.
- Estado/marco novo: preparar a configuração válida antes de introduzir referências.

```sh
"$ADOPTION_CLI" --project "$ADOPTION_PROJECT" show SYS-001
"$ADOPTION_CLI" --project "$ADOPTION_PROJECT" update SYS-001 \
  --file /caminho/alteracao-reconciliada.json --version 4 --revision SHA_LIDO
```

Substitua ID, versão e revisão pelos valores efetivamente lidos. O JSON parcial
pode conter descrição, status, etiquetas, critérios, extensões e `history_note`.
Preserve as extensões existentes ao editar esse objeto. `history` não é editável
por esse comando; conserve o histórico e acrescente notas importadas por
`history_note`, guardando os registros originais completos nas extensões/fontes.
Um 409 ou código 3 exige releitura e reconciliação, sem repetir com valores
antigos. Mapeamento estável evita duplicação em novas rodadas.

A API atual não oferece edição de configuração de estados/marcos nem importação
em lote. Mudanças desses arquivos exigem preparação explícita, backup, janela
sem escritores e validação do snapshot completo. Não use uma substituição em
massa como atalho para contornar versões e histórico.

## 9. Git, fonte canônica e relatórios

Mescle regras específicas ao `.gitignore` existente; não substitua as regras da
aplicação pelo arquivo completo do Backloger. No mínimo:

```gitignore
**/.backloger/.runtime/
backloger-reports/
.venv/
.env
```

Versione `.backloger/project.json`, `work-items/*.json`, marcos, iterações e
visões, ou `backlog.json` no modo único, além da skill quando adotada pelo time.
O campo `history` faz parte desses JSONs. `.runtime` contém auditoria, backups e
diários operacionais; mantenha backup externo, sem colocá-lo no Git.

```sh
git check-ignore -v .backloger/project.json .backloger/work-items/SYS-001.json
git status --short
```

Os JSONs canônicos não devem aparecer na saída de `check-ignore`; o código 1
sem saída significa que não estão ignorados. Ignore não retira arquivos já
rastreados: se `.runtime` foi commitado, revise sua retirada do índice usando o
caminho exato, preservando os arquivos locais. Não execute um `git rm` amplo em
`.backloger`.

Comece com relatórios em um destino novo, para não sobrescrever o Markdown
legado usado como origem:

```sh
"$ADOPTION_CLI" --project "$ADOPTION_PROJECT" export markdown --output backloger-reports/BACKLOG.md
"$ADOPTION_CLI" --project "$ADOPTION_PROJECT" export html --output backloger-reports/BACKLOG.html
"$ADOPTION_CLI" --project "$ADOPTION_PROJECT" export pdf --output backloger-reports/BACKLOG.pdf
```

Saídas são relativas ao diretório atual, não ao valor de `--project`. Defina se
o relatório gerado deve entrar no Git. Só adote `docs/BACKLOG.md` como destino
após resolver o papel do arquivo antigo. Revise o diff; commit e push seguem a
autorização e o fluxo do projeto.

Para CI, incorpore o [exemplo de workflow](../examples/github-actions/reports.yml)
sem substituir jobs existentes. Veja [GITHUB_ACTION.md](GITHUB_ACTION.md) e fixe
o endereço/SHA real da action após publicação. `formats: markdown` é o padrão;
`markdown,html,pdf` inclui PDF. A instância central, autenticação multiusuário e
sincronização de issues não são requisitos para gerar relatórios em CI.

## 10. Rotina de acompanhamento

| Frequência / evento | Procedimento |
| --- | --- |
| Uso diário | Abrir dashboard, revisar bloqueios/vencimentos e próximas ações |
| Iniciar ou revisar trabalho | Mover o card, revisar descrição e critérios; registrar nota de andamento |
| Encerrar uma atividade | Conferir aceite e evidência; mudar para estado de categoria done |
| Alterar JSON no editor | Preservar contrato, versão/histórico; validar e observar atualização da interface |
| Atualização concorrente | Reconciliar o conflito; manter os dados do formulário até decidir |
| Revisão de entrega | Conferir marcos/iterações e exportar o relatório gerencial |
| Nova importação | Reusar mapa, comparar fontes e atualizar incrementalmente |
| Backup/manutenção | Preservar canônicos e .runtime; acompanhar espaço e volume de auditoria |

No editor do card, **Nota de andamento** acrescenta contexto sem apagar notas
anteriores. Para burndown com referência ideal de iteração, configure
`start_date`, `due_date` e registre checkpoints reais durante o período.
O primeiro dia não recria o passado do projeto. Detalhes de métricas e operação
estão em [REPORTS.md](REPORTS.md) e [OPERATIONS.md](OPERATIONS.md).

## 11. Falhas e reversão

| Situação | Ação |
| --- | --- |
| Contrato, estado ou referência inválida | Corrigir proposta; gerar novo candidato, sem tocar no ativo |
| Ciclo ou referência externa não resolvida | Reconciliar sem apagar relações silenciosamente |
| Contagem divergente | Revisar identidade, duplicação, critérios e itens descartados |
| Fonte mudou depois do inventário | Reconciliar a nova versão e atualizar hashes |
| Destino já existe | Parar; não usar opções de sobrescrita/mesclagem |
| PDF indisponível | Conferir Pango e limites; preservar Markdown/HTML para revisão |
| Transação pendente | Usar doctor/recover conforme operação; preservar diário e backup |
| Validação pós-transferência falhou | Manter escritores parados, preservar destino e restaurar referência anterior |

Na primeira adoção, se for necessário voltar ao acompanhamento anterior, pare
os escritores e preserve o novo armazenamento completo em uma pasta de rollback
com nome único, fora do local ativo. Restaure as fontes anteriores do backup
verificado e confirme sua operação. Não apague o candidato nem a evidência.

Se houve novas alterações após a entrada em uso, preserve-as e faça uma
reconciliação antes da reversão. Em projeto Backloger já ativo, use backups e
restauração por atividade/versão; não faça `git reset --hard` ou exclusão ampla
para tentar desfazer a migração. Procedimentos de recuperação estão em
[OPERATIONS.md](OPERATIONS.md).

## 12. Registro de conclusão

Registre versão do Backloger, projeto/chave, fontes/hashes, contagens antes/depois,
mapa de IDs, estados e prioridades, tratamento de datas/histórico, exceções
aceitas, validações executadas, relatórios gerados, localização do backup e como
reverter. Declare separadamente verificações pendentes de navegador, Docker ou
CI remota. A instalação da skill não significa que um projeto externo já foi
migrado; só relate como aplicada a transferência que realmente ocorreu.
