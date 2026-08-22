#!/bin/sh
# Reverses scripts/install.sh. Keeps /var/lib/argus (SQLite — the security audit log) and /etc/argus
# (credentials) untouched by design; see design.md decision #6 for why.
# Usage: make uninstall

set -e

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

systemctl disable --now $UNITS 2>/dev/null || true
for unit in $UNITS; do
    rm -f "/etc/systemd/system/$unit"
done
systemctl daemon-reload

if command -v usbguard >/dev/null 2>&1 && usbguard remove-user "$AGENT_USER" 2>/dev/null; then
    systemctl restart usbguard
fi

command -v pipx >/dev/null 2>&1 && PIPX_HOME="$PIPX_HOME_DIR" PIPX_BIN_DIR="$PIPX_BIN_DIR" pipx uninstall argus 2>/dev/null || true

id -u "$AGENT_USER" >/dev/null 2>&1 && userdel "$AGENT_USER" || true

echo "Done. argus-agent and argus-web are uninstalled."
echo "$DATA_DIR and $CONFIG_DIR were left in place — remove them yourself for a full wipe:"
echo "  rm -rf $DATA_DIR $CONFIG_DIR"
