# Argus

USB device monitoring and control, built on [USBGuard](https://usbguard.github.io/). Full design in `openspec/specs/` and `openspec/changes/archive/`.

## Layout

- **`argus-agent`** — host, outside Docker, systemd service. Only thing that calls the `usbguard` CLI.
- **`argus-web`** — FastAPI dashboard, systemd service on the host by default. Only touches SQLite.

Shared SQLite file, same host.

Requires Debian/Ubuntu and Python 3.12+.

## Install

```
curl -fsSL https://raw.githubusercontent.com/cristianrubioa/argus/main/scripts/install.sh | sudo bash
```

Installs USBGuard, `argus-agent`, and `argus-web`, and starts both (`systemctl status argus.target`). From a clone, `make install` does the same.

Then create `/etc/argus/agent.env` (see `.env.example` for the required keys) and `systemctl restart argus.target`.

Log in at `http://<host>:8420`, pick a profile (Monitor/Enforce) under Ajustes.

Prefer Docker for `argus-web`? `cp .env.example .env && make run` still works — `argus-agent` still needs the install step above either way.

To remove: `make uninstall` (from a clone) or the same `curl` with `uninstall.sh`. Keeps `/var/lib/argus` and `/etc/argus`; `rm -rf` them yourself for a full wipe.

## Development

```
poetry install
make test    # pytest
make check   # ruff check + format --check
make css     # rebuild static/app.css after editing templates (make fix does this too)
```

`make run` bind-mounts `./src` with `--reload`, so code edits take effect without a rebuild. Static/app.css changes still need a browser refresh — it's not part of the poll/htmx swap cycle.

## Log retention

```
# set ARGUS_LOG_RETENTION_DAYS=30 in .env, redeploy argus-agent
```
Off by default (keeps everything forever). Once set, argus-agent permanently deletes events and applied whitelist actions older than N days — irreversible.

## Testing the MQTT bridge locally

```
make mqtt-broker                        # throwaway Mosquitto on localhost:1883
# set ARGUS_MQTT_HOST=localhost in .env, redeploy argus-agent
make mqtt-watch                         # prints every message as it arrives
```
Connect a device — the payload includes device identity, decision, profile, and timestamp.
