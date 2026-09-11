#!/usr/bin/env python3
"""Minimal file API for the computer. Localhost only, no auth.

GET  /api/health -> {"ok": true}
GET  /api/files?path=/home/user -> {"path":..., "entries":[{"name","path","kind":"file"|"dir","size"}]}
GET  /api/file?path=... -> {"path":..., "content": "..."} (text up to 512KB)
POST /api/mkdir {"path": "..."} -> {"ok": true}
GET  /api/audio/devices -> {"sinks":[...], "sources":[...]} (name, description, volume, mute, default)
POST /api/audio/volume {"kind":"sink"|"source","name":...,"volume":0-100} -> {"ok": true}
POST /api/audio/default {"kind":"sink"|"source","name":...} -> {"ok": true} (moves live streams)
GET  /api/clipboard -> {"kind":"image","hash":...} | {"kind":"text","hash":...,"text":...} | {"kind":"none"}
GET  /api/clipboard/image -> raw PNG bytes of the X clipboard image
POST /api/clipboard/image (raw PNG body, max 5MB) -> {"ok": true} (puts it in the X clipboard)
POST /api/clipboard/text {"text":...} (max 1MB) -> {"ok": true} (UTF-8 into the X clipboard)
"""

import hashlib
import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

HOME = os.environ.get("HOME", "/home/user")
MAX_TEXT_BYTES = 512 * 1024
MAX_CLIP_TEXT_BYTES = 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

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


def xclip(*args, data=None, timeout=10):
    env = dict(os.environ)
    env.setdefault("DISPLAY", ":1")
    return subprocess.run(
        ["xclip", "-selection", "clipboard", *args],
        input=data, capture_output=True, timeout=timeout, env=env,
    )


def clip_status():
    """Single clipboard probe. Prefers images; text decoded as UTF-8 only
    (binary never surfaces as text)."""
    try:
        r = xclip("-t", "TARGETS", "-o", timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return {"kind": "none"}
    if r.returncode != 0:
        return {"kind": "none"}
    targets = r.stdout.decode(errors="replace")
    if "image/png" in targets.split():
        try:
            img = xclip("-t", "image/png", "-o", timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            return {"kind": "none"}
        if img.returncode != 0 or not img.stdout.startswith(PNG_MAGIC):
            return {"kind": "none"}
        if len(img.stdout) > MAX_IMAGE_BYTES:
            return {"kind": "none"}
        return {"kind": "image", "hash": hashlib.sha1(img.stdout).hexdigest()}
    for target in ("UTF8_STRING", "TEXT"):
        try:
            t = xclip("-t", target, "-o", timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            return {"kind": "none"}
        if t.returncode != 0:
            continue
        try:
            text = t.stdout.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if len(t.stdout) > MAX_CLIP_TEXT_BYTES:
            return {"kind": "none"}
        return {"kind": "text", "hash": hashlib.sha1(t.stdout).hexdigest(), "text": text}
    return {"kind": "none"}


def clip_write_text(text):
    data = text.encode("utf-8")
    if len(data) > MAX_CLIP_TEXT_BYTES:
        raise ValueError("text too large (1MB max)")
    # Same fork hazard as images: DEVNULL, wait for the parent only.
    env = dict(os.environ)
    env.setdefault("DISPLAY", ":1")
    try:
        p = subprocess.Popen(
            ["xclip", "-selection", "clipboard", "-t", "UTF8_STRING", "-i"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, env=env,
        )
        p.communicate(data, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError("xclip failed: " + str(e)[:120])
    if p.returncode != 0:
        raise ValueError("xclip failed")


def clip_read_png():
    img = xclip("-t", "image/png", "-o")
    if img.returncode != 0 or not img.stdout.startswith(PNG_MAGIC):
        raise ValueError("no png image in clipboard")
    if len(img.stdout) > MAX_IMAGE_BYTES:
        raise ValueError("image too large")
    return img.stdout


def clip_write_png(data):
    if not data.startswith(PNG_MAGIC) or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("body must be a PNG up to 5MB")
    # xclip -i forks to background to serve the selection while holding its
    # fds open: capture_output would hang forever waiting on the daemon, so
    # point its outputs at DEVNULL and only wait for the parent.
    env = dict(os.environ)
    env.setdefault("DISPLAY", ":1")
    try:
        p = subprocess.Popen(
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, env=env,
        )
        p.communicate(data, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError("xclip failed: " + str(e)[:120])
    if p.returncode != 0:
        raise ValueError("xclip failed")


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

    def send_raw(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
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
        if parsed.path == "/api/clipboard":
            try:
                return self.send_json(clip_status())
            except Exception as e:
                return self.send_json({"error": str(e)}, 500)
        if parsed.path == "/api/clipboard/image":
            try:
                return self.send_raw(clip_read_png(), "image/png")
            except ValueError as e:
                return self.send_json({"error": str(e)}, 404)
            except Exception as e:
                return self.send_json({"error": str(e)}, 500)
        return self.send_json({"error": "unknown route"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_IMAGE_BYTES + 1024:
            return self.send_json({"error": "body too large"}, 413)
        raw_body = self.rfile.read(length) if length else b""
        if parsed.path == "/api/clipboard/image":
            try:
                clip_write_png(raw_body)
            except ValueError as e:
                return self.send_json({"error": str(e)}, 400)
            except Exception as e:
                return self.send_json({"error": str(e)}, 500)
            return self.send_json({"ok": True})
        try:
            payload = json.loads(raw_body or b"{}")
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
        if parsed.path == "/api/clipboard/text":
            text = payload.get("text")
            if not isinstance(text, str) or not text:
                return self.send_json({"error": "text required"}, 400)
            try:
                clip_write_text(text)
            except ValueError as e:
                return self.send_json({"error": str(e)}, 400)
            except Exception as e:
                return self.send_json({"error": str(e)}, 500)
            return self.send_json({"ok": True})
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
