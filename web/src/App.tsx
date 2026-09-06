import { useState } from "react";
import { DesktopViewer } from "./components/DesktopViewer";
import { FileManager } from "./components/FileManager";

export function App() {
  const [tab, setTab] = useState<"desktop" | "arquivos">("desktop");

  return (
    <main className="shell">
      <header className="top">
        <div>
          <h1>Premissa — OS no browser</h1>
          <p>MVP: Debian bookworm-slim + Xvfb + XFCE + noVNC + gerenciador de arquivos.</p>
        </div>
        <nav className="tabs" aria-label="Navegação do MVP">
          <button
            type="button"
            className={tab === "desktop" ? "active" : ""}
            onClick={() => setTab("desktop")}
          >
            Desktop
          </button>
          <button
            type="button"
            className={tab === "arquivos" ? "active" : ""}
            onClick={() => setTab("arquivos")}
          >
            Arquivos
          </button>
        </nav>
      </header>
      {tab === "desktop" ? <DesktopViewer /> : <FileManager />}
      <footer>
        MVP local sem auth — só use em <code>127.0.0.1</code>. Não exponha na internet.
      </footer>
    </main>
  );
}
