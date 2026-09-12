#!/usr/bin/env python3
"""YourDaaS control plane: auth (password+TOTP), per-user desktops, suspend,
snapshots, share links, audit. Proxies HTTP+WS to each user's computer with
session/share auth. stdlib only.

Routes:
  /c/api/health, /c/api/users/register
  /c/api/session, /c/api/session/totp, /c/api/session/logout
  /c/api/me, /c/api/heartbeat
  /c/api/session/suspend, /c/api/session/resume, /c/api/session/ensure
  /c/api/snapshots...  /c/api/reset
  /c/api/shares...     /c/api/audit
  /u/<slug>/*  proxied to that user's computer (session owner/admin, or
               ?token= share token; view shares are protocol-enforced)
"""

import hashlib
import hmac
import json
import http.client
import os
import re
import secrets
import socket
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import db
import totp
from docker import Docker

CFG = {
    "db": os.environ.get("CONTROL_DB", "/data/control.db"),
    "snap_dir": os.environ.get("SNAP_DIR", "/snapshots"),
    "sock": os.environ.get("DOCKER_SOCK", "/var/run/docker.sock"),
    "port": int(os.environ.get("PORT", "8080")),
    "computer_image": os.environ.get("COMPUTER_IMAGE", "yourdaas/computer:local"),
    "helper_image": os.environ.get("HELPER_IMAGE", "yourdaas/computer:local"),
    "net": os.environ.get("NET_NAME", "your-daas_default"),
    "snap_volume": os.environ.get("SNAP_VOLUME", "yourdaas-snapshots"),
    "idle_minutes": int(os.environ.get("IDLE_MINUTES", "30")),
    "session_hours": int(os.environ.get("SESSION_HOURS", "24")),
    "sweep_sec": int(os.environ.get("SWEEP_SEC", "60")),
}

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")
SESSION_COOKIE = "yd_session"

# Upstream ports inside every computer container.
UPSTREAM = {"novnc": 6080, "websockify": 6080, "api": 7071, "audio": 7072}

# VNC client->server message types dropped for view-only shares.
VNC_INPUT_TYPES = {4, 5, 6}  # KeyEvent, PointerEvent, ClientCutText


# View shares see pixels and hear audio — nothing else. Guests must not
# read files, clipboard, or device lists through the proxy (all reachable
# via GET on the file API), so view mode is an explicit allowlist.
def view_allowed(sub: str, is_ws: bool, command: str) -> bool:
    if is_ws:
        return sub.startswith("/websockify") or re.match(r"^/audio/out", sub) is not None
    if command not in ("GET", "HEAD", "OPTIONS"):
        return False
    return (
        sub == "/novnc" or sub.startswith("/novnc/")
        or sub == "/api/health" or sub.startswith("/api/health?")
    )


def vnc_frame_dropped(mode: str, opcode: int, payload: bytes) -> bool:
    """True if a client->server WS frame must not reach upstream."""
    return mode == "view" and opcode == 0x2 and bool(payload) and payload[0] in VNC_INPUT_TYPES

log = print


# ---------- small http helpers ----------

def client_ip(handler) -> str:
    fwd = handler.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()[:80]
    return handler.client_address[0]


def read_cookies(handler):
    out = {}
    for part in handler.headers.get("Cookie", "").split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out[k.strip()] = v.strip()
    return out


def send_json(handler, obj, status=200, headers=None):
    body = json.dumps(obj).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    for k, v in (headers or {}).items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler, limit=65536):
    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except ValueError:
        length = 0
    if length <= 0 or length > limit:
        return {}
    try:
        return json.loads(handler.rfile.read(length) or b"{}")
    except (json.JSONDecodeError, ValueError):
        return {}


def audit(actor_id, actor_name, action, target, handler):
    db.run(
        "INSERT INTO audit(actor_id,actor_name,action,target,ip,ua,created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (actor_id, actor_name or "", action, target or "",
         client_ip(handler), (handler.headers.get("User-Agent") or "")[:200], db.now()),
    )


# ---------- auth ----------

def get_session(handler):
    token = read_cookies(handler).get(SESSION_COOKIE, "")
    if not token:
        return None
    s = db.q("SELECT * FROM sessions WHERE token=?", (token,), one=True)
    if not s or s["expires_at"] < db.now():
        return None
    return s


def current_user(handler):
    s = get_session(handler)
    if not s or s["scope"] != "user":
        return None, None
    u = db.q("SELECT * FROM users WHERE id=?", (s["user_id"],), one=True)
    return u, s


def set_session_cookie(handler, headers, token, max_age):
    headers["Set-Cookie"] = (
        f"{SESSION_COOKIE}={token}; HttpOnly; Path=/; SameSite=Lax; Max-Age={max_age}"
    )


def slug_of(username: str) -> str:
    return username.lower()


def container_name(username: str) -> str:
    return f"yourdaas-u-{slug_of(username)}"


