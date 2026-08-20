# Argus

USB device monitoring and control for home lab and workstation environments — built on top of [USBGuard](https://usbguard.github.io/). See `openspec/changes/add-argus-mvp/` for the full proposal, design decisions, and specs.

## How it's split

- **`argus-agent`** — runs on the host, outside Docker, as a systemd service. Talks to USBGuard's native IPC (`usbguard watch`) and is the only piece that ever calls the `usbguard` CLI.
- **`argus-web`** — the FastAPI dashboard, runs in Docker. Only ever touches SQLite; never calls USBGuard directly (it has no path to the host's IPC socket).

Both share one SQLite file over a bind mount.

## Install order

1. Install USBGuard on the host (not bundled): `sudo apt install usbguard`
2. Grant `argus-agent`'s OS user IPC access, without root:
   ```
   sudo usbguard add-user <argus-agent-user> -p list -d modify,list,listen
   ```
3. `poetry install`
4. Copy `.env.example` to `.env` and fill it in (admin credentials, session secret — see the file for how to generate one)
5. Install and start the agent (host):
   ```
   sudo cp systemd/argus-agent.service /etc/systemd/system/
   sudo cp .env /etc/argus/agent.env
   sudo systemctl enable --now argus-agent
   ```
6. Start the dashboard: `make prod` (or `make dev` while developing)
7. Log in with the admin credentials from `.env`, then pick a profile (Monitor or Enforce) under Ajustes. Switching to Enforce for the first time runs `usbguard generate-policy` to authorize whatever is already connected, so it won't lock you out of your own keyboard/mouse.

## Development

```
make dev     # docker compose up with live reload
make test    # pytest
make check   # ruff check + format --check
```
