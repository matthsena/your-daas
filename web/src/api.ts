export interface FileEntry {
  name: string;
  path: string;
  kind: "file" | "dir";
  size: number;
}

// Control-plane prefix (e.g. "/u/alice") routing this client to one user's
// computer through proxying. Legacy single-user mode keeps "".
let ctlBase = "";
export function setCtlBase(prefix: string) {
  ctlBase = prefix;
}

function api(path: string): string {
  return `${ctlBase}${path}`;
}

function audio(path: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}${ctlBase}/audio/${path}`;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { error?: string }).error ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function listFiles(path: string): Promise<{ path: string; entries: FileEntry[] }> {
  const res = await fetch(api(`/api/files?path=${encodeURIComponent(path)}`));
  return json(res);
}

export async function readFile(path: string): Promise<{ path: string; content: string }> {
  const res = await fetch(api(`/api/file?path=${encodeURIComponent(path)}`));
  return json(res);
}

export async function makeDir(path: string): Promise<void> {
  const res = await fetch(api(`/api/mkdir`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  await json(res);
}

export function desktopUrl(viewOnly: boolean, base = "", token?: string): string {
  // Custom chromeless noVNC viewer (no popups/toolbar). Served by the container.
  const q = `view_only=${viewOnly ? "true" : "false"}&base=${encodeURIComponent(base)}`
    + (token ? `&token=${encodeURIComponent(token)}` : "");
  return `${base}/novnc/yourdaas.html?${q}`;
}

export const REMOTE_HOME = "/home/user";
export const REMOTE_DESKTOP = `${REMOTE_HOME}/Desktop`;

export function uploadFile(
  destPath: string,
  file: Blob,
  onProgress?: (loaded: number, total: number) => void,
): Promise<void> {
  // XHR (not fetch): only XHR reports upload progress.
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", api(`/api/upload?path=${encodeURIComponent(destPath)}`));
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress?.(e.loaded, e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else {
        try {
          const body = JSON.parse(xhr.responseText);
          reject(new Error(body.error ?? `HTTP ${xhr.status}`));
        } catch {
          reject(new Error(`HTTP ${xhr.status}`));
        }
      }
    };
    xhr.onerror = () => reject(new Error("upload failed"));
    xhr.send(file);
  });
}

export function audioUrl(path: "out" | "mic"): string {
  // Duplex audio bridge (see docs/AUDIO.md). Same-origin WS via the proxy.
  return audio(path);
}

export function audioUrlCandidates(path: "out" | "mic"): string[] {
  // `localhost` may resolve to ::1 while the stack listens on IPv4 (or the
  // reverse on odd setups). Try the page's host first, then the twin.
  const first = audioUrl(path);
  const u = new URL(first);
  if (u.hostname === "localhost") {
    u.hostname = "127.0.0.1";
    return [first, u.toString()];
  }
  if (u.hostname === "127.0.0.1") {
    u.hostname = "localhost";
    return [first, u.toString()];
  }
  return [first];
}

export async function audioHttpProbe(path: "out" | "mic"): Promise<string> {
  // A plain GET on a WS endpoint returns a short plain-text diagnosis
  // (e.g. why the handshake was rejected). Same origin, no CORS issues.
  for (const url of audioUrlCandidates(path)) {
    try {
      const res = await fetch(url.replace(/^ws/, "http"));
      const body = (await res.text()).trim();
      if (body) return `HTTP ${res.status}: ${body.slice(0, 160)}`;
      return `HTTP ${res.status} (empty)`;
    } catch {
      /* try next candidate */
    }
  }
  return "unreachable";
}

export interface AudioDevice {
  name: string;
  description: string;
  volume: number;
  mute: boolean;
  monitor: boolean;
  default: boolean;
}

export async function listAudioDevices(): Promise<{ sinks: AudioDevice[]; sources: AudioDevice[] }> {
  const res = await fetch(api(`/api/audio/devices`));
  return json(res);
}

export async function setAudioVolume(kind: "sink" | "source", name: string, volume: number): Promise<void> {
  const res = await fetch(api(`/api/audio/volume`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, name, volume }),
  });
  await json(res);
}

export async function setAudioDefault(kind: "sink" | "source", name: string): Promise<void> {
  const res = await fetch(api(`/api/audio/default`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, name }),
  });
  await json(res);
}
