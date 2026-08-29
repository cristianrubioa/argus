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

# Only checked on a fresh install — on a reinstall/update, whatever already holds this port is
# Argus's own running instance, not a conflict.
WEB_PORT="$DEFAULT_WEB_PORT"
_port_is_free() {  # _port_is_free <port>
    python3.12 -c "
import socket
import sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(('0.0.0.0', int(sys.argv[1])))
except OSError:
    sys.exit(1)
" "$1" 2>/dev/null
}

if [ ! -f "$CONFIG_DIR/agent.env" ]; then
    IS_FRESH_INSTALL=1
    while ! _port_is_free "$WEB_PORT"; do
        if [ ! -r /dev/tty ]; then
            echo "Port $WEB_PORT is already in use and no terminal is available to ask for another." >&2
            echo "Set ARGUS_WEB_PORT in $CONFIG_DIR/agent.env after fixing the conflict, then run: systemctl restart argus-web" >&2
            exit 1
        fi
        read -r -p "Port $WEB_PORT is already in use. Enter an alternate port: " WEB_PORT < /dev/tty
    done
fi

# Desktop tray icon: only provisioned for the real invoking user (never root) when they have an
# active desktop session — a headless host is left completely untouched by everything gated on
# this. Cleared back to empty on any tray-specific failure below (see design.md's "fail soft").
TRAY_USER=$(_desktop_session_user || true)

NEED_APT_UPDATE=0
command -v usbguard >/dev/null 2>&1 || NEED_APT_UPDATE=1
command -v pipx >/dev/null 2>&1 || NEED_APT_UPDATE=1
command -v curl >/dev/null 2>&1 || NEED_APT_UPDATE=1
if [ -n "$TRAY_USER" ]; then
    dpkg -s python3-gi >/dev/null 2>&1 || NEED_APT_UPDATE=1
    dpkg -s gir1.2-ayatanaappindicator3-0.1 >/dev/null 2>&1 || NEED_APT_UPDATE=1
    dpkg -s gnome-shell-extension-appindicator >/dev/null 2>&1 || NEED_APT_UPDATE=1
fi

if [ "$NEED_APT_UPDATE" = 1 ]; then
    apt-get update
    command -v usbguard >/dev/null 2>&1 || apt-get install -y usbguard
    command -v pipx >/dev/null 2>&1 || apt-get install -y pipx
    command -v curl >/dev/null 2>&1 || apt-get install -y curl
    if [ -n "$TRAY_USER" ]; then
        if ! apt-get install -y python3-gi gir1.2-ayatanaappindicator3-0.1 gnome-shell-extension-appindicator; then
            echo "Warning: could not install the tray's desktop packages — continuing without the tray icon." >&2
            TRAY_USER=""
        fi
    fi
fi

if [ -n "$TRAY_USER" ] && command -v gnome-extensions >/dev/null 2>&1; then
    TRAY_UID=$(id -u "$TRAY_USER")
    # Enabling an already-enabled extension is a harmless no-op — no need to check state first.
    sudo -u "$TRAY_USER" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$TRAY_UID/bus" \
        XDG_RUNTIME_DIR="/run/user/$TRAY_UID" \
        gnome-extensions enable ubuntu-appindicators@ubuntu.com >/dev/null 2>&1 || true
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

# Downloaded locally rather than handed straight to pipx: pip only honors a trailing [tray]
# extras suffix on a local path — on a bare https:// URL it either 404s (the brackets get
# URL-encoded into the request) or silently drops the extra, depending on the URL's shape.
# Kept under its real wheel filename (not a random mktemp name) — pipx parses the filename
# itself to determine the package name and rejects anything that doesn't look like one.
TMP_WHEEL_DIR=$(mktemp -d)
TMP_WHEEL="$TMP_WHEEL_DIR/$(basename "$WHEEL_URL")"
curl -fsSL "$WHEEL_URL" -o "$TMP_WHEEL"

echo "Installing argus-agent and argus-web via pipx..."
PIPX_INSTALL_TARGET="$TMP_WHEEL"
PIPX_INSTALL_FLAGS=""
if [ -n "$TRAY_USER" ]; then
    PIPX_INSTALL_TARGET="${TMP_WHEEL}[tray]"
    # A plain pipx venv is isolated from system site-packages — argus-tray couldn't otherwise
    # see the apt-installed `gi` (PyGObject isn't pip-installable at all, see design.md decision 1).
    PIPX_INSTALL_FLAGS="--system-site-packages"