def volume_name(username: str) -> str:
    return f"yourdaas-u-{slug_of(username)}-home"


# ---------- docker helpers ----------

dock = Docker(CFG["sock"])


def sync_container_state(user):
    """Reconcile db.state with docker reality. Returns state string."""
    cname = user["container"]
    if not cname:
        return "none"
    try:
        info = dock.inspect_container(cname)
    except Exception:
        return user["state"] or "error"
    state = Docker.state_of(info)
    if state != user["state"]:
        db.run("UPDATE users SET state=? WHERE id=?", (state, user["id"]))
    return state


def _parse_bytes(s: str) -> int:
    s = s.strip().lower()
    mul = {"k": 1024, "m": 1024**2, "g": 1024**3}
    if s and s[-1] in mul:
        return int(float(s[:-1]) * mul[s[-1]])
    return int(s)


def _create_computer_container(user, cname, vname):
    env = []
    if os.environ.get("TZ"):
        env.append(f"TZ={os.environ['TZ']}")
    host_extra = {}
    # Optional per-user caps (quotas phase 1): e.g. USER_MEM_LIMIT=4g,
    # USER_NANO_CPUS=2000000000 (=2 CPUs). Unset = host default (uncapped).
    if os.environ.get("USER_MEM_LIMIT"):
        try:
            host_extra["Memory"] = _parse_bytes(os.environ["USER_MEM_LIMIT"])
        except ValueError:
            pass
    if os.environ.get("USER_NANO_CPUS"):
        try:
            host_extra["NanoCpus"] = int(os.environ["USER_NANO_CPUS"])
        except ValueError:
            pass
    dock.create_container(
        cname, CFG["computer_image"],
        binds=[f"{vname}:/home/user", "/etc/localtime:/etc/localtime:ro"],
        network=CFG["net"],
        labels={"yourdaas.owner": user["username"], "yourdaas.managed": "1"},
        env=env,
        host_extra=host_extra or None,
    )
    db.run("UPDATE users SET container=?, volume=?, state='created' WHERE id=?",
           (cname, vname, user["id"]))


def ensure_desktop(user):
    """Idempotent: volume + container exist and are started. Returns state."""
    cname = container_name(user["username"])
    vname = volume_name(user["username"])
    dock.create_volume(vname)
    info = dock.inspect_container(cname)
    if info is None:
        _create_computer_container(user, cname, vname)
        info = dock.inspect_container(cname)
    state = Docker.state_of(info)
    if state in ("created", "exited", "unknown", "missing"):
        try:
            dock.start(cname)
            state = "running"
        except Exception:
            state = "error"
    elif state == "paused":
        pass
    db.run("UPDATE users SET state=?, last_beat=? WHERE id=?", (state, db.now(), user["id"]))
    return state


def helper_run_volumes(data_volume, cmd):
    name = f"yourdaas-helper-{int(time.time())}-{secrets.token_hex(4)}"
    body = {
        "Image": CFG["helper_image"],
        "Cmd": ["sh", "-c", cmd],
        "Labels": {"yourdaas.helper": "1"},
        "User": "0:0",
        "HostConfig": {
            "Binds": [f"{data_volume}:/data", f"{CFG['snap_volume']}:/backup"],
            "NetworkMode": "none",
        },
    }
    cid = dock._req("POST", "/containers/create?name=" + name, body)["Id"]
    try:
        dock._req("POST", f"/containers/{cid}/start")
        res = dock.wait(cid, timeout=600)
        logs = dock.logs(cid)
    finally:
        try:
            dock.remove_container(cid, force=True)
        except Exception:
            pass
    if res.get("StatusCode", 1) != 0:
        raise RuntimeError(f"helper failed: {logs[-500:]}")
    return logs.strip().splitlines()[-1] if logs.strip() else ""


# ---------- API handlers ----------

def api_register(handler):
    body = read_json(handler)
    username = str(body.get("username") or "").strip().lower()
    password = str(body.get("password") or "")
    if not USERNAME_RE.match(username):
        return send_json(handler, {"error": "username: 3-32 chars, a-z 0-9 _ -"}, 400)
    if len(password) < 8:
        return send_json(handler, {"error": "password: min 8 chars"}, 400)
    if db.q("SELECT id FROM users WHERE username=?", (username,), one=True):
        return send_json(handler, {"error": "username taken"}, 409)
    is_admin = 1 if not db.q("SELECT id FROM users LIMIT 1", one=True) else 0
    phash, salt = db.hash_password(password)
    secret = totp.new_secret()
    uid = db.run(
        "INSERT INTO users(username,pass_hash,pass_salt,totp_secret,is_admin,created_at,last_beat)"
        " VALUES (?,?,?,?,?,?,?)",
        (username, phash, salt, secret, is_admin, db.now(), db.now()),
    )
    user = db.q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    try:
        state = ensure_desktop(user)
    except Exception as e:
        state = f"error: {e}"
    audit(uid, username, "register", username, handler)
    audit(uid, username, "desktop.ensure", container_name(username), handler)
    return send_json(handler, {
        "id": uid, "username": username, "is_admin": bool(is_admin),
        "totp_secret": secret,
        "otpauth_url": totp.otpauth_url(secret, username),
        "container_state": state,
        "note": "Save the authenticator secret now; login needs password + TOTP code.",
    }, 201)


