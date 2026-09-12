# Security Policy

## Trust model (multi-user MVP)

- **Passwords**: PBKDF2-SHA256 (200k rounds), per-user salt. **2FA**: TOTP
  (SHA-1, 30s, ±1 window) mandatory at registration; secret shown once.
- **Sessions**: 32-byte random tokens, HttpOnly + SameSite=Lax cookies,
  24h expiry. No "remember me".
- **Per-user isolation**: one container + one volume per user, no published
  ports. Browsers reach desktops only through the control proxy, which
  checks owner session (or share token) per request.
- **View-only shares are enforced, not cosmetic**: the WS relay drops VNC
  Key/Pointer/CutText frames, refuses `/mic` upgrades, and refuses all
  non-GET writes for view tokens.
- **Audit**: every auth, lifecycle, snapshot, share, and reset action is
  logged with actor, IP, and user-agent.

## Known sharp edges (do not hand-wave these)

- **Docker socket**: control mounts `/var/run/docker.sock` (read-only).
  Anyone with code execution in the control container owns the host's
  Docker. Keep control minimal, dependency-free, and never expose its port
  beyond loopback/tunnel. A rootless socket or scoped proxy (e.g. socket
  proxy with POST-only-allowlist) is the follow-up.
- **No rate limiting** on login/register (local MVP). Add it before any
  hostile network touches the app.
- **Cookies lack `Secure`**: fine on loopback; behind HTTPS they still work,
  but set `Secure` once HTTP is fully gone.
- **First user is admin** (sees all audit rows). There is no user deletion
  yet — remove containers/volumes/rows manually if needed.
- **Suspend is `docker pause`** (RAM retained, zero CPU) — not encrypted
  hibernation. Snapshots are plain tarballs; encrypt at rest before R2.
- **Single-user services (file-api, audio-ws) have no auth of their own**;
  they stay safe by binding loopback / living on the internal network only.

## Reporting a vulnerability

Open a GitHub Security Advisory on this repo (preferred). Do not open a
public issue for unpatched vulnerabilities.
