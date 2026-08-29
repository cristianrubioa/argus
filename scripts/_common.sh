# Shared constants for scripts/install.sh and scripts/uninstall.sh. Sourced, not executed directly.

AGENT_USER="argus-agent"
DATA_DIR="/var/lib/argus"
CONFIG_DIR="/etc/argus"
PIPX_HOME_DIR="/opt/argus/pipx"
PIPX_BIN_DIR="/opt/argus/bin"
UNITS="argus-agent.service argus-web.service argus.target"
DEFAULT_WEB_PORT=8420  # kept in sync with argus.web.main._DEFAULT_PORT
PORT_FILE="$CONFIG_DIR/port"  # kept in sync with argus.tray.config.PORT_FILE
TRAY_AUTOSTART_REL=".config/autostart/argus-tray.desktop"
TRAY_APPLICATIONS_REL=".local/share/applications/argus-tray.desktop"

# Resolves the real invoking user when running under sudo — never root itself. Echoes the
# username and returns 0 on success; returns 1 with no output when run without sudo from a
# real root shell (no real desktop user to attribute anything to).
_sudo_user() {
    if [ -n "$SUDO_USER" ] && [ "$SUDO_USER" != "root" ]; then
        echo "$SUDO_USER"
        return 0
    fi
    return 1
}

# Like _sudo_user, but only succeeds if that user also has an active desktop session right now.
# `sudo` strips $DISPLAY/$WAYLAND_DISPLAY by default, so this checks loginctl/`/run/user/<uid>`
# instead of trusting inherited env vars — those would look empty even when a real session
# exists. Used by the installer to decide whether to provision the tray in the first place;
# the uninstaller uses the weaker _sudo_user instead, since tray artifacts from a past install
# should still be cleaned up even if that session isn't active right now.
_desktop_session_user() {
    _user=$(_sudo_user) || return 1
    _uid=$(id -u "$_user" 2>/dev/null) || return 1
    [ -d "/run/user/$_uid" ] || return 1
    command -v loginctl >/dev/null 2>&1 || return 1
    [ "$(loginctl show-user "$_user" -p State --value 2>/dev/null)" = "active" ] || return 1
    echo "$_user"
}

_desktop_user_home() {  # _desktop_user_home <user>
    getent passwd "$1" 2>/dev/null | cut -d: -f6
}