def api_login(handler):
    body = read_json(handler)
    username = str(body.get("username") or "").strip().lower()
    password = str(body.get("password") or "")
    user = db.q("SELECT * FROM users WHERE username=?", (username,), one=True)
    ok = False
    if user:
        phash, _ = db.hash_password(password, user["pass_salt"])
        ok = hmac.compare_digest(phash, user["pass_hash"])
    if not ok:
        audit(None, username, "login.failed", username, handler)
        return send_json(handler, {"error": "invalid credentials"}, 401)
    if user["totp_secret"]:
        ticket = secrets.token_hex(24)
        db.run("INSERT INTO sessions(token,user_id,scope,created_at,expires_at)"
               " VALUES (?,?, 'ticket', ?, ?)",
               (ticket, user["id"], db.now(), db.now() + 300))
        return send_json(handler, {"need_totp": True, "ticket": ticket})
    return _new_user_session(handler, user)


def _new_user_session(handler, user):
    token = secrets.token_hex(32)
    exp = db.now() + CFG["session_hours"] * 3600
    db.run("INSERT INTO sessions(token,user_id,scope,created_at,expires_at)"
           " VALUES (?,?, 'user', ?, ?)", (token, user["id"], db.now(), exp))
    db.run("UPDATE users SET last_beat=? WHERE id=?", (db.now(), user["id"]))
    headers = {}
    set_session_cookie(handler, headers, token, CFG["session_hours"] * 3600)
    audit(user["id"], user["username"], "login", user["username"], handler)
    return send_json(handler, {
        "user": {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])},
    }, 200, headers)


def api_login_totp(handler):
    body = read_json(handler)
    ticket = str(body.get("ticket") or "")
    code = str(body.get("code") or "")
    s = db.q("SELECT * FROM sessions WHERE token=? AND scope='ticket'", (ticket,), one=True)
    if not s or s["expires_at"] < db.now():
        return send_json(handler, {"error": "ticket expired, login again"}, 401)
    user = db.q("SELECT * FROM users WHERE id=?", (s["user_id"],), one=True)
    db.run("DELETE FROM sessions WHERE token=?", (ticket,))
    if not user or not totp.verify(user["totp_secret"], code):
        audit(user["id"] if user else None, user["username"] if user else "",
              "login.totp.failed", user["username"] if user else "", handler)
        return send_json(handler, {"error": "invalid code"}, 401)
    return _new_user_session(handler, user)


def api_logout(handler):
    token = read_cookies(handler).get(SESSION_COOKIE, "")
    if token:
        db.run("DELETE FROM sessions WHERE token=?", (token,))
    return send_json(handler, {"ok": True}, 200,
                     {"Set-Cookie": f"{SESSION_COOKIE}=; HttpOnly; Path=/; Max-Age=0"})


def user_payload(user):
    state = sync_container_state(user)
    return {
        "user": {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])},
        "container": {"name": user["container"], "state": state,
                      "suspended": state == "paused"},
        "base": f"/u/{slug_of(user['username'])}",
        "idle_minutes": CFG["idle_minutes"],
    }


def require_user(handler):
    user, _sess = current_user(handler)
    if not user:
        send_json(handler, {"error": "login required"}, 401)
        return None
    return user


# ---------- proxy to user computers ----------

HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailers", "transfer-encoding", "upgrade"}


def resolve_proxy_access(handler, slug):
    """Return (username, mode) with mode in {'full','view','control'} or (None,None)."""
    if not re.match(r"^[a-z0-9][a-z0-9_-]{2,31}$", slug or ""):
        return None, None
    # 1) owner/admin session cookie -> full access
    user, _sess = current_user(handler)
    if user and (slug_of(user["username"]) == slug or user["is_admin"]):
        return user["username"], "full"
    # 2) share token in query -> scoped access
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    token = (qs.get("token") or [""])[0]
    if token:
        sh = db.q("SELECT * FROM shares WHERE token=?", (token,), one=True)
        if sh and not sh["revoked"] and sh["expires_at"] > db.now():
            owner = db.q("SELECT * FROM users WHERE id=?", (sh["owner_id"],), one=True)
            if owner and slug_of(owner["username"]) == slug:
                return owner["username"], sh["mode"]
    return None, None


