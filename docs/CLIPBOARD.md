# Clipboard design (text + images)

## How it flows

- **PC → Linux (text)**: `Ctrl+V` keydown (the gesture) → `clipboard.read()`
  for images, else `readText()` → `POST /api/clipboard/text` (exact UTF-8
  into the X clipboard via xclip) → remote `Ctrl+V`. The `paste` DOM event
  stays as fallback. noVNC's `clipboardPasteFrom` is deliberately NOT used:
  it truncates to Latin-1 bytes, which drops accents.
- **Linux → PC (text)**: copy inside Linux → x11vnc pushes `ServerCutText`
  → the noVNC `clipboard` event acts only as a wake-up call (its payload is
  Latin-1-decoded bytes: accents mojibake, images arrive as binary garbage)
  → the viewer fetches the true state from `GET /api/clipboard` (exact
  UTF-8 JSON) and writes it (`execCommand` first, async API, panel last).
  The first poll only sets a baseline so page load never clobbers the PC.

## Browser limits you must know

- Clipboard **read** needs a user gesture + permission (granted once per
  origin). First `Ctrl+V` may show a permission prompt — that is the browser,
  not a bug.
- Clipboard **write** without a gesture is rejected by Chrome; that is why
  the `execCommand` attempt exists and why the panel is the last resort.
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
- **PC → Linux:** `Ctrl+V` tries `clipboard.read()` for `image/*` first
  (the keydown is the gesture; the browser asks once), normalizes to PNG
  via canvas, POSTs to `/api/clipboard/image` (xclip owns the X selection),
  then sends the remote `Ctrl+V`. No image (or denied) falls through to
  the text path — the `paste` event still handles plain text.
- Server notes: `xclip -i` forks to serve the selection while holding its
  fds, so the endpoint uses `Popen(..., DEVNULL)` + `communicate()` instead
  of `capture_output` (which hangs forever). `GET /api/clipboard/image`
  serves raw bytes with `Content-Type: image/png`.
