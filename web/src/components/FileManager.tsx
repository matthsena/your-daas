import { useCallback, useEffect, useState } from "react";
import { listFiles, makeDir, readFile, type FileEntry } from "../api";

const HOME = "/home/rakazo";

function parent(path: string): string {
  if (path === "/" || path === HOME) return HOME;
  const cut = path.lastIndexOf("/");
  return cut <= 0 ? "/" : path.slice(0, cut);
}

export function FileManager() {
  const [path, setPath] = useState(HOME);
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [newFolder, setNewFolder] = useState("");

  const load = useCallback(async (next: string) => {
    setLoading(true);
    setError(null);
    try {
      const out = await listFiles(next);
      setPath(out.path);
      setEntries(out.entries);
    } catch (e) {
      setError(e instanceof Error ? e.message : "falha ao listar");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(HOME);
  }, [load]);

  const open = async (entry: FileEntry) => {
    if (entry.kind === "dir") {
      setPreview(null);
      setPreviewPath(null);
      await load(entry.path);
      return;
    }
    setError(null);
    try {
      const out = await readFile(entry.path);
      setPreviewPath(out.path);
      setPreview(out.content);
    } catch (e) {
      setError(e instanceof Error ? e.message : "falha ao ler");
    }
  };

  const create = async () => {
    const name = newFolder.trim().replace(/\//g, "");
    if (!name) return;
    setError(null);
    try {
      await makeDir(`${path}/${name}`);
      setNewFolder("");
      await load(path);
    } catch (e) {
      setError(e instanceof Error ? e.message : "falha ao criar pasta");
    }
  };

  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2>Arquivos</h2>
          <p>Gerenciador mínimo sobre a file-api do container. Preso ao home.</p>
        </div>
        <div className="row">
          <button type="button" onClick={() => void load(parent(path))}>
            ↑ Voltar
          </button>
          <button type="button" onClick={() => void load(path)}>
            Recarregar
          </button>
        </div>
      </header>

      <code className="path">{loading ? "carregando…" : path}</code>
      {error && <p className="error">{error}</p>}

      <div className="row">
        <input
          value={newFolder}
          onChange={(e) => setNewFolder(e.target.value)}
          placeholder="nova-pasta"
          aria-label="Nome da nova pasta"
        />
        <button type="button" onClick={() => void create()}>
          Criar pasta
        </button>
      </div>

      <div className="files">
        <ul>
          {entries.map((entry) => (
            <li key={entry.path}>
              <button type="button" onClick={() => void open(entry)} title={entry.path}>
                <span>{entry.kind === "dir" ? "📁" : "📄"}</span>
                <span className="name">{entry.name}</span>
                <span className="size">
                  {entry.kind === "dir" ? "" : `${(entry.size / 1024).toFixed(1)} KB`}
                </span>
              </button>
            </li>
          ))}
          {entries.length === 0 && !loading && <li className="empty">pasta vazia</li>}
        </ul>
        <div className="preview">
          {previewPath ? (
            <>
              <strong>{previewPath}</strong>
              <pre>{preview}</pre>
            </>
          ) : (
            <span className="empty">clique num arquivo de texto para pré-visualizar</span>
          )}
        </div>
      </div>
    </section>
  );
}
