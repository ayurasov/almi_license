# Makefile — targets from section 5 of docs/specs/07-environments.md.
# Targets without code yet print "not implemented" and exit 0 (E00-05);
# they are filled in by later stories (see comments next to each target).

.DEFAULT_GOAL := help

define not_implemented
	@echo "$@: not implemented"
endef

.PHONY: help up down up-local seed test test-server test-console test-dl lint \
	contract-check vectors e2e bundle-airgap

help: ## Show available targets
	@grep -hE '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  %-16s %s\n", $$1, $$2}'

up: ## Start the dev environment (DEPLOYMENT_MODE=central) — E00-07
	$(not_implemented)

down: ## Stop the dev environment — E00-07
	$(not_implemented)

up-local: ## Start the dev environment with DEPLOYMENT_MODE=local — E00-07
	$(not_implemented)

seed: ## Apply migrations and load the seed-minimal data set — E00-07
	$(not_implemented)

test: test-server test-console test-dl ## Run all tests

test-server: ## Server tests (pytest) — I0-02
	$(not_implemented)

test-console: ## Console tests (vitest) — I2-07
	$(not_implemented)

test-dl: ## DL module tests (ctest) — I0-04
	$(not_implemented)

lint: ## All linters: ruff, mypy, eslint, vue-tsc, clang-tidy — I0-02, I0-04, I2-07
	$(not_implemented)

contract-check: ## Compare the implemented OpenAPI with contracts/ — I0-03
	$(not_implemented)

vectors: ## Run reference vectors on the server and in DL — E00-04
	$(not_implemented)

e2e: ## Playwright and API scenarios against dev — E16-04
	$(not_implemented)

bundle-airgap: ## Build the air-gapped bundle locally — E15-04
	$(not_implemented)
