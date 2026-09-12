# Roadmap

Target: DaaS for individuals — your PC, anywhere. Linux-only.

## Done (this repo)

- Container desktop (XFCE + Brave + dock), noVNC web client, file manager.
- Text + image clipboard both ways, host-timezone clock, persistent home volume.
- Duplex audio (Opus/WebM out, PCM mic in), binary upload, drag-and-drop onto the remote Desktop.
- Local/prod compose split, tunnel + backup + VPS docs.
- **Control plane**: signup/login + TOTP 2FA, one container per user,
  idle suspend/resume, volume snapshots + factory reset, view/control share
  links (view-only protocol-enforced), audit log.

## Phase 1 — Accounts & sessions (demo → product)

- [x] Signup/login + 2FA, one container per user from this image.
- [ ] Per-user subdomains (`user.<domain>`) via reverse proxy + tunnel.
- [x] Idle suspend/resume (the margin lever — idle desktops must freeze).
- [ ] Remove passwordless sudo; auth on the file API.

## Phase 2 — Feels like my PC

- [x] Audio (WS+Opus bridge; WebRTC still the long-term path).
- [x] File upload/download (binary) through the file API (+ drag-and-drop).
- [x] Image clipboard (text already works).

## Phase 3 — Conversion & retention

- Ready-made images per profile: Study, Dev, Light browsing.
- Plans: included hours/month + bigger CPU/RAM tiers.
- [x] Temporary view/control share links (support, pairing, word of mouth).

## Explicitly out of scope

Windows/macOS hosting, corporate SSO/audit, enterprise SLAs.
