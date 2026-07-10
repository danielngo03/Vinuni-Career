/**
 * Tier V3 (preferred) — true full-duplex realtime voice for the AI mock
 * interview, streamed through OUR server relay.
 *
 * This is the highest-quality voice tier: the student's mic audio is streamed to
 * our backend, which relays it to the live-voice model and streams the
 * interviewer's native audio back — a real-time spoken conversation. It is used
 * only when prep advertises `realtime_relay` and the session is created with
 * `modality: "realtime"`.
 *
 * Transport & safety:
 * - Connects to `{wsBase}/mock-interview/sessions/{id}/live?token={access}` where
 *   `wsBase` is {@link env.apiBaseUrl} with `http`→`ws` / `https`→`wss`. The
 *   access token rides as a query param because browsers cannot set a WS
 *   `Authorization` header. No provider/model/prompt identity is ever referenced
 *   — the relay keeps all of that server-side.
 * - Mic → mono PCM16 LE @ 16 kHz sent as raw BINARY frames. Interviewer audio
 *   arrives as raw BINARY PCM16 @ 24 kHz and is played back gaplessly with a
 *   barge-in flush. Everything reuses the shared {@link MicCapture} +
 *   {@link Pcm24Player} machinery.
 * - Transcripts are persisted server-side by the relay, so this client never
 *   records turns — it only renders live captions and drives the presence orb.
 */

import { env } from "@/lib/env";
import { getAccessToken } from "@/lib/api/session";
import {
  MicCapture,
  MicCaptureError,
  Pcm24Player,
  float32ToPcm16Bytes,
  pcm16BytesToFloat32,
} from "./live-audio";

/* ------------------------------ public types ------------------------------ */

/** Interviewer-audio presence for the orb: playing vs. waiting for the student. */
export type RelayVoiceState = "speaking" | "listening";

export type RelayErrorReason =
  | "mic_denied"
  | "unsupported"
  | "connection_failed"
  | "connection_lost"
  | "server_error";

export interface LiveRelayHandlers {
  /** Session is live; the interviewer will speak the first question automatically. */
  onReady?: () => void;
  /** Incremental transcript of what the STUDENT said (for live captions). */
  onInputTranscript?: (text: string) => void;
  /** Incremental transcript of what the INTERVIEWER said (for live captions). */
  onOutputTranscript?: (text: string) => void;
  /** The interviewer finished its turn. */
  onTurnComplete?: () => void;
  /** Leak-safe failure; the caller degrades (text / turn-based tier). */
  onError?: (reason: RelayErrorReason) => void;
  /** Orb state: interviewer speaking vs. waiting for the student. */
  onStateChange?: (state: RelayVoiceState) => void;
}

/* -------------------------- server message shape -------------------------- */

interface RelayControlMessage {
  type?: string;
  text?: string;
  reason?: string;
}

/* --------------------------------- helpers -------------------------------- */

/**
 * Derive the WebSocket base from {@link env.apiBaseUrl} (which already ends in
 * `/api/v1`). Handles an absolute base (`http(s)://host/api/v1`) and a relative
 * same-origin base (`/api/v1`, resolved against the current origin).
 */
export function deriveWsBase(): string {
  const base = env.apiBaseUrl.replace(/\/$/, "");
  if (base.startsWith("http://")) return `ws://${base.slice("http://".length)}`;
  if (base.startsWith("https://")) return `wss://${base.slice("https://".length)}`;
  // Relative base ("/api/v1") → resolve against the current origin.
  if (typeof window !== "undefined") {
    const origin = window.location.origin;
    const wsOrigin = origin.startsWith("https://")
      ? `wss://${origin.slice("https://".length)}`
      : `ws://${origin.slice("http://".length)}`;
    return `${wsOrigin}${base.startsWith("/") ? "" : "/"}${base}`;
  }
  return base;
}

/* -------------------------------- client ---------------------------------- */

export class LiveRelayClient {
  private handlers: LiveRelayHandlers = {};
  private sessionId = "";

  /* transport */
  private ws: WebSocket | null = null;
  private ready = false;
  private triedReconnect = false;

  /* audio (shared machinery) */
  private mic: MicCapture | null = null;
  private player: Pcm24Player | null = null;

  /* lifecycle */
  private started = false;
  private ended = false;
  /** True while the student is holding/toggled the push-to-talk mic. */
  private speaking = false;

  /** Current mic amplitude in [0,1] for the presence orb (0 if no analyser). */
  get level(): number {
    return this.mic?.level ?? 0;
  }

  /** Interviewer playback amplitude in [0,1] for avatar lip movement. */
  get outputLevel(): number {
    return this.player?.level ?? 0;
  }

  /** True while the student's push-to-talk is engaged. */
  get isSpeaking(): boolean {
    return this.speaking;
  }

  /* -------------------------------- connect ------------------------------- */

