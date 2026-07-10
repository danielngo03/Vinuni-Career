/**
 * Shared low-level Web Audio machinery for the AI mock-interview voice tiers.
 *
 * Two realtime clients build on these primitives so the audio path is written
 * ONCE, not duplicated:
 * - {@link GeminiLiveClient} — direct constrained endpoint; base64-in-JSON transport.
 * - {@link LiveRelayClient}  — our server relay; raw-binary PCM transport.
 *
 * The machinery is identical for both: mic capture → mono PCM16 @ 16 kHz on the
 * way up, and gapless PCM16 @ 24 kHz playback with barge-in flush on the way
 * down. No provider/model identity is referenced anywhere in this module.
 */

/** PCM16 sample rate sent upstream (mic → model). */
export const INPUT_SAMPLE_RATE = 16000;
/** PCM16 sample rate received downstream (voice → speakers). */
export const OUTPUT_SAMPLE_RATE = 24000;
/** Silence gap (ms) after the last chunk before playback is reported idle. */
const DEFAULT_IDLE_DEBOUNCE_MS = 180;

/* ------------------------------ base64 codec ------------------------------ */

export function bytesToBase64(bytes: Uint8Array): string {
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

export function base64ToBytes(b64: string): Uint8Array {
  const binary = atob(b64);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

/* --------------------------- PCM16 <-> Float32 ---------------------------- */

/** Float32 [-1,1] → little-endian PCM16 bytes. */
export function float32ToPcm16Bytes(input: Float32Array): Uint8Array {
  const bytes = new Uint8Array(input.length * 2);
  const view = new DataView(bytes.buffer);
  for (let i = 0; i < input.length; i++) {
    let s = input[i]!;
    s = s < -1 ? -1 : s > 1 ? 1 : s;
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return bytes;
}

/** Little-endian PCM16 bytes → Float32 [-1,1]. */
export function pcm16BytesToFloat32(bytes: Uint8Array): Float32Array {
  const sampleCount = bytes.length >> 1;
  const view = new DataView(bytes.buffer, bytes.byteOffset, sampleCount * 2);
  const out = new Float32Array(sampleCount);
  for (let i = 0; i < sampleCount; i++) {
    out[i] = view.getInt16(i * 2, true) / 32768;
  }
  return out;
}

/** Float32 [-1,1] → PCM16 LE → base64. */
export function float32ToPcm16Base64(input: Float32Array): string {
  return bytesToBase64(float32ToPcm16Bytes(input));
}

/** base64 PCM16 LE → Float32 [-1,1]. */
export function pcm16Base64ToFloat32(b64: string): Float32Array {
  return pcm16BytesToFloat32(base64ToBytes(b64));
}

/* ------------------------------- resampler -------------------------------- */

/**
 * Streaming linear resampler. The mic AudioContext runs at the device rate
 * (usually 48 kHz); the model needs 16 kHz. A one-sample carry preserves
 * continuity across worklet blocks so there is no per-block click.
 */
export class LinearResampler {
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

/* ------------------------------ audio context ----------------------------- */

interface AudioWindow {
  webkitAudioContext?: typeof AudioContext;
}

export function makeAudioContext(sampleRate?: number): AudioContext {
  const Ctor = window.AudioContext ?? (window as unknown as AudioWindow).webkitAudioContext;
  if (!Ctor) throw new Error("AudioContext unsupported");
  // Requesting a rate is best-effort; we always read back the real rate and
  // resample as needed, so Safari ignoring the hint is harmless.
  return sampleRate ? new Ctor({ sampleRate }) : new Ctor();
}

/* ------------------------------- mic capture ------------------------------ */

export type MicCaptureFailure = "mic_denied" | "unsupported";

/** Typed failure so callers can distinguish a denied prompt from no support. */
export class MicCaptureError extends Error {
  readonly reason: MicCaptureFailure;
  constructor(reason: MicCaptureFailure) {
    super(reason);
    this.name = "MicCaptureError";
    this.reason = reason;
  }
}

/**
 * Owns the mic stream + capture graph. Emits mono Float32 frames already
 * resampled to {@link INPUT_SAMPLE_RATE} (16 kHz) via {@link onFrame}; the
 * caller encodes/sends them. Also exposes a presence-orb `level`. Fully
 * feature-detected (AudioWorklet with a ScriptProcessor fallback).
 */
export class MicCapture {
  private readonly onFrame: (frames: Float32Array) => void;
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private scriptNode: ScriptProcessorNode | null = null;
  private muteGain: GainNode | null = null;
  private analyser: AnalyserNode | null = null;
  private levelBuf: Uint8Array<ArrayBuffer> | null = null;
  private resampler: LinearResampler | null = null;

  constructor(onFrame: (frames: Float32Array) => void) {
    this.onFrame = onFrame;
  }

  /**
   * Prompt for the mic and build the capture graph. Throws
   * {@link MicCaptureError} with `mic_denied` (user rejected) or `unsupported`
   * (no getUserMedia / Web Audio) so the caller can degrade.
   */
  async start(): Promise<void> {
    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices ||
      typeof navigator.mediaDevices.getUserMedia !== "function"
    ) {
      throw new MicCaptureError("unsupported");
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch {
      throw new MicCaptureError("mic_denied");
    }
    this.stream = stream;
    try {
      await this.buildGraph(stream);
    } catch {
      this.teardown();
      throw new MicCaptureError("unsupported");
    }
  }

  private async buildGraph(stream: MediaStream): Promise<void> {
    const ctx = makeAudioContext(INPUT_SAMPLE_RATE);
    this.ctx = ctx;
    try {
      await ctx.resume();
    } catch {
      /* resume is best-effort; a user gesture preceded start(). */
    }
    this.resampler = new LinearResampler(ctx.sampleRate, INPUT_SAMPLE_RATE);

    const source = ctx.createMediaStreamSource(stream);
    this.source = source;

    // Level meter for the presence orb.
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    this.analyser = analyser;
    this.levelBuf = new Uint8Array(new ArrayBuffer(analyser.frequencyBinCount));

    const emit = (frames: Float32Array): void => {
      const resampled = this.resampler ? this.resampler.process(frames) : frames;
      if (resampled.length === 0) return;
      this.onFrame(resampled);
    };

    // Prefer AudioWorklet; fall back to ScriptProcessor. Both feed emit().
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
          if (e.data instanceof Float32Array) emit(e.data);
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
        emit(new Float32Array(ch));
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

  /** Release the graph and stop the mic tracks. Idempotent. */
  teardown(): void {
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
    if (this.source) {
      try {
        this.source.disconnect();
      } catch {
        /* ignore */
      }
      this.source = null;
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
    if (this.ctx) {
      try {
        void this.ctx.close();
      } catch {
        /* ignore */
      }
      this.ctx = null;
    }
    this.resampler = null;
  }
}

/* -------------------------------- playback -------------------------------- */

/**
 * Gapless PCM16 @ {@link OUTPUT_SAMPLE_RATE} (24 kHz) player. Each decoded chunk
 * is scheduled back-to-back on one output node so there are no clicks; a
 * barge-in {@link flush} stops and drops everything queued. `onSpeakingChange`
 * fires true while audio is playing/queued and false (after a short debounce)
 * once drained.
 */
export class Pcm24Player {
  private readonly onSpeakingChange?: (speaking: boolean) => void;
  private readonly idleDebounceMs: number;
  private ctx: AudioContext | null = null;
  private gain: GainNode | null = null;
  private readonly activeSources = new Set<AudioBufferSourceNode>();
  private nextStartTime = 0;
  private idleTimer: number | null = null;
  private speaking = false;

  constructor(opts?: {
    onSpeakingChange?: (speaking: boolean) => void;
    idleDebounceMs?: number;
  }) {
    this.onSpeakingChange = opts?.onSpeakingChange;
    this.idleDebounceMs = opts?.idleDebounceMs ?? DEFAULT_IDLE_DEBOUNCE_MS;
  }

  /** Build the output node. Throws if Web Audio is unavailable. */
  setup(): void {
    const ctx = makeAudioContext(OUTPUT_SAMPLE_RATE);
    this.ctx = ctx;
    void ctx.resume().catch(() => undefined);
    const gain = ctx.createGain();
    gain.gain.value = 1;
    gain.connect(ctx.destination);
    this.gain = gain;
    this.nextStartTime = ctx.currentTime;
  }

  get isSpeaking(): boolean {
    return this.speaking;
  }

  enqueue(samples: Float32Array): void {
    const ctx = this.ctx;
    const gain = this.gain;
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

  /** Barge-in: stop and drop everything queued immediately. */
  flush(): void {
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
    if (this.ctx) this.nextStartTime = this.ctx.currentTime;
    this.setSpeaking(false);
  }

  private scheduleIdle(): void {
    if (this.idleTimer !== null) window.clearTimeout(this.idleTimer);
    this.idleTimer = window.setTimeout(() => {
      this.idleTimer = null;
      if (this.activeSources.size === 0) this.setSpeaking(false);
    }, this.idleDebounceMs);
  }

  private setSpeaking(next: boolean): void {
    if (next && this.idleTimer !== null) {
      window.clearTimeout(this.idleTimer);
      this.idleTimer = null;
    }
    if (this.speaking === next) return;
    this.speaking = next;
    this.onSpeakingChange?.(next);
  }

  /** Flush, cancel timers, and close the output context. Idempotent. */
  teardown(): void {
    this.flush();
    if (this.idleTimer !== null) {
      window.clearTimeout(this.idleTimer);
      this.idleTimer = null;
    }
    if (this.ctx) {
      try {
        void this.ctx.close();
      } catch {
        /* ignore */
      }
      this.ctx = null;
    }
    this.gain = null;
  }
}
