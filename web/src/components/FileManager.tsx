import { useCallback, useEffect, useState } from "react";
import { listFiles, makeDir, readFile, type FileEntry } from "../api";

const HOME = "/home/user";

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
      setError(e instanceof Error ? e.message : "failed to list");
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
      setError(e instanceof Error ? e.message : "failed to read");
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
      setError(e instanceof Error ? e.message : "failed to create folder");
    }
  };

  return (
    <section className="panel">
      <header className="panel-head">
        <div className="row">
          <button type="button" onClick={() => void load(parent(path))}>
            ↑ Up
          </button>
          <button type="button" onClick={() => void load(path)}>
            Reload
          </button>
        </div>
      </header>

      <code className="path">{loading ? "loading…" : path}</code>
      {error && <p className="error">{error}</p>}

      <div className="row">
        <input
          value={newFolder}
          onChange={(e) => setNewFolder(e.target.value)}
          placeholder="new-folder"
          aria-label="New folder name"
        />
        <button type="button" onClick={() => void create()}>
          Create folder
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
          {entries.length === 0 && !loading && <li className="empty">empty folder</li>}
        </ul>
        <div className="preview">
          {previewPath ? (
            <>
              <strong>{previewPath}</strong>
              <pre>{preview}</pre>
            </>
          ) : (
            <span className="empty">click a text file to preview</span>
          )}
        </div>
      </div>
    </section>
  );
}
