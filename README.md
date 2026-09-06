# YourDaaS — your PC in the cloud

Desktop-as-a-Service for individuals: a full Linux desktop (XFCE + Chrome) running in a container, accessible from any browser via noVNC. Your files persist in a per-user volume; the host clock, clipboard (text), and a minimal web client are built in.

> **Status:** local MVP. No auth yet — everything binds to `127.0.0.1` only. Read [SECURITY.md](SECURITY.md) before exposing anything.

## Quickstart (5 minutes)

Requirements: Docker + Docker Compose.

```bash
cp .env.example .env
docker compose up --build -d
```

- Web client: http://127.0.0.1:5174 (Desktop + Files tabs)
- noVNC direct: http://127.0.0.1:6080/yourdaas.html
- File API health: http://127.0.0.1:7071/api/health

Fresh desktop settings (XFCE caches its own config in the home volume):

```bash
docker compose down -v && docker compose up --build -d   # wipes home volume
```

## Layout

- `computer/` — desktop image: Debian + Xvfb + XFCE + plank dock + Chrome + x11vnc + noVNC page + file API.
- `web/` — Vite + React client embedding the desktop (iframe) plus a minimal file manager.
- `deploy/` — production topology: Cloudflare Tunnel example, R2 backup script, VPS sizing guide.
- `docs/` — architecture, clipboard design, troubleshooting, roadmap.

## How it works (30 seconds)

One container runs an X server (Xvfb), a full XFCE session, and x11vnc; `websockify` bridges VNC to WebSocket and noVNC renders it in the browser. A tiny Python file API (jailed to the user's home) powers the Files tab. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Production topology

```text
user → Cloudflare (DNS/CDN/Zero Trust) → cloudflared Tunnel → VPS (1 container per user)
                                                              ↘ R2 (volume snapshots)
```

Local compose is the dev loop; `docker-compose.prod.yml` removes public ports and adds the tunnel service. Details in [deploy/](deploy/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Docs in English; be nice.

## License

MIT — see [LICENSE](LICENSE).
