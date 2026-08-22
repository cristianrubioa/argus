#!/bin/sh
# Idempotent host-side install of argus-agent + argus-web. Works both from a cloned repo
# (./scripts/install.sh) and piped via curl (curl -fsSL .../install.sh | sudo bash) — falls back
# to fetching files from GitHub when there's no local checkout to read them from.
# Usage: make install

set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "This script needs root — re-run with sudo." >&2
    exit 1
fi

GITHUB_REPO="cristianrubioa/argus"
SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo "")"

_fetch() {  # _fetch <repo-relative-path> <dest>
    if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/../$1" ]; then
        cp "$SCRIPT_DIR/../$1" "$2"
    else
        curl -fsSL "https://raw.githubusercontent.com/$GITHUB_REPO/main/$1" -o "$2"
    fi
}

TMP_COMMON=$(mktemp)
_fetch scripts/_common.sh "$TMP_COMMON"
. "$TMP_COMMON"
rm -f "$TMP_COMMON"

if ! command -v python3.12 >/dev/null 2>&1; then
    echo "python3.12 not found. Argus requires Python 3.12+ — install it and re-run." >&2
    exit 1
fi

if ! command -v usbguard >/dev/null 2>&1 || ! command -v pipx >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
    apt-get update
    command -v usbguard >/dev/null 2>&1 || apt-get install -y usbguard
    command -v pipx >/dev/null 2>&1 || apt-get install -y pipx
    command -v curl >/dev/null 2>&1 || apt-get install -y curl
fi

echo "Current ImplicitPolicyTarget: $(usbguard get-parameter ImplicitPolicyTarget)"

if ! id -u "$AGENT_USER" >/dev/null 2>&1; then
    echo "Creating system user $AGENT_USER"
    useradd --system --no-create-home --shell /usr/sbin/nologin "$AGENT_USER"
fi

if [ ! -f "/etc/usbguard/IPCAccessControl.d/$AGENT_USER" ]; then
    echo "Granting $AGENT_USER IPC access (listen always; modify/policy for Enforce profile)..."
    usbguard add-user "$AGENT_USER" -p modify,list -d modify,list,listen -P modify,list
    # usbguard-daemon doesn't hot-reload IPCAccessControl.d — restart so the grant actually takes effect.
    systemctl restart usbguard
fi

mkdir -p "$DATA_DIR" "$CONFIG_DIR"
chown -R "$AGENT_USER":"$AGENT_USER" "$DATA_DIR"

echo "Resolving latest release wheel from GitHub..."
WHEEL_URL=$(curl -fsSL "https://api.github.com/repos/$GITHUB_REPO/releases/latest" \
    | grep -o '"browser_download_url": *"[^"]*\.whl"' \
    | grep -o 'https://[^"]*')
if [ -z "$WHEEL_URL" ]; then
    echo "No release wheel found for $GITHUB_REPO — has a vX.Y.Z tag been released yet?" >&2
    exit 1
fi

echo "Installing argus-agent and argus-web via pipx..."
TMP_PIPX_LOG=$(mktemp)
if ! PIPX_HOME="$PIPX_HOME_DIR" PIPX_BIN_DIR="$PIPX_BIN_DIR" pipx install --quiet --force "$WHEEL_URL" >"$TMP_PIPX_LOG" 2>&1; then
    cat "$TMP_PIPX_LOG" >&2
    rm -f "$TMP_PIPX_LOG"
    exit 1
fi
rm -f "$TMP_PIPX_LOG"

for unit in $UNITS; do
    _fetch "systemd/$unit" "/etc/systemd/system/$unit"
    chmod 644 "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable --now $UNITS

if [ ! -f "$CONFIG_DIR/agent.env" ] && [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/../.env" ]; then
    install -m 600 "$SCRIPT_DIR/../.env" "$CONFIG_DIR/agent.env"
fi

if [ ! -f "$CONFIG_DIR/agent.env" ]; then
    _fetch agent.env.example "$CONFIG_DIR/agent.env"
    chmod 600 "$CONFIG_DIR/agent.env"
fi

systemctl restart $UNITS
echo "Done. argus-agent and argus-web are running. Create the admin account in the browser on first visit."