  /**
   * Acquire the mic (permission prompt up front so a denial degrades before we
   * ever open the socket), build the audio graph, then open the relay WS and
   * wait for `{"type":"ready"}`. Rejects (after firing `onError`) on mic denial
   * or missing Web Audio so the caller can fall back.
   */
  async connect(sessionId: string, handlers: LiveRelayHandlers): Promise<void> {
    if (this.started) return;
    this.started = true;
    this.sessionId = sessionId;
    this.handlers = handlers;

    if (typeof WebSocket === "undefined") {
      this.emitError("unsupported");
      throw new Error("websocket unsupported");
    }

    // 1) Mic first — the permission prompt happens before we connect.
    const mic = new MicCapture((frames) => this.onFrames(frames));
    this.mic = mic;
    try {
      await mic.start();
    } catch (err) {
      const reason: RelayErrorReason =
        err instanceof MicCaptureError && err.reason === "mic_denied"
          ? "mic_denied"
          : "unsupported";
      this.mic = null;
      this.emitError(reason);
      throw new Error(reason);
    }
    if (this.ended) {
      mic.teardown();
      this.mic = null;
      return;
    }

    // 2) Playback graph. Fatal if Web Audio output is unavailable.
    try {
      const player = new Pcm24Player({
        onSpeakingChange: (s) => {
          if (!this.ended) this.handlers.onStateChange?.(s ? "speaking" : "listening");
        },
      });
      player.setup();
      this.player = player;
    } catch {
      mic.teardown();
      this.mic = null;
      this.emitError("unsupported");
      throw new Error("web audio unavailable");
    }

    // 3) Open the relay socket. `ready` / audio arrive over it.
    this.openSocket();
  }

  /* ------------------------------- transport ------------------------------ */

  private openSocket(): void {
    const wsBase = deriveWsBase();
    const token = getAccessToken();
    const url =
      `${wsBase}/mock-interview/sessions/${encodeURIComponent(this.sessionId)}/live` +
      `?token=${encodeURIComponent(token ?? "")}`;

    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      this.handleTransportFailure();
      return;
    }
    // Interviewer audio arrives as raw bytes — take ArrayBuffers, not Blobs.
    ws.binaryType = "arraybuffer";
    this.ws = ws;

    ws.onopen = () => {
      /* Nothing to send — we wait for the server's {"type":"ready"}. */
    };
    ws.onmessage = (event: MessageEvent) => {
      void this.onSocketMessage(event.data);
    };
    ws.onerror = () => {
      /* onclose carries the actionable signal; avoid double-handling here. */
    };
    ws.onclose = () => {
      if (this.ended || this.ws !== ws) return;
      this.handleTransportFailure();
    };
  }

  private handleTransportFailure(): void {
    if (this.ended) return;
    // Never became ready → one bounded reconnect attempt (do NOT retry hard).
    if (!this.ready && !this.triedReconnect) {
      this.triedReconnect = true;
      try {
        this.ws?.close();
      } catch {
        /* ignore */
      }
      this.ws = null;
      this.openSocket();
      return;
    }
    const reason: RelayErrorReason = this.ready ? "connection_lost" : "connection_failed";
    this.emitError(reason);
    this.teardown();
  }

  private async onSocketMessage(data: unknown): Promise<void> {
    // Binary interviewer audio (PCM16 @ 24 kHz) → gapless playback.
    if (data instanceof ArrayBuffer) {
      this.player?.enqueue(pcm16BytesToFloat32(new Uint8Array(data)));
      return;
    }
    if (typeof Blob !== "undefined" && data instanceof Blob) {
      const buf = await data.arrayBuffer();
      this.player?.enqueue(pcm16BytesToFloat32(new Uint8Array(buf)));
      return;
    }
    if (typeof data !== "string") return;

    let msg: RelayControlMessage;
    try {
      const parsed: unknown = JSON.parse(data);
      if (!parsed || typeof parsed !== "object") return;
      msg = parsed as RelayControlMessage;
    } catch {
      return;
    }

    switch (msg.type) {
      case "ready":
        this.ready = true;
        this.handlers.onReady?.();
        break;
      case "input_transcript":
        if (msg.text) this.handlers.onInputTranscript?.(msg.text);
        break;
      case "output_transcript":
        if (msg.text) this.handlers.onOutputTranscript?.(msg.text);
        break;
      case "interrupted":
        // Barge-in from the server side → drop any queued interviewer audio.
        this.player?.flush();
        break;
      case "turn_complete":
        this.handlers.onTurnComplete?.();
        break;
      case "error":
        // Leak-safe reason; we don't surface it, we just degrade.
        this.emitError("server_error");
        this.teardown();
        break;
      default:
        break;
    }
  }

  /* --------------------------- push-to-talk mic --------------------------- */

  /** Student began speaking: flush the interviewer (barge-in), then stream mic. */
  startSpeaking(): void {
    if (this.ended || !this.ready || this.speaking) return;
    this.speaking = true;
    // Barge-in: cut any interviewer audio the instant the student speaks.
    this.player?.flush();
    this.safeSend({ type: "activity_start" });
  }

  /** Student stopped: signal end-of-turn so the interviewer may answer. */
  stopSpeaking(): void {
    if (this.ended || !this.speaking) return;
    this.speaking = false;
    this.safeSend({ type: "activity_end" });
  }

  private onFrames(frames: Float32Array): void {
    if (this.ended || !this.ready || !this.speaking || frames.length === 0) return;
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try {
      ws.send(float32ToPcm16Bytes(frames));
    } catch {
      /* a failed send surfaces via onclose. */
    }
  }

  /* --------------------------------- end ---------------------------------- */

  /** User-initiated end: say bye (server persists the transcript), then release. */
  async end(): Promise<void> {
    if (this.ended) return;
    this.safeSend({ type: "bye" });
    this.teardown();
  }

  private teardown(): void {
    if (this.ended) return;
    this.ended = true;
    this.ready = false;
    this.speaking = false;

    this.mic?.teardown();
    this.mic = null;
    this.player?.teardown();
    this.player = null;

    try {
      this.ws?.close();
    } catch {
      /* ignore */
    }
    this.ws = null;
  }

  private safeSend(payload: unknown): void {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try {
      ws.send(JSON.stringify(payload));
    } catch {
      /* a failed send surfaces via onclose. */
    }
  }

  private emitError(reason: RelayErrorReason): void {
    this.handlers.onError?.(reason);
  }
}
