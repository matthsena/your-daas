import { useRef, useState } from "react";
import { DesktopViewer } from "./components/DesktopViewer";
import { FileManager } from "./components/FileManager";
import { SoundToggle } from "./components/SoundToggle";

export function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [viewOnly, setViewOnly] = useState(false);
  const [nonce, setNonce] = useState(0);
  const [filesOpen, setFilesOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);

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
        </div>
      </aside>

      <main className="stage">
        <DesktopViewer viewOnly={viewOnly} nonce={nonce} wrapRef={wrapRef} />
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
    </div>
  );
}
