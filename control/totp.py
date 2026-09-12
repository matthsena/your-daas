"""TOTP (RFC 6238, SHA-1, 30s, 6 digits) on stdlib only."""

import base64
import hashlib
import hmac
import secrets
import struct
import time

STEP = 30
DIGITS = 6


def new_secret(nbytes: int = 20) -> str:
    return base64.b32encode(secrets.token_bytes(nbytes)).decode()


def _key(secret: str) -> bytes:
    s = secret.strip().upper()
    s += "=" * (-len(s) % 8)
    return base64.b32decode(s)


def code(secret: str, at: float | None = None) -> str:
    t = int((time.time() if at is None else at) // STEP)
    mac = hmac.new(_key(secret), struct.pack(">Q", t), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    num = struct.unpack(">I", mac[off : off + 4])[0] & 0x7FFFFFFF
    return str(num % (10**DIGITS)).zfill(DIGITS)


def verify(secret: str, value: str, window: int = 1) -> bool:
    value = (value or "").strip()
    if not value.isdigit():
        return False
    now = time.time()
    for skew in range(-window, window + 1):
        if hmac.compare_digest(code(secret, now + skew * STEP), value):
            return True
    return False


def otpauth_url(secret: str, account: str, issuer: str = "YourDaaS") -> str:
    return f"otpauth://totp/{issuer}:{account}?secret={secret}&issuer={issuer}&digits={DIGITS}&period={STEP}"
