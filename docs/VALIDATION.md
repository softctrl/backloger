# Validação da fundação 0.1.0

## Evolução: instalação, gitignore e adoção em projetos existentes

`make check` aprovou **109 testes Python**, com 1 E2E de navegador fora dessa
execução, Ruff em 44 arquivos Python e Mypy strict em 21 módulos. Os novos casos
verificam conteúdo e integridade do ZIP, recusa de wheel adulterado antes da
criação de venv, exclusão de dados operacionais/credenciais do bundle e regras
de Git que preservam contratos, exemplos, documentação e arquivos de lock.

O wheel foi instalado com `pip --no-index --no-deps` em outro venv, usando
dependências locais copiadas/reutilizadas. O módulo carregado veio do
site-packages desse ambiente, fora do checkout. Foram exercitados init, add,
link, move, validate, exportações Markdown/HTML/PDF real e API em processo
(health, interface, documento, assets e schemas incluídos).

A tentativa de resolver todas as dependências em um venv limpo, com o cache
offline, parou porque FastAPI não estava disponível no cache. Portanto esse
smoke não comprova instalação limpa com resolução completa nem substitui a
homologação online. O instalador normal resolve dependências e executa pip check;
essa sequência completa aguarda um ambiente com índice/wheelhouse disponível.

A skill `backloger-adoption` passou no validador de estrutura da skill-creator.
Seu helper foi exercitado nos modos split/single, preservando origens, IDs,
notas datadas, critérios, relações e proveniência de datas de importação. Os
testes cobrem destinos existentes, ciclos, referências ausentes, contagem
divergente, datas parciais e metadados inválidos, sem publicar candidato inválido.

O exemplo fictício reconciliou três registros em CSV/Markdown. O procedimento
de transferência do runbook foi executado em um projeto temporário com README
e fonte existentes, preservou esses arquivos, conferiu a revisão canônica,
recusou repetição sobre o destino ativo e gerou os três formatos de relatório.
Nenhum projeto externo foi migrado nesta validação. Links locais foram conferidos.

`make package` gera wheel, fonte, ZIP com instalador/guias/skill/exemplos,
inventário SPDX e SHA256SUMS. O fonte contém `.gitignore`; dados `.runtime` ficam
fora dos artefatos. Não houve publicação ou assinatura; as pendências anteriores
de navegador real, Docker, CI remota e auditoria online continuam aplicáveis.

## Evolução: relatório gerencial completo

Foram aprovados **100 testes Python** sem navegador e **9 testes DOM**, com Ruff
e Mypy strict em 21 módulos. Os novos casos verificam indicadores com estados
personalizados, cancelamentos fora da conclusão, atrasos, deduplicação de
throughput, datas UTC, escopo completo, critérios de aceite, histórico, dados
ausentes, burndown com lacunas/ideal, metadados inválidos e tentativas de injeção
em descrições e gráficos. PDF real foi extraído e validado com conteúdo gerencial.

O documento do próprio Backloger foi gerado em Markdown, HTML e PDF. Resumo,
gráficos e fichas tiveram inspeção visual por rasterização do PDF. A prévia
recebeu atualização manual e o mesmo gerador alimenta CLI/API/action. As 20
descrições genéricas do backlog do produto foram substituídas por objetivo,
entrega disponível e pendências, com versionamento, backup e histórico do núcleo.
Os dados sem responsável, prazo ou estimativa continuam explicitamente ausentes.

Os testes DOM validam atualização do documento e download. As restrições de
navegador real, Docker e CI remota abaixo continuam aplicáveis. Não foi calculada
uma nova porcentagem de cobertura nesta evolução.

## Evolução: gráficos, documentos, histórico e action

Em 11/11/2026 foram aprovados **90 testes Python** sem navegador e **9 testes
DOM** de interface. Ruff e Mypy strict passaram em 18 módulos. A evolução inclui:

- Gráficos SVG com filtros, janelas de atividade e burndown com datas desconhecidas
  preservadas, baseline de iteração e checkpoints reais.
- Motor Cytoscape em modo headless nos testes DOM, com seleção, caminho crítico,
  layouts e preservação de pan/zoom durante atualização externa.
- Histórico canônico por card, notas, conflitos de revisão/versão e restauração
  preservando comentários posteriores ao backup.
- Markdown renderizado, HTML autocontido e PDF real, incluindo acentos, paginação,
  escaping, limites de renderização e operação em modo somente leitura.
- Runner da composite action testado com os três formatos, formatos opcionais,
  manifestos SHA-256, rejeição de entradas inseguras e integridade dos JSONs.

O PDF do próprio produto foi gerado, teve as 20 atividades verificadas por
extração de texto e passou por inspeção visual da primeira página. O pacote
inclui os novos assets e schemas. Os testes DOM usam JSDOM 29.1.1 e não substituem
homologação visual em navegador. A instalação npm ficou bloqueada por rede/cache;
os testes locais usaram a distribuição já instalada no ambiente.

