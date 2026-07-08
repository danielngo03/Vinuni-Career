/**
 * Browser voice primitives for the AI mock interview.
 *
 * Tiering (see mock-interview-screen):
 * - Tier V1 (voice): browser SpeechRecognition (STT) → SSE turn → speechSynthesis
 *   (TTS) with captions as the accessibility layer. Barge-in cancels TTS when the
 *   candidate starts speaking.
 * - Tier Text: no mic; captions come from typed answers.
 * - Tier V2 (realtime): thin transport-agnostic connector used ONLY when the
 *   server returns a realtime descriptor (disabled by default → normally no-op).
 *
 * Everything is feature-detected. No provider/model strings are referenced;
 * the realtime path uses ONLY the ephemeral token from the descriptor.
 */

import type { MockInterviewRealtimeDescriptor } from "@/lib/api/mock-interview";

/* ----------------------- Minimal Web Speech typings ----------------------- */
// The DOM lib doesn't ship SpeechRecognition types; declare the slice we use.

interface SpeechRecognitionAlternativeLike {
  readonly transcript: string;
  readonly confidence: number;
}
interface SpeechRecognitionResultLike {
  readonly isFinal: boolean;
  readonly length: number;
  item(index: number): SpeechRecognitionAlternativeLike;
}
interface SpeechRecognitionResultListLike {
  readonly length: number;
  item(index: number): SpeechRecognitionResultLike;
}
interface SpeechRecognitionEventLike extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultListLike;
}
interface SpeechRecognitionErrorEventLike extends Event {
  readonly error: string;
}
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  onspeechstart: (() => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

interface SpeechWindow {
  SpeechRecognition?: SpeechRecognitionCtor;
  webkitSpeechRecognition?: SpeechRecognitionCtor;
  webkitAudioContext?: typeof AudioContext;
}

function speechWindow(): SpeechWindow {
  return window as unknown as SpeechWindow;
}

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = speechWindow();
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/* --------------------------- Capability detection ------------------------- */

export interface VoiceSupport {
  /** `navigator.mediaDevices.getUserMedia` is available. */
  getUserMedia: boolean;
  /** A SpeechRecognition constructor is available (STT). */
  speechRecognition: boolean;
  /** `speechSynthesis` is available (TTS — optional; captions cover a11y). */
  speechSynthesis: boolean;
  /** The full voice tier can run (mic + STT). TTS is a bonus, not required. */
  voiceReady: boolean;
}

/** Synchronous, prompt-free capability probe (safe to call on mount). */
export function detectVoiceSupport(): VoiceSupport {
  if (typeof window === "undefined" || typeof navigator === "undefined") {
    return {
      getUserMedia: false,
      speechRecognition: false,
      speechSynthesis: false,
      voiceReady: false,
    };
  }
  const getUserMedia =
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === "function";
  const speechRecognition = getRecognitionCtor() !== null;
  const speechSynthesis =
    typeof window.speechSynthesis !== "undefined" &&
    typeof window.SpeechSynthesisUtterance !== "undefined";
  return {
    getUserMedia,
    speechRecognition,
    speechSynthesis,
    voiceReady: getUserMedia && speechRecognition,
  };
}

export type MicPermission = "granted" | "denied" | "prompt" | "unknown";

/** Read mic permission WITHOUT prompting (Permissions API; best effort). */
export async function queryMicPermission(): Promise<MicPermission> {
  try {
    if (typeof navigator === "undefined" || !navigator.permissions?.query) {
      return "unknown";
    }
    const status = await navigator.permissions.query({
      name: "microphone" as PermissionName,
    });
    const state = status.state;
    if (state === "granted" || state === "denied" || state === "prompt") {
      return state;
    }
    return "unknown";
  } catch {
    return "unknown";
  }
}

/** BCP-47 tag for the STT/TTS engine from the app locale. */
export function speechLang(locale: string): string {
  return locale.toLowerCase().startsWith("vi") ? "vi-VN" : "en-US";
}

/* ------------------------------- Controller ------------------------------- */

export type VoiceErrorReason = "mic_denied" | "stt_failed" | "unsupported";

export interface VoiceControllerHandlers {
  /** Fires when the candidate begins speaking (drives barge-in). */
  onSpeechStart?: () => void;
  /** Live partial transcript for the current utterance. */
  onInterim?: (text: string) => void;
  /** A finalized candidate utterance. */
  onFinal?: (text: string) => void;
  /** TTS started/stopped speaking. */
  onSpeakingChange?: (speaking: boolean) => void;
  /** Unrecoverable capability/permission failure → caller degrades to text. */
  onError?: (reason: VoiceErrorReason) => void;
}

/**
 * Owns the mic stream, the STT recognizer, an analyser for the presence-orb
 * level, and TTS playback. All lifecycle is idempotent and cleaned up in
 * {@link dispose}.
 */
export class VoiceController {
  private locale: string;
  private handlers: VoiceControllerHandlers;

  private stream: MediaStream | null = null;
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private levelBuf: Uint8Array<ArrayBuffer> | null = null;

  private recognition: SpeechRecognitionLike | null = null;
  private wantListening = false;
  private speaking = false;
  private disposed = false;

  constructor(locale: string, handlers: VoiceControllerHandlers) {
    this.locale = locale;
    this.handlers = handlers;
  }

  /** Acquire the mic and wire the analyser. Rejects (and reports) on denial. */
  async acquireMic(): Promise<void> {
    if (this.stream) return;
    const support = detectVoiceSupport();
    if (!support.getUserMedia) {
      this.handlers.onError?.("unsupported");
      throw new Error("getUserMedia unsupported");
    }
    let stream: MediaStream;
    try {
      // Echo/noise cancellation keeps the interviewer's TTS from bleeding into
      // STT (which would otherwise cause false barge-ins / echoed answers).
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch {
      this.handlers.onError?.("mic_denied");
      throw new Error("mic denied");
    }
    if (this.disposed) {
      stream.getTracks().forEach((ttrack) => ttrack.stop());
      return;
    }
    this.stream = stream;
    try {
      const Ctx = window.AudioContext ?? speechWindow().webkitAudioContext;
      if (Ctx) {
        this.audioCtx = new Ctx();
        const source = this.audioCtx.createMediaStreamSource(stream);
        const analyser = this.audioCtx.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);
        this.analyser = analyser;
        this.levelBuf = new Uint8Array(new ArrayBuffer(analyser.frequencyBinCount));
      }
    } catch {
      // Level metering is non-essential; the orb falls back to idle breathing.
      this.audioCtx = null;
      this.analyser = null;
    }
  }

  /** Current mic amplitude in [0, 1], or 0 when no analyser is available. */
  get level(): number {
    if (!this.analyser || !this.levelBuf) return 0;
    this.analyser.getByteTimeDomainData(this.levelBuf);
    let sumSq = 0;
    for (let i = 0; i < this.levelBuf.length; i++) {
      const v = (this.levelBuf[i] ?? 128) - 128;
      sumSq += v * v;
    }
    const rms = Math.sqrt(sumSq / this.levelBuf.length) / 128;
    // Light gain so ordinary speech reads clearly on the orb.
    return Math.min(1, rms * 3.2);
  }

  get isSpeaking(): boolean {
    return this.speaking;
  }

  /** Start continuous STT. Auto-restarts across the browser's silence timeouts. */
  startListening(): void {
    if (this.disposed) return;
    const Ctor = getRecognitionCtor();
    if (!Ctor) {
      this.handlers.onError?.("unsupported");
      return;
    }
    this.wantListening = true;
    if (this.recognition) return;

    const rec = new Ctor();
    rec.lang = speechLang(this.locale);
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onspeechstart = () => {
      this.handlers.onSpeechStart?.();
    };

    rec.onresult = (event) => {
      let interim = "";
      let final = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results.item(i);
        const alt = result.item(0);
        if (result.isFinal) final += alt.transcript;
        else interim += alt.transcript;
      }
      if (interim.trim()) {
        this.handlers.onSpeechStart?.();
        this.handlers.onInterim?.(interim.trim());
      }
      if (final.trim()) {
        this.handlers.onFinal?.(final.trim());
      }
    };

    rec.onerror = (event) => {
      // "no-speech"/"aborted" are benign; onend restarts. Denial is terminal.
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        this.wantListening = false;
        this.handlers.onError?.("mic_denied");
      }
    };

    rec.onend = () => {
      // Restart if the caller still wants to listen (browsers auto-stop on
      // silence). Guard against tight loops after disposal.
      if (this.wantListening && !this.disposed && this.recognition === rec) {
        try {
          rec.start();
        } catch {
          // Already starting/started — ignore.
        }
      }
    };

    this.recognition = rec;
    try {
      rec.start();
    } catch {
      // A start() while already running throws; safe to ignore.
    }
  }

  /** Stop STT (used briefly, e.g. while ending). Safe to call repeatedly. */
  stopListening(): void {
    this.wantListening = false;
    const rec = this.recognition;
    this.recognition = null;
    if (rec) {
      rec.onend = null;
      rec.onresult = null;
      rec.onerror = null;
      rec.onspeechstart = null;
      try {
        rec.abort();
      } catch {
        // Ignore.
      }
    }
  }

  /**
   * Speak `text` via TTS. Resolves when playback ends (or immediately when TTS
   * is unavailable). Cancels any in-flight utterance first.
   */
  speak(text: string): Promise<void> {
    if (
      this.disposed ||
      typeof window === "undefined" ||
      typeof window.speechSynthesis === "undefined" ||
      typeof window.SpeechSynthesisUtterance === "undefined" ||
      !text.trim()
    ) {
      return Promise.resolve();
    }
    return new Promise<void>((resolve) => {
      try {
        window.speechSynthesis.cancel();
        const utter = new SpeechSynthesisUtterance(text);
        utter.lang = speechLang(this.locale);
        const voice = this.pickVoice();
        if (voice) utter.voice = voice;
        const finish = () => {
          if (this.speaking) {
            this.speaking = false;
            this.handlers.onSpeakingChange?.(false);
          }
          resolve();
        };
        utter.onend = finish;
        utter.onerror = finish;
        this.speaking = true;
        this.handlers.onSpeakingChange?.(true);
        window.speechSynthesis.speak(utter);
      } catch {
        this.speaking = false;
        this.handlers.onSpeakingChange?.(false);
        resolve();
      }
    });
  }

  /** Barge-in / stop TTS immediately. */
  cancelSpeaking(): void {
    if (typeof window === "undefined" || typeof window.speechSynthesis === "undefined") {
      return;
    }
    try {
      window.speechSynthesis.cancel();
    } catch {
      // Ignore.
    }
    if (this.speaking) {
      this.speaking = false;
      this.handlers.onSpeakingChange?.(false);
    }
  }

  private pickVoice(): SpeechSynthesisVoice | null {
    try {
      const target = speechLang(this.locale).toLowerCase();
      const short = target.split("-")[0] ?? target;
      const voices = window.speechSynthesis.getVoices();
      const exact = voices.find((v) => v.lang.toLowerCase() === target);
      if (exact) return exact;
      const partial = voices.find((v) => v.lang.toLowerCase().startsWith(short));
      return partial ?? null;
    } catch {
      return null;
    }
  }

  /** Full teardown: stop STT, cancel TTS, release the mic + audio graph. */
  dispose(): void {
    this.disposed = true;
    this.stopListening();
    this.cancelSpeaking();
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
    if (this.audioCtx) {
      try {
        void this.audioCtx.close();
      } catch {
        // Ignore.
      }
      this.audioCtx = null;
    }
    this.analyser = null;
    this.levelBuf = null;
  }
}