def proxy_target(sub):
    """Map /u/<slug>/<sub...> to (upstream_port, upstream_path)."""
    parts = sub.lstrip("/").split("/", 1)
    head = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    if head == "novnc":
        # websockify serves the noVNC files at its root: strip the prefix
        # (same as the legacy nginx location).
        return 6080, f"/{rest}" if rest else "/"
    if head == "websockify":
        return 6080, "/websockify"
    if head == "api":
        return 7071, f"/api/{rest}" if rest else "/api/"
    if head == "audio":
        return 7072, f"/{rest}" if rest else "/"
    return None, None


SPOOL_THRESHOLD = 64 * 1024 * 1024


def read_body_spooled(handler, length):
    """Read a request body, spooling large ones to disk so a 1GB upload
    never balloons proxy RAM. Returns (bytes_or_None, tmp_path_or_None)."""
    if length <= 0:
        return None, None
    if length <= SPOOL_THRESHOLD:
        return handler.rfile.read(length), None
    tmp = tempfile.NamedTemporaryFile(prefix="yd-up-", dir="/tmp", delete=False)
    try:
        remaining = length
        while remaining > 0:
            chunk = handler.rfile.read(min(1048576, remaining))
            if not chunk:
                break
            tmp.write(chunk)
            remaining -= len(chunk)
        tmp.close()
        return None, tmp.name
    except Exception:
        try:
            tmp.close()
        except Exception:
            pass
        try:
            os.remove(tmp.name)
        except Exception:
            pass
        raise


def proxy_http(handler, username, mode, port, upath):
    if mode == "view":
        if handler.command not in ("GET", "HEAD", "OPTIONS"):
            return send_json(handler, {"error": "view-only share"}, 403)
    length = int(handler.headers.get("Content-Length") or 0)
    if length > 1024 * 1024 * 1024 + 65536:
        return send_json(handler, {"error": "body too large"}, 413)
    try:
        body, spooled = read_body_spooled(handler, length)
    except Exception:
        return send_json(handler, {"error": "failed reading request"}, 400)
    if handler.command == "OPTIONS" and mode == "view":
        if spooled:
            try:
                os.remove(spooled)
            except Exception:
                pass
        return send_json(handler, {"ok": True})
    cname = container_name(username)
    conn = http.client.HTTPConnection(cname, port, timeout=15)
    try:
        fwd = {}
        for k, v in handler.headers.items():
            if k.lower() in HOP_HEADERS:
                continue
            fwd[k] = v
        fwd["Host"] = f"{cname}:{port}"
        fwd["X-Forwarded-For"] = client_ip(handler)
        if spooled:
            fwd["Content-Length"] = str(length)
            conn.putrequest(handler.command, upath, skip_accept_encoding=True)
            for k, v in fwd.items():
                conn.putheader(k, v)
            conn.endheaders()
            try:
                with open(spooled, "rb") as f:
                    while True:
                        chunk = f.read(1048576)
                        if not chunk:
                            break
                        conn.send(chunk)
            finally:
                try:
                    os.remove(spooled)
                except Exception:
                    pass
        else:
            conn.request(handler.command, upath, body=body, headers=fwd)
        res = conn.getresponse()
        data = res.read(1024 * 1024 * 1024 + 65536)
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return send_json(handler, {"error": f"upstream unreachable ({type(e).__name__})"}, 502)
    try:
        conn.close()
    except Exception:
        pass
    handler.send_response(res.status)
    for k, v in res.getheaders():
        if k.lower() in HOP_HEADERS or k.lower() == "content-length":
            continue
        handler.send_header(k, v)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(data)
    touch_beat(username)


def touch_beat(username):
    db.run("UPDATE users SET last_beat=? WHERE username=?", (db.now(), username))


# ----- websocket relay with view-only VNC filtering -----

def read_ws_frame(rfile):
    h = rfile.read(2)
    if len(h) < 2:
        return None
    b1, b2 = h[0], h[1]
    opcode = b1 & 0x0F
    ln = b2 & 0x7F
    ext = b""
    if ln == 126:
        ext = rfile.read(2)
        if len(ext) < 2:
            return None
        ln = int.from_bytes(ext, "big")
    elif ln == 127:
        ext = rfile.read(8)
        if len(ext) < 8:
            return None
        ln = int.from_bytes(ext, "big")
    mask = b""
    if b2 & 0x80:
        mask = rfile.read(4)
        if len(mask) < 4:
            return None
    payload = b""
    while len(payload) < ln:
        chunk = rfile.read(ln - len(payload))
        if not chunk:
            return None
        payload += chunk
    raw = h + ext + mask + payload
    if mask:
        payload = bytes(p ^ mask[i % 4] for i, p in enumerate(payload))
    return opcode, payload, raw


def write_ws_frame(wfile, opcode, payload, lock):
    ln = len(payload)
    head = bytes([0x80 | opcode])
    if ln < 126:
        head += bytes([ln])
    elif ln < 65536:
        head += b"\x7e" + ln.to_bytes(2, "big")
    else:
        head += b"\x7f" + ln.to_bytes(8, "big")
    with lock:
        wfile.write(head + payload)
        wfile.flush()


