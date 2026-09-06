#!/usr/bin/env python3
"""Minimal file API for the computer. Localhost only, no auth.

GET  /api/health -> {"ok": true}
GET  /api/files?path=/home/user -> {"path":..., "entries":[{"name","path","kind":"file"|"dir","size"}]}
GET  /api/file?path=... -> {"path":..., "content": "..."} (text up to 512KB)
POST /api/mkdir {"path": "..."} -> {"ok": true}
GET  /api/audio/devices -> {"sinks":[...], "sources":[...]} (name, description, volume, mute, default)
POST /api/audio/volume {"kind":"sink"|"source","name":...,"volume":0-100} -> {"ok": true}
POST /api/audio/default {"kind":"sink"|"source","name":...} -> {"ok": true} (moves live streams)
"""

import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

HOME = os.environ.get("HOME", "/home/user")
MAX_TEXT_BYTES = 512 * 1024

NAME_RE = re.compile(r"^[A-Za-z0-9_.@-]+$")


def pa(*args):
    return subprocess.run(
        ["pactl", *args], capture_output=True, text=True, timeout=10
    )


def pa_percent(device):
    try:
        vols = device.get("volume", {}).values()
        pcts = [
            int(str(v.get("value_percent", "0%")).rstrip("%"))
            for v in vols
            if isinstance(v, dict)
        ]
        return max(pcts) if pcts else 0
    except (ValueError, AttributeError):
        return 0


def audio_devices():
    sinks = json.loads(pa("--format=json", "list", "sinks").stdout or "[]")
    sources = json.loads(pa("--format=json", "list", "sources").stdout or "[]")
    default_sink = pa("get-default-sink").stdout.strip()
    default_source = pa("get-default-source").stdout.strip()

    def shape(devs, default):
        out = []
        for d in devs:
            out.append({
                "name": d.get("name", ""),
                "description": d.get("description", "") or d.get("name", ""),
                "volume": pa_percent(d),
                "mute": bool(d.get("mute", False)),
                "monitor": "monitor" in (d.get("name", "")),
                "default": d.get("name") == default,
            })
        return out

    return {"sinks": shape(sinks, default_sink), "sources": shape(sources, default_source)}


def audio_set_volume(kind, name, volume):
    if kind not in ("sink", "source") or not NAME_RE.match(name):
        raise ValueError("invalid target")
    volume = int(volume)
    if not 0 <= volume <= 100:
        raise ValueError("volume out of range")
    r = pa(f"set-{kind}-volume", name, f"{volume}%")
    if r.returncode != 0:
        raise ValueError(r.stderr.strip() or "pactl failed")


def audio_set_default(kind, name):
    if kind not in ("sink", "source") or not NAME_RE.match(name):
        raise ValueError("invalid target")
    r = pa(f"set-default-{kind}", name)
    if r.returncode != 0:
        raise ValueError(r.stderr.strip() or "pactl failed")
    # Move live streams so apps follow the new default immediately.
    if kind == "sink":
        for line in pa("list", "short", "sink-inputs").stdout.splitlines():
            parts = line.split()
            if parts:
                pa("move-sink-input", parts[0], name)
    else:
        for line in pa("list", "short", "source-outputs").stdout.splitlines():
            parts = line.split()
            if parts:
                pa("move-source-output", parts[0], name)


def safe_path(raw: str) -> str:
    # Jail everything inside HOME.
    base = os.path.realpath(HOME)
    target = os.path.realpath(os.path.join(base, raw.lstrip("/") if raw.startswith("/") else raw) if not raw.startswith(base) else raw)
    if raw.startswith("/"):
        target = os.path.realpath(raw)
    if target != base and not target.startswith(base + os.sep):
        raise ValueError("outside home")
    return target


class Handler(BaseHTTPRequestHandler):
    server_version = "yourdaas-file-api/0.1"

    def log_message(self, *args):
        pass

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_json({})

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/api/health":
            return self.send_json({"ok": True})
        if parsed.path == "/api/files":
            raw = (qs.get("path") or [HOME])[0]
            try:
                target = safe_path(raw)
                names = sorted(os.listdir(target))
            except FileNotFoundError:
                return self.send_json({"error": "not found"}, 404)
            except ValueError:
                return self.send_json({"error": "invalid path"}, 400)
            entries = []
            for name in names:
                if name.startswith(".") and name not in (".browser-profiles",):
                    # show hidden files except cache noise
                    pass
                full = os.path.join(target, name)
                try:
                    st = os.stat(full)
                    entries.append({
                        "name": name,
                        "path": full,
                        "kind": "dir" if os.path.isdir(full) else "file",
                        "size": st.st_size,
                    })
                except OSError:
                    continue
            entries.sort(key=lambda e: (e["kind"] != "dir", e["name"].lower()))
            return self.send_json({"path": target, "entries": entries})
        if parsed.path == "/api/file":
            raw = (qs.get("path") or [""])[0]
            if not raw:
                return self.send_json({"error": "path required"}, 400)
            try:
                target = safe_path(raw)
                size = os.path.getsize(target)
                if size > MAX_TEXT_BYTES:
                    return self.send_json({"error": "file too large (512KB max)"}, 413)
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except FileNotFoundError:
                return self.send_json({"error": "not found"}, 404)
            except (ValueError, IsADirectoryError):
                return self.send_json({"error": "invalid path"}, 400)
            except OSError as e:
                return self.send_json({"error": str(e)}, 500)
            return self.send_json({"path": target, "content": content})
        if parsed.path == "/api/audio/devices":
            try:
                return self.send_json(audio_devices())
            except Exception as e:
                return self.send_json({"error": str(e)}, 500)
        return self.send_json({"error": "unknown route"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.send_json({"error": "invalid json"}, 400)
        if parsed.path == "/api/mkdir":
            raw = str(payload.get("path") or "")
            if not raw:
                return self.send_json({"error": "path required"}, 400)
            try:
                target = safe_path(raw)
                os.makedirs(target, exist_ok=True)
            except ValueError:
                return self.send_json({"error": "invalid path"}, 400)
            except OSError as e:
                return self.send_json({"error": str(e)}, 500)
            return self.send_json({"ok": True, "path": target})
        if parsed.path == "/api/audio/volume":
            try:
                audio_set_volume(
                    str(payload.get("kind") or ""),
                    str(payload.get("name") or ""),
                    payload.get("volume"),
                )
            except (ValueError, TypeError) as e:
                return self.send_json({"error": str(e) or "invalid request"}, 400)
            except Exception as e:
                return self.send_json({"error": str(e)}, 500)
            return self.send_json({"ok": True})
        if parsed.path == "/api/audio/default":
            try:
                audio_set_default(
                    str(payload.get("kind") or ""),
                    str(payload.get("name") or ""),
                )
            except (ValueError, TypeError) as e:
                return self.send_json({"error": str(e) or "invalid request"}, 400)
            except Exception as e:
                return self.send_json({"error": str(e)}, 500)
            return self.send_json({"ok": True})
        return self.send_json({"error": "unknown route"}, 404)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 7071), Handler)
    print("file-api on :7071", flush=True)
    server.serve_forever()
