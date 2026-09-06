export interface FileEntry {
  name: string;
  path: string;
  kind: "file" | "dir";
  size: number;
}

const base = ""; // same origin: vite proxies in dev, nginx in prod. No prefix.

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { error?: string }).error ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function listFiles(path: string): Promise<{ path: string; entries: FileEntry[] }> {
  const res = await fetch(`${base}/api/files?path=${encodeURIComponent(path)}`);
  return json(res);
}

export async function readFile(path: string): Promise<{ path: string; content: string }> {
  const res = await fetch(`${base}/api/file?path=${encodeURIComponent(path)}`);
  return json(res);
}

export async function makeDir(path: string): Promise<void> {
  const res = await fetch(`${base}/api/mkdir`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  await json(res);
}

export function desktopUrl(viewOnly: boolean): string {
  // Custom chromeless noVNC viewer (no popups/toolbar). Served by the container.
  return `/novnc/yourdaas.html?view_only=${viewOnly ? "true" : "false"}`;
}

export function audioUrl(path: "out" | "mic"): string {
  // Duplex audio bridge (see docs/AUDIO.md). Same-origin WS via the proxy.
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/audio/${path}`;
}
