# Argus

USB device monitoring and control, built on [USBGuard](https://usbguard.github.io/). Full design in `openspec/specs/` and `openspec/changes/archive/`.

## Layout

- **`argus-agent`** — host, systemd service. Only thing that calls the `usbguard` CLI.
- **`argus-web`** — FastAPI dashboard, systemd service on the host. Only touches SQLite.

Shared SQLite file, same host.

Requires Debian/Ubuntu and Python 3.12+.

## Install

```
curl -fsSL https://install.crubio.fyi/argus | sudo bash
```

Installs USBGuard, `argus-agent`, and `argus-web`, and starts both (`systemctl status argus.target`). From a clone, `make install` does the same.

Visit `http://<host>:8420` — first visit creates the admin account, then pick a profile (Monitor/Enforce) under Settings.

To update to the latest release: same command again, or `make update` from a clone.

To remove: `make uninstall` (from a clone), or without one:

```
curl -fsSL https://raw.githubusercontent.com/cristianrubioa/argus/main/scripts/uninstall.sh | sudo bash
```

Keeps `/var/lib/argus` and `/etc/argus`; `rm -rf` them yourself for a full wipe.

## Development

```
poetry install
make test    # pytest
make check   # ruff check + format --check
make css     # rebuild static/app.css after editing templates (make fix does this too)
poetry run uvicorn argus.web.main:app --reload   # argus-web with live reload
```

Static/app.css changes still need a browser refresh — it's not part of the poll/htmx swap cycle.

## Log retention

```
# set ARGUS_LOG_RETENTION_DAYS=30 in /etc/argus/agent.env, sudo systemctl restart argus-agent
```
Off by default (keeps everything forever). Once set, argus-agent permanently deletes events and applied whitelist actions older than N days — irreversible.

## Testing the MQTT bridge locally

```
make mqtt-broker                        # throwaway Mosquitto on localhost:1883
# set ARGUS_MQTT_HOST=localhost in /etc/argus/agent.env, sudo systemctl restart argus-agent
make mqtt-watch                         # prints every message as it arrives
```
Connect a device — the payload includes device identity, decision, profile, and timestamp.
