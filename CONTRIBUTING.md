# Contributing

Requires Python 3.12+ and [Poetry](https://python-poetry.org/docs/#installation) installed.

```
make deps    # poetry install
make check   # ruff check + format --check
make test    # pytest
```

Conventions (commit format, code style, testing rules) live in [`CLAUDE.md`](CLAUDE.md) — read it before opening a PR.

## Managing an install from a clone

```
make install         # install on this host, from the latest release (needs sudo)
make update          # same as install — re-fetches the latest release and restarts
make uninstall       # remove argus-agent + argus-web, keeps /var/lib/argus and /etc/argus
make restart-agent   # restart argus-agent, e.g. after Settings shows it Stale
make agent-logs      # tail argus-agent's systemd journal
```

Bugs and feature requests: [open an issue](https://github.com/cristianrubioa/argus/issues/new).
