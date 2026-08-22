.DEFAULT_GOAL := help

help:
	@echo "Available commands:"
	@echo "  make install          Install argus-agent + argus-web on this host, from the latest release (needs sudo)"
	@echo "  make uninstall        Remove argus-agent + argus-web from this host, keeping /var/lib/argus and /etc/argus (needs sudo)"
	@echo "  make restart-agent    Restart the argus-agent service, e.g. after Ajustes shows it Stale (needs sudo)"
	@echo "  make agent-logs       Tail argus-agent's systemd journal"
	@echo "  make monitor-mode     Force USBGuard to stop blocking, right now (needs sudo)"
	@echo "  make mqtt-broker      Start a throwaway local Mosquitto broker for testing"
	@echo "  make mqtt-watch       Watch messages on the local test broker"
	@echo ""
	@echo "  make run              (optional) Run argus-web in Docker instead (port 8420, live reload)"
	@echo "  make down             Stop the Docker argus-web container"
	@echo "  make build            Build the Docker image"
	@echo "  make logs             View the argus-web Docker container logs"
	@echo ""
	@echo "  make lint             Check style with ruff"
	@echo "  make format           Format code with ruff"
	@echo "  make fix              Auto-fix and format (also rebuilds static/app.css)"
	@echo "  make css              Rebuild static/app.css from templates (downloads the Tailwind CLI on first run)"
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

install:
	chmod +x ./scripts/install.sh
	sudo ./scripts/install.sh

uninstall:
	chmod +x ./scripts/uninstall.sh
	sudo ./scripts/uninstall.sh

restart-agent:
	sudo systemctl restart argus-agent

agent-logs:
	journalctl -u argus-agent -f

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

TAILWIND_VERSION := 3.4.19
TAILWIND_BIN := .tools/tailwindcss

$(TAILWIND_BIN):
	mkdir -p .tools
	curl -fsSL -o $(TAILWIND_BIN) https://github.com/tailwindlabs/tailwindcss/releases/download/v$(TAILWIND_VERSION)/tailwindcss-linux-x64
	chmod +x $(TAILWIND_BIN)

css: $(TAILWIND_BIN)
	$(TAILWIND_BIN) -c tailwind.config.js -i src/argus/web/static/tailwind-input.css -o src/argus/web/static/app.css --minify

fix: css
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
