.DEFAULT_GOAL := help

help:
	@echo "Available commands:"
	@echo "  make run              Start argus-web, in Docker (port 8420, live reload)"
	@echo "  make down             Stop argus-web"
	@echo "  make build            Build Docker image"
	@echo "  make logs             View argus-web container logs"
	@echo "  make install-agent    Install argus-agent on this host (needs sudo)"
	@echo "  make monitor-mode     Force USBGuard to stop blocking, right now (needs sudo)"
	@echo "  make mqtt-broker      Start a throwaway local Mosquitto broker for testing"
	@echo "  make mqtt-watch       Watch messages on the local test broker"
	@echo ""
	@echo "  make lint             Check style with ruff"
	@echo "  make format           Format code with ruff"
	@echo "  make fix              Auto-fix and format"
	@echo "  make check            Check without modifying (used by CI)"
	@echo "  make test             Run tests with pytest"
	@echo "  make clean            Remove __pycache__ and .pyc files"

run:
	docker compose up --build -d

down:
	docker compose down

build:
	poetry lock
	poetry install
	docker compose build

logs:
	docker compose logs -f argus-web

install-agent:
	chmod +x ./scripts/install-agent.sh
	sudo ./scripts/install-agent.sh

monitor-mode:
	sudo usbguard set-parameter ImplicitPolicyTarget allow

mqtt-broker:
	docker run --rm -d --name argus-test-mosquitto -p 1883:1883 eclipse-mosquitto

mqtt-watch:
	docker run --rm --network host eclipse-mosquitto mosquitto_sub -h localhost -t 'argus/#' -v

lint:
	ruff check .

format:
	ruff format .

fix:
	ruff check . --fix
	ruff format .

check:
	ruff check .
	ruff format . --check

test:
	poetry run pytest

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