fi
TMP_PIPX_LOG=$(mktemp)
if ! PIPX_HOME="$PIPX_HOME_DIR" PIPX_BIN_DIR="$PIPX_BIN_DIR" pipx install --quiet --force $PIPX_INSTALL_FLAGS "$PIPX_INSTALL_TARGET" >"$TMP_PIPX_LOG" 2>&1; then
    if [ -n "$TRAY_USER" ]; then
        echo "Warning: installing the tray extra failed, retrying without it:" >&2
        cat "$TMP_PIPX_LOG" >&2
        TRAY_USER=""
        if ! PIPX_HOME="$PIPX_HOME_DIR" PIPX_BIN_DIR="$PIPX_BIN_DIR" pipx install --quiet --force "$TMP_WHEEL" >"$TMP_PIPX_LOG" 2>&1; then
            cat "$TMP_PIPX_LOG" >&2
            rm -f "$TMP_PIPX_LOG"
            rm -rf "$TMP_WHEEL_DIR"
            exit 1
        fi
    else
        cat "$TMP_PIPX_LOG" >&2
        rm -f "$TMP_PIPX_LOG"
        rm -rf "$TMP_WHEEL_DIR"
        exit 1
    fi
fi
rm -f "$TMP_PIPX_LOG"
rm -rf "$TMP_WHEEL_DIR"

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

if [ -n "$IS_FRESH_INSTALL" ]; then
    echo "ARGUS_WEB_PORT=$WEB_PORT" >> "$CONFIG_DIR/agent.env"
fi

DASHBOARD_PORT=$(grep -o '^ARGUS_WEB_PORT=.*' "$CONFIG_DIR/agent.env" 2>/dev/null | cut -d= -f2)
DASHBOARD_PORT=${DASHBOARD_PORT:-$DEFAULT_WEB_PORT}

# A small world-readable companion to agent.env (which stays 600 and may hold credentials) —
# lets the unprivileged tray learn the configured port without widening agent.env's own access.
echo "ARGUS_WEB_PORT=$DASHBOARD_PORT" > "$PORT_FILE"
chmod 644 "$PORT_FILE"

if [ -n "$TRAY_USER" ]; then
    TRAY_HOME=$(_desktop_user_home "$TRAY_USER")
    TRAY_ICON=$("$PIPX_HOME_DIR/venvs/argus/bin/python3" -c \
        "import importlib.resources; print(importlib.resources.files('argus.web').joinpath('static', 'icon.svg'))" 2>/dev/null)
    # importlib.resources only builds the path — it doesn't confirm the file is actually there.
    if [ -n "$TRAY_HOME" ] && [ -n "$TRAY_ICON" ] && [ -f "$TRAY_ICON" ]; then
        TRAY_DESKTOP_FILE=$(mktemp)
        cat > "$TRAY_DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Argus
Comment=Open the Argus dashboard
Exec=$PIPX_BIN_DIR/argus-tray
Icon=$TRAY_ICON
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
EOF
        mkdir -p "$TRAY_HOME/.config/autostart" "$TRAY_HOME/.local/share/applications"
        chown "$TRAY_USER":"$TRAY_USER" "$TRAY_HOME/.config/autostart" "$TRAY_HOME/.local/share/applications"
        install -m 644 -o "$TRAY_USER" -g "$TRAY_USER" "$TRAY_DESKTOP_FILE" "$TRAY_HOME/$TRAY_AUTOSTART_REL"
        install -m 644 -o "$TRAY_USER" -g "$TRAY_USER" "$TRAY_DESKTOP_FILE" "$TRAY_HOME/$TRAY_APPLICATIONS_REL"
        rm -f "$TRAY_DESKTOP_FILE"
        TRAY_PROVISIONED=1
    else
        echo "Warning: could not resolve the tray's home directory or installed icon — skipping desktop integration." >&2
    fi
fi

systemctl restart $UNITS

DASHBOARD_HOST=$(hostname -I 2>/dev/null | awk '{print $1}')
DASHBOARD_HOST=${DASHBOARD_HOST:-localhost}

echo ""
echo "Done. Argus is running."
echo ""
echo "  Dashboard:  http://$DASHBOARD_HOST:$DASHBOARD_PORT"
echo "  Next step:  open that URL and create the admin account."
if [ -n "$TRAY_PROVISIONED" ]; then
    echo ""
    echo "  Tray icon:  added to your top bar and Applications menu."
    echo "              If it doesn't appear, log out and back in once — GNOME Shell"
    echo "              only picks up a newly enabled extension on next login."
fi