def proxy_ws(handler, username, mode, port, upath):
    # Rebuild the client handshake for upstream; relay bytes both ways.
    # View-only shares drop VNC input messages (Key/Pointer/CutText).
    try:
        up = socket.create_connection((container_name(username), port), timeout=10)
    except Exception as e:
        return send_json(handler, {"error": f"upstream unreachable ({type(e).__name__})"}, 502)
    lines = [f"GET {upath} HTTP/1.1"]
    for k, v in handler.headers.items():
        if k.lower() in ("host", "content-length"):
            continue
        lines.append(f"{k}: {v}")
    lines.append(f"Host: {container_name(username)}:{port}")
    lines.append("")
    lines.append("")
    try:
        up.sendall("\r\n".join(lines).encode())
        uf = up.makefile("rb")
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = uf.read(1)
            if not chunk:
                raise RuntimeError("upstream closed handshake")
            head += chunk
            if len(head) > 16384:
                raise RuntimeError("handshake too large")
    except Exception as e:
        try:
            up.close()
        except Exception:
            pass
        return send_json(handler, {"error": f"upstream handshake failed ({e})"}, 502)
    try:
        status = head.split(b"\r\n", 1)[0].decode(errors="replace")
        if " 101 " not in status:
            try:
                up.close()
            except Exception:
                pass
            return send_json(handler, {"error": f"upstream refused WS ({status[:60]})"}, 502)
        handler.send_response(101)
        for line in head.split(b"\r\n")[1:]:
            if not line or b":" not in line:
                continue
            k, v = line.split(b":", 1)
            kl = k.decode(errors="replace").strip().lower()
            if kl in ("transfer-encoding", "content-length"):
                continue
            handler.send_header(k.decode(errors="replace").strip(), v.decode(errors="replace").strip())
        handler.end_headers()
    except (BrokenPipeError, ConnectionResetError):
        try:
            up.close()
        except Exception:
            pass
        return
    dead = threading.Event()
    wlock = threading.Lock()

    def client_to_server():
        try:
            while not dead.is_set():
                fr = read_ws_frame(handler.rfile)
                if fr is None:
                    break
                opcode, payload, raw = fr
                if opcode == 0x8:
                    try:
                        up.sendall(raw)
                    except Exception:
                        pass
                    break
                if opcode == 0x1:
                    # text frames pass through (rare on these sockets)
                    try:
                        up.sendall(raw)
                    except Exception:
                        break
                    continue
                if opcode == 0x9 or opcode == 0xA:
                    try:
                        up.sendall(raw)
                    except Exception:
                        break
                    continue
                # binary data frame
                if vnc_frame_dropped(mode, opcode, payload):
                    continue  # enforce view-only: drop input
                try:
                    up.sendall(raw)
                except Exception:
                    break
        finally:
            dead.set()
            try:
                up.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass

    t = threading.Thread(target=client_to_server, daemon=True)
    t.start()
    try:
        while not dead.is_set():
            fr = read_ws_frame(uf)
            if fr is None:
                break
            opcode, payload, raw = fr
            if opcode == 0x8:
                break
            if opcode in (0x1, 0x2):
                write_ws_frame(handler.wfile, opcode, payload, wlock)
                continue
            if opcode in (0x9, 0xA):
                write_ws_frame(handler.wfile, opcode, payload, wlock)
                continue
    finally:
        dead.set()
        try:
            up.close()
        except Exception:
            pass
    handler.close_connection = True


# ---------- session/container/snapshot/share/audit handlers ----------

def api_me(handler):
    user = require_user(handler)
    if not user:
        return None
    return send_json(handler, user_payload(user))


def api_heartbeat(handler):
    user = require_user(handler)
    if not user:
        return None
    db.run("UPDATE users SET last_beat=? WHERE id=?", (db.now(), user["id"]))
    return send_json(handler, {"ok": True})


def api_suspend(handler):
    user = require_user(handler)
    if not user:
        return None
    cname = user["container"]
    if not cname:
        return send_json(handler, {"error": "no desktop yet"}, 409)
    state = sync_container_state(user)
    if state == "running":
        try:
            dock.pause(cname)
            state = "paused"
        except Exception as e:
            return send_json(handler, {"error": str(e)[:200]}, 502)
        db.run("UPDATE users SET state='paused' WHERE id=?", (user["id"],))
        audit(user["id"], user["username"], "desktop.suspend", cname, handler)
    return send_json(handler, {"state": state})


def api_resume(handler):
    user = require_user(handler)
    if not user:
        return None
    cname = user["container"]
    if not cname:
        return send_json(handler, {"error": "no desktop yet"}, 409)
    state = sync_container_state(user)
    if state == "paused":
        try:
            dock.unpause(cname)
            state = "running"
        except Exception as e:
            return send_json(handler, {"error": str(e)[:200]}, 502)
        db.run("UPDATE users SET state='running', last_beat=? WHERE id=?",
               (db.now(), user["id"]))
        audit(user["id"], user["username"], "desktop.resume", cname, handler)
    return send_json(handler, {"state": state})


