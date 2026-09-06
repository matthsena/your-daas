import { useEffect, useRef, useState } from "react";
import {
  audioUrl,
  listAudioDevices,
  setAudioVolume,
} from "../api";

const MIC_WORKLET = `
registerProcessor("yd-mic", class extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) {
      const pcm = new Int16Array(ch.length);
      for (let i = 0; i < ch.length; i++) {
        const s = Math.max(-1, Math.min(1, ch[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }
    return true;
  }
});
`;

interface OutLive {
  ws: WebSocket;
  audio: HTMLAudioElement;
  urls: string[];
}

interface MicLive {
  ws: WebSocket;
  stream: MediaStream;
  ctx: AudioContext;
  urls: string[];
}

export function SoundToggle() {
  // Speaker and mic are fully independent channels.
  const [outState, setOutState] = useState<"off" | "starting" | "on">("off");
  const [outErr, setOutErr] = useState("");
  const [micOn, setMicOn] = useState(false);
  const [micNote, setMicNote] = useState("Turn the microphone on/off");
  // Remote plumbing (Linux side): only the volume target matters here.
  const [outName, setOutName] = useState("");
  const [volume, setVolume] = useState(100);
  // Physical endpoints (native OS side, via the browser).
  const [hostIns, setHostIns] = useState<MediaDeviceInfo[]>([]);
  const [hostOuts, setHostOuts] = useState<MediaDeviceInfo[]>([]);
  const [hostInId, setHostInId] = useState("");
  const [hostOutId, setHostOutId] = useState("");
  const outRef = useRef<OutLive | null>(null);
  const micRef = useRef<MicLive | null>(null);
  const gen = useRef(0);
  const micGen = useRef(0);
  const hostInIdRef = useRef("");
  const hostOutIdRef = useRef("");

  // A dismissed mic-permission prompt never settles in Chrome, so every
  // await here needs a timeout — otherwise buttons hang with no feedback.
  const withTimeout = <T,>(p: Promise<T>, ms: number, label: string): Promise<T> =>
    Promise.race([
      p,
      new Promise<T>((_, reject) => setTimeout(() => reject(new Error(label)), ms)),
    ]);

  const loadDevices = async () => {
    try {
      const dev = await listAudioDevices();
      const out = dev.sinks.find((d) => d.default) ?? dev.sinks[0];
      if (out) {
        setOutName(out.name);
        setVolume(out.volume);
      }
    } catch {
      /* audio service unreachable; buttons will report it */
    }
  };

  const refreshHostDevices = async () => {
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      setHostIns(all.filter((d) => d.kind === "audioinput"));
      setHostOuts(all.filter((d) => d.kind === "audiooutput"));
    } catch {
      /* ignore */
    }
  };

  const cleanupOut = (parts: OutLive) => {
    try { parts.ws.close(); } catch { /* ignore */ }
    parts.audio.pause();
    parts.urls.forEach((u) => URL.revokeObjectURL(u));
  };

  const cleanupMic = (parts: MicLive) => {
    try { parts.ws.close(); } catch { /* ignore */ }
    parts.stream.getTracks().forEach((t) => t.stop());
    void parts.ctx.close().catch(() => undefined);
  };

  const startOut = async (tracker?: { ws: WebSocket | null }): Promise<OutLive> => {
    const urls: string[] = [];
    const audio = new Audio();
    // Muted autoplay is always allowed: start silent, unmute on gesture.
    audio.muted = true;
    const ws = new WebSocket(audioUrl("out"));
    if (tracker) tracker.ws = ws;
    ws.binaryType = "arraybuffer";
    const ready = new Promise<void>((resolve, reject) => {
      const ms = new MediaSource();
      urls.push(URL.createObjectURL(ms));
      audio.src = urls[0];
      ms.addEventListener("sourceopen", () => {
        let sb: SourceBuffer;
        try {
          sb = ms.addSourceBuffer('audio/webm;codecs=opus');
        } catch (e) {
          reject(e);
          return;
        }
        const queue: ArrayBuffer[] = [];
        const pump = () => {
          if (!sb.updating && queue.length && ms.readyState === "open") {
            sb.appendBuffer(queue.shift()!);
          }
        };
        sb.addEventListener("updateend", pump);
        ws.onmessage = (e) => {
          queue.push(e.data as ArrayBuffer);
          if (queue.length > 50) queue.splice(0, queue.length - 50);
          pump();
        };
        resolve();
      }, { once: true });
      ws.onerror = () => reject(new Error("audio channel failed"));
    });
    await ready;
    try {
      await audio.play();
    } catch (e) {
      // Autoplay blocked (no gesture yet): don't leak the socket/ffmpeg.
      try { ws.close(); } catch { /* ignore */ }
      urls.forEach((u) => URL.revokeObjectURL(u));
      throw e;
    }
    return { ws, audio, urls };
  };

  const tryUnmute = () => {
    const a = outRef.current?.audio;
    if (!a || !a.muted) return;
    a.muted = false;
    if (a.paused) void a.play().catch(() => undefined);
  };

  const describeOutErr = (e: unknown): string => {
    const m = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
    if (/NotAllowedError|didn't interact/i.test(m))
      return "Blocked: click anywhere on the page, then Sound";
    if (/audio channel|speaker timeout/i.test(m))
      return "Audio channel unreachable — is the stack running?";
    return `Sound failed: ${m.slice(0, 80)}`;
  };

  const enableOut = async (myGen: number) => {
    if (outRef.current) return;
    setOutState("starting");
    setOutErr("");
    // The socket exists before playback starts: sweep it on every exit
    // path (timeout, stale generation) or its ffmpeg leaks server-side.
    const attempt: { ws: WebSocket | null } = { ws: null };
    const sweep = () => {
      if (attempt.ws) {
        try { attempt.ws.close(); } catch { /* ignore */ }
        attempt.ws = null;
      }
    };
    let parts: OutLive | null = null;
    try {
      parts = await withTimeout(startOut(attempt), 10000, "speaker timeout");
    } catch (e) {
      parts = null;
      if (gen.current === myGen) setOutErr(describeOutErr(e));
    }
    if (!parts || gen.current !== myGen || outRef.current) {
      sweep();
      if (parts) cleanupOut(parts);
      if (gen.current === myGen && !outRef.current) setOutState("off");
      return;
    }
    if (hostOutIdRef.current && typeof parts.audio.setSinkId === "function") {
      try {
        await parts.audio.setSinkId(hostOutIdRef.current);
      } catch {
        /* keep default output */
      }
    }
    outRef.current = parts;
    setOutState("on");
  };

  const disableOut = () => {
    gen.current += 1;
    const cur = outRef.current;
    outRef.current = null;
    if (cur) cleanupOut(cur);
    setOutState("off");
  };

  const startMic = async (deviceId?: string): Promise<MicLive> => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
      },
    });
    const ctx = new AudioContext({ sampleRate: 16000 });
    const urls = [URL.createObjectURL(new Blob([MIC_WORKLET], { type: "application/javascript" }))];
    await ctx.audioWorklet.addModule(urls[0]);
    const ws = new WebSocket(audioUrl("mic"));
    ws.binaryType = "arraybuffer";
    await new Promise<void>((resolve, reject) => {
      ws.onopen = () => resolve();
      ws.onerror = () => reject(new Error("mic channel failed"));
    });
    const src = ctx.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(ctx, "yd-mic");
    const mute = ctx.createGain();
    mute.gain.value = 0;
    src.connect(node);
    node.connect(mute);
    mute.connect(ctx.destination);
    node.port.onmessage = (e) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(e.data as ArrayBuffer);
    };
    return { ws, stream, ctx, urls };
  };

  const attachMic = async (id: string, myGen: number): Promise<boolean> => {
    try {
      const parts = await withTimeout(startMic(id || undefined), 20000, "mic timeout");
      if (micGen.current !== myGen) {
        cleanupMic(parts);
        return false;
      }
      micRef.current = parts;
      setMicOn(true);
      setMicNote("Microphone live");
      void refreshHostDevices();
      return true;
    } catch {
      if (micGen.current === myGen) setMicNote("Mic unavailable — check permission");
      return false;
    }
  };

  const stopMic = () => {
    micGen.current += 1;
    const cur = micRef.current;
    micRef.current = null;
    if (cur) cleanupMic(cur);
    setMicOn(false);
  };

  const toggleMic = () => {
    if (micRef.current) {
      stopMic();
      setMicNote("Turn the microphone on/off");
      return;
    }
    setMicNote("Requesting microphone…");
    void attachMic(hostInIdRef.current, ++micGen.current);
  };

  useEffect(() => {
    void loadDevices();
    void refreshHostDevices();
    // Output defaults to ON: try immediately, and once more on the first
    // gesture (browsers block audio before any interaction).
    const g = ++gen.current;
    void enableOut(g);
    const retry = () => {
      if (outRef.current) {
        tryUnmute();
        return;
      }
      void enableOut(++gen.current);
    };
    window.addEventListener("pointerdown", retry, { once: true });
    window.addEventListener("keydown", retry, { once: true });
    // Clicks/keys inside the desktop iframe never reach the parent window
    // (separate document), so DesktopViewer re-dispatches them here.
    window.addEventListener("yd-gesture", retry);
    const refresh = () => void refreshHostDevices();
    navigator.mediaDevices.addEventListener("devicechange", refresh);
    return () => {
      gen.current += 1;
      micGen.current += 1;
      window.removeEventListener("pointerdown", retry);
      window.removeEventListener("keydown", retry);
      window.removeEventListener("yd-gesture", retry);
      navigator.mediaDevices.removeEventListener("devicechange", refresh);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const changeVolume = (v: number) => {
    setVolume(v);
    if (outName) void setAudioVolume("sink", outName, v).catch(() => undefined);
  };

  const changeHostInput = (id: string) => {
    setHostInId(id);
    hostInIdRef.current = id;
    if (!micRef.current) return; // applies when the mic is toggled on
    stopMic();
    setMicNote("Switching microphone…");
    void attachMic(id, ++micGen.current);
  };

  const changeHostOut = async (id: string) => {
    setHostOutId(id);
    hostOutIdRef.current = id;
    const audio = outRef.current?.audio;
    if (audio && typeof audio.setSinkId === "function") {
      try {
        await audio.setSinkId(id);
      } catch {
        /* device refused; output stays where it was */
      }
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => (outRef.current ? disableOut() : void enableOut(++gen.current))}
        title={outState === "on" ? "Remote sound is on" : "Turn the remote sound on"}
        aria-pressed={outState === "on"}
      >
        {outState === "on" ? "Sound on" : outState === "starting" ? "Sound…" : "Sound off"}
      </button>
      {outErr && <span className="sound-err">{outErr}</span>}
      <button type="button" onClick={toggleMic} title={micNote} aria-pressed={micOn}>
        {micOn ? "Mic on" : "Mic off"}
      </button>
      <label className="sound-row">
        <span>Volume</span>
        <input
          type="range"
          min={0}
          max={100}
          value={volume}
          aria-label="Output volume"
          onChange={(e) => changeVolume(Number(e.target.value))}
        />
        <span className="sound-val">{volume}</span>
      </label>
      <label className="sound-row">
        <span>Output (this PC)</span>
        <select
          aria-label="Output device (this PC)"
          value={hostOutId}
          onChange={(e) => void changeHostOut(e.target.value)}
        >
          <option value="">Default</option>
          {hostOuts.map((d, i) => (
            <option key={d.deviceId} value={d.deviceId}>
              {d.label || `Speaker ${i + 1}`}
            </option>
          ))}
        </select>
      </label>
      <label className="sound-row">
        <span>Input (this PC)</span>
        <select
          aria-label="Input device (this PC)"
          value={hostInId}
          onChange={(e) => changeHostInput(e.target.value)}
        >
          <option value="">Default</option>
          {hostIns.map((d, i) => (
            <option key={d.deviceId} value={d.deviceId}>
              {d.label || `Microphone ${i + 1}`}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}
