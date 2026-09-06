#!/usr/bin/env python3
"""MVP: API minima de arquivos do computer. Somente localhost, sem auth.

GET  /api/health -> {"ok": true}
GET  /api/files?path=/home/rakazo -> {"path":..., "entries":[{"name","path","kind":"file"|"dir","size"}]}
GET  /api/file?path=... -> {"path":..., "content": "..."} (texto ate 512KB)
POST /api/mkdir {"path": "..."} -> {"ok": true}
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

HOME = os.environ.get("HOME", "/home/rakazo")
MAX_TEXT_BYTES = 512 * 1024


def safe_path(raw: str) -> str:
    # MVP: prende tudo dentro do HOME.
    base = os.path.realpath(HOME)
    target = os.path.realpath(os.path.join(base, raw.lstrip("/") if raw.startswith("/") else raw) if not raw.startswith(base) else raw)
    if raw.startswith("/"):
        target = os.path.realpath(raw)
    if target != base and not target.startswith(base + os.sep):
        raise ValueError("fora do home")
    return target


class Handler(BaseHTTPRequestHandler):
    server_version = "premissa-file-api/0.1"

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
                return self.send_json({"error": "nao encontrado"}, 404)
            except ValueError:
                return self.send_json({"error": "caminho invalido"}, 400)
            entries = []
            for name in names:
                if name.startswith(".") and name not in (".browser-profiles",):
                    # mostra ocultos exceto sujeira? MVP: mostra tudo menos cache
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
                return self.send_json({"error": "path obrigatorio"}, 400)
            try:
                target = safe_path(raw)
                size = os.path.getsize(target)
                if size > MAX_TEXT_BYTES:
                    return self.send_json({"error": "arquivo grande demais p/ MVP"}, 413)
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except FileNotFoundError:
                return self.send_json({"error": "nao encontrado"}, 404)
            except (ValueError, IsADirectoryError):
                return self.send_json({"error": "caminho invalido"}, 400)
            except OSError as e:
                return self.send_json({"error": str(e)}, 500)
            return self.send_json({"path": target, "content": content})
        return self.send_json({"error": "rota desconhecida"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.send_json({"error": "json invalido"}, 400)
        if parsed.path == "/api/mkdir":
            raw = str(payload.get("path") or "")
            if not raw:
                return self.send_json({"error": "path obrigatorio"}, 400)
            try:
                target = safe_path(raw)
                os.makedirs(target, exist_ok=True)
            except ValueError:
                return self.send_json({"error": "caminho invalido"}, 400)
            except OSError as e:
                return self.send_json({"error": str(e)}, 500)
            return self.send_json({"ok": True, "path": target})
        return self.send_json({"error": "rota desconhecida"}, 404)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 7071), Handler)
    print("file-api em :7071", flush=True)
    server.serve_forever()
