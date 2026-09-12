# Architecture

One `computer` container is a whole PC. The `web` container is a thin client.

```text
browser ──HTTPS──► web (nginx)
   │                 ├─ /            → static React app
   │                 ├─ /novnc/* ──┐ (legacy single-user computer)
   │                 ├─ /websockify ┤
   │                 ├─ /api/* ─────┤
   │                 ├─ /audio/* ───┘
   │                 ├─ /c/* ──────► control:8080 (auth API)
   │                 └─ /u/<user>/* ► control:8080 (authed proxy per user)
   │                                   ├─ novnc/websockify → computer:6080
   │                                   ├─ api/ → computer:7071
   │                                   └─ audio/ → computer:7072
   │
   └─ iframe allow="clipboard-read; clipboard-write" (clipboard needs it)
```

Without the control plane running, the app falls back to legacy
single-user mode (direct `/novnc`, `/api`, `/audio` routes).

Inside `computer` (`computer/start.sh` is PID 1's script):

```text
Xvfb :1 (1280x800) ──► xfce4-session (wm + panel + desktop, 1 workspace)
                    ──► plank dock (3 pins: Brave, Thunar, terminal)
                    ──► x11vnc :5900 (bound to 127.0.0.1 inside netns; published on loopback)
                    ──► websockify :6080 (VNC→WebSocket, serves /usr/share/novnc)
                    ──► file-api :7071 (Python stdlib only, jailed to $HOME)
autocutsel ×2 bridges X CLIPBOARD ↔ CUTBUFFER ↔ PRIMARY
```

## Key files

| Path | Role |
|---|---|
| `computer/Dockerfile` | Debian + XFCE + Brave + VNC stack (1.35GB image), `user` (uid 1000), canonical `.desktop` launchers |
| `computer/start.sh` | boot order, plank pins via dconf, Brave Singleton lock cleanup |
| `computer/viewer.html` | chromeless noVNC page (`yourdaas.html` in the image): keyboard focus, right-click passthrough, clipboard bridge |
| `computer/file-api.py` | `GET /api/health, /api/files, /api/file`, `POST /api/mkdir`, `POST /api/upload?path=` (raw bytes, jailed, 1GB cap), audio + clipboard bridges; path-jailed, no auth (loopback only) |
| `computer/audio-ws.py` | duplex audio: `/out` Opus/WebM speaker stream, `/mic` PCM16 mic injection; no auth (loopback only) |
| `computer/desktop-files/` | canonical launchers with `StartupWMClass` (grouping depends on these) |
| `computer/xfce/` | panel / wm / icon-theme defaults (first boot seeds; later the home volume wins) |
| `web/src` | `DesktopViewer` (iframe), `FileManager` (file API), `api.ts` (routes) |
| `control/` | auth (password+TOTP), per-user desktops via Docker socket, suspend/resume + idle sweeper, snapshots, share links, audit; HTTP+WS proxy with session/share auth (stdlib + python3-websockets) |

## Control plane model

- One computer container per user (`yourdaas-u-<name>`, volume `...-home`),
  spawned at registration, no published ports (reachable only via control).
- Sessions: password → 5-min ticket → TOTP → 24h HttpOnly cookie.
- Idle: web beacons genuine input (60s throttle); sweeper `pause`s past
  `IDLE_MINUTES` (default 30). Suspended desktops fail closed (409) until resume.
- Snapshots: pause → tar volume → unpause; restore stops/wipes/extracts/starts.
- Shares (`#/s/<token>`, view|control, TTL): view mode is **protocol-enforced**
  — the WS relay drops VNC Key/Pointer/CutText frames, `/mic` upgrades and
  non-GET writes are refused. Control shares are full interaction.

## Data & persistence

- Named volume `yourdaas-home` → `/home/user`: files, Brave profile, XFCE/plank config. Survives `down`, `up --build`, image rebuilds.
- `down -v` destroys it on purpose (pristine-boot recipe).
- Anything outside `/home/user` is ephemeral.

## Production mapping

Local compose binds loopback ports. The prod overlay drops them and adds
`cloudflared`; Cloudflare (DNS/CDN/Access) + R2 snapshots wrap around the
same two containers. See `deploy/`.
