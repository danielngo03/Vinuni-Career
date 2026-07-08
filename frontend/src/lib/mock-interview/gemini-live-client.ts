/**
 * Tier V2 — true realtime speech-to-speech client for the AI mock interview.
 *
 * This is the ONLY place the browser talks to the live-voice backend. It is used
 * strictly when {@link MockInterviewSession.realtime} is present (a descriptor
 * the server hands out rarely, behind the `realtime_voice_enabled` flag). When
 * the descriptor is absent the mock interview keeps running the browser-voice
 * (Tier V1) or text tier unchanged — this module is never constructed.
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

const INPUT_SAMPLE_RATE = 16000; // PCM16 the model expects on the way in.
const OUTPUT_SAMPLE_RATE = 24000; // PCM16 the model sends on the way out.
/** Silence gap (ms) after the last chunk before we report the orb as idle. */
const IDLE_DEBOUNCE_MS = 180;
/** Periodic transcript flush cadence. */
const FLUSH_INTERVAL_MS = 15000;

/* ------------------------------ audio helpers ----------------------------- */

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x4000;
  for (let i = 0; i < bytes.length; i += chunk) {
    const slice = bytes.subarray(i, i + chunk);
    for (let j = 0; j < slice.length; j++) {
      binary += String.fromCharCode(slice[j]!);
    }
  }
  return btoa(binary);
}

