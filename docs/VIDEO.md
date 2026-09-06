# Video pipeline notes

Loopback measurements (click → photon sampled at 60fps in a real browser;
FPS = distinct canvas frames per 4s of full-screen motion):

| x11vnc flags | UI click→photon | synth motion | H.264 trailer |
|---|---|---|---|
| defaults (`-ncache 0`) | ~87ms (77–93) | ~9.5fps | ~9.5fps |
| `+ -deferupdate 5 -wait 5` | — | ~11fps | — |
| `+ -nonap` | — | no gain (naps don't trigger under motion) | — |
| `+ -threads` (final) | 16–51ms | 11–18fps | ~13–14fps |

Shipped flags: `-deferupdate 5 -wait 5 -threads` (see `computer/start.sh`).

## Why these

- The old pacing floor was `-wait 20` + `-deferupdate 40` (~60ms/frame
  before encoding even starts). Dropping both to 5ms moved the ceiling to
  the encoder.
- `-threads` (separate input/output threads per client) parallelizes the
  tight encode across cores — the biggest single win on multi-core hosts.
- `-nonap` was tried and dropped: no effect under constant motion.

## Caveats

- Numbers were taken with host load average ~24 on 12 cores; expect run to
  run variance ±30%. Re-measure on a quiet host before tuning further.
- This build has no tight/JPEG quality knobs (`-quality` absent), so the
  remaining lever is encode parallelism, not quality tiers. The structural
  fix for 60fps video is GPU encode (Sunshine-style), not x11vnc flags.
- `-threads` changes pointer-event handling; UI latency was re-verified
  after enabling (no regression — slightly faster thanks to `-deferupdate`).
