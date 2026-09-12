import { useEffect, useRef, useState } from "react";
import { resolveShare, type ShareResolve } from "../control";
import { DesktopViewer } from "./DesktopViewer";

export function ShareView({ token }: { token: string }) {
  const [info, setInfo] = useState<ShareResolve | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let live = true;
    resolveShare(token)
      .then((out) => { if (live) setInfo(out); })
      .catch((e: unknown) => { if (live) setError(e instanceof Error ? e.message : "invalid link"); });
    return () => { live = false; };
  }, [token]);

  if (error) {
    return (
      <main className="auth-wrap">
        <section className="panel auth-panel">
          <h1>Link unavailable</h1>
          <p className="error">{error}</p>
        </section>
      </main>
    );
  }
  if (!info) {
    return (
      <main className="auth-wrap">
        <section className="panel auth-panel">
          <p className="muted">Resolving link…</p>
        </section>
      </main>
    );
  }

  return (
    <div className="layout">
      <aside className="side open share-side" aria-label="Shared session info">
        <div className="menu" style={{ display: "flex" }}>
          <strong>{info.owner}&rsquo;s desktop</strong>
          <span className="muted">{info.mode === "view" ? "View only" : "You can interact"}</span>
          <button type="button" onClick={() => setNonce((n) => n + 1)}>
            Reconnect
          </button>
        </div>
      </aside>
      <main className="stage">
        <DesktopViewer
          viewOnly={info.mode === "view"}
          nonce={nonce}
          wrapRef={wrapRef}
          base={info.base}
          token={token}
        />
      </main>
    </div>
  );
}
