/**
 * Tier V2 — true realtime speech-to-speech client for the AI mock interview.
 *
 * This is the direct-endpoint realtime path (used only when the server hands out
 * a {@link MockInterviewRealtimeDescriptor}). The newer, preferred realtime path
 * is the server relay in {@link LiveRelayClient}; both share the SAME audio
 * machinery via `./live-audio` ({@link MicCapture} + {@link Pcm24Player}) so the
 * capture/playback code is written once.
 *
 * Transport & safety:
 * - Opens a WebSocket to the descriptor's constrained bidi endpoint using ONLY
 *   the ephemeral token (as `?access_token=…`). The token is server-locked to a
 *   model + system instruction, so the client sends an EMPTY `{"setup": {}}`
 *   and never references a provider/model/prompt. Nothing here exposes AI
 *   internals to the UI.
 * - Mic → mono PCM16 little-endian @ 16 kHz, base64, streamed up as
 *   `realtimeInput`. Interviewer audio (PCM16 @ 24 kHz) is decoded and played
 *   back gaplessly through one output node with barge-in flush.
 * - Live input/output transcriptions drive captions (the a11y layer) and are
 *   accumulated into ordered turns that are flushed to the backend via
 *   {@link mockInterviewApi.recordTurns} — periodically and once more at end —
 *   so the coaching report has the full transcript.
 *
 * The public surface mirrors the browser {@link VoiceController}: `start()`,
 * `stop()`, `onCaption()`, `onInterviewerAudioState()`, `onError()`,
 * `onEnded()`, plus a `.level` getter for the presence orb.
 */

import {
  mockInterviewApi,
  type MockInterviewRealtimeDescriptor,
  type MockInterviewSpeaker,
  type RecordTurnInput,
} from "@/lib/api/mock-interview";
import {
  INPUT_SAMPLE_RATE,
  MicCapture,
  MicCaptureError,
  Pcm24Player,
  float32ToPcm16Base64,
  pcm16Base64ToFloat32,
} from "./live-audio";

/* ------------------------------ public types ------------------------------ */

/** Speaking = interviewer audio is playing/queued; idle = playback drained. */
export type InterviewerAudioState = "speaking" | "idle";

/**
 * A caption update for the live transcript overlay.
 * - `final: false` — a growing partial for the speaker's current utterance.
 * - `final: true`  — the utterance is complete (interviewer turn done, or the
 *   candidate's turn closed because the interviewer began replying).
 */
export interface CaptionUpdate {
  speaker: MockInterviewSpeaker;
  text: string;
  final: boolean;
}

export type GeminiLiveErrorReason =
  | "mic_denied"
  | "unsupported"
  | "connection_failed"
  | "connection_lost";

/* -------------------------------- constants ------------------------------- */

/** Periodic transcript flush cadence. */
const FLUSH_INTERVAL_MS = 15000;

/* -------------------------- server message shape -------------------------- */

interface LiveServerPart {
  inlineData?: { data?: string; mimeType?: string };
  text?: string;
}
interface LiveServerContent {
  modelTurn?: { parts?: LiveServerPart[] };
  inputTranscription?: { text?: string };
  outputTranscription?: { text?: string };
  turnComplete?: boolean;
  interrupted?: boolean;
  generationComplete?: boolean;
}
interface LiveServerMessage {
  setupComplete?: unknown;
  serverContent?: LiveServerContent;
  goAway?: unknown;
  error?: { message?: string } | unknown;
}

/* -------------------------------- client ---------------------------------- */

export class GeminiLiveClient {
  private readonly descriptor: MockInterviewRealtimeDescriptor;
  private readonly sessionId: string;

  private captionCb: ((u: CaptionUpdate) => void) | null = null;
  private audioStateCb: ((s: InterviewerAudioState) => void) | null = null;
  private errorCb: ((r: GeminiLiveErrorReason) => void) | null = null;
  private endedCb: (() => void) | null = null;

  /* transport */
  private ws: WebSocket | null = null;
  private sendShape: "audio" | "mediaChunks" = "audio";
  private triedReconnect = false;
  private receivedContent = false;
  private readyToSend = false;

  /* audio (shared machinery) */
  private mic: MicCapture | null = null;
  private player: Pcm24Player | null = null;

  /* transcript accumulation */
  private pendingInterviewer = "";
  private pendingCandidate = "";
  private readonly turns: RecordTurnInput[] = [];
  private flushedIndex = 0;
  private flushing = false;
  private interviewerTurnCount = 0;
  private limitReached = false;

  /* lifecycle */
  private started = false;
  private ended = false;
  private flushTimer: number | null = null;
  private capTimer: number | null = null;

  constructor(descriptor: MockInterviewRealtimeDescriptor, sessionId: string) {
    this.descriptor = descriptor;
    this.sessionId = sessionId;
  }

  /* ------------------------------ subscribe ------------------------------- */

