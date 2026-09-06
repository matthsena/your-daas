# Audio design (duplex, voice-grade)

VNC carries no audio, so sound travels on a parallel channel that mirrors
the noVNC pattern: browser ↔ nginx (`/audio/`) ↔ `audio-ws` (`:7072`) ↔
headless PulseAudio.

## Signal path

**Out (Linux → headphones):** apps play to the default sink `yd_out`
(a null sink) → `ffmpeg` captures `yd_out.monitor`, encodes Opus 24kHz mono
(~48kbps, 10ms frames, `voip`) as ~20ms WebM clusters → WebSocket `/out` →
browser `MediaSource` (`audio/webm;codecs=opus`) → `<audio>` element.
Measured end-to-end (container signal → decoded host audio, host decode
included): median ~135ms, range 80–300ms. Smaller clusters cost mux
overhead; don't shrink them further without raising the bitrate.

**In (mic → Linux):** browser `getUserMedia` (16kHz mono, echo cancellation)
→ `AudioWorklet` converts float32 → PCM16 → WebSocket `/mic` → server pipes
frames into `pacat --playback` on sink `yd_mic` (`--latency-msec=30`),
exposed to apps as the default source `yd_mic_in` (`module-remap-source`).

## Container notes

- PulseAudio runs unprivileged with its runtime under `/tmp/yourdaas/run`
  (`XDG_RUNTIME_DIR`) — there is no `/run/user/<uid>` and no system bus.
  Anything via `docker exec` must export the same `XDG_RUNTIME_DIR` or
  `pactl`/`parec` will report "connection refused" while the daemon is fine.
- `audio-ws` binds `0.0.0.0` inside the container netns because Docker
  forwards from the host loopback via eth0; external reachability is still
  decided by `ports:` (`127.0.0.1` only), same posture as the file API.
- One ffmpeg per `/out` connection; it is killed on disconnect.
- Codecs: libopus accepts 8/12/16/24/48kHz only (32kHz fails to init).

## Browser notes (Chrome-first)

- The rail has two independent buttons: **Sound** (speaker) and **Mic**.
  Sound defaults to ON: it starts muted on page load (muted autoplay is
  always allowed) and unmutes on the first click/keypress anywhere —
  including inside the desktop, which re-dispatches gestures to the page.
  Mic starts only when its button is pressed (permission is asked then).
- Every async step has a timeout and every exit path closes its socket:
  a timed-out attempt never leaks a server-side ffmpeg (one ffmpeg exists
  per live `/out` connection, killed on toggle-off/disconnect).
- Firefox/Safari: MediaSource Opus and AudioWorklet coverage varies;
  Chrome is the verified path. WebRTC (with TURN) is the planned upgrade
  for lower latency and wider deployability — see `docs/ROADMAP.md`.

## Verify without ears

```bash
# sinks/sources up?
docker exec <computer> sh -c 'export XDG_RUNTIME_DIR=/tmp/yourdaas/run; pactl info | grep -E "Default (Sink|Source)"'
# out: valid Opus/WebM bytes on the socket (see /tmp/ws-audio-test.py pattern)
# mic: inject a 440Hz sine on /mic, record yd_mic.monitor with parec, check RMS
```

## Control API (volume + device selects)

The file API exposes PulseAudio controls (same loopback-only posture):

- `GET /api/audio/devices` → sinks/sources with volume, mute, default flags.
- `POST /api/audio/volume {"kind","name","volume"}` → 0–100, name-validated.
- `POST /api/audio/default {"kind","name"}` → switches the default **and
  moves live streams** so apps follow immediately.

Two device levels (don't confuse them):

- **Physical endpoints (native OS)** — what the menu selects show. Output
  uses the browser's device list + `setSinkId()` on the `<audio>` element;
  input picks the host mic via `deviceId` in `getUserMedia()` (changing it
  rebuilds the mic chain live). Real labels appear after mic permission is
  granted; before that, generic `Speaker N` / `Microphone N` entries.
- **Remote routing (Linux)** — stays on the API above. The volume slider
  drives the default Linux sink; the default source is the virtual mic fed
  by the browser. Use the API directly for exotic routing (e.g. monitor-as-mic).

The rail menu renders a volume slider plus Output/Input selects from these
endpoints; the slider drives the selected output sink.
