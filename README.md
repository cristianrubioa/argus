# Argus

USB device monitoring and control, built on [USBGuard](https://usbguard.github.io/). Full design in `openspec/specs/` and `openspec/changes/archive/`.

## Layout

- **`argus-agent`** — host, outside Docker, systemd service. Only thing that calls the `usbguard` CLI.
- **`argus-web`** — FastAPI dashboard, in Docker. Only touches SQLite.

Shared SQLite file via bind mount.

## Install

```
cp .env.example .env   # fill in admin creds + session secret
make install-agent     # USBGuard + argus-agent user + IPC grant + own venv + systemd unit, starts argus-agent
make run                # argus-web, in Docker
```

Log in, pick a profile (Monitor/Enforce) under Ajustes.

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
