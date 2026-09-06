import { useEffect, useRef, useState } from "react";
import {
  audioUrl,
  listAudioDevices,
  setAudioDefault,
  setAudioVolume,
  type AudioDevice,
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

interface Live {
  outWs: WebSocket | null;
  micWs: WebSocket | null;
  audio: HTMLAudioElement;
  urls: string[];
  stream: MediaStream | null;
  ctx: AudioContext | null;
}

export function SoundToggle() {
  const [on, setOn] = useState(false);
  const [note, setNote] = useState("Turn the remote sound on/off");
  const [sinks, setSinks] = useState<AudioDevice[]>([]);
  const [sources, setSources] = useState<AudioDevice[]>([]);
  const [outName, setOutName] = useState("");
  const [inName, setInName] = useState("");
  const [volume, setVolume] = useState(100);
  const live = useRef<Live | null>(null);

  const loadDevices = async () => {
    try {
      const dev = await listAudioDevices();
      setSinks(dev.sinks);
      setSources(dev.sources);
      const out = dev.sinks.find((d) => d.default) ?? dev.sinks[0];
      const inp = dev.sources.find((d) => d.default) ?? dev.sources[0];
      if (out) {
        setOutName(out.name);
        setVolume(out.volume);
      }
      if (inp) setInName(inp.name);
    } catch {
      /* audio service unreachable; toggle will report it */
    }
  };

  useEffect(() => {
    void loadDevices();
  }, []);

  const stop = () => {
    const cur = live.current;
    live.current = null;
    if (!cur) return;
    try { cur.outWs?.close(); } catch { /* ignore */ }
    try { cur.micWs?.close(); } catch { /* ignore */ }
    cur.audio.pause();
    cur.urls.forEach((u) => URL.revokeObjectURL(u));
    cur.stream?.getTracks().forEach((t) => t.stop());
    void cur.ctx?.close().catch(() => undefined);
  };

  const startOut = async (): Promise<{ ws: WebSocket; audio: HTMLAudioElement; urls: string[] }> => {
    const urls: string[] = [];
    const audio = new Audio();
    const ws = new WebSocket(audioUrl("out"));
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
    await audio.play();
    return { ws, audio, urls };
  };

  const startMic = async (): Promise<{ ws: WebSocket; stream: MediaStream; ctx: AudioContext; urls: string[] }> => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true },
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

  const toggle = async () => {
    if (live.current) {
      stop();
      setOn(false);
      setNote("Turn the remote sound on/off");
      return;
    }
    // Speaker and mic are independent: one may work without the other.
    const problems: string[] = [];
    let out: { ws: WebSocket; audio: HTMLAudioElement; urls: string[] } | null = null;
    let mic: { ws: WebSocket; stream: MediaStream; ctx: AudioContext; urls: string[] } | null = null;
    try {
      out = await startOut();
    } catch {
      problems.push("no speaker");
    }
    try {
      mic = await startMic();
    } catch {
      problems.push("no mic");
    }
    if (!out && !mic) {
      setNote("Sound unavailable — check the connection and mic permission");
      return;
    }
    live.current = {
      outWs: out ? out.ws : null,
      micWs: mic ? mic.ws : null,
      audio: out ? out.audio : new Audio(),
      urls: [...(out ? out.urls : []), ...(mic ? mic.urls : [])],
      stream: mic ? mic.stream : null,
      ctx: mic ? mic.ctx : null,
    };
    setOn(true);
    setNote(problems.length ? `On (${problems.join(", ")} unavailable)` : "Remote sound is on");
  };

  const changeVolume = (v: number) => {
    setVolume(v);
    if (outName) void setAudioVolume("sink", outName, v).catch(() => undefined);
  };

  const changeDefault = async (kind: "sink" | "source", name: string) => {
    if (!name) return;
    try {
      await setAudioDefault(kind, name);
      await loadDevices();
    } catch {
      /* keep previous selection */
    }
  };

  return (
    <>
      <button type="button" onClick={() => void toggle()} title={note} aria-pressed={on}>
        {on ? "Sound on" : "Sound off"}
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
        <span>Output</span>
        <select
          aria-label="Output device"
          value={outName}
          onChange={(e) => {
            setOutName(e.target.value);
            const dev = sinks.find((d) => d.name === e.target.value);
            if (dev) setVolume(dev.volume);
            void changeDefault("sink", e.target.value);
          }}
        >
          {sinks.map((d) => (
            <option key={d.name} value={d.name}>
              {d.description}
            </option>
          ))}
        </select>
      </label>
      <label className="sound-row">
        <span>Input</span>
        <select
          aria-label="Input device"
          value={inName}
          onChange={(e) => {
            setInName(e.target.value);
            void changeDefault("source", e.target.value);
          }}
        >
          {sources.map((d) => (
            <option key={d.name} value={d.name}>
              {d.description}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}
