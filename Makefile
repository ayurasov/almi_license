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
DRILL_DIR ?= $(CURDIR)/.drill
POSTGRES_IMAGE ?= postgres:17
BUNDLE_DIR ?= $(CURDIR)/dist
DL_CONFIG ?= Debug
DL_CMAKE_ARGS ?=
CLANG_FORMAT := uvx clang-format==23.1.3
DL_FORMAT_SOURCES = $(shell git ls-files -co --exclude-standard 'sdk/cpp/*.cpp' 'sdk/cpp/*.h')
# The Windows platform file needs Windows headers: clang-tidy checks it only in a Windows build.
DL_TIDY_SOURCES = $(shell git ls-files -co --exclude-standard 'sdk/cpp/src/*.cpp' ':!sdk/cpp/src/platform/win/*')

define not_implemented
	@echo "$@: not implemented"
endef

PHONY_OPS = backup-drill
.PHONY: $(PHONY_OPS) help up down up-local up-pair seed test test-server test-compat test-console test-dl coverage-dl test-keytool dl-configure lint lint-server lint-dl lint-keytool lint-console \
	contract-check vectors cross-verify offline-e2e admin-schema e2e bundle-airgap

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

up-pair: ## Central server plus a local server (profile local, API http://localhost:8090) — E09
	$(COMPOSE) --profile local up -d --build --wait --wait-timeout 180
	@echo "central http://localhost:8080; local server API http://localhost:8090 (wizard: central http://api:8000)"

seed: ## Apply migrations and load the initial catalog (fixtures/catalog-v1.json)
	$(COMPOSE) exec -T api python manage.py migrate --noinput
	$(COMPOSE) exec -T api python manage.py loadcatalog

test: test-server test-console test-dl test-keytool ## Run all tests

test-server: ## Server tests (pytest); policy coverage >= 95 % (prompt I2-02)
	cd server && uv run pytest --cov --cov-report= && \
		uv run coverage report --include='apps/policy/*' --fail-under=95

test-compat: ## Compatibility tests of the compat adapters against tests/compat fixtures (E11-04; also part of test-server)
	cd server && uv run pytest tests/compat

test-console: ## Console tests (vitest)
	cd console && npm run test

test-dl: dl-configure ## DL module build and tests (ctest)
	cmake --build $(DL_BUILD) --config $(DL_CONFIG)
	ctest --test-dir $(DL_BUILD) -C $(DL_CONFIG) --output-on-failure

test-keytool: ## almi-keytool tests (pytest)
	cd tools/almi-keytool && uv run --locked pytest

coverage-dl: ## DL line coverage of LeaseVerifier, StateEvaluator, TrialTracker >= 90 % (E13-12; GCC)
	cmake -S sdk/cpp -B $(DL_BUILD)-coverage -DCMAKE_BUILD_TYPE=Debug -DLM_COVERAGE=ON $(DL_CMAKE_ARGS)
	cmake --build $(DL_BUILD)-coverage --parallel --target lm_tests
	find $(DL_BUILD)-coverage -name '*.gcda' -delete
	ctest --test-dir $(DL_BUILD)-coverage --output-on-failure
	python3 tools/dl_coverage.py $(DL_BUILD)-coverage --min 90

dl-configure:
	cmake -S sdk/cpp -B $(DL_BUILD) -DCMAKE_BUILD_TYPE=$(DL_CONFIG) -DCMAKE_EXPORT_COMPILE_COMMANDS=ON $(DL_CMAKE_ARGS)

lint: lint-server lint-dl lint-keytool lint-console ## All linters: ruff, mypy, import-linter, eslint, vue-tsc, clang-format, clang-tidy

lint-console: ## Console linters: eslint, vue-tsc
	cd console && npm run lint

# The console client is generated from the Admin API schema (prompt I2-07); CI checks that the
# committed schema and types match the server.
admin-schema: ## Admin API schema -> console/src/api/admin-api.yaml and generated TypeScript types
	cd server && DATABASE_URL="$${DATABASE_URL:-postgres://localhost/unused}" uv run python manage.py \
		spectacular --urlconf apps.api_admin.api.schema_urls --validate --fail-on-warn \
		--file ../console/src/api/admin-api.yaml
	cd console && npm run gen:api

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
offline-e2e: ## lm-demo (dev trust root) and the server: .alk-req -> .alk-lic -> apply, release (E08-01, E13-09); needs DATABASE_URL
	cmake -S sdk/cpp -B $(DL_BUILD)-dev -DCMAKE_BUILD_TYPE=Release -DLM_TRUST_ROOTS=dev -DLM_BUILD_TESTS=OFF $(DL_CMAKE_ARGS)
	cmake --build $(DL_BUILD)-dev --parallel --target lm-demo
	cd server && LM_DEMO=$(abspath $(DL_BUILD)-dev)/bin/lm-demo uv run pytest -q -p no:cacheprovider \
		tests/api_product/test_lm_demo_offline.py

cross-verify: ## Server-issued JWS pass almi-keytool and the DL LeaseVerifier (E02-03); needs make test-dl and DATABASE_URL
	rm -rf $(ISSUED_VECTORS) && mkdir -p $(ISSUED_VECTORS)
	cd server && ALMI_ISSUED_VECTORS_DIR=$(ISSUED_VECTORS) uv run pytest -q -p no:cacheprovider \
		apps/signing/tests/test_issue_jws.py tests/api_product/test_activate.py -k cross_verification
	test "$$(ls $(ISSUED_VECTORS)/*.json | wc -l)" -eq 3
	cd tools/almi-keytool && ALMI_ISSUED_VECTORS_DIR=$(ISSUED_VECTORS) uv run --locked pytest -q \
		tests/test_vectors.py -k issued
	ALMI_ISSUED_VECTORS_DIR=$(ISSUED_VECTORS) $(DL_BUILD)/bin/lm_tests --gtest_filter='Issued/*'

e2e: ## Playwright scenarios of the console against a local server (needs DATABASE_URL); API scenarios — E16-04
	cd console && npm run e2e

backup-drill: ## Backup, restore into almi_restore_drill, compare rows, verify the audit chain (E15-03); needs DATABASE_URL and Docker
	@test -n "$$DATABASE_URL" || { echo "DATABASE_URL is required"; exit 1; }
	mkdir -p $(DRILL_DIR) && head -c 32 /dev/urandom | base64 > $(DRILL_DIR)/passphrase && chmod 600 $(DRILL_DIR)/passphrase
	docker run --rm --network host --user $$(id -u):$$(id -g) -e HOME=/drill \
		-v $(CURDIR)/deploy/ops:/ops:ro -v $(DRILL_DIR):/drill \
		-e SOURCE_URL="$$DATABASE_URL" -e TARGET_URL="$${DATABASE_URL%/*}/almi_restore_drill" \
		-e BACKUP_DIR=/drill/backups -e BACKUP_PASSPHRASE_FILE=/drill/passphrase \
		$(POSTGRES_IMAGE) /ops/drill.sh
	cd server && DATABASE_URL="$${DATABASE_URL%/*}/almi_restore_drill" uv run python manage.py verify_audit
	rm -rf $(DRILL_DIR)

bundle-airgap: ## Bundle of a local server for a closed network (E15-04): VERSION=… TRUST_ROOTS=kid:pub
	tools/build_airgap_bundle.sh $(BUNDLE_DIR)

