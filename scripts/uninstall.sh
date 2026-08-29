#!/bin/sh
# Reverses scripts/install.sh. Keeps /var/lib/argus (SQLite — the security audit log) and /etc/argus
# (credentials) untouched by design; see design.md decision #6 for why.
# Usage: make uninstall

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

for unit in $UNITS; do
    # One unit at a time: a single multi-unit `disable --now` can bail out on the first unit that
    # doesn't exist (e.g. a host installed before argus-web.service/argus.target existed) and skip
    # stopping the rest — silently leaving a live process behind.
    systemctl disable --now "$unit" 2>/dev/null || true
    rm -f "/etc/systemd/system/$unit"
done
systemctl daemon-reload

if command -v usbguard >/dev/null 2>&1 && usbguard remove-user "$AGENT_USER" 2>/dev/null; then
    systemctl restart usbguard
fi

command -v pipx >/dev/null 2>&1 && PIPX_HOME="$PIPX_HOME_DIR" PIPX_BIN_DIR="$PIPX_BIN_DIR" pipx uninstall argus >/dev/null 2>&1 || true

id -u "$AGENT_USER" >/dev/null 2>&1 && userdel "$AGENT_USER" || true

rm -f "$PORT_FILE"

# Tray artifacts, if the invoking user ever had them provisioned — checked regardless of
# whether their desktop session is active right now, unlike the installer's stricter check.
TRAY_USER=$(_sudo_user || true)
if [ -n "$TRAY_USER" ]; then
    TRAY_HOME=$(_desktop_user_home "$TRAY_USER")
    if [ -n "$TRAY_HOME" ]; then
        rm -f "$TRAY_HOME/$TRAY_AUTOSTART_REL" "$TRAY_HOME/$TRAY_APPLICATIONS_REL"
    fi
fi

echo "Done. argus-agent and argus-web are uninstalled."
echo "$DATA_DIR and $CONFIG_DIR were left in place — remove them yourself for a full wipe:"
echo "  rm -rf $DATA_DIR $CONFIG_DIR"
