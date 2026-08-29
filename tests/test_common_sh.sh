#!/bin/sh
# Dry-run check for the desktop-session detection helpers in scripts/_common.sh.
# Not part of `make test` (pytest doesn't collect .sh files) — run directly:
#   sh tests/test_common_sh.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
. "$SCRIPT_DIR/scripts/_common.sh"

_assert_fail() {  # _assert_fail <description> <command...>
    desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "FAIL: $desc — expected failure, got success" >&2
        exit 1
    fi
    echo "ok: $desc"
}

_assert_ok_eq() {  # _assert_ok_eq <description> <expected> <command...>
    desc="$1"
    expected="$2"
    shift 2
    actual=$("$@") || {
        echo "FAIL: $desc — command failed, expected success with '$expected'" >&2
        exit 1
    }
    if [ "$actual" != "$expected" ]; then
        echo "FAIL: $desc — expected '$expected', got '$actual'" >&2
        exit 1
    fi
    echo "ok: $desc"
}

unset SUDO_USER
_assert_fail "_sudo_user with no SUDO_USER (real root shell, not sudo)" _sudo_user
_assert_fail "_desktop_session_user with no SUDO_USER" _desktop_session_user

SUDO_USER=root
_assert_fail "_sudo_user rejects SUDO_USER=root" _sudo_user

SUDO_USER=$(whoami)
_assert_ok_eq "_sudo_user resolves the real invoking user" "$SUDO_USER" _sudo_user
if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
    _assert_ok_eq "_desktop_session_user resolves the real user with an active session" "$SUDO_USER" _desktop_session_user
else
    echo "skip: _desktop_session_user positive case — no desktop session on this host"
fi

SUDO_USER=nobody
_assert_fail "_desktop_session_user rejects a user with no active session" _desktop_session_user

echo "All desktop-session detection checks passed."
