# Troubleshooting

## Plank running-dot offset / ghost icons

Symptoms: the blue running indicator sits at the dock's edge instead of
under its icon, icons shift ~20 px, tooltips name the wrong app
("Bulk Rename" for Files, duplicate browser entries).

Causes, in order of likelihood:

1. **Duplicate `.desktop` files.** Browsers ship two (Chrome:
   `google-chrome.desktop` + `com.google.Chrome.desktop`; Brave Origin:
   `brave-origin.desktop` + `com.brave.Origin.desktop`); Bamf matches either,
   plank can't merge.
   The image deletes the shadow copies and installs canonical launchers from
   `computer/desktop-files/`. If you add an app, give it exactly one
   `.desktop` with a correct `StartupWMClass` — and verify the class with
   `xprop`, never trust the shipped file alone (Brave's main window reports
   `brave-origin`, its 10x10 helper reports `brave`).
2. **Stale Bamf/plank state** from unclean shutdowns. Restart the session;
   for a guaranteed-clean state use a pristine volume
   (`docker compose down -v && docker compose up --build`).
3. **Ghost windows**: a lingering `Thunar --daemon` or a second `bamfdaemon`
   can anchor phantoms. Check with `xwininfo -root -tree` inside the container.

Never debug this by `kill -9`-ing session processes in a loop — the churn
itself (respawn races, transient dock items) produces the same symptoms and
masks the real cause. One clean boot, then observe.

## Browser pin opens nothing

A stale `Singleton*` lock in the persistent profile (container killed with
the browser open) blocks new windows: a process runs, no window appears.
`computer/start.sh` wipes the lock files at boot (glob over
`~/.config/BraveSoftware/*`, covering all channels). If it still happens,
the profile itself may be corrupt — rename `~/.config/BraveSoftware` and
retry.

## Changed desktop defaults don't apply

XFCE/plank read `~/.config` from the home volume first; image defaults only
seed a fresh volume. Recipe: `docker compose down -v && docker compose up --build`
(wipes home files — back up first).

## Clock shows UTC

The guest follows the host via the `/etc/localtime:ro` mount. If it drifts,
check the host clock; override per-boot with `TZ=... docker compose up -d`.

## Clipboard quirks

See `docs/CLIPBOARD.md`. The two classics: cached `yourdaas.html`
(hard-reload) and clipboard permission granted on one origin
(`127.0.0.1:5174` vs `127.0.0.1:6080` are different origins) but expected
on the other.

## Audio quirks

- **No sound after toggling:** the `<audio>` element requires the toggle
  click itself (user gesture). Toggling programmatically never produces audio.
- **"Sound unavailable":** the `/audio/` proxy reaches `computer:7072`
  (fixed inside the container; only the host side is configurable via
  `AUDIO_PORT`). Check `audio-ws` is listening (`/tmp/yourdaas/audio-ws.log`)
  and the container was recreated after compose changes.
- **`pactl` says "connection refused" but audio works:** export
  `XDG_RUNTIME_DIR=/tmp/yourdaas/run` in your `docker exec` shell first.
- **Mic missing but speaker fine (or vice versa):** by design — the toggle
  reports which direction failed. Mic needs per-origin permission; check the
  browser site settings.
- **Choppy out:** one ffmpeg per connection is normal; two ffmpeg processes
  means a leaked connection (toggling Sound off kills it).
- **Works in incognito/private, fails in the normal profile:** first suspect
  `localhost` vs `127.0.0.1`. If `localhost` resolves to `::1` (IPv6) while
  the stack publishes IPv4 loopback only, the browser's WebSocket may fail
  without falling back — the app now retries the twin host automatically
  (`localhost` <-> `127.0.0.1`), so this heals itself; explicit `127.0.0.1`
  in the address bar is the manual workaround. If it still fails on both,
  suspect a header-mangling extension or local MITM (privacy, anti-miner,
  AV web shields): decisive test is Firefox Troubleshoot Mode (or Chrome
  with extensions disabled). Server-side fingerprint of a mangled handshake:
  nginx logs `GET /audio/out → 400` with a 77-byte body, which is exactly
  `missing Sec-WebSocket-Version header` — a header no page can remove.
- **Firefox `Feature Policy: Skipping clipboard-read/write`:** Firefox doesn't
  recognize those iframe allow-tokens; clipboard inside the viewer is
  degraded there. Chrome is the verified path (see `docs/CLIPBOARD.md`).

## Slimming rules (earned the hard way)

- `x11-utils` was cut once and **re-added**: `start.sh` gates the boot on
  `xdpyinfo`, so removing it boot-loops the container (`Xvfb failed to start`
  × N restarts) — 712KB that earns its place twice (boot check + `xprop`
  debugging). Rule: if you cut a package, grep the image for its binaries first.
- `papirus-icon-theme` (202MB) → Adwaita (in tree). `mousepad`,
  `imagemagick`, `x11-utils` went only after checking reverse deps
  (`apt-cache rdepends --installed`) — `libnode108`/`python3-numpy`/`oslo`
  stay because the `novnc`/`websockify` debs hard-require them (vendoring
  noVNC statics is the documented future saving, ~50MB).
- `libllvm15` (114MB, Mesa) stays: dropping it risks black browser rendering.

## Logs

Inside the container, `/tmp/yourdaas/` holds `xvfb.log`, `xfce.log`,
`plank.log`, `x11vnc.log`, `novnc.log`, `file-api.log`.
