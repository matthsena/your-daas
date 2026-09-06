import type { RefObject } from "react";
import { desktopUrl } from "../api";

interface Props {
  viewOnly: boolean;
  nonce: number;
  wrapRef: RefObject<HTMLDivElement | null>;
}

export function DesktopViewer({ viewOnly, nonce, wrapRef }: Props) {
  return (
    <div className="screen-wrap" ref={wrapRef}>
      <iframe
        key={`${viewOnly}-${nonce}`}
        title="computer"
        src={desktopUrl(viewOnly)}
        allow="clipboard-read; clipboard-write"
        allowFullScreen
      />
    </div>
  );
}
