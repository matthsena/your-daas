"""Minimal Docker Engine API client over the unix socket (stdlib only)."""

import http.client
import json
import socket
import urllib.parse


class _UDS(http.client.HTTPConnection):
    def __init__(self, sock_path: str):
        super().__init__("localhost")
        self._sock_path = sock_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.sock.connect(self._sock_path)


class Docker:
    def __init__(self, sock_path: str = "/var/run/docker.sock"):
        self.sock_path = sock_path

    def _req(self, method, path, body=None, raw: bytes | None = None):
        c = _UDS(self.sock_path)
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if raw is not None:
            data = raw
        c.request(method, path, body=data, headers=headers)
        res = c.getresponse()
        payload = res.read()
        c.close()
        if res.status >= 400:
            raise RuntimeError(f"docker {method} {path}: {res.status} {payload[:200]!r}")
        ctype = res.getheader("Content-Type", "")
        if payload and "json" in ctype:
            return json.loads(payload)
        return payload

    # ---- containers ----
    def inspect_container(self, name):
        try:
            return self._req("GET", f"/containers/{urllib.parse.quote(name, safe='')}/json")
        except RuntimeError as e:
            if " 404 " in str(e):
                return None
            raise

    def create_container(self, name, image, binds, network, labels, env=None):
        body = {
            "Image": image,
            "Env": env or [],
            "Labels": labels or {},
            "HostConfig": {"Binds": binds, "RestartPolicy": {"Name": "unless-stopped"}},
            "NetworkingConfig": {"EndpointsConfig": {network: {}}},
        }
        out = self._req("POST", f"/containers/create?name={urllib.parse.quote(name, safe='')}", body)
        return out["Id"]

    def start(self, ref):
        self._req("POST", f"/containers/{ref}/start")

    def stop(self, ref, timeout=10):
        self._req("POST", f"/containers/{ref}/stop?t={timeout}")

    def pause(self, ref):
        self._req("POST", f"/containers/{ref}/pause")

    def unpause(self, ref):
        self._req("POST", f"/containers/{ref}/unpause")

    def remove_container(self, ref, force=False):
        q = "?force=1" if force else ""
        self._req("DELETE", f"/containers/{ref}{q}")

    def wait(self, ref, timeout=300):
        c = _UDS(self.sock_path)
        c.sock.settimeout(timeout + 10)
        c.request("POST", f"/containers/{ref}/wait")
        res = c.getresponse()
        payload = res.read()
        c.close()
        return json.loads(payload) if payload else {}

    # ---- volumes ----
    def create_volume(self, name):
        try:
            return self._req("POST", "/volumes/create", {"Name": name})
        except RuntimeError as e:
            if " 409 " in str(e) or "already exists" in str(e):
                return {"Name": name}
            raise

    def remove_volume(self, name):
        self._req("DELETE", f"/volumes/{urllib.parse.quote(name, safe='')}")

    # ---- state helper ----
    @staticmethod
    def state_of(info) -> str:
        if not info:
            return "missing"
        st = (info.get("State") or {})
        if st.get("Paused"):
            return "paused"
        if st.get("Running"):
            return "running"
        return st.get("Status", "unknown")
