# Troubleshooting

## Plank running-dot offset / ghost icons

Symptoms: the blue running indicator sits at the dock's edge instead of
under its icon, icons shift ~20 px, tooltips name the wrong app
("Bulk Rename" for Files, duplicate Chrome entries).

Causes, in order of likelihood:

1. **Duplicate `.desktop` files.** Chrome ships both `google-chrome.desktop`
   and `com.google.Chrome.desktop`; Bamf matches either, plank can't merge.
   The image deletes the shadow copies and installs canonical launchers from
   `computer/desktop-files/`. If you add an app, give it exactly one
   `.desktop` with a correct `StartupWMClass`.
2. **Stale Bamf/plank state** from unclean shutdowns. Restart the session;
   for a guaranteed-clean state use a pristine volume
   (`docker compose down -v && docker compose up --build`).
3. **Ghost windows**: a lingering `Thunar --daemon` or a second `bamfdaemon`
   can anchor phantoms. Check with `xwininfo -root -tree` inside the container.

Never debug this by `kill -9`-ing session processes in a loop — the churn
itself (respawn races, transient dock items) produces the same symptoms and
masks the real cause. One clean boot, then observe.

## Chrome pin opens nothing

A stale `Singleton*` lock in the persistent profile (container killed with
Chrome open) blocks new windows: a process runs, no window appears.
`computer/start.sh` wipes the lock files at boot. If it still happens, the
profile itself may be corrupt — rename `~/.config/google-chrome` and retry.

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

## Logs

Inside the container, `/tmp/yourdaas/` holds `xvfb.log`, `xfce.log`,
`plank.log`, `x11vnc.log`, `novnc.log`, `file-api.log`.
