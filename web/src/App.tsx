import { useState } from "react";
import { DesktopViewer } from "./components/DesktopViewer";
import { FileManager } from "./components/FileManager";

export function App() {
  const [tab, setTab] = useState<"desktop" | "files">("desktop");

  return (
    <main className="shell">
      <header className="top">
        <div>
          <h1>YourDaaS — your PC in the browser</h1>
          <p>Debian + Xvfb + XFCE + Chrome via noVNC, plus a minimal file manager.</p>
        </div>
        <nav className="tabs" aria-label="Client navigation">
          <button
            type="button"
            className={tab === "desktop" ? "active" : ""}
            onClick={() => setTab("desktop")}
          >
            Desktop
          </button>
          <button
            type="button"
            className={tab === "files" ? "active" : ""}
            onClick={() => setTab("files")}
          >
            Files
          </button>
        </nav>
      </header>
      {tab === "desktop" ? <DesktopViewer /> : <FileManager />}
      <footer>
        Local MVP without auth — only use on <code>127.0.0.1</code>. Do not expose to the internet.
      </footer>
    </main>
  );
}
