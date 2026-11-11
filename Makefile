SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
PYTHON ?= .venv/bin/python
PIP_FLAGS ?=
PROJECT ?= .
PORT ?= 8765
export BACKLOGER_PROJECT := $(abspath $(PROJECT))
export LOCAL_UID := $(shell id -u)
export LOCAL_GID := $(shell id -g)
export PYTEST_DISABLE_PLUGIN_AUTOLOAD := 1
COMPOSE := docker compose -f compose.yaml

.PHONY: install install-dev build package lint format typecheck test test-unit test-integration test-e2e test-security test-ui coverage check validate serve export-md graph doctor docker-build docker-up docker-down docker-restart docker-logs docker-ps docker-config security-scan sbom clean help schemas test-docker
.PHONY: export-pdf

.venv/bin/python:
	python3 -m venv .venv

install: .venv/bin/python ## Instalar o pacote no ambiente virtual
	$(PYTHON) -m pip install $(PIP_FLAGS) -e .

install-dev: install ## Instalar dependências de desenvolvimento
	$(PYTHON) scripts/install_dev.py

build: ## Construir wheel e sdist
	$(PYTHON) -m hatchling build

package: build sbom ## Gerar wheel, fonte, ZIP de instalação, SBOM e checksums
	$(PYTHON) scripts/package_release.py

lint: ## Verificar Python e sintaxe JavaScript
	$(PYTHON) -m ruff check src tests scripts skills
	$(PYTHON) -m ruff format --check src tests scripts skills
	$(PYTHON) scripts/check_assets.py

format: ## Formatar Python
	$(PYTHON) -m ruff check --fix src tests scripts skills
	$(PYTHON) -m ruff format src tests scripts skills

typecheck: ## Verificar tipagem estrita do núcleo e adaptadores
	$(PYTHON) -m mypy src/backloger

test: ## Executar testes sem navegador
	$(PYTHON) -m pytest -m 'not e2e'

test-unit: ## Testar domínio, contrato e grafos
	$(PYTHON) -m pytest -m unit

test-integration: ## Testar arquivos, concorrência, CLI e API
	$(PYTHON) -m pytest -m integration

test-e2e: ## Testar interface em Chromium (playwright install chromium)
	$(PYTHON) -m pytest -m e2e

test-ui: ## Testar gráficos e interações em DOM (npm install --ignore-scripts)
	mkdir -p .cache
	$(PYTHON) scripts/ui_fixture.py > .cache/ui-fixture.json
	node tests/ui/interface.test.cjs

test-security: ## Testar limites, escrita atômica e segurança HTTP
	$(PYTHON) -m pytest -m security

coverage: ## Gerar cobertura HTML e relatório
	$(PYTHON) -m pytest -p pytest_cov -m 'not e2e' --cov=backloger --cov-report=term-missing --cov-report=html

check: lint typecheck test validate ## Executar verificações locais

validate: ## Validar o backlog do projeto
	$(PYTHON) -m backloger --project "$(PROJECT)" validate --strict

schemas: ## Atualizar JSON Schemas oficiais
	$(PYTHON) -m backloger.schema

serve: ## Iniciar interface local
	$(PYTHON) -m backloger --project "$(PROJECT)" serve --port "$(PORT)"

export-md: ## Gerar docs/BACKLOG.md
	$(PYTHON) -m backloger --project "$(PROJECT)" export markdown --output docs/BACKLOG.md

export-pdf: ## Gerar dist/BACKLOG.pdf a partir do mesmo Markdown
	$(PYTHON) -m backloger --project "$(PROJECT)" export pdf --output dist/BACKLOG.pdf

graph: ## Gerar docs/graph.svg
	$(PYTHON) -m backloger --project "$(PROJECT)" graph --format svg --output docs/graph.svg

doctor: ## Diagnosticar projeto e ambiente
	$(PYTHON) -m backloger --project "$(PROJECT)" doctor

docker-build: ## Construir imagem OCI
	$(COMPOSE) build

docker-up: ## Subir aplicação (porta publicada apenas em loopback)
	$(COMPOSE) up --build -d

docker-down: ## Parar aplicação preservando os dados do projeto
	$(COMPOSE) down

docker-restart: ## Recriar aplicação e aplicar configuração atual
	$(COMPOSE) up -d --force-recreate

docker-logs: ## Exibir últimas 100 linhas de logs
	$(COMPOSE) logs --tail 100

docker-ps: ## Exibir estado dos serviços
	$(COMPOSE) ps

docker-config: ## Validar e exibir Compose resolvido
	$(COMPOSE) config --quiet
	$(COMPOSE) config

test-docker: ## Testar ciclo completo e volume somente leitura no Docker
	$(PYTHON) scripts/docker_smoke.py

security-scan: ## Consultar vulnerabilidades das dependências de runtime (requer rede)
	$(PYTHON) scripts/sbom.py
	$(PYTHON) -m pip_audit --cache-dir .cache/pip-audit --timeout 10 --no-deps --disable-pip -r dist/requirements-runtime.txt

sbom: ## Gerar inventário SPDX 2.3 das dependências de runtime
	$(PYTHON) scripts/sbom.py

clean: ## Remover apenas artefatos gerados (preserva dados e backups)
	$(PYTHON) scripts/clean.py

help: ## Listar alvos disponíveis
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "%-20s %s\n", $$1, $$2}' Makefile
