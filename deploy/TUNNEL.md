# Tunnel & access (production)

This is the documented path from `127.0.0.1` to a user-facing hostname.
Nothing here is required to run locally.

## 1. Tunnel

Use the dashboard-managed flow (see comments in
`deploy/cloudflared-config.example.yml`):

```bash
cp .env.example .env   # then set TUNNEL_TOKEN from the Zero Trust dashboard
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The prod overlay removes every published port. If the tunnel drops, the
desktop is unreachable from the outside — that fail-closed behavior is
intentional.

## 2. Access policy (do this before sharing the URL)

Zero Trust → Access → application for your hostname:

- Allow: your email(s), and any IdP you already use (Google/GitHub).
- Require: 2FA / Warp posture if available.
- Session lifetime: short (24h) while there is no in-product auth.

Until built-in auth ships, this Access policy **is** the login screen.

## 3. DNS

Public Hostname in the tunnel (`desktop.<domain>` → `http://web:80`).
No A records, no open firewall ports on the VPS besides the tunnel's
outbound HTTPS.

## 4. Pre-launch checklist

- [ ] `SECURITY.md` posture reviewed (no passwordless sudo in prod images).
- [ ] File API reachable only via the internal network (prod overlay) or Access-gated.
- [ ] Backups running (`deploy/r2-backup.sh` on cron) and a restore tested.
- [ ] Tunnel token rotated into the host `.env`, never in git/screenshots.
