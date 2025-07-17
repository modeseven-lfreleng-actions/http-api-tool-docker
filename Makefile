# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

.PHONY: help install install-test install-dev test test-cov lint format clean docker-build docker-run

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install-pdm: ## Install PDM package manager with caching
	pip install --cache-dir ~/.cache/pip pdm==2.24.2

install: ## Install dependencies using PDM
	pdm install

install-test: ## Install test dependencies using PDM
	pdm install -G test

install-dev: ## Install development dependencies using PDM
	pdm install -G dev -G test

test: install-test ## Run tests
	pdm run pytest tests/ -v

test-cov: install-test ## Run tests with coverage
	pdm run pytest tests/ --cov=http_api_tool --cov-report=html --cov-report=term

lint: ## Run linting checks
	pdm run pre-commit run --all-files

security-check: ## Check pip install commands for SHA hash pinning
	python3 scripts/check-pip-security.py

format: ## Format code
	pdm run pre-commit run --all-files ruff-format

clean: ## Clean build artifacts
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf coverage_html_report/
	rm -rf .coverage
	rm -rf bandit-report.json
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete

docker-build: ## Build Docker image with caching
	DOCKER_BUILDKIT=1 docker build \
		--cache-from http-api-tool:latest \
		--build-arg BUILDKIT_INLINE_CACHE=1 \
		-t http-api-tool .

docker-build-push: ## Build and push Docker image with registry caching
	DOCKER_BUILDKIT=1 docker build \
		--cache-from ghcr.io/$(shell echo $(GITHUB_REPOSITORY) | tr '[:upper:]' '[:lower:]'):latest \
		--cache-to type=registry,ref=ghcr.io/$(shell echo $(GITHUB_REPOSITORY) | tr '[:upper:]' '[:lower:]'):buildcache,mode=max \
		--build-arg BUILDKIT_INLINE_CACHE=1 \
		-t http-api-tool \
		-t ghcr.io/$(shell echo $(GITHUB_REPOSITORY) | tr '[:upper:]' '[:lower:]'):latest \
		--push .

docker-run: ## Run Docker container (example)
	docker run --rm http-api-tool \
		test \
		--url https://localhost:8080/get \
		--http-method GET \
		--expected-http-code 200 \
		--ca-bundle-path ./mkcert-ca.pem

setup-go-httpbin: ## Start local go-httpbin service for testing
	@echo "Starting go-httpbin service on https://localhost:8080..."
	@echo "Installing mkcert if not already installed..."
	@which mkcert > /dev/null || (echo "Installing mkcert..." && \
		if command -v brew > /dev/null 2>&1; then \
			brew install mkcert; \
		elif command -v apt-get > /dev/null 2>&1; then \
			sudo apt-get update && sudo apt-get install -y mkcert; \
		elif command -v pacman > /dev/null 2>&1; then \
			sudo pacman -S mkcert; \
		else \
			echo "Please install mkcert manually from https://github.com/FiloSottile/mkcert"; \
			exit 1; \
		fi)
	@echo "Setting up local CA and generating certificates..."
	@mkcert -install
	@mkcert -key-file /tmp/localhost-key.pem -cert-file /tmp/localhost-cert.pem localhost 127.0.0.1
	@mkdir -p /tmp/certs
	@cp /tmp/localhost-key.pem /tmp/certs/
	@cp /tmp/localhost-cert.pem /tmp/certs/
	@cp "$(shell mkcert -CAROOT)/rootCA.pem" ./mkcert-ca.pem
	@echo "CA certificate saved to ./mkcert-ca.pem"
	@docker run -d --name go-httpbin \
		-p 8080:8080 \
		-v /tmp/certs:/certs:ro \
		--rm \
		ghcr.io/mccutchen/go-httpbin:latest \
		-https-addr=0.0.0.0:8080 \
		-https-cert=/certs/localhost-cert.pem \
		-https-key=/certs/localhost-key.pem

stop-go-httpbin: ## Stop local go-httpbin service
	@echo "Stopping go-httpbin service..."
	@docker stop go-httpbin || true
	@rm -f ./mkcert-ca.pem
	@rm -f /tmp/localhost-*.pem
	@rm -rf /tmp/certs

test-with-httpbin: setup-go-httpbin ## Run docker example with local go-httpbin
	@echo "Waiting for go-httpbin to be ready..."
	@sleep 3
	@echo "Running test against local go-httpbin..."
	docker run --rm --network host \
		-v $(PWD)/mkcert-ca.pem:/tmp/mkcert-ca.pem:ro \
		http-api-tool \
		test \
		--url https://localhost:8080/get \
		--http-method GET \
		--expected-http-code 200 \
		--ca-bundle-path /tmp/mkcert-ca.pem
	@$(MAKE) stop-go-httpbin

pre-commit-install: ## Install pre-commit hooks
	pdm run pre-commit install

pre-commit-run: ## Run pre-commit hooks on all files
	pdm run pre-commit run --all-files

ci: install-dev lint security-check test ## Run CI pipeline locally

setup-dev: install-dev pre-commit-install ## Setup development environment

bootstrap: install-pdm install-dev ## Bootstrap the development environment from scratch
