# VPS sizing & hardening

## Sizing (measured on the XFCE image)

- Idle desktop: ~300–500 MB RAM.
- Light active use (browser + terminal): ~1 GB.
- Rule of thumb: a 32 GB host fits ~15–25 active users — more if most
  sessions are idle. The single biggest margin lever is suspend/resume
  (freeze idle containers), which is on the roadmap, not in the MVP.

Start small (8 GB VPS for the first users), watch `docker stats`, and grow
the host before adding orchestration.

## Host hardening basics

- SSH keys only, no password auth; automatic security updates on.
- Firewall: allow 22 (your IP), 80/443 only if something other than the
  tunnel needs them — with the prod overlay, inbound app traffic is unnecessary.
- `cloudflared` runs as a container; the tunnel token lives in the host
  `.env` with `chmod 600`.
- Backups: `deploy/r2-backup.sh backup` on cron (daily), plus a monthly
  restore drill into a scratch volume.

## Multi-user note

This repo runs one desktop per compose project. Per-user isolation
(1 container per account, subdomains, quotas) is Fase 1 of the roadmap —
see `docs/ROADMAP.md`. Do not fake it by sharing one container between users.
