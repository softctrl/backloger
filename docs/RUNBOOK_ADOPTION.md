# Instalar o Backloger e a skill

Você instala o comando e a skill. Depois, o agente integra o Backloger ao
projeto, importa o acompanhamento existente e passa a mantê-lo atualizado.

## 1. Instalar o comando

Requisitos: Python 3.12+ e [pipx](https://pipx.pypa.io/latest/how-to/install-pipx.html).
Extraia `backloger-0.1.0-install.zip`, entre na pasta extraída e execute:

```sh
pipx install --python python3 ./backloger-0.1.0-py3-none-any.whl
pipx ensurepath
```

Reabra o terminal e confirme:

```sh
backloger --version
```

Outras formas de instalação e os requisitos opcionais para PDF estão em
[INSTALL.md](../INSTALL.md).

## 2. Instalar a skill no projeto

Volte à pasta extraída do pacote e substitua `/caminho/projeto` pelo seu repositório:

```sh
mkdir -p /caminho/projeto/.agents/skills
cp -R skills/backloger-adoption /caminho/projeto/.agents/skills/
```

Copie a pasta inteira, incluindo referências, scripts e modelo de instruções.
Se a skill já estiver instalada, atualize essa mesma pasta.
Abra o projeto no Codex; se a skill não aparecer, reinicie a sessão.
A descoberta em `.agents/skills` segue as
[OpenAI Docs](https://learn.chatgpt.com/docs/build-skills).

## 3. Pedir a integração ao agente

No projeto, envie:

```text
Use $backloger-adoption para integrar o Backloger neste projeto,
importar os backlogs e acompanhamentos que já existem e configurar
as instruções do projeto para mantê-lo atualizado daqui para frente.
```

O agente deve importar as atividades preservando origem e histórico, validar o
backlog, gerar o relatório e registrar a rotina no `AGENTS.md`. Os detalhes de
migração ficam na skill; você não precisa executar etapas de conversão manual.

Nos próximos trabalhos, essa rotina orienta o agente a consultar e atualizar
cards, status, critérios, dependências e notas de andamento, além de regenerar
o relatório. Para reforçar a instrução em uma solicitação:

```text
Use $backloger-adoption e mantenha o backlog atualizado ao executar esta tarefa.
```

## Consultar o resultado

Dentro do projeto:

```sh
backloger list
backloger serve
```

Abra `http://127.0.0.1:8765` para ver o quadro, os gráficos e o documento.
