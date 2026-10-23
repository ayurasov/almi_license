# Makefile — targets from section 5 of docs/specs/07-environments.md.
# Targets without code yet print "not implemented" and exit 0 (E00-05);
# they are filled in by later stories (see comments next to each target).

.DEFAULT_GOAL := help

# Server commands need DATABASE_URL (PostgreSQL 17); DEPLOYMENT_MODE defaults to central.
export DEPLOYMENT_MODE ?= central
SERVER := uv run --project server

COMPOSE := docker compose -f deploy/dev/docker-compose.yml

# DL module: dependencies come from vcpkg (set VCPKG_ROOT); extra configure options via DL_CMAKE_ARGS.
DL_BUILD ?= sdk/cpp/build
DL_CONFIG ?= Debug
DL_CMAKE_ARGS ?=
CLANG_FORMAT := uvx clang-format==23.1.3
DL_FORMAT_SOURCES = $(shell git ls-files -co --exclude-standard 'sdk/cpp/*.cpp' 'sdk/cpp/*.h')
DL_TIDY_SOURCES = $(shell git ls-files -co --exclude-standard 'sdk/cpp/src/*.cpp')

define not_implemented
	@echo "$@: not implemented"
endef

.PHONY: help up down up-local seed test test-server test-console test-dl test-keytool dl-configure lint lint-server lint-dl lint-keytool \
	contract-check vectors cross-verify e2e bundle-airgap

help: ## Show available targets
	@grep -hE '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  %-16s %s\n", $$1, $$2}'

up: ## Start the dev environment (DEPLOYMENT_MODE=central): http://localhost:8080
	$(COMPOSE) up -d --build --wait --wait-timeout 120
	@echo "DEPLOYMENT_MODE=$(DEPLOYMENT_MODE); gateway http://localhost:8080, console http://localhost:5173"

down: ## Stop the dev environment (data volume is kept)
	$(COMPOSE) down

up-local: ## Start the dev environment with DEPLOYMENT_MODE=local
	$(MAKE) up DEPLOYMENT_MODE=local

seed: ## Apply migrations and load the seed-minimal data set
	$(COMPOSE) exec -T api python manage.py migrate --noinput
	@echo "seed-minimal: not implemented (data set comes with the data model, I1-03)"

test: test-server test-console test-dl test-keytool ## Run all tests

test-server: ## Server tests (pytest)
	$(SERVER) pytest server

test-console: ## Console tests (vitest) — I2-07
	$(not_implemented)

test-dl: dl-configure ## DL module build and tests (ctest)
	cmake --build $(DL_BUILD) --config $(DL_CONFIG)
	ctest --test-dir $(DL_BUILD) -C $(DL_CONFIG) --output-on-failure

test-keytool: ## almi-keytool tests (pytest)
	cd tools/almi-keytool && uv run --locked pytest

dl-configure:
	cmake -S sdk/cpp -B $(DL_BUILD) -DCMAKE_BUILD_TYPE=$(DL_CONFIG) -DCMAKE_EXPORT_COMPILE_COMMANDS=ON $(DL_CMAKE_ARGS)

lint: lint-server lint-dl lint-keytool ## All linters: ruff, mypy, import-linter, eslint, vue-tsc, clang-format, clang-tidy
	@echo "lint-console (eslint, vue-tsc): not implemented"

# mypy loads Django settings (django-stubs); the database is not contacted, so a
# placeholder DATABASE_URL is enough when none is set.
lint-server: ## Server linters: ruff, mypy, import-linter
	cd server && export DATABASE_URL="$${DATABASE_URL:-postgres://localhost/lint}" && \
		uv run ruff check . && \
		uv run ruff format --check . && \
		uv run mypy . && \
		uv run lint-imports

lint-dl: dl-configure ## DL linters: clang-format, clang-tidy (needs compile_commands.json)
	$(CLANG_FORMAT) --dry-run --Werror $(DL_FORMAT_SOURCES)
	clang-tidy -p $(DL_BUILD) --quiet $(DL_TIDY_SOURCES)

lint-keytool: ## almi-keytool linters: ruff, mypy --strict
	cd tools/almi-keytool && uv run --locked ruff check . && uv run --locked ruff format --check . && \
		uv run --locked mypy src tests

contract-check: ## Contract: OpenAPI validity, JSON Schemas, their examples, docs/specs/02 examples
	uvx --from openapi-spec-validator==0.9.0 openapi-spec-validator contracts/openapi-product-api-v1.yaml
	uv run --locked --script tools/contract_check.py
	@echo "comparison with drf-spectacular: not implemented (comes with Product API endpoints)"

vectors: ## Reference vectors: up to date and valid; server and DL runners come with E02-03, E04-01, E13-02
	uv run --locked --script tools/vectors/generate.py --check
	@echo "vectors on the server and in DL: not implemented (E02-03, E04-01, E13-02)"

# Leases signed by the server (issue_jws) are written in the contracts/vectors/jws format and
# checked by the two independent verifiers: almi-keytool (PyNaCl) and LeaseVerifier (libsodium).
ISSUED_VECTORS ?= $(abspath $(DL_BUILD))/issued-vectors
cross-verify: ## Server-issued JWS pass almi-keytool and the DL LeaseVerifier (E02-03); needs make test-dl first
	rm -rf $(ISSUED_VECTORS) && mkdir -p $(ISSUED_VECTORS)
	cd server && export DATABASE_URL="$${DATABASE_URL:-postgres://localhost/unused}" && \
		ALMI_ISSUED_VECTORS_DIR=$(ISSUED_VECTORS) uv run pytest -q -p no:cacheprovider \
		apps/signing/tests/test_issue_jws.py -k cross_verification
	test -n "$$(ls $(ISSUED_VECTORS)/*.json)"
	cd tools/almi-keytool && ALMI_ISSUED_VECTORS_DIR=$(ISSUED_VECTORS) uv run --locked pytest -q \
		tests/test_vectors.py -k issued
	ALMI_ISSUED_VECTORS_DIR=$(ISSUED_VECTORS) $(DL_BUILD)/bin/lm_tests --gtest_filter='Issued/*'

e2e: ## Playwright and API scenarios against dev — E16-04
	$(not_implemented)

bundle-airgap: ## Build the air-gapped bundle locally — E15-04
	$(not_implemented)
