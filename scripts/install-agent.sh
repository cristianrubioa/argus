#!/bin/sh
# Idempotent host-side setup for argus-agent. Must run on the host, with sudo (design.md decision #1).
# Usage: make install-agent

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Must match User= in systemd/argus-agent.service.
AGENT_USER="argus-agent"

if ! command -v usbguard >/dev/null 2>&1 || ! command -v poetry >/dev/null 2>&1; then
    apt-get update
    command -v usbguard >/dev/null 2>&1 || apt-get install -y usbguard
    command -v poetry >/dev/null 2>&1 || apt-get install -y python3-poetry
fi

echo "Current ImplicitPolicyTarget: $(usbguard get-parameter ImplicitPolicyTarget)"

if ! id -u "$AGENT_USER" >/dev/null 2>&1; then
    echo "Creating system user $AGENT_USER"
    useradd --system --no-create-home --shell /usr/sbin/nologin "$AGENT_USER"
fi

echo "Granting $AGENT_USER IPC access (listen always; modify/policy for Enforce profile)..."
usbguard add-user "$AGENT_USER" -p modify,list -d modify,list,listen -P modify,list
# usbguard-daemon doesn't hot-reload IPCAccessControl.d — restart so the grant actually takes effect.
systemctl restart usbguard

mkdir -p /var/lib/argus /etc/argus
chown "$AGENT_USER" /var/lib/argus

echo "Installing argus-agent into /opt/argus/app (poetry, same tooling as dev/Docker)..."
mkdir -p /opt/argus/app
tar --exclude .git --exclude .venv --exclude data --exclude .claude --exclude openspec --exclude .env \
    -C "$REPO_ROOT" -cf - . | tar -x -C /opt/argus/app
cd /opt/argus/app
poetry config virtualenvs.in-project true --local
poetry install --only main --quiet
chown -R "$AGENT_USER" /opt/argus

install -m 644 "$REPO_ROOT/systemd/argus-agent.service" /etc/systemd/system/argus-agent.service
systemctl daemon-reload
systemctl enable argus-agent

REPO_ENV="$REPO_ROOT/.env"
if [ -f "$REPO_ENV" ]; then
    install -m 600 "$REPO_ENV" /etc/argus/agent.env
    systemctl restart argus-agent
    echo "Done. argus-agent is running."
else
    echo "Done, but no .env found at repo root — copy .env.example to .env, fill it in, then re-run this script (or: cp .env /etc/argus/agent.env && systemctl start argus-agent)."
fi
