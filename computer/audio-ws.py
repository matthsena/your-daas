#!/usr/bin/env python3
"""Duplex audio bridge: Linux speaker/mic <-> browser. Localhost only, no auth.

WS /out : streams the default speaker monitor as Opus/WebM chunks
          (voice-grade: 24kHz mono). Play with MediaSource in the browser.
WS /mic : accepts raw PCM16 mono 16kHz frames and plays them into the
          virtual mic sink (apps see it as the default source).
"""
import asyncio
import logging
import os
import subprocess

import websockets

PORT = int(os.environ.get("AUDIO_PORT", "7072"))
OUT_SOURCE = os.environ.get("YD_OUT", "yd_out.monitor")
MIC_SINK = os.environ.get("YD_MIC", "yd_mic")

FFMPEG_OUT = [
    "ffmpeg", "-hide_banner", "-loglevel", "warning",
    "-f", "pulse", "-i", OUT_SOURCE,
    "-ac", "1", "-ar", "24000",
    "-c:a", "libopus", "-b:a", "40k", "-application", "voip",
    "-f", "webm",
    "-cluster_size_limit", "2048", "-cluster_time_limit", "100",
    "-flush_packets", "1",
    "pipe:1",
]
PACAT_MIC = [
    "pacat", "--playback", "-d", MIC_SINK,
    "--format=s16le", "--rate=16000", "--channels=1",
]

log = logging.getLogger("audio-ws")


async def handle_out(ws):
    proc = await asyncio.create_subprocess_exec(
        *FFMPEG_OUT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            await ws.send(chunk)
    except websockets.ConnectionClosed:
        pass
    finally:
        proc.kill()
        await proc.wait()


async def handle_mic(ws):
    proc = await asyncio.create_subprocess_exec(
        *PACAT_MIC,
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async for msg in ws:
            if isinstance(msg, bytes) and proc.stdin is not None:
                try:
                    proc.stdin.write(msg)
                    await proc.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    break
    except websockets.ConnectionClosed:
        pass
    finally:
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except BrokenPipeError:
            pass
        proc.terminate()
        await proc.wait()


async def router(ws):
    if ws.path == "/out":
        await handle_out(ws)
    elif ws.path == "/mic":
        await handle_mic(ws)
    else:
        await ws.close(code=4404, reason="unknown path")


async def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    # 0.0.0.0 inside the container netns: Docker forwards from the host
    # loopback only (see ports in docker-compose.yml), same as file-api.
    async with websockets.serve(router, "0.0.0.0", PORT, max_size=1 << 20):
        log.info("audio-ws on :%d", PORT)
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