  onCaption(cb: (u: CaptionUpdate) => void): this {
    this.captionCb = cb;
    return this;
  }
  onInterviewerAudioState(cb: (s: InterviewerAudioState) => void): this {
    this.audioStateCb = cb;
    return this;
  }
  onError(cb: (r: GeminiLiveErrorReason) => void): this {
    this.errorCb = cb;
    return this;
  }
  onEnded(cb: () => void): this {
    this.endedCb = cb;
    return this;
  }

  /** Current mic amplitude in [0,1] for the presence orb (0 if no analyser). */
  get level(): number {
    return this.mic?.level ?? 0;
  }

  /** Interviewer playback amplitude in [0,1] for avatar lip movement. */
  get outputLevel(): number {
    return this.player?.level ?? 0;
  }

  /* -------------------------------- start --------------------------------- */

  /**
   * Acquire the mic, build the audio graph, and open the live socket. Rejects
   * (after firing `onError`) when the mic is denied or Web Audio is missing, so
   * the caller can degrade to the text tier.
   */
  async start(): Promise<void> {
    if (this.started) return;
    this.started = true;

    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices ||
      typeof navigator.mediaDevices.getUserMedia !== "function" ||
      typeof WebSocket === "undefined"
    ) {
      this.emitError("unsupported");
      throw new Error("realtime unsupported");
    }

