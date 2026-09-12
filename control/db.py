"""SQLite store (stdlib). Single shared connection + lock (server is threaded)."""

import hashlib
import secrets
import sqlite3
import threading
import time

_lock = threading.RLock()
_db = None


def init(path: str):
    global _db
    _db = sqlite3.connect(path, check_same_thread=False, timeout=10)
    _db.row_factory = sqlite3.Row
    with _lock, _db:
        _db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
              id INTEGER PRIMARY KEY,
              username TEXT UNIQUE NOT NULL,
              pass_hash TEXT NOT NULL,
              pass_salt TEXT NOT NULL,
              totp_secret TEXT NOT NULL,
              is_admin INTEGER NOT NULL DEFAULT 0,
              container TEXT,
              volume TEXT,
              state TEXT NOT NULL DEFAULT 'none',
              created_at INTEGER NOT NULL,
              last_beat INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions(
              token TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id),
              scope TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shares(
              token TEXT PRIMARY KEY,
              owner_id INTEGER NOT NULL REFERENCES users(id),
              mode TEXT NOT NULL,
              note TEXT NOT NULL DEFAULT '',
              created_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL,
              revoked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS snapshots(
              id INTEGER PRIMARY KEY,
              owner_id INTEGER NOT NULL REFERENCES users(id),
              name TEXT NOT NULL,
              size INTEGER NOT NULL DEFAULT 0,
              created_at INTEGER NOT NULL,
              note TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS audit(
              id INTEGER PRIMARY KEY,
              actor_id INTEGER,
              actor_name TEXT NOT NULL DEFAULT '',
              action TEXT NOT NULL,
              target TEXT NOT NULL DEFAULT '',
              ip TEXT NOT NULL DEFAULT '',
              ua TEXT NOT NULL DEFAULT '',
              created_at INTEGER NOT NULL
            );
            """
        )
    return _db


def q(sql, args=(), one=False):
    with _lock:
        cur = _db.execute(sql, args)
        rows = cur.fetchall()
    if one:
        return dict(rows[0]) if rows else None
    return [dict(r) for r in rows]


def run(sql, args=()):
    with _lock, _db:
        cur = _db.execute(sql, args)
        return cur.lastrowid


def now() -> int:
    return int(time.time())


def hash_password(password: str, salt_hex: str | None = None):
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return h.hex(), salt.hex()
