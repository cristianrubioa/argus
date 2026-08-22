# CLAUDE.md

## Commits
- Format: `:gitmoji: [scope] Message` — message starts uppercase, written in English.
- Scopes: `back` · `front` · `infra` · `ci` · `doc`
- No co-author lines — never add `Co-Authored-By` trailers.

## Code Style
- Formatter: ruff (`make fix` to apply, `make check` to verify)
- Tailwind classes are compiled statically (`make css`, folded into `make fix`) — no CDN script, no `tailwind.config` inline in templates. Edit `tailwind.config.js` for config changes.
- Line length: 124 · Target: Python 3.12 · Rules: E, F, I, W
- Tuples over lists for literals that aren't mutated at runtime
- No multi-name imports (`from x import A, B`) — one name per line, or `from app import models` + `models.Thing`
- Multi-item tuples/lists (fields, choices, ordering...): one item per line with trailing comma, let ruff explode it
- DRF status codes: `status.HTTP_201_CREATED`, never bare ints
- DRF validation lives in the serializer, never in the view

## Deployment
- Native install via systemd (`scripts/install.sh`/`uninstall.sh`, or `make install`/`make update`/`make uninstall`) is the primary path — not Docker. `docker-compose.yml` is an optional, isolated secondary path (own port `8421`, own data volume) that won't see real `argus-agent` events.
- `argus-agent` + `argus-web` run under `argus.target` (`Wants=`/`PartOf=`) — always control both as `argus.target`; the bare name `argus` resolves to the nonexistent `argus.service` and fails.
- Releases: push a `vX.Y.Z` tag → CI builds a wheel-only release (`poetry build --format wheel`, no sdist) and publishes it to GitHub Releases. Poetry is dev/CI-only — the host installs via `pipx` from the published wheel, never `poetry install`.
- Shell scripts touching systemd: disable/stop units one at a time in a loop, never as one multi-unit command — a single nonexistent unit aborts the whole call and silently skips the rest.
- `chown` on `/var/lib/argus` must be `-R` — a recreated `argus-agent` system user gets a new UID, orphaning existing files' ownership.
- Port-availability pre-checks (e.g. `argus-web`'s bind probe) need `SO_REUSEADDR`, or a recent restart's lingering `TIME_WAIT` connections cause a false "port already in use".

## Testing
- `assert`, not `self.assert*` · structure each test with `# Setup` / `# Action` / `# Expected`, no extra blank lines
- Build test data with factories (`src/factories.py`, factory-boy) — not raw `Model.objects.create(...)` inline
- JSON responses: assert the full body (`response.json() == {...}`), not membership of individual keys
- One identity per test class: shared login goes in `setUp`, not repeated per test — split into separate classes when tests need different identities


## Language
- Code (variables, functions, classes, comments, exception/validation messages): English
