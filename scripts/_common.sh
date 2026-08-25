# Shared constants for scripts/install.sh and scripts/uninstall.sh. Sourced, not executed directly.

AGENT_USER="argus-agent"
DATA_DIR="/var/lib/argus"
CONFIG_DIR="/etc/argus"
PIPX_HOME_DIR="/opt/argus/pipx"
PIPX_BIN_DIR="/opt/argus/bin"
UNITS="argus-agent.service argus-web.service argus.target"
DEFAULT_WEB_PORT=8420  # kept in sync with argus.web.main._DEFAULT_PORT
