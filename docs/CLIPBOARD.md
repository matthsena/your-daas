# Clipboard design (text only)

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