def api_ensure(handler):
    user = require_user(handler)
    if not user:
        return None
    try:
        state = ensure_desktop(user)
    except Exception as e:
        return send_json(handler, {"error": str(e)[:200]}, 502)
    audit(user["id"], user["username"], "desktop.ensure", user["username"], handler)
    return send_json(handler, {"state": state})


def snap_name():
    # Unique per call: two snapshots within the same second must not share
    # a tarball (the second would silently overwrite the first).
    return "snap-" + time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + secrets.token_hex(3)


MAX_SNAPSHOTS_PER_USER = 10


def api_snapshots_list(handler):
    user = require_user(handler)
    if not user:
        return None
    rows = db.q("SELECT id,name,size,created_at,note FROM snapshots WHERE owner_id=? ORDER BY id DESC",
                (user["id"],))
    return send_json(handler, {"snapshots": rows})


def api_snapshot_create(handler):
    user = require_user(handler)
    if not user:
        return None
    body = read_json(handler)
    note = str(body.get("note") or "")[:120]
    cname, vname = user["container"], user["volume"]
    if not cname or not vname:
        return send_json(handler, {"error": "no desktop yet"}, 409)
    state = sync_container_state(user)
    was_running = state == "running"
    try:
        if was_running:
            dock.pause(cname)
        name = snap_name()
        out = helper_run_volumes(
            vname,
            f"mkdir -p /backup/{user['id']} && "
            f"tar czf /backup/{user['id']}/{name}.tgz -C /data . && "
            f"stat -c %s /backup/{user['id']}/{name}.tgz",
        )
        size = int(out.strip().splitlines()[-1])
    except Exception as e:
        return send_json(handler, {"error": str(e)[:200]}, 502)
    finally:
        if was_running:
            try:
                dock.unpause(cname)
            except Exception:
                pass
    sid = db.run("INSERT INTO snapshots(owner_id,name,size,created_at,note) VALUES (?,?,?,?,?)",
                 (user["id"], name, size, db.now(), note))
    # Cap stored snapshots per user: disk-fill via snapshot spam.
    # Delete tarballs too (rows alone wouldn't free disk).
    old = db.q("SELECT id, name FROM snapshots WHERE owner_id=? ORDER BY id DESC LIMIT -1 OFFSET ?",
               (user["id"], MAX_SNAPSHOTS_PER_USER))
    for row in old:
        if re.match(r"^snap-[0-9]{8}-[0-9]{6}-[0-9a-f]+$", row["name"] or ""):
            try:
                os.remove(os.path.join(CFG["snap_dir"], str(user["id"]), row["name"] + ".tgz"))
            except OSError:
                pass
        db.run("DELETE FROM snapshots WHERE id=?", (row["id"],))
    audit(user["id"], user["username"], "snapshot.create", name, handler)
    return send_json(handler, {"id": sid, "name": name, "size": size}, 201)


def api_snapshot_restore(handler, sid):
    user = require_user(handler)
    if not user:
        return None
    snap = db.q("SELECT * FROM snapshots WHERE id=? AND owner_id=?", (sid, user["id"]), one=True)
    if not snap:
        return send_json(handler, {"error": "snapshot not found"}, 404)
    cname, vname = user["container"], user["volume"]
    try:
        try:
            dock.unpause(cname)
        except Exception:
            pass
        dock.stop(cname)
        helper_run_volumes(
            vname,
            f"rm -rf /data/* /data/.[!.]* 2>/dev/null; "
            f"tar xzf /backup/{user['id']}/{snap['name']}.tgz -C /data",
        )
        dock.start(cname)
        db.run("UPDATE users SET state='running', last_beat=? WHERE id=?", (db.now(), user["id"]))
    except Exception as e:
        return send_json(handler, {"error": str(e)[:200]}, 502)
    audit(user["id"], user["username"], "snapshot.restore", snap["name"], handler)
    return send_json(handler, {"ok": True})


def api_reset(handler):
    user = require_user(handler)
    if not user:
        return None
    cname, vname = user["container"], user["volume"]
    if not cname or not vname:
        return send_json(handler, {"error": "no desktop yet"}, 409)
    try:
        try:
            dock.unpause(cname)
        except Exception:
            pass
        try:
            dock.stop(cname)
        except Exception:
            pass
        # A stopped container still holds its volume: recreate both.
        try:
            dock.remove_container(cname, force=True)
        except Exception:
            pass
        try:
            dock.remove_volume(vname)
        except Exception as e:
            return send_json(handler, {"error": str(e)[:200]}, 502)
        dock.create_volume(vname)
        _create_computer_container(user, cname, vname)
        dock.start(cname)
        db.run("UPDATE users SET state='running', last_beat=? WHERE id=?", (db.now(), user["id"]))
    except Exception as e:
        return send_json(handler, {"error": str(e)[:200]}, 502)
    audit(user["id"], user["username"], "desktop.reset", cname, handler)
    return send_json(handler, {"ok": True})