O exemplo consumidor da action contém OWNER/BACKLOGER_REPO e FULL_COMMIT_SHA
intencionalmente pendentes de publicação. A execução remota e o upload de
artefatos no GitHub não foram executados nesta sessão. As restrições de Chromium,
Docker e auditoria online abaixo continuam aplicáveis. As referências da nova
action e da CI foram fixadas em SHAs de commits oficiais verificados.

## Validação anterior

Execução local em 11/11/2026, Linux, Python 3.14.10. Este relatório distingue
verificações executadas de testes preparados que dependem de outro ambiente.

## Aprovado

| Verificação | Evidência |
| --- | --- |
| pytest sem navegador | **66 testes aprovados**, 1 teste E2E excluído dessa execução |
| Cobertura Python | **90%**; relatório em htmlcov/ |
| Ruff | Lint e formatação aprovados para src/, tests/ e scripts/ |
| Mypy | Strict aprovado em 14 módulos Python; exceção NetworkX documentada |
| JSON Schema | Geração, validade Draft 2020-12 e comparação com arquivos versionados |
| Backlogs | Produto com 20 atividades e exemplos split/single validados |
| API e CLI | Criação, edição, links, ciclos, WIP, métricas, visões, relatórios e códigos de erro |
| Concorrência | Dois processos sobre o mesmo snapshot: uma gravação e um conflito |
| Integridade | Falhas antes/depois do replace, recuperação, backup, restauração e rejeição de payload corrompido |
| Edição externa | Conflito detectado mesmo sem incremento de version; campos desconhecidos preservados |
| Segurança | CSRF, Origin, Host, body cap, somente leitura, symlinks, escaping e proteção de exportação sobre dados canônicos |
| Assets | Sintaxe JavaScript e checksums das bibliotecas locais aprovados |
| UI em DOM simulado | Criação, edição, drag/drop, conflito preservando formulário, WIP, XSS em título, filtros, dashboard, tabela e roadmap |
| Distribuição | Wheel/sdist construídos, licença/assets/templates presentes e schemas incluídos no wheel |
| Wheel instalado | Instalação sem dependências de rede em outro venv com dependências locais; CLI, schemas e criação da API aprovados |
| SBOM | SPDX 2.3 com 24 pacotes runtime; ferramentas dev excluídas |
| Compose | Configuração normal, override dev e modo somente leitura resolvidos; app/volume ro e bind 127.0.0.1 conferidos |
| Make | Todos os alvos requeridos resolvidos em dry-run; lint, typecheck, testes, coverage, build/package, validate, export-md, graph, doctor, sbom, docker-config e help executados |
| Instalação dev | Alvo install-dev executado offline com dependências disponíveis localmente e PIP_FLAGS=--no-build-isolation |
| Clean | Alvo executado em fixture temporária, preservando JSON, backups, docs e venv |

`make check` foi aprovado com 64 testes antes da inclusão de duas verificações
de backup corrompido (uma por formato). Após essa inclusão, lint, typecheck e
validate passaram novamente e `make coverage` aprovou os 66 testes. O teste DOM
foi ad hoc com JSDOM local; não representa inspeção visual nem navegador real.

## Pendente por restrições do ambiente

| Verificação | Resultado efetivo |
| --- | --- |
| Teste Playwright em Chrome | Processo interrompido pelo sandbox: setsockopt, Operation not permitted |
| Fallback Chromium headless | Processo interrompido: shutdown, Operation not permitted |
| Docker build/up/smoke | Acesso negado ao socket /var/run/docker.sock; configuração sintática aprovada, execução em container não homologada |
| Auditoria de vulnerabilidades | pip-audit iniciou e falhou ao resolver pypi.org; não existe resultado de segurança de dependências |
| Instalação limpa online/lock | Resolver remoto bloqueado por DNS; ambiente local foi montado com pacotes do sistema/cache |
| CI remota/Python 3.12 | Workflow preparado, sem execução remota nesta sessão |

Os testes de navegador e Compose permanecem habilitados, sem skip que transforme
falhas do ambiente em sucesso. `make test-e2e`, `make test-docker` e
`make security-scan` precisam passar num host com os recursos necessários antes
de homologar a primeira versão. A CI inclui essas etapas.

## Escopo ainda aberto

BKL-009/010/011 permanecem em andamento até validação real da interface.
BKL-013 aguarda execução em Docker. BKL-014 inclui homologação da CI, auditoria
online, lock com hashes e fixação de imagens/actions por digest/SHA. Autenticação,
integrações, plugins, centralização e dependências entre projetos são P1/P2.

Limites de concorrência com editores que ignoram locks, suporte de filesystem
e comportamento histórico estão detalhados em [ARCHITECTURE.md](ARCHITECTURE.md).
Prazos e janelas de métricas são avaliados em UTC nesta versão.
