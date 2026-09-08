# Clipboard design (text + images)

## How it flows

- **PC → Linux**: `Ctrl+V` keydown in the viewer (a real user gesture, so the
  browser allows `readText()`) → `rfb.clipboardPasteFrom(text)` sets the
  remote X clipboard → after a 250 ms grace period (x11vnc picks the
  clipboard up asynchronously) the viewer sends a remote `Ctrl+V`.
  The `paste` DOM event is kept as a fallback for menu/gesture pastes.
- **Linux → PC**: copy inside Linux → x11vnc pushes `ServerCutText` →
  noVNC `clipboard` event → the viewer tries `execCommand("copy")` first
  (needs no gesture), then async `writeText()`. Only if both are blocked
  does a transient panel appear with the text pre-selected (one `Ctrl+C`).

## Browser limits you must know

- Clipboard **read** needs a user gesture + permission (granted once per
  origin). First `Ctrl+V` may show a permission prompt — that is the browser,
  not a bug.
- Clipboard **write** without a gesture is rejected by Chrome; that is why
  the `execCommand` attempt exists and why the panel is the last resort.
- Only text crosses. Images/files do not (roadmap).
- The iframe **must** keep `allow="clipboard-read; clipboard-write"`.
- Serve over a secure context (`127.0.0.1` counts; plain `http://lan-ip` does not).

## App-specific notes

- Terminal copy is `Ctrl+Shift+C`; `Ctrl+V` does not paste in a terminal —
  use right-click → Paste or `Shift+Insert` (the text is already in the
  Linux clipboard after your `Ctrl+V`).
- Stuck after an upgrade? Hard-reload the viewer (`Ctrl+F5`): a cached
  `yourdaas.html` keeps old clipboard code and old buttons.

## Rich clipboard: images (files are still out of scope)

VNC clipboard is text-only, so images travel on the file-api X bridge
(`xclip`, PNG only, 5MB cap — text keeps flowing via RFB, untouched).

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
