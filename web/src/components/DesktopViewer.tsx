import { useRef, type RefObject } from "react";
import { desktopUrl } from "../api";

interface Props {
  viewOnly: boolean;
  nonce: number;
  wrapRef: RefObject<HTMLDivElement | null>;
}

export function DesktopViewer({ viewOnly, nonce, wrapRef }: Props) {
  const frameRef = useRef<HTMLIFrameElement | null>(null);

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

  return (
    <div className="screen-wrap" ref={wrapRef}>
      <iframe
        key={`${viewOnly}-${nonce}`}
        ref={frameRef}
        title="computer"
        src={desktopUrl(viewOnly)}
        allow="clipboard-read; clipboard-write"
        allowFullScreen
        onLoad={forwardGestures}
      />
    </div>
  );
}