/* ------------------------------ Realtime (V2) ----------------------------- */

export interface RealtimeConnection {
  close: () => void;
  /** Best-effort send over the channel (no-op for unwired transports). */
  send: (data: unknown) => void;
}

export interface RealtimeHandlers {
  onOpen?: () => void;
  onClose?: () => void;
  onError?: () => void;
  onMessage?: (data: unknown) => void;
}

/**
 * Thin, transport-agnostic realtime connector. Uses ONLY the ephemeral token
 * from the descriptor. WebSocket is wired; WebRTC gracefully no-ops so callers
 * fall back to Tier V1. This path is disabled server-side by default.
 */
export function connectRealtime(
  descriptor: MockInterviewRealtimeDescriptor,
  handlers: RealtimeHandlers,
): RealtimeConnection {
  if (descriptor.transport === "websocket" && typeof WebSocket !== "undefined") {
    let ws: WebSocket | null = null;
    try {
      const url = new URL(descriptor.url);
      // WebSocket can't send an Authorization header; pass the ephemeral token
      // as a query param (never a durable key, never a provider/model string).
      url.searchParams.set("token", descriptor.ephemeral_token);
      ws = new WebSocket(url.toString());
      ws.onopen = () => handlers.onOpen?.();
      ws.onclose = () => handlers.onClose?.();
      ws.onerror = () => handlers.onError?.();
      ws.onmessage = (event: MessageEvent) => {
        try {
          handlers.onMessage?.(JSON.parse(String(event.data)));
        } catch {
          handlers.onMessage?.(event.data);
        }
      };
    } catch {
      handlers.onError?.();
    }
    return {
      close: () => {
        try {
          ws?.close();
        } catch {
          // Ignore.
        }
      },
      send: (data: unknown) => {
        try {
          ws?.send(typeof data === "string" ? data : JSON.stringify(data));
        } catch {
          // Ignore.
        }
      },
    };
  }

  // WebRTC (or unsupported WebSocket): not wired client-side yet — signal error
  // so the caller degrades to Tier V1 immediately.
  handlers.onError?.();
  return { close: () => undefined, send: () => undefined };
}
