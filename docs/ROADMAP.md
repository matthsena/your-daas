# Roadmap

Target: DaaS for individuals — your PC, anywhere. Linux-only.

## Done (this repo)

- Container desktop (XFCE + Chrome + dock), noVNC web client, file manager.
- Text clipboard both ways, host-timezone clock, persistent home volume.
- Local/prod compose split, tunnel + backup + VPS docs.

## Phase 1 — Accounts & sessions (demo → product)

- Signup/login + 2FA, one container per user from this image.
- Per-user subdomains (`user.<domain>`) via reverse proxy + tunnel.
- Idle suspend/resume (the margin lever — idle desktops must freeze).
- Remove passwordless sudo; auth on the file API.

## Phase 2 — Feels like my PC

- Audio (PulseAudio → WebRTC/Opus; VNC has no sound).
- File upload/download (binary) through the file API.
- Image clipboard (text already works).

## Phase 3 — Conversion & retention

- Ready-made images per profile: Study, Dev, Light browsing.
- Plans: included hours/month + bigger CPU/RAM tiers.
- Temporary view-only share links (support, pairing, word of mouth).

## Explicitly out of scope

Windows/macOS hosting, corporate SSO/audit, enterprise SLAs.