function base64ToBytes(b64: string): Uint8Array {
  const binary = atob(b64);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

/** Float32 [-1,1] → PCM16 LE → base64. */
function float32ToPcm16Base64(input: Float32Array): string {
  const bytes = new Uint8Array(input.length * 2);
  const view = new DataView(bytes.buffer);
  for (let i = 0; i < input.length; i++) {
    let s = input[i]!;
    s = s < -1 ? -1 : s > 1 ? 1 : s;
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return bytesToBase64(bytes);
}

/** base64 PCM16 LE → Float32 [-1,1]. */
function pcm16Base64ToFloat32(b64: string): Float32Array {
  const bytes = base64ToBytes(b64);
  const sampleCount = bytes.length >> 1;
  const view = new DataView(bytes.buffer, bytes.byteOffset, sampleCount * 2);
  const out = new Float32Array(sampleCount);
  for (let i = 0; i < sampleCount; i++) {
    out[i] = view.getInt16(i * 2, true) / 32768;
  }
  return out;
}

/**
 * Streaming linear resampler. The mic AudioContext runs at the device rate
 * (usually 48 kHz); the model needs 16 kHz. A one-sample carry preserves
 * continuity across worklet blocks so there is no per-block click.
 */
class LinearResampler {
  private readonly ratio: number;
  private carry = 0;
  private hasCarry = false;
  private phase = 0;

  constructor(inputRate: number, outputRate: number) {
    this.ratio = inputRate / outputRate;
  }

  process(input: Float32Array): Float32Array {
    if (input.length === 0) return input;
    if (Math.abs(this.ratio - 1) < 1e-6) return input;

    const hasCarry = this.hasCarry;
    const base = hasCarry ? 1 : 0;
    let work: Float32Array;
    if (hasCarry) {
      work = new Float32Array(input.length + 1);
      work[0] = this.carry;
      work.set(input, 1);
    } else {
      work = input;
    }

    const out: number[] = [];
    let pos = base + this.phase;
    const maxPos = work.length - 1;
    while (pos <= maxPos) {
      const i = Math.floor(pos);
      const frac = pos - i;
      const a = work[i]!;
      const b = i + 1 < work.length ? work[i + 1]! : a;
      out.push(a + (b - a) * frac);
      pos += this.ratio;
    }

    this.carry = input[input.length - 1]!;
    this.hasCarry = true;
    // Distance the read head overshot the last real input sample; carried into
    // the next block (which re-seats the last sample at index 0).
    this.phase = pos - work.length;
    return Float32Array.from(out);
  }
}

/* --------------------------- worklet (inline) ----------------------------- */

/**
 * Mic-capture worklet. Buffers ~40 ms of mono frames then transfers them to the
 * main thread (which resamples + encodes). Kept minimal so it works identically
 * across browsers; a ScriptProcessor path covers engines without AudioWorklet.
 */
const MIC_WORKLET_SOURCE = `
class MicCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._chunks = [];
    this._count = 0;
    this._target = 2048;
  }
  process(inputs) {
    const input = inputs[0];
    const ch = input && input[0];
    if (ch && ch.length) {
      this._chunks.push(new Float32Array(ch));
      this._count += ch.length;
      if (this._count >= this._target) {
        const merged = new Float32Array(this._count);
        let offset = 0;
        for (let i = 0; i < this._chunks.length; i++) {
          merged.set(this._chunks[i], offset);
          offset += this._chunks[i].length;
        }
        this.port.postMessage(merged, [merged.buffer]);
        this._chunks = [];
        this._count = 0;
      }
    }
    return true;
  }
}
registerProcessor('mic-capture-processor', MicCaptureProcessor);
`;

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

/* -------------------------------- window ---------------------------------- */

interface AudioWindow {
  webkitAudioContext?: typeof AudioContext;
}

function makeAudioContext(sampleRate?: number): AudioContext {
  const Ctor = window.AudioContext ?? (window as unknown as AudioWindow).webkitAudioContext;
  if (!Ctor) throw new Error("AudioContext unsupported");
  // Requesting a rate is best-effort; we always read back the real rate and
  // resample as needed, so Safari ignoring the hint is harmless.
  return sampleRate ? new Ctor({ sampleRate }) : new Ctor();
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

  /* mic capture graph */
  private stream: MediaStream | null = null;
  private inCtx: AudioContext | null = null;
  private micSource: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private scriptNode: ScriptProcessorNode | null = null;
  private muteGain: GainNode | null = null;
  private analyser: AnalyserNode | null = null;
  private levelBuf: Uint8Array<ArrayBuffer> | null = null;
  private resampler: LinearResampler | null = null;

  /* playback graph */
  private outCtx: AudioContext | null = null;
  private outGain: GainNode | null = null;
  private activeSources = new Set<AudioBufferSourceNode>();
  private nextStartTime = 0;
  private idleTimer: number | null = null;
  private speaking = false;

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
    if (!this.analyser || !this.levelBuf) return 0;
    this.analyser.getByteTimeDomainData(this.levelBuf);
    let sumSq = 0;
    for (let i = 0; i < this.levelBuf.length; i++) {
      const v = (this.levelBuf[i] ?? 128) - 128;
      sumSq += v * v;
    }
    const rms = Math.sqrt(sumSq / this.levelBuf.length) / 128;
    return Math.min(1, rms * 3.2);
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
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch {
      this.emitError("mic_denied");
      throw new Error("mic denied");
    }
    if (this.ended) {
      this.stream.getTracks().forEach((t) => t.stop());
      return;
    }

    // 2) Audio graph (capture + playback). Non-fatal if it partially fails; the
    //    orb simply won't animate to mic level.
    try {
      await this.setupCaptureGraph(this.stream);
      this.setupPlaybackGraph();
    } catch {
      // If Web Audio itself is unavailable we cannot do speech-to-speech.
      this.teardownAudio();
      this.emitError("unsupported");
      throw new Error("web audio unavailable");
    }

    // 3) Connect. Errors surface via onError('connection_failed'|'lost').
    this.connect();

    // 4) Hard caps from the descriptor.
    this.startTimers();
  }

  private async setupCaptureGraph(stream: MediaStream): Promise<void> {
    const ctx = makeAudioContext(INPUT_SAMPLE_RATE);
    this.inCtx = ctx;
    try {
      await ctx.resume();
    } catch {
      /* resume is best-effort; a user gesture preceded start(). */
    }
    this.resampler = new LinearResampler(ctx.sampleRate, INPUT_SAMPLE_RATE);

    const source = ctx.createMediaStreamSource(stream);
    this.micSource = source;

    // Level meter for the orb.
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    this.analyser = analyser;
    this.levelBuf = new Uint8Array(new ArrayBuffer(analyser.frequencyBinCount));

    // Prefer AudioWorklet; fall back to ScriptProcessor. Both feed onFrames().
    let usedWorklet = false;
    if (ctx.audioWorklet && typeof ctx.audioWorklet.addModule === "function") {
      try {
        const blob = new Blob([MIC_WORKLET_SOURCE], { type: "application/javascript" });
        const url = URL.createObjectURL(blob);
        try {
          await ctx.audioWorklet.addModule(url);
        } finally {
          URL.revokeObjectURL(url);
        }
        const node = new AudioWorkletNode(ctx, "mic-capture-processor");
        node.port.onmessage = (e: MessageEvent) => {
          if (e.data instanceof Float32Array) this.onFrames(e.data);
        };
        source.connect(node);
        // A worklet with no output still needs to be pulled by the graph.
        const sink = ctx.createGain();
        sink.gain.value = 0;
        node.connect(sink);
        sink.connect(ctx.destination);
        this.worklet = node;
        this.muteGain = sink;
        usedWorklet = true;
      } catch {
        usedWorklet = false;
      }
    }

    if (!usedWorklet) {
      const node = ctx.createScriptProcessor(4096, 1, 1);
      node.onaudioprocess = (e: AudioProcessingEvent) => {
        const ch = e.inputBuffer.getChannelData(0);
        this.onFrames(new Float32Array(ch));
      };
      const sink = ctx.createGain();
      sink.gain.value = 0; // never echo the mic to the speakers.
      source.connect(node);
      node.connect(sink);
      sink.connect(ctx.destination);
      this.scriptNode = node;
      this.muteGain = sink;
    }
  }

  private setupPlaybackGraph(): void {
    const ctx = makeAudioContext(OUTPUT_SAMPLE_RATE);
    this.outCtx = ctx;
    void ctx.resume().catch(() => undefined);
    const gain = ctx.createGain();
    gain.gain.value = 1;
    gain.connect(ctx.destination);
    this.outGain = gain;
    this.nextStartTime = ctx.currentTime;
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
      this.flushPlayback();
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
        if (b64) this.enqueuePlayback(pcm16Base64ToFloat32(b64));
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
    if (!this.readyToSend || this.ended) return;
    const resampled = this.resampler ? this.resampler.process(frames) : frames;
    if (resampled.length === 0) return;
    const data = float32ToPcm16Base64(resampled);
    const mimeType = `audio/pcm;rate=${INPUT_SAMPLE_RATE}`;
    if (this.sendShape === "audio") {
      this.safeSend({ realtimeInput: { audio: { data, mimeType } } });
    } else {
      this.safeSend({ realtimeInput: { mediaChunks: [{ mimeType, data }] } });
    }
  }

  /* ------------------------------- playback ------------------------------- */

  private enqueuePlayback(samples: Float32Array): void {
    const ctx = this.outCtx;
    const gain = this.outGain;
    if (!ctx || !gain || samples.length === 0) return;
    const buffer = ctx.createBuffer(1, samples.length, OUTPUT_SAMPLE_RATE);
    buffer.getChannelData(0).set(samples);
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(gain);

    const now = ctx.currentTime;
    const startAt = Math.max(now, this.nextStartTime);
    try {
      src.start(startAt);
    } catch {
      return;
    }
    this.nextStartTime = startAt + buffer.duration;
    this.activeSources.add(src);
    this.setSpeaking(true);
    src.onended = () => {
      this.activeSources.delete(src);
      if (this.activeSources.size === 0) this.scheduleIdle();
    };
  }

  private flushPlayback(): void {
    for (const src of this.activeSources) {
      try {
        src.onended = null;
        src.stop();
      } catch {
        /* already stopped */
      }
      try {
        src.disconnect();
      } catch {
        /* ignore */
      }
    }
    this.activeSources.clear();
    if (this.outCtx) this.nextStartTime = this.outCtx.currentTime;
    this.setSpeaking(false);
  }

  private scheduleIdle(): void {
    if (this.idleTimer !== null) window.clearTimeout(this.idleTimer);
    this.idleTimer = window.setTimeout(() => {
      this.idleTimer = null;
      if (this.activeSources.size === 0) this.setSpeaking(false);
    }, IDLE_DEBOUNCE_MS);
  }

  private setSpeaking(next: boolean): void {
    if (next && this.idleTimer !== null) {
      window.clearTimeout(this.idleTimer);
      this.idleTimer = null;
    }
    if (this.speaking === next) return;
    this.speaking = next;
    this.audioStateCb?.(next ? "speaking" : "idle");
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
    if (this.idleTimer !== null) {
      window.clearTimeout(this.idleTimer);
      this.idleTimer = null;
    }

    // Fold any in-flight partials into final turns before the last flush.
    this.finalizeCandidateTurn();
    this.finalizeInterviewerTurn();

    this.flushPlayback();
    this.teardownAudio();

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

  private teardownAudio(): void {
    if (this.worklet) {
      try {
        this.worklet.port.onmessage = null;
        this.worklet.disconnect();
      } catch {
        /* ignore */
      }
      this.worklet = null;
    }
    if (this.scriptNode) {
      try {
        this.scriptNode.onaudioprocess = null;
        this.scriptNode.disconnect();
      } catch {
        /* ignore */
      }
      this.scriptNode = null;
    }
    if (this.muteGain) {
      try {
        this.muteGain.disconnect();
      } catch {
        /* ignore */
      }
      this.muteGain = null;
    }
    if (this.micSource) {
      try {
        this.micSource.disconnect();
      } catch {
        /* ignore */
      }
      this.micSource = null;
    }
    if (this.analyser) {
      try {
        this.analyser.disconnect();
      } catch {
        /* ignore */
      }
      this.analyser = null;
    }
    this.levelBuf = null;
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    if (this.inCtx) {
      try {
        void this.inCtx.close();
      } catch {
        /* ignore */
      }
      this.inCtx = null;
    }
    if (this.outCtx) {
      try {
        void this.outCtx.close();
      } catch {
        /* ignore */
      }
      this.outCtx = null;
    }
    this.outGain = null;
    this.activeSources.clear();
  }

  private emitError(reason: GeminiLiveErrorReason): void {
    this.errorCb?.(reason);
  }
}
