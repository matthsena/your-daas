import { useCallback, useEffect, useState } from "react";
import {
  createShare,
  createSnapshot,
  ensureDesktop,
  fmtSize,
  fmtTime,
  listAudit,
  listShares,
  listSnapshots,
  resetDesktop,
  restoreSnapshot,
  resumeDesktop,
  revokeShare,
  suspendDesktop,
  type AuditRow,
  type Me,
  type Share,
  type Snapshot,
} from "../control";

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function Console({ me, onChanged, onResumed }: {
  me: Me;
  onChanged: () => void;
  onResumed: () => void;
}) {
  const [status, setStatus] = useState(me);
  const [snaps, setSnaps] = useState<Snapshot[]>([]);
  const [shares, setShares] = useState<Share[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [note, setNote] = useState("");
  const [shareMode, setShareMode] = useState("view");
  const [shareTtl, setShareTtl] = useState("24");
  const [shareNote, setShareNote] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [s1, s2, s3] = await Promise.all([listSnapshots(), listShares(), listAudit()]);
      setSnaps(s1);
      setShares(s2);
      setAudit(s3);
    } catch {
      /* control hiccup: keep stale view */
    }
  }, []);

  useEffect(() => {
    setStatus(me);
    void refresh();
  }, [me, refresh]);

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setMsg(null);
    setBusy(true);
    try {
      await fn();
      if (ok) setMsg(ok);
      onChanged();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "failed");
    } finally {
      setBusy(false);
      void refresh();
    }
  };

  const suspended = status.container.suspended;

  return (
    <div className="console">
      {msg && <p className={msg.startsWith("http") || msg.includes("fail") ? "error" : "ok"}>{msg}</p>}

      <section>
        <h3>Desktop</h3>
        <p>
          State: <strong>{status.container.state || "none"}</strong>
          {suspended && <span className="badge"> suspended — resume to continue</span>}
        </p>
        <p className="muted">Auto-suspends after {status.idle_minutes} min without input.</p>
        <div className="row">
          {suspended ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void run(async () => { await resumeDesktop(); onResumed(); }, "Resumed — reconnecting desktop")}
            >
              Resume
            </button>
          ) : (
            <button type="button" disabled={busy} onClick={() => void run(suspendDesktop, "Suspended")}>
              Suspend
            </button>
          )}
          {confirmReset ? (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={() => void run(resetDesktop, "Reset started — fresh boot incoming").finally(() => setConfirmReset(false))}
              >
                Confirm factory reset
              </button>
              <button type="button" onClick={() => setConfirmReset(false)}>Cancel</button>
            </>
          ) : (
            <button type="button" disabled={busy} onClick={() => setConfirmReset(true)}>
              Factory reset
            </button>
          )}
          <button
            type="button"
            disabled={busy}
            title="Recreate a missing container or volume"
            onClick={() => void run(ensureDesktop, "Desktop ensured")}
          >
            Repair
          </button>
        </div>
      </section>

      <section>
        <h3>Snapshots</h3>
        <div className="row">
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="note (optional)" aria-label="Snapshot note" />
          <button
            type="button"
            disabled={busy}
            onClick={() => void run(async () => { await createSnapshot(note); setNote(""); }, "Snapshot saved")}
          >
            Take snapshot
          </button>
        </div>
        <ul className="list">
          {snaps.map((s) => (
            <li key={s.id}>
              <span>{s.name} · {fmtSize(s.size)} · {fmtTime(s.created_at)}{s.note ? ` · ${s.note}` : ""}</span>
              <button
                type="button"
                disabled={busy}
                onClick={() => void run(() => restoreSnapshot(s.id), "Restoring — desktop will reboot into the snapshot")}
              >
                Restore
              </button>
            </li>
          ))}
          {snaps.length === 0 && <li className="muted">No snapshots yet.</li>}
        </ul>
      </section>

      <section>
        <h3>Share links</h3>
        <p className="muted">View links are enforced read-only (input is dropped by the server).</p>
        <div className="row">
          <select value={shareMode} onChange={(e) => setShareMode(e.target.value)} aria-label="Share mode">
            <option value="view">View only</option>
            <option value="control">View + control</option>
          </select>
          <input
            value={shareTtl}
            onChange={(e) => setShareTtl(e.target.value)}
            placeholder="hours"
            aria-label="Link lifetime in hours"
            inputMode="numeric"
            style={{ width: "5em" }}
          />
          <input value={shareNote} onChange={(e) => setShareNote(e.target.value)} placeholder="note" aria-label="Share note" />
          <button
            type="button"
            disabled={busy}
            onClick={() => void run(async () => {
              const out = await createShare(shareMode, Number(shareTtl) || 24, shareNote);
              setShareNote("");
              const url = `${window.location.origin}${window.location.pathname}#/s/${out.token}`;
              const ok = await copyText(url);
              setMsg(ok ? `Link copied: ${url}` : `Link (copy manually): ${url}`);
            })}
          >
            Create link
          </button>
        </div>
        <ul className="list">
          {shares.map((s) => (
            <li key={s.token}>
              <span>
                {s.mode} · expires {fmtTime(s.expires_at)}{s.revoked ? " · revoked" : ""}{s.note ? ` · ${s.note}` : ""}
              </span>
              {!s.revoked && (
                <button type="button" disabled={busy} onClick={() => void run(() => revokeShare(s.token))}>
                  Revoke
                </button>
              )}
            </li>
          ))}
          {shares.length === 0 && <li className="muted">No links yet.</li>}
        </ul>
      </section>

      <section>
        <h3>Activity</h3>
        <ul className="list audit">
          {audit.map((a) => (
            <li key={a.id}>
              <span>{fmtTime(a.created_at)} · {a.actor_name} · {a.action}{a.target ? ` · ${a.target}` : ""}</span>
            </li>
          ))}
          {audit.length === 0 && <li className="muted">Nothing yet.</li>}
        </ul>
      </section>
    </div>
  );
}
