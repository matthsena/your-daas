import { useRef, useState, type DragEvent, type RefObject } from "react";
import { desktopUrl, REMOTE_DESKTOP, uploadFile } from "../api";

interface Props {
  viewOnly: boolean;
  nonce: number;
  wrapRef: RefObject<HTMLDivElement | null>;
}

interface DroppedFile {
  path: string;
  file: File;
}

interface Progress {
  done: number;
  total: number;
  current: string;
  percent: number;
  errors: string[];
  finished: boolean;
}

// Recursive walk so dropped folders arrive with their structure intact.
// Plain files (no entries API) fall back to a flat list.
async function collectFiles(dt: DataTransfer): Promise<DroppedFile[]> {
  const out: DroppedFile[] = [];
  const items = [...dt.items].filter((i) => i.kind === "file");
  const entries = items
    .map((i) => (i as DataTransferItem & { webkitGetAsEntry?: () => unknown }).webkitGetAsEntry?.())
    .filter((e): e is FileSystemEntry => !!e);
  if (!entries.length) {
    for (const f of dt.files) out.push({ path: f.name, file: f });
    return out;
  }
  const walk = async (entry: FileSystemEntry, prefix: string): Promise<void> => {
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) =>
        (entry as FileSystemFileEntry).file(resolve, reject),
      );
      out.push({ path: prefix + entry.name, file });
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      for (;;) {
        const batch: FileSystemEntry[] = await new Promise((resolve, reject) =>
          reader.readEntries(resolve, reject),
        );
        if (!batch.length) break;
        for (const e of batch) await walk(e, `${prefix}${entry.name}/`);
      }
    }
  };
  for (const e of entries) await walk(e, "");
  return out;
}

const cleanSegment = (s: string): string => s.replace(/\//g, "").trim();

export function DesktopViewer({ viewOnly, nonce, wrapRef }: Props) {
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);

  // The iframe is same-origin (proxied): forward its gestures to the parent
  // window so features gated on user activation (audio autoplay) unlock
  // when the user interacts with the desktop.
  const forwardGestures = () => {
    const cw = frameRef.current?.contentWindow;
    if (!cw) return;
    const fire = () => window.dispatchEvent(new Event("yd-gesture"));
    cw.addEventListener("pointerdown", fire, { once: true });
    cw.addEventListener("keydown", fire, { once: true });
  };

  const onDragEnter = (e: DragEvent) => {
    if (viewOnly || ![...e.dataTransfer.types].includes("Files")) return;
    e.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
    setProgress(null);
  };

  const onDragLeave = (e: DragEvent) => {
    e.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  };

  const onDrop = async (e: DragEvent) => {
    e.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    if (viewOnly) return;
    const files = (await collectFiles(e.dataTransfer)).filter(
      (f) => f.file.size > 0 && cleanSegment(f.path.split("/").pop() ?? ""),
    );
    if (!files.length) return;
    const errors: string[] = [];
    let done = 0;
    setProgress({ done: 0, total: files.length, current: "", percent: 0, errors, finished: false });
    for (const f of files) {
      const rel = f.path
        .split("/")
        .map(cleanSegment)
        .filter(Boolean)
        .join("/");
      setProgress({ done, total: files.length, current: rel, percent: 0, errors, finished: false });
      try {
        await uploadFile(`${REMOTE_DESKTOP}/${rel}`, f.file, (_loaded, total) =>
          setProgress({
            done,
            total: files.length,
            current: rel,
            percent: total ? Math.round((_loaded / total) * 100) : 0,
            errors,
            finished: false,
          }),
        );
      } catch (err) {
        errors.push(`${rel}: ${err instanceof Error ? err.message : "failed"}`);
      }
      done += 1;
      setProgress({ done, total: files.length, current: rel, percent: 100, errors, finished: done === files.length });
    }
  };

  return (
    <div
      className="screen-wrap"
      ref={wrapRef}
      onDragEnter={onDragEnter}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={onDragLeave}
      onDrop={(e) => void onDrop(e)}
    >
      <iframe
        key={`${viewOnly}-${nonce}`}
        ref={frameRef}
        title="computer"
        src={desktopUrl(viewOnly)}
        allow="clipboard-read; clipboard-write"
        allowFullScreen
        onLoad={forwardGestures}
      />
      {(dragging || progress) && (
        <div className="drop-overlay" aria-label="File drop zone">
          {dragging && !progress && (
            <>
              <strong>Drop to save on the remote Desktop</strong>
              <span>Files and folders keep their structure</span>
            </>
          )}
          {progress && (
            <>
              <strong>
                {progress.finished
                  ? `Done: ${progress.done - progress.errors.length}/${progress.total} uploaded`
                  : `Uploading ${progress.done + 1}/${progress.total}: ${progress.current} (${progress.percent}%)`}
              </strong>
              {progress.errors.length > 0 && (
                <ul className="drop-errors">
                  {progress.errors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              )}
              {progress.finished && (
                <button type="button" onClick={() => setProgress(null)}>
                  Close
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
