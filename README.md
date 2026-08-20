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
make prod               # argus-web, in Docker
```

Log in, pick a profile (Monitor/Enforce) under Ajustes.

## Development

```
poetry install
make dev     # docker compose up, live reload
make test    # pytest
make check   # ruff check + format --check
```

## Testing the MQTT bridge locally

```
make mqtt-broker                        # throwaway Mosquitto on localhost:1883
# set ARGUS_MQTT_HOST=localhost in .env, redeploy argus-agent
make mqtt-watch                         # prints every message as it arrives
```
Connect a device — the payload includes device identity, decision, profile, and timestamp.
