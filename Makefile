.PHONY: gen-env test test-cov test-verbose test-parser parser gen-all help install-parser uv-sync test-api test-cli test-all build-package run-init run-update run-list run-search run-info run-pull run-deploy run-upgrade build lint lint-fix format run-deploy-recommends run-init-force run-help run-completion run-install-completion

PYTHON_VERSION := 3.11

## Show this help message
help:
	@echo "Available targets:"; echo; \
	awk '/^##/{desc=substr($$0,4); getline; if(/^[a-z-]+:/){target=substr($$1,1,length($$1)-1); printf "  %-20s %s\n", target, desc}}' Makefile

## Generate .env.template files
gen-env:
	@echo "Generating .env.template files..."
	@cd 00.homestack && .venv/bin/python3 -c "import sys; sys.path.insert(0, 'src'); from server.generate_env_template import create_template_files; create_template_files('$(CURDIR)')"
	@echo ".env.template files generated successfully."

## Install homestack parser dependencies (requires uv)
install-parser:
	@echo "Installing parser dependencies..."
	@cd 00.homestack && uv python install $(PYTHON_VERSION)
	@cd 00.homestack && uv venv --python $(PYTHON_VERSION) --clear .venv
	@cd 00.homestack && uv sync --extra dev --python $(PYTHON_VERSION)
	@echo "Parser dependencies installed successfully."

## Sync all project dependencies with uv
uv-sync:
	@echo "Syncing dependencies with uv..."
	@cd 00.homestack && uv python install $(PYTHON_VERSION)
	@cd 00.homestack && uv venv --python $(PYTHON_VERSION) --clear .venv
	@cd 00.homestack && uv sync --extra dev --python $(PYTHON_VERSION)
	@echo "Dependency sync completed."

## Run parser tests
test: gen-all
	@echo "Running parser tests..."
	@cd 00.homestack && .venv/bin/pytest tests/ -q
	@echo "Tests completed."

## Run parser tests with verbose output
test-verbose:
	@echo "Running parser tests (verbose)..."
	@cd 00.homestack && .venv/bin/pytest tests/ -v

## Run parser tests with coverage report
test-cov:
	@echo "Running parser tests with coverage..."
	@cd 00.homestack && .venv/bin/pytest tests/ --cov=src --cov-report=term-missing

## Alias for 'test'
test-parser: test

## Run API client tests
test-api:
	@echo "Running API client tests..."
	@cd 00.homestack && .venv/bin/pytest tests/test_api_client.py -q

## Run CLI and orchestration tests
test-cli:
	@echo "Running CLI related tests..."
	@cd 00.homestack && .venv/bin/pytest tests/test_questionary.py -q

## Run full test suite
test-all:
	@echo "Running full test suite..."
	@cd 00.homestack && .venv/bin/pytest tests/ -q

## Run parser on all project readmes and generate JSON metadata
parser:
	@echo "Parsing readme files and generating metadata..."
	@cd 00.homestack && .venv/bin/python3 -c "import sys; sys.path.insert(0, 'src'); from server.main import generate_all; payload = generate_all('$(CURDIR)'); print(f'✓ Generated env={len(payload[\"env\"])}, projects={len(payload[\"projects\"])}, meta={len(payload[\"meta\"])})')"

## Generate env templates + run parser
gen-all: gen-env parser
	@echo "✓ All generation tasks completed."

## Build package artifacts
build-package: 
	@echo "Building homestack package..."
	@rm -rf 00.homestack/dist
	@cd 00.homestack && uv build

## Build the whole project (format, sync dependencies, generate env templates, run parser, build package)
build: format uv-sync gen-all test build-package
	@echo "✓ Build completed successfully."

## Run linting with ruff
lint:
	@echo "Running ruff linting..."
	@cd 00.homestack && uvx ruff check src tests
	@echo "Linting completed."

## Fix linting issues with ruff
lint-fix: 
	@echo "Running ruff linting with auto-fix..."
	@cd 00.homestack && uvx ruff check src tests --fix
	@echo "Linting auto-fix completed."

## Run lint format with ruff
format: lint-fix
	@echo "Running ruff format..."
	@cd 00.homestack && uvx ruff format src tests
	@echo "Formatting completed."

## Run homestack init
run-init:
	@cd 00.homestack && .venv/bin/homestack init

## Run homestack init with --force
run-init-force:
	@cd 00.homestack && .venv/bin/homestack init --force

## Run homestack update
run-update:
	@cd 00.homestack && .venv/bin/homestack update

## Run homestack list
run-list:
	@cd 00.homestack && .venv/bin/homestack list

## Run homestack search, pass PROJECT=<name_or_keyword>
run-search:
	@if [ -z "$(PROJECT)" ]; then echo "Usage: make run-search PROJECT=<name_or_keyword>"; exit 1; fi
	@cd 00.homestack && .venv/bin/homestack search $(PROJECT)

## Run homestack info, pass PROJECT=<name>
run-info:
	@if [ -z "$(PROJECT)" ]; then echo "Usage: make run-info PROJECT=<project_name>"; exit 1; fi
	@cd 00.homestack && .venv/bin/homestack info $(PROJECT)

## Run homestack pull, pass PROJECT=<name>
run-pull:
	@if [ -z "$(PROJECT)" ]; then echo "Usage: make run-pull PROJECT=<project_name>"; exit 1; fi
	@cd 00.homestack && .venv/bin/homestack pull $(PROJECT)

## Run homestack deploy, pass PROJECT=<name>
run-deploy:
	@if [ -z "$(PROJECT)" ]; then echo "Usage: make run-deploy PROJECT=<project_name>"; exit 1; fi
	@cd 00.homestack && .venv/bin/homestack deploy $(PROJECT)

## Run homestack deploy --use-recommends, pass PROJECT=<name>
run-deploy-recommends:
	@if [ -z "$(PROJECT)" ]; then echo "Usage: make run-deploy-recommends PROJECT=<project_name>"; exit 1; fi
	@cd 00.homestack && .venv/bin/homestack deploy $(PROJECT) --use-recommends


## Run homestack upgrade, pass PROJECT=<name>
run-upgrade:
	@if [ -z "$(PROJECT)" ]; then echo "Usage: make run-upgrade PROJECT=<project_name>"; exit 1; fi
	@cd 00.homestack && .venv/bin/homestack upgrade $(PROJECT)

## Run homestack --help
run-help:
	@cd 00.homestack && .venv/bin/homestack --help

## Run homestack --show-completion
run-completion:
	@cd 00.homestack && .venv/bin/homestack --show-completion

## Run homestack --install-completion
run-install-completion:
	@cd 00.homestack && .venv/bin/homestack --install-completion