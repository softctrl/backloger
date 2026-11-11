# Contrato JSON 1.0.0

`schema_version` identifica o contrato; `version` é o contador de alterações de
uma atividade. Versões desconhecidas do contrato são rejeitadas. Os schemas em
[schemas/1.0.0](../schemas/1.0.0) são gerados dos modelos Pydantic (`make schemas`).

## Arquivos por atividade (padrão)

```text
.backloger/
  project.json
  work-items/SYS-001.json
  milestones.json
  iterations.json
  views.json
  .runtime/           # fora do Git, preservar para recuperação
    project.lock
    journal/
    backups/
    audit/
```

`project.json`: `schema_version`, `name`, `key`, `statuses`, `extensions`.
Os arquivos de milestones, iterações e visões contêm arrays JSON, inicialmente
vazios. Cada nome em `work-items/` deve coincidir com o ID da atividade.

## Arquivo único

`init --storage single` cria `backlog.json` na raiz:

```json
{
  "schema_version": "1.0.0",
  "project": {"name": "Meu Sistema", "key": "SYS"},
  "work_items": [],
  "milestones": [],
  "iterations": [],
  "views": []
}
```

Estados padrão são aplicados quando omitidos. A serialização produz o contrato
completo. `.backloger/.runtime` é criado na primeira mutação. Os dois formatos
não podem coexistir no mesmo projeto. Veja [examples](../examples).

## Campos e regras

Atividades: `id`, `title`, `description`, `type`, `status`, `priority`, `component`,
`owner`, `labels`, `milestone_id`, `iteration_id`, `due_date`, `estimate`,
`dependencies`, `acceptance_criteria`, `created_at`, `updated_at`, `version`,
`history`, `extensions` e `schema_version`.

- ID: chave maiúscula de 2 a 16 caracteres, hífen e número de 3 a 9 dígitos.
- Tipos: epic, feature, story, task, bug, maintenance, security, documentation,
  spike e incident.
- Prioridades: critical, high, medium, low. P0/P1/P2 classificam entregas do
  produto e são representados por etiquetas, sem criar valores alternativos.
- Estados: `id`, `name`, `category`, `wip_limit` opcional. Categorias: pending,
  active, done, cancelled. Deve existir pelo menos um estado pending.
- Timestamps exigem fuso horário; `due_date` usa YYYY-MM-DD.
- Estimativa: `unit` hours/days/points, `value` não negativo.
- Critério: `id`, `text`, `done`; IDs únicos por atividade.
- Milestone: `id`, `name`, `due_date` opcional. Iteração admite `start_date`.
- Visão salva: `id`, `name`, `filters` (mapa de valores textuais).

`blocked_by` cria aresta do alvo para a atividade; `blocks` cria aresta da
atividade para o alvo. `relates_to` e `child_of` validam referências sem impor
precedência. Itens isolados são informados e são válidos. Referências
inexistentes, ciclos de precedência, IDs duplicados e estados desconhecidos
rejeitam a operação inteira.

Campos desconhecidos nos arquivos são preservados, inclusive em estruturas
aninhadas. Integrações devem usar `extensions` com namespace próprio.
`validate --strict` rejeita campos desconhecidos fora de `extensions`. DTOs
da API rejeitam propriedades extras e não permitem alterar ID, schema,
timestamps ou versão arbitrariamente.

Limites: 2.000 atividades, 10.000 relações, 100 dependências por atividade,
8 MiB por arquivo canônico e 32 MiB no projeto dividido. Descrições admitem
50.000 caracteres. O corpo HTTP admite 256 KiB, inclusive em chunks. JSON com
chaves duplicadas, NaN, Infinity ou UTF-8 inválido é rejeitado. Não se enumeram
todos os ciclos ou todos os caminhos de um grafo.

## Concorrência HTTP

1. `GET /api/v1/state` retorna `revision` e `ETag`: SHA-256 dos arquivos canônicos.
   `If-None-Match` permite resposta 304.
2. POST, PATCH e PUT exigem `X-Backloger-Token` da página local e `If-Match` com o
   ETag lido. PATCH exige também `expected_version`.
3. Revisão ou versão divergente retorna 409; If-Match ausente retorna 428.
   A interface preserva os campos abertos. Releia e revise antes de reaplicar.

O hash global é conservador: editar B pode invalidar uma edição aberta de A.
Isso protege referências e configurações que mudaram durante a edição.

## Histórico dos cards

`history` é um campo opcional de cada atividade. Arquivos existentes sem esse
campo continuam válidos. Cada registro tem `id`, `at` com fuso, `kind`
(created/updated/comment/restored), `text`, `version` e `changed_fields`.
A aplicação acrescenta registros de criação, mudanças e restaurações. Notas
de andamento são enviadas como `history_note` em CreateItem/UpdateItem, por
exemplo `{"expected_version": 2, "history_note": "Revisão concluída"}`.
`history` não é um campo editável diretamente pela API; notas passam pelo mesmo
controle de revisão/versão. Restaurações preservam as notas posteriores ao backup.

O histórico acompanha o JSON no Git e contém até 1.000 registros por card;
notas admitem 4.000 caracteres. Não há exclusão automática. Arquivos antigos não
recebem eventos retroativos inventados. O proprietário dos arquivos ainda pode
editá-los e revisá-los no Git; não se trata de um registro à prova de adulteração.

## Automação CLI

Opções globais precedem o comando: `backloger --project /repo --json list`.
`--project` encontra o projeto mais próximo nos ancestrais. `init` sempre usa o
diretório indicado. `move`, `update`, `restore` aceitam versão/revisão explícitas
para clientes que mantiveram uma leitura anterior. Mutações sempre comparam
novamente o snapshot sob bloqueio, mesmo sem opções explícitas.

Dados vão para stdout; erros para stderr. `--json` produz erros no formato
`{"error":"...","message":"..."}`. Exportações mantêm seu formato específico.
`--show-completion bash` gera autocompletar sem modificar o shell;
`--install-completion` é opt-in.

| Código | Significado |
| --- | --- |
| 0 | Sucesso |
| 1 | Dados inválidos, recurso ausente ou erro de I/O |
| 2 | Uso incorreto |
| 3 | Conflito de versão, revisão, WIP ou bloqueio |
| 4 | Modo somente leitura |

O wrapper Docker propaga o código do Compose. Não há telemetria ou rede
implícita nos comandos locais.
