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

## Testing
- `assert`, not `self.assert*` · structure each test with `# Setup` / `# Action` / `# Expected`, no extra blank lines
- Build test data with factories (`src/factories.py`, factory-boy) — not raw `Model.objects.create(...)` inline
- JSON responses: assert the full body (`response.json() == {...}`), not membership of individual keys
- One identity per test class: shared login goes in `setUp`, not repeated per test — split into separate classes when tests need different identities


## Language
- Code (variables, functions, classes, comments, exception/validation messages): English
