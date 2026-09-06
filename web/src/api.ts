export interface FileEntry {
  name: string;
  path: string;
  kind: "file" | "dir";
  size: number;
}

const base = ""; // mesmo origin: vite faz proxy, nginx faz proxy. Sem prefixo.

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
  // Viewer próprio sem chrome do noVNC (sem popups/barra). Servido pelo container.
  return `/novnc/premissa.html?view_only=${viewOnly ? "true" : "false"}`;
}
