import { useRef, useState } from "react";
import { desktopUrl } from "../api";

export function DesktopViewer() {
  const [viewOnly, setViewOnly] = useState(false);
  const [nonce, setNonce] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);

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
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2>Desktop (Debian no browser)</h2>
          <p>Xvfb + XFCE + Chrome via noVNC. Menu Applications no painel superior.</p>
        </div>
        <div className="row">
          <label className="check">
            <input
              type="checkbox"
              checked={viewOnly}
              onChange={(e) => setViewOnly(e.target.checked)}
            />
            somente ver
          </label>
          <button type="button" onClick={() => setNonce((n) => n + 1)}>
            Reconectar
          </button>
          <button type="button" onClick={fullscreen}>
            Tela cheia
          </button>
          <a className="button" href={desktopUrl(viewOnly)} target="_blank" rel="noreferrer">
            Abrir em aba
          </a>
        </div>
      </header>
      <div className="screen-wrap" ref={wrapRef}>
        <iframe
          key={`${viewOnly}-${nonce}`}
          title="computer"
          src={desktopUrl(viewOnly)}
          allow="clipboard-read; clipboard-write"
          allowFullScreen
        />
      </div>
    </section>
  );
}
