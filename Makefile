.PHONY: setup db-up db-down db-init install verify test lint clean help

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: install db-up db-init verify  ## Full setup (install + database + verify)
	@echo ""
	@echo "Setup complete! Copy .env.example to .env and add your API key:"
	@echo "  cp .env.example .env"
	@echo "  # Edit .env and set ANTHROPIC_API_KEY=sk-ant-..."

install:  ## Install Python dependencies
	python3 -m venv venv
	. venv/bin/activate && pip install -e ".[dev]"
	. venv/bin/activate && crawl4ai-setup

db-up:  ## Start PostgreSQL + AGE container
	docker compose -f db/docker-compose.yml up -d
	@echo "Waiting for database to be ready..."
	@sleep 5

db-down:  ## Stop database container
	docker compose -f db/docker-compose.yml down

db-reset:  ## Reset database (destroys all data)
	docker compose -f db/docker-compose.yml down -v
	docker compose -f db/docker-compose.yml up -d
	@sleep 5

db-init:  ## Create AGE graph (run after db-up)
	. venv/bin/activate && python -m build_kg.setup_graph

verify:  ## Verify setup (database, AGE, LLM)
	. venv/bin/activate && python -m build_kg.verify

test:  ## Run tests
	. venv/bin/activate && pytest tests/ -v

lint:  ## Run linter
	. venv/bin/activate && ruff check src/ tests/

clean:  ## Remove build artifacts and caches
	rm -rf __pycache__ src/build_kg/__pycache__ *.egg-info dist build .pytest_cache
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -delete