    // 1) Mic — the permission prompt happens up front, before we connect.
    const mic = new MicCapture((frames) => this.onFrames(frames));
    this.mic = mic;
    try {
      await mic.start();
    } catch (err) {
      const reason: GeminiLiveErrorReason =
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
        onSpeakingChange: (s) => this.audioStateCb?.(s ? "speaking" : "idle"),
      });
      player.setup();
      this.player = player;
    } catch {
      mic.teardown();
      this.mic = null;
      this.emitError("unsupported");
      throw new Error("web audio unavailable");
    }

    // 3) Connect. Errors surface via onError('connection_failed'|'lost').
    this.connect();

    // 4) Hard caps from the descriptor.
    this.startTimers();
  }

  /* ------------------------------- transport ------------------------------ */

  private connect(): void {
    const token = encodeURIComponent(this.descriptor.ephemeral_token);
    const sep = this.descriptor.url.includes("?") ? "&" : "?";
    const url = `${this.descriptor.url}${sep}access_token=${token}`;

    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      this.handleTransportFailure();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      // Constraints (model + system instruction) live in the token, so setup is
      // intentionally empty. This IS the "no model" form the constrained
      // endpoint expects — there is nothing further to strip on a setup error.
      this.safeSend({ setup: {} });
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
    // Never established → one reconnect with the alternate input shape (some
    // constrained builds accept `mediaChunks` instead of `audio`).
    if (!this.receivedContent && !this.triedReconnect) {
      this.triedReconnect = true;
      this.sendShape = this.sendShape === "audio" ? "mediaChunks" : "audio";
      this.readyToSend = false;
      try {
        this.ws?.close();
      } catch {
        /* ignore */
      }
      this.ws = null;
      this.connect();
      return;
    }
    const reason: GeminiLiveErrorReason = this.receivedContent
      ? "connection_lost"
      : "connection_failed";
    this.emitError(reason);
    void this.teardown();
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

  private async onSocketMessage(data: unknown): Promise<void> {
    let text: string;
    if (typeof data === "string") {
      text = data;
    } else if (typeof Blob !== "undefined" && data instanceof Blob) {
      text = await data.text();
    } else if (data instanceof ArrayBuffer) {
      text = new TextDecoder().decode(data);
    } else {
      return;
    }

    let msg: LiveServerMessage;
    try {
      const parsed: unknown = JSON.parse(text);
      if (!parsed || typeof parsed !== "object") return;
      msg = parsed as LiveServerMessage;
    } catch {
      return;
    }

    if (msg.setupComplete !== undefined) {
      // Setup acknowledged — begin streaming mic audio.
      this.readyToSend = true;
      return;
    }

    if (msg.serverContent) {
      this.receivedContent = true;
      this.handleServerContent(msg.serverContent);
    }

    if (msg.goAway !== undefined) {
      // Server asked us to wind down — end gracefully with a report.
      void this.endFromCap();
    }
  }

  private handleServerContent(content: LiveServerContent): void {
    // Barge-in: the candidate spoke over the interviewer → flush playback now.
    if (content.interrupted) {
      this.player?.flush();
    }

    // Candidate (input) transcription.
    if (content.inputTranscription?.text) {
      this.pendingCandidate += content.inputTranscription.text;
      this.emitCaption("candidate", this.pendingCandidate, false);
    }

    // Interviewer (output) transcription. Its arrival closes the candidate turn.
    if (content.outputTranscription?.text) {
      this.finalizeCandidateTurn();
      this.pendingInterviewer += content.outputTranscription.text;
      this.emitCaption("interviewer", this.pendingInterviewer, false);
    }

    // Interviewer audio → schedule gapless playback.
    const parts = content.modelTurn?.parts;
    if (parts) {
      for (const part of parts) {
        const b64 = part.inlineData?.data;
        if (b64) this.player?.enqueue(pcm16Base64ToFloat32(b64));
      }
    }

    if (content.turnComplete) {
      this.finalizeInterviewerTurn();
    }
  }

  /* --------------------------- turn accumulation -------------------------- */

  private finalizeCandidateTurn(): void {
    const text = this.pendingCandidate.trim();
    this.pendingCandidate = "";
    if (!text) return;
    this.turns.push({ speaker: "candidate", text });
    this.emitCaption("candidate", text, true);
    // The candidate answered — if we're past the question cap, wind down.
    if (this.limitReached) void this.endFromCap();
  }

  private finalizeInterviewerTurn(): void {
    const text = this.pendingInterviewer.trim();
    this.pendingInterviewer = "";
    if (!text) return;
    this.turns.push({ speaker: "interviewer", text });
    this.emitCaption("interviewer", text, true);
    this.interviewerTurnCount += 1;
    // A natural checkpoint to persist progress.
    void this.flush();
    if (
      this.descriptor.turn_limit > 0 &&
      this.interviewerTurnCount >= this.descriptor.turn_limit
    ) {
      // Let the candidate answer this final question; end on their next turn.
      this.limitReached = true;
    }
  }

  private emitCaption(speaker: MockInterviewSpeaker, textRaw: string, final: boolean): void {
    const text = final ? textRaw.trim() : textRaw;
    if (!text && !final) return;
    this.captionCb?.({ speaker, text, final });
  }

  /* ------------------------------ mic upload ------------------------------ */

  private onFrames(frames: Float32Array): void {
    if (!this.readyToSend || this.ended || frames.length === 0) return;
    const data = float32ToPcm16Base64(frames);
    const mimeType = `audio/pcm;rate=${INPUT_SAMPLE_RATE}`;
    if (this.sendShape === "audio") {
      this.safeSend({ realtimeInput: { audio: { data, mimeType } } });
    } else {
      this.safeSend({ realtimeInput: { mediaChunks: [{ mimeType, data }] } });
    }
  }

  /* -------------------------------- flush --------------------------------- */

  /** Persist newly-finalized turns. Idempotent; safe to call concurrently. */
  private async flush(): Promise<void> {
    if (this.flushing) return;
    const slice = this.turns.slice(this.flushedIndex);
    if (slice.length === 0) return;
    this.flushing = true;
    const upto = this.turns.length;
    try {
      await mockInterviewApi.recordTurns(this.sessionId, slice);
      this.flushedIndex = upto;
    } catch {
      // Keep flushedIndex; the next flush (or endSession fallback) retries.
    } finally {
      this.flushing = false;
    }
  }

  /** Turns finalized but not yet persisted (for an endSession fallback). */
  get pendingTurns(): RecordTurnInput[] {
    return this.turns.slice(this.flushedIndex);
  }

  /* -------------------------------- caps ---------------------------------- */

  private startTimers(): void {
    this.flushTimer = window.setInterval(() => void this.flush(), FLUSH_INTERVAL_MS);
    if (this.descriptor.duration_cap_s > 0) {
      this.capTimer = window.setTimeout(
        () => void this.endFromCap(),
        this.descriptor.duration_cap_s * 1000,
      );
    }
  }

  /** Descriptor cap / goAway / turn-limit reached → wind down and report. */
  private async endFromCap(): Promise<void> {
    if (this.ended) return;
    await this.teardown();
    this.endedCb?.();
  }

  /* --------------------------- stop / teardown ---------------------------- */

  /**
   * User-initiated end (the End button). Persists remaining turns and releases
   * everything. Idempotent — safe to call after a cap-driven end. Does NOT fire
   * `onEnded` (the caller already owns the "go to report" transition).
   */
  async stop(): Promise<void> {
    await this.teardown();
  }

  private async teardown(): Promise<void> {
    if (this.ended) return;
    this.ended = true;
    this.readyToSend = false;

    if (this.flushTimer !== null) {
      window.clearInterval(this.flushTimer);
      this.flushTimer = null;
    }
    if (this.capTimer !== null) {
      window.clearTimeout(this.capTimer);
      this.capTimer = null;
    }

    // Fold any in-flight partials into final turns before the last flush.
    this.finalizeCandidateTurn();
    this.finalizeInterviewerTurn();

    this.player?.flush();
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

    // Best-effort final flush; anything still pending is exposed via
    // `pendingTurns` so the caller can hand it to endSession instead.
    await this.flush();
  }

  private emitError(reason: GeminiLiveErrorReason): void {
    this.errorCb?.(reason);
  }
}