def api_shares_list(handler):
    user = require_user(handler)
    if not user:
        return None
    rows = db.q("SELECT token,mode,note,created_at,expires_at,revoked FROM shares"
                " WHERE owner_id=? ORDER BY created_at DESC", (user["id"],))
    return send_json(handler, {"shares": rows})


def api_share_create(handler):
    user = require_user(handler)
    if not user:
        return None
    body = read_json(handler)
    mode = str(body.get("mode") or "view")
    if mode not in ("view", "control"):
        return send_json(handler, {"error": "mode must be view|control"}, 400)
    try:
        ttl = int(body.get("ttl_hours") or 24)
    except (TypeError, ValueError):
        return send_json(handler, {"error": "ttl_hours must be a number"}, 400)
    ttl = max(1, min(24 * 7, ttl))
    note = str(body.get("note") or "")[:120]
    token = "yds_" + secrets.token_hex(16)
    exp = db.now() + ttl * 3600
    db.run("INSERT INTO shares(token,owner_id,mode,note,created_at,expires_at)"
           " VALUES (?,?,?,?,?,?)", (token, user["id"], mode, note, db.now(), exp))
    audit(user["id"], user["username"], "share.create", f"{mode} {token[:12]}…", handler)
    return send_json(handler, {"token": token, "mode": mode,
                               "url": f"#/s/{token}", "expires_at": exp}, 201)


def api_share_revoke(handler, token):
    user = require_user(handler)
    if not user:
        return None
    sh = db.q("SELECT * FROM shares WHERE token=?", (token,), one=True)
    if not sh or (sh["owner_id"] != user["id"] and not user["is_admin"]):
        return send_json(handler, {"error": "share not found"}, 404)
    db.run("UPDATE shares SET revoked=1 WHERE token=?", (token,))
    audit(user["id"], user["username"], "share.revoke", token[:16] + "…", handler)
    return send_json(handler, {"ok": True})


def api_share_resolve(handler, token):
    sh = db.q("SELECT * FROM shares WHERE token=?", (token,), one=True)
    if not sh or sh["revoked"] or sh["expires_at"] < db.now():
        return send_json(handler, {"error": "invalid or expired link"}, 404)
    owner = db.q("SELECT * FROM users WHERE id=?", (sh["owner_id"],), one=True)
    if not owner or not owner["container"]:
        return send_json(handler, {"error": "desktop unavailable"}, 404)
    state = sync_container_state(owner)
    if state == "paused":
        return send_json(handler, {"error": "desktop suspended, ask the owner to resume"}, 409)
    if state != "running":
        return send_json(handler, {"error": f"desktop {state}"}, 409)
    return send_json(handler, {
        "mode": sh["mode"], "base": f"/u/{slug_of(owner['username'])}",
        "expires_at": sh["expires_at"], "owner": owner["username"],
    })


