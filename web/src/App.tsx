import { useCallback, useEffect, useRef, useState } from "react";
import { DesktopViewer } from "./components/DesktopViewer";
import { FileManager } from "./components/FileManager";
import { SoundToggle } from "./components/SoundToggle";
import { Login } from "./components/Login";
import { Console } from "./components/Console";
import { ShareView } from "./components/ShareView";
import { fetchMe, controlAlive, heartbeat, logout, type Me } from "./control";
import { setCtlBase as setApiBase } from "./api";

function shareToken(): string | null {
  const m = window.location.hash.match(/^#\/s\/([A-Za-z0-9_]+)/);
  return m ? m[1] : null;
}

export function App() {
  const [route, setRoute] = useState(window.location.hash);
  const [mode, setMode] = useState<"loading" | "legacy" | "login" | "console">("loading");
  const [me, setMe] = useState<Me | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [viewOnly, setViewOnly] = useState(false);
  const [nonce, setNonce] = useState(0);
  const [filesOpen, setFilesOpen] = useState(false);
  const [sessionOpen, setSessionOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const refreshMe = useCallback(async () => {
    try {
      const out = await fetchMe();
      setApiBase(out.base);
      setMe(out);
      setMode("console");
    } catch {
      setMode("login");
    }
  }, []);

  useEffect(() => {
    const onHash = () => setRoute(window.location.hash);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (shareToken()) return; // share view needs no session
    let live = true;
    controlAlive().then((ok) => {
      if (!live) return;
      if (!ok) {
        setMode("legacy"); // single-user stack without control plane
        return;
      }
      void refreshMe();
    });
    return () => { live = false; };
  }, [refreshMe, route]);

  // Heartbeat on genuine input (drives idle auto-suspend). Throttled.
  useEffect(() => {
    if (mode !== "console") return;
    let last = 0;
    const beat = () => {
      const now = Date.now();
      if (now - last < 60000) return;
      last = now;
      void heartbeat();
    };
    window.addEventListener("pointerdown", beat);
    window.addEventListener("keydown", beat);
    return () => {
      window.removeEventListener("pointerdown", beat);
      window.removeEventListener("keydown", beat);
    };
  }, [mode]);

  const token = shareToken();
  if (token) return <ShareView token={token} />;

  if (mode === "loading") {
    return (
      <main className="auth-wrap">
        <section className="panel auth-panel"><p className="muted">Loading…</p></section>
      </main>
    );
  }
  if (mode === "login") {
    return <Login onDone={() => void refreshMe()} />;
  }

  const fullscreen = () => {
    const el = wrapRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      void document.exitFullscreen().catch(() => undefined);
    } else {
      void el.requestFullscreen().catch(() => undefined);
    }
  };

  return (
    <div className="layout">
      <aside className={menuOpen ? "side open" : "side"} aria-label="Command menu">
        <button
          type="button"
          className="menu-toggle"
          aria-expanded={menuOpen}
          aria-label={menuOpen ? "Collapse menu" : "Expand menu"}
          onClick={() => setMenuOpen((v) => !v)}
        >
          {menuOpen ? "✕" : "☰"}
        </button>
        <div className="menu">
          <label className="check">
            <input
              type="checkbox"
              checked={viewOnly}
              onChange={(e) => setViewOnly(e.target.checked)}
            />
            View only
          </label>
          <button type="button" onClick={() => setNonce((n) => n + 1)}>
            Reconnect
          </button>
          <button type="button" onClick={fullscreen}>
            Fullscreen
          </button>
          <SoundToggle />
          <button type="button" onClick={() => setFilesOpen(true)}>
            Files
          </button>
          {mode === "console" && (
            <>
              <button type="button" onClick={() => setSessionOpen(true)}>
                Session
              </button>
              <button
                type="button"
                onClick={() => void logout().then(() => {
                  setApiBase("");
                  setMe(null);
                  setMode("login");
                })}
              >
                Sign out{me ? ` (${me.user.username})` : ""}
              </button>
            </>
          )}
        </div>
      </aside>

      <main className="stage">
        <DesktopViewer viewOnly={viewOnly} nonce={nonce} wrapRef={wrapRef} base={me?.base ?? ""} />
      </main>

      {filesOpen && (
        <div className="drawer" role="dialog" aria-label="Files">
          <div className="drawer-head">
            <strong>Files</strong>
            <button type="button" onClick={() => setFilesOpen(false)} aria-label="Close files">
              ✕
            </button>
          </div>
          <FileManager />
        </div>
      )}

      {sessionOpen && me && (
        <div className="drawer" role="dialog" aria-label="Session">
          <div className="drawer-head">
            <strong>Session</strong>
            <button type="button" onClick={() => setSessionOpen(false)} aria-label="Close session">
              ✕
            </button>
          </div>
          <Console
            me={me}
            onChanged={() => void refreshMe()}
            onResumed={() => {
              setSessionOpen(false);
              setTimeout(() => setNonce((n) => n + 1), 1500);
            }}
          />
        </div>
      )}
    </div>
  );
}
