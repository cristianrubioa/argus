# Security

Argus is a LAN-use home-lab/workstation tool: single admin, plain HTTP by default, no multi-tenant model.

## Mitigations in place

- **Process isolation**: `argus-web` and `argus-agent` run as separate system users; only `argus-agent` can modify USBGuard policy, `argus-web` has read-only device-list access.
- **Systemd sandboxing**: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, restricted address families — filesystem writes confined to `/var/lib/argus`.
- **Release integrity**: the installer verifies the release wheel's SHA-256 checksum (published by CI) before installing, refusing on a mismatch or a missing checksum.
- **Session security**: required signing secret (no default), rate-limited login with temporary lockout, per-session CSRF token on every state-changing request.
- **Password storage**: PBKDF2-HMAC-SHA256, 600,000 iterations, random per-user salt.
- **Setup token**: first-run registration requires a one-time token the installer prints — only whoever ran it can create the admin account.
- **Rule injection guard**: a device serial containing a quote character is rejected before it's embedded into a USBGuard rule string.

## Known limitations

- **MQTT bridge**: optional, disabled by default — no TLS, no broker authentication, events sent in plaintext.
- **Plain HTTP by default**: intended for LAN use — put a TLS reverse proxy in front before exposing Argus beyond your local network.

## Reporting a vulnerability

Open a private security advisory on this repository, or email cristianrubioa@gmail.com. Please don't open a public issue for undisclosed vulnerabilities.