def api_audit(handler):
    user = require_user(handler)
    if not user:
        return None
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    try:
        limit = max(1, min(500, int((qs.get("limit") or ["100"])[0])))
    except ValueError:
        limit = 100
    if user["is_admin"] and (qs.get("all") or [""])[0] == "1":
        rows = db.q("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
    else:
        rows = db.q("SELECT * FROM audit WHERE actor_id=? ORDER BY id DESC LIMIT ?",
                    (user["id"], limit))
    return send_json(handler, {"audit": rows})


# ---------- request dispatcher ----------

class Handler(BaseHTTPRequestHandler):
    server_version = "yourdaas-control/0.1"

    def log_message(self, *args):
        pass

    def _route_api(self):
        p = urllib.parse.urlparse(self.path)
        path = p.path
        if path == "/c/api/health":
            return send_json(self, {"ok": True})
        if path == "/c/api/users/register" and self.command == "POST":
            return api_register(self)
        if path == "/c/api/session" and self.command == "POST":
            return api_login(self)
        if path == "/c/api/session/totp" and self.command == "POST":
            return api_login_totp(self)
        if path == "/c/api/session/logout" and self.command == "POST":
            return api_logout(self)
        if path == "/c/api/me":
            return api_me(self)
        if path == "/c/api/heartbeat" and self.command == "POST":
            # drain body if present (beacon may send {})
            try:
                ln = int(self.headers.get("Content-Length") or 0)
                if ln:
                    self.rfile.read(min(ln, 4096))
            except ValueError:
                pass
            return api_heartbeat(self)
        if path == "/c/api/session/suspend" and self.command == "POST":
            return api_suspend(self)
        if path == "/c/api/session/resume" and self.command == "POST":
            return api_resume(self)
        if path == "/c/api/session/ensure" and self.command == "POST":
            return api_ensure(self)
        if path == "/c/api/snapshots" and self.command == "GET":
            return api_snapshots_list(self)
        if path == "/c/api/snapshots" and self.command == "POST":
            return api_snapshot_create(self)
        m = re.match(r"^/c/api/snapshots/(\d+)/restore$", path)
        if m and self.command == "POST":
            return api_snapshot_restore(self, int(m.group(1)))
        if path == "/c/api/reset" and self.command == "POST":
            return api_reset(self)
        if path == "/c/api/shares" and self.command == "GET":
            return api_shares_list(self)
        if path == "/c/api/shares" and self.command == "POST":
            return api_share_create(self)
        m = re.match(r"^/c/api/shares/(yds_[0-9a-f]+)$", path)
        if m and self.command == "DELETE":
            return api_share_revoke(self, m.group(1))
        if m and self.command == "GET":
            return api_share_resolve(self, m.group(1))
        if path == "/c/api/audit":
            return api_audit(self)
        return send_json(self, {"error": "unknown route"}, 404)

    def _route_proxy(self):
        # /u/<slug>/... -> owner's computer. Auth: owner/admin session or
        # ?token= share. View shares: GET-ish + VNC-filtered WS + audio-out.
        m = re.match(r"^/u/([A-Za-z0-9][A-Za-z0-9_-]*)(/.*)?$", urllib.parse.urlparse(self.path).path)
        if not m:
            return send_json(self, {"error": "unknown route"}, 404)
        slug, sub = m.group(1).lower(), m.group(2) or "/"
        username, mode = resolve_proxy_access(self, slug)
        if not username:
            return send_json(self, {"error": "login or valid share link required"}, 401)
        port, upath = proxy_target(sub)
        if port is None:
            return send_json(self, {"error": "unknown route"}, 404)
        q = urllib.parse.urlparse(self.path).query
        if q:
            upath += ("&" if "?" in upath else "?") + q
        is_ws = self.headers.get("Upgrade", "").lower() == "websocket"
        if mode == "view" and not view_allowed(sub, is_ws, self.command):
            return send_json(self, {"error": "view-only share"}, 403)
        # Suspended desktops fail closed with an actionable error.
        owner = db.q("SELECT * FROM users WHERE username=?", (username,), one=True)
        if owner and sync_container_state(owner) == "paused":
            return send_json(self, {"error": "desktop suspended", "action": "resume"}, 409)
        # Only owner/admin traffic counts as activity: a guest holding a view
        # link open must not keep the owner's container awake (and billable).
        if mode == "full":
            touch_beat(username)
        if is_ws:
            # VNC input filtering applies to websockify only; audio PCM
            # frames may start with the same bytes — never filter those.
            return proxy_ws(self, username, mode if sub.startswith("/websockify") else "full",
                            port, upath)
        return proxy_http(self, username, mode, port, upath)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/c/api/health" or p.startswith("/c/api/"):
            # Public endpoints (health, share resolve) skip auth inside handlers.
            return self._route_api()
        if p.startswith("/u/"):
            return self._route_proxy()
        return send_json(self, {"error": "unknown route"}, 404)

    def do_POST(self):
        return self.do_GET()

    def do_DELETE(self):
        return self.do_GET()

    def do_PUT(self):
        return self.do_GET()


# ---------- idle sweeper ----------

def sweeper():
    while True:
        try:
            time.sleep(CFG["sweep_sec"])
            cutoff = db.now() - CFG["idle_minutes"] * 60
            for u in db.q("SELECT * FROM users WHERE state='running' AND last_beat < ?", (cutoff,)):
                try:
                    dock.pause(container_name(u["username"]))
                    db.run("UPDATE users SET state='paused' WHERE id=?", (u["id"],))
                    # system audit entry (no handler available)
                    db.run("INSERT INTO audit(actor_name,action,target,created_at)"
                           " VALUES (?,?,?,?)", ("system", "desktop.suspend-idle",
                                                 container_name(u["username"]), db.now()))
                    log(f"sweeper: suspended {u['username']} (idle)")
                except Exception as e:
                    log(f"sweeper: suspend {u['username']} failed: {e}")
            # prune expired tickets/sessions, cap audit table
            db.run("DELETE FROM sessions WHERE expires_at < ?", (db.now(),))
            db.run("DELETE FROM audit WHERE id NOT IN "
                   "(SELECT id FROM audit ORDER BY id DESC LIMIT 20000)")
        except Exception as e:
            log(f"sweeper error: {e}")


def main():
    os.makedirs(os.path.dirname(CFG["db"]) or ".", exist_ok=True)
    os.makedirs(CFG["snap_dir"], exist_ok=True)
    db.init(CFG["db"])
    try:
        dock._req("GET", "/version")
    except Exception as e:
        log(f"WARNING: docker socket unreachable ({e}); lifecycle calls will fail")
    threading.Thread(target=sweeper, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", CFG["port"]), Handler)
    log(f"control on :{CFG['port']} (net={CFG['net']}, idle={CFG['idle_minutes']}m)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
