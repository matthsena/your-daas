# Clipboard design (text + images)

## How it flows

- **PC → Linux (text)**: `Ctrl+V` → the `paste` event carries data + gesture
  together, so no `clipboard.read()`/`readText()` call and no permission
  prompt, ever. Text goes `POST /api/clipboard/text` (exact UTF-8 via xclip)
  → remote `Ctrl+V`. The keydown handler only shields noVNC from the
  keystroke (no double paste) and arms a one-shot `readText()` fallback if
  no paste event arrives within 800ms.
- **Linux → PC (text)**: copy inside Linux → x11vnc pushes `ServerCutText`
  → the noVNC `clipboard` event acts only as a wake-up call (its payload is
  Latin-1-decoded bytes: accents mojibake, images arrive as binary garbage)
  → the viewer fetches the true state from `GET /api/clipboard` (exact
  UTF-8 JSON) and writes it (`execCommand` first, async API, panel last).
  The first poll only sets a baseline so page load never clobbers the PC.

## Browser limits you must know

- Clipboard **reads never prompt**: the host→remote path uses the `paste`
  event (gesture-scoped by design). **Writes** without a gesture are rejected
  by Chrome; that is why the `execCommand` attempt exists and why the panel
  is the last resort.
- Only text crosses. Images/files do not (roadmap).
- The iframe **must** keep `allow="clipboard-read; clipboard-write"`.
- Serve over a secure context (`127.0.0.1` counts; plain `http://lan-ip` does not).
- The container must run a UTF-8 locale (`LANG=C.UTF-8`, set in image +
  entrypoint): X selection conversions depend on it.
- `Backspace` with focus on the viewer page (not a field) is swallowed to
  stop the host browser navigating away; the keystroke still reaches noVNC,
  so remote Backspace keeps working.

## App-specific notes

- Terminal copy is `Ctrl+Shift+C`; `Ctrl+V` does not paste in a terminal —
  use right-click → Paste or `Shift+Insert` (the text is already in the
  Linux clipboard after your `Ctrl+V`).
- Stuck after an upgrade? Hard-reload the viewer (`Ctrl+F5`): a cached
  `yourdaas.html` keeps old clipboard code and old buttons.

## Rich clipboard: images (files are still out of scope)

VNC clipboard is text-only, so images travel on the file-api X bridge
(`xclip`, PNG only, 5MB cap).

- **Linux → PC:** the viewer polls `GET /api/clipboard` every 2s (hash of
  the X image). New hash → fetch PNG → `ClipboardItem` write; if the
  browser blocks the gestureless write, a transient panel shows a thumbnail
  + copy button (one click).
- **PC → Linux (images):** `Ctrl+V` → `paste` event `files[]` (no prompt)
  → PNG normalize via canvas → `POST /api/clipboard/image` → remote `Ctrl+V`.
  Non-image files get a "not supported yet" notice instead of silence.
- Server notes: `xclip -i` forks to serve the selection while holding its
  fds, so the endpoint uses `Popen(..., DEVNULL)` + `communicate()` instead
  of `capture_output` (which hangs forever). `GET /api/clipboard/image`
  serves raw bytes with `Content-Type: image/png`.
- The viewer finds the file-api as same-origin `/api` when proxied,
  else `<viewer-host>:7071`, else `<viewer-port>+991` (local compose
  overrides) — probed once at load, awaited by every call.
