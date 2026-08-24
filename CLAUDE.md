# CLAUDE.md

## Commits
- Format: `:gitmoji: [scope] Message` — message starts uppercase, written in English.
- Scopes: `back` · `front` · `infra` · `ci` · `doc`
- No co-author lines — never add `Co-Authored-By` trailers.

## USBGuard Safety
- Any code path that writes live/non-permanent USBGuard authorization (`allow-device`/`block-device` without `--permanent`), especially a bulk sweep over `list_devices()`, MUST filter to `hotplug` (external) devices only. Never touch internal/hardwired devices (host controllers, integrated camera, onboard Bluetooth) — blocking a host controller takes every device on that bus down with it, indistinguishable from unplugging it.
- Incident: `block_live_devices_except()` (2026-08-24) shipped without this filter and blocked all 4 xHCI host controllers on switch to Enforce, disconnecting mouse/camera/Bluetooth entirely. Fixed by filtering to `listed.hotplug`, matching the pattern `_reconcile_whitelist_drift` already used. `deauthorize_device()`'s live-kick is the one deliberate exception — it only ever targets one specific device an admin explicitly whitelisted before, never a blanket sweep.

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
- Release: push a `vX.Y.Z` tag → CI builds `poetry build --format wheel` and publishes it to GitHub Releases. Poetry is dev/CI-only, never installed on the target host.
- Install/uninstall: `scripts/install.sh` / `scripts/uninstall.sh` (or `make install` / `make update` / `make uninstall`).

## Testing
- `assert`, not `self.assert*` · structure each test with `# Setup` / `# Action` / `# Expected`, no extra blank lines
- Those three comments stand alone, nothing appended after them — no inline rationale. If the test name doesn't already make the "why" obvious, fix the name instead of explaining it in a comment
- Build test data with factories (`src/factories.py`, factory-boy) — not raw `Model.objects.create(...)` inline
- JSON responses: assert the full body (`response.json() == {...}`), not membership of individual keys
- One identity per test class: shared login goes in `setUp`, not repeated per test — split into separate classes when tests need different identities
- Always mock `usbguard_cli` calls in tests, never let one reach the real subprocess — this dev machine has `usbguard` installed and will mask a missing mock that fails in CI. Sanity-check with `usbguard` stripped from `PATH` before trusting a green local run.


## Language
- Code (variables, functions, classes, comments, exception/validation messages): English
