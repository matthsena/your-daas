// Control-plane client (/c/api/*, same origin via nginx). Throws Error(message)
// with the server's {error} when present.

async function ctlJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { error?: string }).error ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function post(path: string, body?: unknown): Promise<Response> {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export interface Me {
  user: { id: number; username: string; is_admin: boolean };
  container: { name: string | null; state: string; suspended: boolean };
  base: string;
  idle_minutes: number;
}

export async function fetchMe(): Promise<Me> {
  return ctlJson(await fetch("/c/api/me"));
}

export async function controlAlive(): Promise<boolean> {
  try {
    const signal =
      typeof AbortSignal.timeout === "function" ? AbortSignal.timeout(5000) : undefined;
    const res = await fetch("/c/api/health", { signal });
    return res.ok;
  } catch {
    return false;
  }
}

export async function register(username: string, password: string): Promise<{
  username: string;
  totp_secret: string;
  otpauth_url: string;
  container_state: string;
}> {
  return ctlJson(await post("/c/api/users/register", { username, password }));
}

export async function loginStep1(username: string, password: string): Promise<{ ticket: string }> {
  const res = await post("/c/api/session", { username, password });
  const out = (await ctlJson(res)) as { need_totp?: boolean; ticket?: string };
  if (!out.ticket) throw new Error("unexpected login response");
  return { ticket: out.ticket };
}

export async function loginStep2(ticket: string, code: string): Promise<void> {
  await ctlJson(await post("/c/api/session/totp", { ticket, code }));
}

export async function logout(): Promise<void> {
  await post("/c/api/session/logout").catch(() => undefined);
}

export async function heartbeat(): Promise<void> {
  await post("/c/api/heartbeat", {}).catch(() => undefined);
}

export async function suspendDesktop(): Promise<{ state: string }> {
  return ctlJson(await post("/c/api/session/suspend"));
}

export async function resumeDesktop(): Promise<{ state: string }> {
  return ctlJson(await post("/c/api/session/resume"));
}

export async function ensureDesktop(): Promise<{ state: string }> {
  return ctlJson(await post("/c/api/session/ensure"));
}

export async function resetDesktop(): Promise<void> {
  await ctlJson(await post("/c/api/reset"));
}

export interface Snapshot {
  id: number;
  name: string;
  size: number;
  created_at: number;
  note: string;
}

export async function listSnapshots(): Promise<Snapshot[]> {
  const out = (await ctlJson(await fetch("/c/api/snapshots"))) as { snapshots: Snapshot[] };
  return out.snapshots;
}

export async function createSnapshot(note: string): Promise<Snapshot> {
  return ctlJson(await post("/c/api/snapshots", { note }));
}

export async function restoreSnapshot(id: number): Promise<void> {
  await ctlJson(await post(`/c/api/snapshots/${id}/restore`));
}

export interface Share {
  token: string;
  mode: string;
  note: string;
  created_at: number;
  expires_at: number;
  revoked: number;
}

export async function listShares(): Promise<Share[]> {
  const out = (await ctlJson(await fetch("/c/api/shares"))) as { shares: Share[] };
  return out.shares;
}

export async function createShare(mode: string, ttl_hours: number, note: string): Promise<Share & { url: string; expires_at: number }> {
  return ctlJson(await post("/c/api/shares", { mode, ttl_hours, note }));
}

export async function revokeShare(token: string): Promise<void> {
  const res = await fetch(`/c/api/shares/${encodeURIComponent(token)}`, { method: "DELETE" });
  await ctlJson(res);
}

export interface ShareResolve {
  mode: string;
  base: string;
  expires_at: number;
  owner: string;
}

export async function resolveShare(token: string): Promise<ShareResolve> {
  return ctlJson(await fetch(`/c/api/shares/${encodeURIComponent(token)}`));
}

export interface AuditRow {
  id: number;
  actor_name: string;
  action: string;
  target: string;
  ip: string;
  created_at: number;
}

export async function listAudit(all = false): Promise<AuditRow[]> {
  const out = (await ctlJson(
    await fetch(`/c/api/audit?limit=100${all ? "&all=1" : ""}`),
  )) as { audit: AuditRow[] };
  return out.audit;
}

export function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}
