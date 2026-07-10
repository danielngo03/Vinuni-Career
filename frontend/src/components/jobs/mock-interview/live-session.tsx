"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  ArrowRight,
  CircleNotch,
  Keyboard,
  Microphone,
  MicrophoneSlash,
  PhoneDisconnect,
  Stop,
  VideoCamera,
  VideoCameraSlash,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import {
  mockInterviewApi,
  type MockInterviewSession,
  type RecordTurnInput,
} from "@/lib/api";
import { VoiceController } from "@/lib/mock-interview/voice-controller";
import { GeminiLiveClient } from "@/lib/mock-interview/gemini-live-client";
import { LiveRelayClient } from "@/lib/mock-interview/live-relay-client";
import { usePrefersReducedMotion } from "@/lib/hooks/use-mount-animation";
import { cn } from "@/lib/utils";
import { InterviewerAvatar, type AvatarState } from "./interviewer-avatar";
import { SelfViewTile, useSelfViewCamera } from "./student-self-view";
import { CoverageChips } from "./coverage-progress";
import type { AnswerMode } from "./pre-session-setup";

type Phase = "interviewer_speaking" | "listening" | "thinking" | "ending";

// If the realtime (V2) socket opens but produces no audio/transcription within
// this window, we stop waiting and degrade to the browser-voice/text tier.
const REALTIME_CONNECT_TIMEOUT_MS = 12_000;

// While it's the candidate's turn, this much silence (no recognized speech and
// no typing) surfaces a calm nudge that also offers to switch to typing — the
// escape hatch when browser STT is quietly failing to hear anything.
const IDLE_HINT_MS = 22_000;

function formatClock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${rem.toString().padStart(2, "0")}`;
}

function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

interface Props {
  session: MockInterviewSession;
  mode: AnswerMode;
  locale: string;
  /**
   * True when the server-mediated voice tier is available (from prep's
   * `server_voice`). In voice mode this drives AI narration (TTS) of the
   * interviewer's lines and spoken answers transcribed server-side (STT).
   * When false, voice mode uses the browser voice tier / text as before.
   */
  serverVoice?: boolean;
  /**
   * True when the true full-duplex realtime relay tier is active (the session
   * was created with `modality: "realtime"`). This is the PREFERRED voice path:
   * mic audio streams to our server and the interviewer's native audio streams
   * back in real time. Takes precedence over server voice and browser voice.
   */
  realtimeRelay?: boolean;
  onRequestEnd: (payload: { duration_seconds: number; turns?: RecordTurnInput[] }) => void;
}

/** Pick the best-supported MediaRecorder container for answer capture. */
function pickRecorderMime(): string | undefined {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") {
    return undefined;
  }
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
    "audio/mpeg",
  ];
  for (const c of candidates) {
    if (MediaRecorder.isTypeSupported(c)) return c;
  }
  return undefined;
}

/**
 * The "Room": a single presence orb, subtitle-style captions, a question
 * timeline, a quiet countdown + counter, and an End control. Drives the voice
 * controller (STT → SSE turn → TTS) or a text answer box. Captions are the
 * accessibility layer for the voice conversation.
 */
export function LiveSession({
  session,
  mode,
  locale,
  serverVoice,
  realtimeRelay,
  onRequestEnd,
}: Props) {
  const t = useTranslations("jobs.mockInterview");
  const reduced = usePrefersReducedMotion();
  const camera = useSelfViewCamera();

  const target = Math.max(1, session.caps.target_questions || session.caps.max_questions || 1);

  // Realtime (Tier V2) is active only when the server hands out a descriptor.
  // Its visible countdown never exceeds the hard live-voice duration cap.
  const realtime = session.realtime;

  const recorderSupported = useMemo(
    () =>
      typeof window !== "undefined" &&
      typeof MediaRecorder !== "undefined" &&
      typeof navigator !== "undefined" &&
      !!navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === "function",
    [],
  );
  const initialSeconds =
    realtime && realtime.duration_cap_s > 0
      ? Math.min(session.caps.max_session_seconds, realtime.duration_cap_s)
      : session.caps.max_session_seconds;

  const [effectiveMode, setEffectiveMode] = useState<AnswerMode>(mode);
  const [degraded, setDegraded] = useState(false);
  // The relay tier can be disabled at runtime when it fails and we fall back to
  // the turn-based server-voice tier (see degradeFromRelay).
  const [relayDisabled, setRelayDisabled] = useState(false);

  // Realtime relay (Tier V3, PREFERRED): true full-duplex live voice over our
  // server WebSocket. Active when the session is `modality: "realtime"`, no
  // direct descriptor is present, and it hasn't fallen back. Takes precedence
  // over server voice and browser voice.
  const useRelay = realtimeRelay === true && !realtime && !relayDisabled;

  // Server-mediated voice tier: AI narrates the interviewer (TTS) and answers
  // are transcribed server-side (STT). Only when neither realtime tier is active
  // and the server advertised it via prep. Distinct from the browser voice tier.
  const serverVoiceActive = !realtime && !useRelay && serverVoice === true;
  const [phase, setPhase] = useState<Phase>(mode === "voice" ? "interviewer_speaking" : "listening");
  const [currentQuestion, setCurrentQuestion] = useState(session.opening.text);
  const [interviewerStreaming, setInterviewerStreaming] = useState<string | null>(null);
  const [candidateCaption, setCandidateCaption] = useState("");
  const [questionCount, setQuestionCount] = useState(1);
  // Live topic coverage: seeded from the plan at session start, then advanced
  // per turn from each done event's leak-safe coverage summary.
  const [liveCoverage, setLiveCoverage] = useState(session.coverage ?? null);
  const [timeLeft, setTimeLeft] = useState(initialSeconds);
  const [turnError, setTurnError] = useState(false);
  const [idleHint, setIdleHint] = useState(false);
  const [textDraft, setTextDraft] = useState("");
  // Realtime-only presentation states (unused on the V1/text path). Both the
  // descriptor tier and the relay tier show the "connecting live voice" state.
  const [realtimeConnecting, setRealtimeConnecting] = useState(
    !!realtime || (useRelay && mode === "voice"),
  );
  const [realtimeLost, setRealtimeLost] = useState(false);
  // Relay push-to-talk: true while the student holds/toggles the mic to speak.
  const [relaySpeaking, setRelaySpeaking] = useState(false);
  // Server voice tier presentation states.
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceNotice, setVoiceNotice] = useState<null | "tts" | "stt" | "mic">(null);

  const phaseRef = useRef<Phase>(phase);
  const effectiveModeRef = useRef<AnswerMode>(effectiveMode);
  const controllerRef = useRef<VoiceController | null>(null);
  const geminiRef = useRef<GeminiLiveClient | null>(null);
  const relayRef = useRef<LiveRelayClient | null>(null);
  // Growing per-turn caption buffers for the relay tier (incremental chunks).
  const relayInBufRef = useRef("");
  const relayOutBufRef = useRef("");
  const abortRef = useRef<AbortController | null>(null);
  const interviewerBufRef = useRef("");
  const lastAnswerRef = useRef("");
  const startedAtRef = useRef<number>(Date.now());
  const endedRef = useRef(false);
  const turnsRef = useRef<RecordTurnInput[]>([]);
  // Server voice tier: TTS playback element + recorder graph.
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const playbackDoneRef = useRef<(() => void) | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recordChunksRef = useRef<Blob[]>([]);

  const setPhaseNow = useCallback((next: Phase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);

  useEffect(() => {
    effectiveModeRef.current = effectiveMode;
  }, [effectiveMode]);

  /* -------------------- server voice tier (TTS + STT) --------------------- */
  // Stop any in-flight interviewer narration (barge-in / re-speak / teardown).
  const stopServerAudio = useCallback(() => {
    const el = audioRef.current;
    if (el) {
      try {
        el.pause();
      } catch {
        /* ignore */
      }
    }
    // Resolve the awaiting speak() promise (if any) so the caller advances.
    const done = playbackDoneRef.current;
    playbackDoneRef.current = null;
    done?.();
    if (audioUrlRef.current) {
      try {
        URL.revokeObjectURL(audioUrlRef.current);
      } catch {
        /* ignore */
      }
      audioUrlRef.current = null;
    }
  }, []);

  // Narrate one interviewer line. Resolves when playback ends (or immediately if
  // TTS is unavailable). Captions are NEVER blocked on audio — on any failure we
  // set a calm notice and resolve so the caller can move to the student's turn.
  const speakServer = useCallback(
    async (text: string): Promise<void> => {
      if (!text.trim() || endedRef.current || typeof Audio === "undefined") return;
      stopServerAudio();
      let blob: Blob;
      try {
        blob = await mockInterviewApi.synthesizeSpeech(session.session_id, text);
      } catch {
        setVoiceNotice("tts");
        return;
      }
      if (endedRef.current) return;
      await new Promise<void>((resolve) => {
        let el = audioRef.current;
        if (!el) {
          el = new Audio();
          audioRef.current = el;
        }
        const url = URL.createObjectURL(blob);
        audioUrlRef.current = url;
        const finish = () => {
          if (playbackDoneRef.current === finish) playbackDoneRef.current = null;
          el!.onended = null;
          el!.onerror = null;
          if (audioUrlRef.current === url) {
            try {
              URL.revokeObjectURL(url);
            } catch {
              /* ignore */
            }
            audioUrlRef.current = null;
          }
          resolve();
        };
        playbackDoneRef.current = finish;
        el.onended = finish;
        el.onerror = finish;
        el.src = url;
        // Sticky user activation from the Start click permits autoplay; if the
        // browser still rejects, captions carry and we advance the turn.
        void el.play().catch(() => {
          setVoiceNotice("tts");
          finish();
        });
      });
    },
    [session.session_id, stopServerAudio],
  );

  // Send a recorded answer for server-side transcription, then drop the text
  // into the answer box for the student to REVIEW/edit. Never auto-submits.
  const transcribe = useCallback(
    async (blob: Blob): Promise<void> => {
      if (endedRef.current) return;
      setTranscribing(true);
      try {
        const { transcript } = await mockInterviewApi.transcribeAnswer(
          session.session_id,
          blob,
        );
        const clean = transcript.trim();
        if (!clean) {
          setVoiceNotice("stt");
        } else if (!endedRef.current) {
          setTextDraft((prev) => (prev.trim() ? `${prev.trim()} ${clean}` : clean));
        }
      } catch {
        setVoiceNotice("stt");
      } finally {
        setTranscribing(false);
      }
    },
    [session.session_id],
  );

  const startRecording = useCallback(async () => {
    if (endedRef.current || recorderRef.current || !recorderSupported) return;
    setVoiceNotice(null);
    // Barge-in: cut the interviewer's narration the moment the student answers.
    stopServerAudio();

    let stream = micStreamRef.current;
    if (!stream) {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        micStreamRef.current = stream;
      } catch {
        setVoiceNotice("mic");
        return;
      }
    }
    if (endedRef.current) return;

    const mime = pickRecorderMime();
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    } catch {
      setVoiceNotice("mic");
      return;
    }
    recordChunksRef.current = [];
    recorder.ondataavailable = (e: BlobEvent) => {
      if (e.data && e.data.size > 0) recordChunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      const chunks = recordChunksRef.current;
      recordChunksRef.current = [];
      recorderRef.current = null;
      setRecording(false);
      if (chunks.length === 0 || endedRef.current) return;
      const blob = new Blob(chunks, { type: mime ?? chunks[0]?.type ?? "audio/webm" });
      void transcribe(blob);
    };
    recorderRef.current = recorder;
    setPhaseNow("listening");
    setRecording(true);
    try {
      recorder.start();
    } catch {
      recorderRef.current = null;
      setRecording(false);
      setVoiceNotice("mic");
    }
  }, [recorderSupported, stopServerAudio, transcribe, setPhaseNow]);

  const stopRecording = useCallback(() => {
    const rec = recorderRef.current;
    if (!rec) return;
    try {
      if (rec.state !== "inactive") rec.stop();
    } catch {
      recorderRef.current = null;
      setRecording(false);
    }
  }, []);

  const toggleRecord = useCallback(() => {
    if (recording) stopRecording();
    else void startRecording();
  }, [recording, startRecording, stopRecording]);

  // Full teardown of the server voice graph (audio + recorder + mic).
  const disposeServerVoice = useCallback(() => {
    stopServerAudio();
    const rec = recorderRef.current;
    recorderRef.current = null;
    if (rec) {
      rec.ondataavailable = null;
      rec.onstop = null;
      try {
        if (rec.state !== "inactive") rec.stop();
      } catch {
        /* ignore */
      }
    }
    recordChunksRef.current = [];
    const stream = micStreamRef.current;
    micStreamRef.current = null;
    if (stream) stream.getTracks().forEach((tr) => tr.stop());
  }, [stopServerAudio]);

  /* ------------------------------ end session ----------------------------- */
  const finalize = useCallback(() => {
    if (endedRef.current) return;
    endedRef.current = true;
    const duration = Math.round((Date.now() - startedAtRef.current) / 1000);
    abortRef.current?.abort();
    controllerRef.current?.dispose();
    disposeServerVoice();
    setPhaseNow("ending");

    const relay = relayRef.current;
    const gemini = geminiRef.current;
    if (relay) {
      // Relay tier: say bye + release the socket BEFORE ending so the report
      // sees the full transcript. The relay persists turns server-side, so
      // there is nothing to hand off to endSession.
      void relay.end().then(() => {
        onRequestEnd({ duration_seconds: duration });
      });
    } else if (gemini) {
      // Descriptor realtime: stop (releases mic, flushes remaining turns) BEFORE
      // ending so the coaching report sees the full transcript. Turns are already
      // persisted via recordTurns; hand over only what a failed final flush left
      // behind so endSession can persist it without double-recording.
      void gemini.stop().then(() => {
        const pending = gemini.pendingTurns;
        onRequestEnd({
          duration_seconds: duration,
          turns: pending.length > 0 ? pending : undefined,
        });
      });
    } else {
      onRequestEnd({
        duration_seconds: duration,
        turns: turnsRef.current.length > 0 ? turnsRef.current : undefined,
      });
    }
  }, [onRequestEnd, setPhaseNow, disposeServerVoice]);

  /* ------------------------------- one turn ------------------------------- */
  const beginTurn = useCallback(
    async (answer: string) => {
      const text = answer.trim();
      if (!text || endedRef.current) return;
      lastAnswerRef.current = text;
      setTurnError(false);
      setCandidateCaption(text);
      setInterviewerStreaming("");
      interviewerBufRef.current = "";
      setPhaseNow("thinking");

      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      await mockInterviewApi.streamTurn(
        session.session_id,
        text,
        {
          onToken: (tk) => {
            interviewerBufRef.current += tk;
            setInterviewerStreaming(interviewerBufRef.current);
            if (phaseRef.current !== "interviewer_speaking") {
              setPhaseNow("interviewer_speaking");
            }
          },
          onDone: (evt) => {
            const finalText = evt.text || interviewerBufRef.current;
            setInterviewerStreaming(null);
            setCurrentQuestion(finalText);
            setQuestionCount(evt.question_count > 0 ? evt.question_count : (c) => c + 1);
            setCandidateCaption("");
            if (evt.coverage) setLiveCoverage(evt.coverage);
            if (evt.ended) {
              finalize();
              return;
            }
            if (effectiveModeRef.current === "voice" && serverVoiceActive) {
              setPhaseNow("interviewer_speaking");
              void speakServer(finalText).then(() => {
                if (!endedRef.current) setPhaseNow("listening");
              });
            } else if (effectiveModeRef.current === "voice" && controllerRef.current) {
              void controllerRef.current.speak(finalText).then(() => {
                if (!endedRef.current) setPhaseNow("listening");
              });
            } else {
              setPhaseNow("listening");
            }
          },
          onError: () => {
            setInterviewerStreaming(null);
            setTurnError(true);
            setPhaseNow("listening");
          },
        },
        ac.signal,
      );
    },
    [session.session_id, finalize, setPhaseNow, serverVoiceActive, speakServer],
  );

  const beginTurnRef = useRef(beginTurn);
  useEffect(() => {
    beginTurnRef.current = beginTurn;
  }, [beginTurn]);

  /* --------------------------- degrade voice→text ------------------------- */
  const degradeToText = useCallback(() => {
    if (effectiveModeRef.current === "text") return;
    setDegraded(true);
    setRealtimeConnecting(false);
    setRealtimeLost(false);
    setEffectiveMode("text");
    setPhaseNow("listening");
  }, [setPhaseNow]);

  /** Realtime dropped mid-session → user chooses to keep going by text. */
  const continueInText = useCallback(() => {
    setRealtimeLost(false);
    degradeToText();
  }, [degradeToText]);

  /**
   * Relay failed (not a clean mid-session drop) → prefer the turn-based
   * server-voice tier when the server advertised it, else fall to text. This
   * keeps the room alive instead of hard-crashing.
   */
  const degradeFromRelay = useCallback(() => {
    if (serverVoice === true) {
      setRelayDisabled(true);
      setRealtimeConnecting(false);
      setRealtimeLost(false);
      setRelaySpeaking(false);
      setPhaseNow("interviewer_speaking");
    } else {
      degradeToText();
    }
  }, [serverVoice, degradeToText, setPhaseNow]);

  /* --------------------- relay (V3) push-to-talk toggle ------------------- */
  const toggleRelaySpeak = useCallback(() => {
    const relay = relayRef.current;
    if (!relay) return;
    if (relaySpeaking) {
      relay.stopSpeaking();
      setRelaySpeaking(false);
    } else {
      // startSpeaking flushes interviewer playback (barge-in) inside the client.
      relay.startSpeaking();
      setRelaySpeaking(true);
    }
  }, [relaySpeaking]);

  /* ---------------------------- voice lifecycle --------------------------- */
  useEffect(() => {
    // Realtime tiers (descriptor V2 or relay V3) own the voice tier; the browser
    // STT/TTS controller must not also grab the mic.
    if (realtime && effectiveMode === "voice") return;
    if (useRelay && effectiveMode === "voice") return;
    // Server voice tier owns the mic/narration for voice mode; the browser
    // SpeechRecognition/synthesis controller must not also run.
    if (serverVoiceActive && effectiveMode === "voice") return;
    if (effectiveMode !== "voice") {
      // Text tier (chosen or degraded): no mic; wait for a typed answer.
      if (phaseRef.current === "interviewer_speaking") setPhaseNow("listening");
      return;
    }

    let cancelled = false;
    const controller = new VoiceController(locale, {
      onInterim: (text) => {
        setCandidateCaption(text);
        // Barge-in: the candidate speaks over the interviewer → cut TTS.
        if (phaseRef.current === "interviewer_speaking" && wordCount(text) >= 2) {
          controller.cancelSpeaking();
          setPhaseNow("listening");
        }
      },
      onFinal: (text) => {
        if (phaseRef.current === "listening" && text.trim().length >= 2) {
          void beginTurnRef.current(text);
        }
      },
      onError: (reason) => {
        if (reason === "mic_denied" || reason === "unsupported" || reason === "stt_failed") {
          degradeToText();
        }
      },
    });
    controllerRef.current = controller;

    void (async () => {
      try {
        await controller.acquireMic();
      } catch {
        return; // onError already triggered degradeToText
      }
      if (cancelled) return;
      controller.startListening();
      setPhaseNow("interviewer_speaking");
      await controller.speak(session.opening.text);
      if (!cancelled && !endedRef.current) setPhaseNow("listening");
    })();

    return () => {
      cancelled = true;
      controller.dispose();
      if (controllerRef.current === controller) controllerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveMode]);

  /* --------------------- realtime (V2) speech-to-speech ------------------- */
  useEffect(() => {
    if (!realtime) return; // Normal path: server disables realtime → V1/Text.
    if (effectiveMode !== "voice") return; // Degraded to text → text tier runs.

    let cancelled = false;
    let connected = false;
    const markConnected = () => {
      connected = true;
    };
    const client = new GeminiLiveClient(realtime, session.session_id);
    geminiRef.current = client;

    // Connect watchdog: a socket that opens + completes setup but never emits
    // audio/transcription would otherwise leave the student stuck on
    // "Connecting live voice…" forever. Degrade to the browser-voice/text tier.
    const connectTimer = window.setTimeout(() => {
      if (!cancelled && !connected) degradeToText();
    }, REALTIME_CONNECT_TIMEOUT_MS);

    client
      .onCaption((u) => {
        if (cancelled) return;
        markConnected();
        if (u.speaker === "interviewer") {
          setRealtimeConnecting(false);
          if (u.final) {
            setInterviewerStreaming(null);
            setCurrentQuestion(u.text);
            setCandidateCaption("");
            setQuestionCount((c) => c + 1);
          } else {
            setInterviewerStreaming(u.text);
          }
        } else {
          setCandidateCaption(u.text);
        }
      })
      .onInterviewerAudioState((state) => {
        if (cancelled) return;
        markConnected();
        setRealtimeConnecting(false);
        setPhaseNow(state === "speaking" ? "interviewer_speaking" : "listening");
      })
      .onError((reason) => {
        if (cancelled) return;
        if (reason === "connection_lost") {
          // Established then dropped → calm banner offering to continue by text.
          setRealtimeConnecting(false);
          setRealtimeLost(true);
        } else {
          // Mic denied / unsupported / never connected → fall to the text tier.
          degradeToText();
        }
      })
      .onEnded(() => {
        if (cancelled) return;
        finalize();
      });

    void client.start().catch(() => {
      // onError already fired and drove degradation; nothing else to do.
    });

    return () => {
      cancelled = true;
      window.clearTimeout(connectTimer);
      void client.stop();
      if (geminiRef.current === client) geminiRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [realtime, effectiveMode]);

  /* ------------------- realtime relay (V3) speech-to-speech --------------- */
  useEffect(() => {
    if (!useRelay) return; // Not the relay tier.
    if (effectiveMode !== "voice") return; // Degraded to text → text tier runs.

    let cancelled = false;
    let connected = false;
    const markConnected = () => {
      connected = true;
    };
    const client = new LiveRelayClient();
    relayRef.current = client;
    relayInBufRef.current = "";
    relayOutBufRef.current = "";

    // Connect watchdog: a socket that never produces `ready`/audio/transcription
    // would otherwise leave the student stuck on "Connecting live voice…". Fall
    // back to the turn-based tier when available, else text.
    const connectTimer = window.setTimeout(() => {
      if (!cancelled && !connected) degradeFromRelay();
    }, REALTIME_CONNECT_TIMEOUT_MS);

    void client
      .connect(session.session_id, {
        onReady: () => {
          if (cancelled) return;
          markConnected();
          setRealtimeConnecting(false);
        },
        onStateChange: (state) => {
          if (cancelled) return;
          markConnected();
          setRealtimeConnecting(false);
          // Interviewer took the floor → release the student's push-to-talk so
          // the mic isn't left streaming behind an idle-looking button.
          if (state === "speaking") {
            relayRef.current?.stopSpeaking();
            setRelaySpeaking(false);
          }
          setPhaseNow(state === "speaking" ? "interviewer_speaking" : "listening");
        },
        onInputTranscript: (chunk) => {
          if (cancelled) return;
          markConnected();
          relayInBufRef.current += chunk;
          setCandidateCaption(relayInBufRef.current);
        },
        onOutputTranscript: (chunk) => {
          if (cancelled) return;
          markConnected();
          setRealtimeConnecting(false);
          relayOutBufRef.current += chunk;
          setInterviewerStreaming(relayOutBufRef.current);
        },
        onTurnComplete: () => {
          if (cancelled) return;
          const finalText = relayOutBufRef.current.trim();
          relayOutBufRef.current = "";
          relayInBufRef.current = "";
          setInterviewerStreaming(null);
          if (finalText) setCurrentQuestion(finalText);
          setCandidateCaption("");
          setQuestionCount((c) => c + 1);
        },
        onError: (reason) => {
          if (cancelled) return;
          if (reason === "connection_lost") {
            // Established then dropped → calm banner offering to continue by text.
            setRealtimeConnecting(false);
            setRealtimeLost(true);
          } else if (reason === "mic_denied") {
            // Mic unavailable → the turn-based tier needs it too; drop to text.
            degradeToText();
          } else {
            // unsupported / connection_failed / server_error → turn-based tier
            // when available, else text.
            degradeFromRelay();
          }
        },
      })
      .catch(() => {
        // onError already fired and drove degradation; nothing else to do.
      });

    return () => {
      cancelled = true;
      window.clearTimeout(connectTimer);
      void client.end();
      if (relayRef.current === client) relayRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [useRelay, effectiveMode]);

  /* --------------------- server voice: opening narration ------------------ */
  // Narrate the opening line when the server voice tier is engaged. Captions
  // already show the line; audio is a bonus and never blocks the turn.
  useEffect(() => {
    if (!serverVoiceActive || effectiveMode !== "voice") return;
    let cancelled = false;
    setPhaseNow("interviewer_speaking");
    void speakServer(session.opening.text).then(() => {
      if (!cancelled && !endedRef.current) setPhaseNow("listening");
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverVoiceActive, effectiveMode]);

  // Release the server voice graph (audio + recorder + mic) on unmount.
  useEffect(() => disposeServerVoice, [disposeServerVoice]);

  /* -------------------------------- timer --------------------------------- */
  useEffect(() => {
    const id = window.setInterval(() => {
      setTimeLeft((prev) => {
        const next = prev - 1;
        if (next <= 0) {
          window.clearInterval(id);
          finalize();
          return 0;
        }
        return next;
      });
    }, 1000);
    return () => window.clearInterval(id);
  }, [finalize]);

  /* ----------------------- idle nudge / silent STT ------------------------ */
  // While it's the candidate's turn, a long silence means they're either stuck
  // or (on the browser/realtime voice path) STT isn't hearing them. After a
  // grace period we surface a calm nudge offering to switch to typing. Any
  // recognized speech (candidateCaption) or a phase change resets the wait.
  useEffect(() => {
    setIdleHint(false);
    if (phase !== "listening" || endedRef.current) return;
    const id = window.setTimeout(() => {
      if (!endedRef.current) setIdleHint(true);
    }, IDLE_HINT_MS);
    return () => window.clearTimeout(id);
  }, [phase, candidateCaption, effectiveMode]);

  /* ------------------------ interviewer audio level ----------------------- */
  // Smoothed 0..1 amplitude of the INTERVIEWER's live audio, used to drive the
  // avatar's mouth. The realtime relay / descriptor tiers expose the REAL PCM
  // playback amplitude (a pure side-tap that never touches playback). The
  // turn-based TTS and browser speech-synthesis tiers expose no amplitude, so
  // the avatar falls back to a lifelike synthetic talk envelope while the
  // interviewer speaks (see InterviewerAvatar).
  const getInterviewerLevel = useCallback(() => {
    if (relayRef.current) return relayRef.current.outputLevel;
    if (geminiRef.current) return geminiRef.current.outputLevel;
    return 0;
  }, []);

  /* --------------------------------- render ------------------------------- */
  const statusLabel = realtimeConnecting
    ? t("realtimeConnectingLabel")
    : phase === "interviewer_speaking"
      ? t("speakingLabel")
      : phase === "thinking"
        ? t("thinkingLabel")
        : phase === "ending"
          ? t("endingLabel")
          : effectiveMode === "voice"
            ? t("yourTurnLabel")
            : t("waitingLabel");

  const avatarState: AvatarState = realtimeConnecting
    ? "idle"
    : phase === "interviewer_speaking"
      ? "speaking"
      : phase === "thinking"
        ? "thinking"
        : phase === "listening"
          ? "listening"
          : "idle";

  const bigCaption = interviewerStreaming ?? currentQuestion;
  const lastMinute = timeLeft <= 60;
  const announceMinutes = Math.ceil(timeLeft / 60);
  const speaking = phase === "interviewer_speaking";
  const progressPct = Math.round((Math.min(questionCount, target) / target) * 100);

  return (
    <div className="mx-auto flex min-h-[calc(100vh-var(--topbar-height))] w-full max-w-4xl flex-col gap-3 px-3 py-4 sm:px-4 sm:py-5">
      {/* Top bar: room label + status · question progress + countdown */}
      <header className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="kicker shrink-0">{t("roomTitle")}</span>
          <StatusPill state={avatarState} label={statusLabel} />
        </div>
        <div className="flex shrink-0 items-center gap-2.5 sm:gap-3">
          <span className="hidden font-data text-xs text-[var(--text-muted)] sm:inline">
            {t("questionCounter", { current: Math.min(questionCount, target), target })}
          </span>
          <span
            aria-hidden
            className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-[var(--bg-muted)] sm:block"
          >
            <span
              className="block h-full rounded-full bg-[var(--brand-primary)] transition-all duration-500"
              style={{ width: `${Math.max(progressPct, 4)}%` }}
            />
          </span>
          <span
            aria-hidden
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-data text-xs tabular-nums",
              lastMinute
                ? "border-[var(--brand-red)]/30 bg-[var(--red-50)] text-[var(--brand-red)]"
                : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)]",
            )}
          >
            {formatClock(timeLeft)}
          </span>
        </div>
        {/* Coarse, non-chatty SR announcement for the countdown. */}
        <span aria-live="polite" className="sr-only">
          {lastMinute ? t("timeLastMinute") : t("timeLeftAnnounce", { minutes: announceMinutes })}
        </span>
      </header>

      {/* Stage — the interviewer "video tile" + student self-view PiP */}
      <div
        className="relative flex min-h-[280px] flex-1 items-center justify-center overflow-hidden rounded-2xl border border-[var(--border-default)] p-4 sm:p-6"
        style={{
          background:
            "radial-gradient(120% 85% at 50% 10%, var(--viz-indigo-soft), transparent 58%), linear-gradient(180deg, var(--bg-muted) 0%, var(--bg-subtle) 100%)",
        }}
      >
        {/* Interviewer camera tile */}
        <div
          className={cn(
            "relative aspect-[4/5] h-full max-h-[min(52vh,420px)] overflow-hidden rounded-2xl shadow-xl transition-shadow duration-500",
            speaking
              ? "ring-2 ring-[var(--content-info)]/55"
              : "ring-1 ring-black/10",
          )}
        >
          <div
            className="absolute inset-0"
            style={{
              background: "linear-gradient(165deg, #eef1f7 0%, #dee3ee 55%, #cfd6e4 100%)",
            }}
          />
          {/* soft speaking glow */}
          {speaking && !reduced && (
            <span
              aria-hidden
              className="pointer-events-none absolute -inset-2 rounded-3xl opacity-70 blur-xl"
              style={{ background: "radial-gradient(50% 40% at 50% 60%, var(--viz-indigo-soft), transparent 70%)" }}
            />
          )}
          <InterviewerAvatar
            state={avatarState}
            getLevel={getInterviewerLevel}
            reduced={reduced}
            className="relative"
          />

          {/* Thinking indicator */}
          {avatarState === "thinking" && <ThinkingDots reduced={reduced} label={t("thinkingLabel")} />}

          {/* Nameplate */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 p-2.5">
            <div className="flex items-center gap-1.5 rounded-lg bg-black/45 px-2 py-1 backdrop-blur-sm">
              <span className="text-xs font-semibold text-white">{t("interviewerName")}</span>
              <span className="rounded bg-white/20 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white">
                {t("roomAiTag")}
              </span>
            </div>
          </div>
        </div>

        {/* Student self-view PiP */}
        <div className="absolute bottom-3 right-3 z-10">
          <SelfViewTile camera={camera} />
        </div>

        {/* Connecting overlay */}
        {realtimeConnecting && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/35 backdrop-blur-sm">
            <span className="inline-flex items-center gap-2 rounded-full bg-black/55 px-3.5 py-2 text-xs font-semibold text-white">
              <CircleNotch aria-hidden weight="bold" className="size-4 animate-spin" />
              {t("realtimeConnectingLabel")}
            </span>
          </div>
        )}
      </div>

      {/* Captions — the accessibility layer */}
      <div
        className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-3.5 sm:px-5"
        aria-live="polite"
      >
        <p className="kicker">{t("interviewerLabel")}</p>
        <p className="mt-1 text-balance text-base font-semibold leading-snug text-[var(--text-primary)] sm:text-lg">
          {bigCaption}
        </p>
        {candidateCaption && (
          <div className="mt-3 border-t border-[var(--border-subtle)] pt-3">
            <p className="kicker">{t("youLabel")}</p>
            <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">
              {candidateCaption}
            </p>
          </div>
        )}
      </div>

      {/* Subtle interview-topic coverage (real backend summary, advances live) */}
      {liveCoverage ? (
        <CoverageChips coverage={liveCoverage} className="justify-center px-1" />
      ) : null}

      {/* Bottom controls */}
      <div className="space-y-3">
        {realtimeLost && (
          <div
            role="alert"
            className="mx-auto max-w-xl rounded-lg border border-[var(--amber-600)]/30 bg-[var(--amber-50)] px-3 py-2.5 text-center"
          >
            <p className="text-xs font-semibold text-[var(--text-primary)]">{t("realtimeLostTitle")}</p>
            <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-secondary)]">
              {t("realtimeLostBody")}
            </p>
            <div className="mt-2 flex justify-center">
              <Button variant="secondary" size="sm" onClick={continueInText}>
                <Keyboard aria-hidden weight="bold" className="size-4" />
                {t("realtimeContinueText")}
              </Button>
            </div>
          </div>
        )}

        {degraded && (
          <p className="mx-auto max-w-xl rounded-lg bg-[var(--amber-50)] px-3 py-2 text-center text-xs leading-relaxed text-[var(--amber-700)]">
            {t("textModeNotice")}
          </p>
        )}

        {turnError && (
          <div className="mx-auto flex max-w-xl items-center justify-center gap-3 rounded-lg bg-[var(--red-50)] px-3 py-2 text-xs text-[var(--red-700)]">
            <span>{t("turnError")}</span>
            {lastAnswerRef.current && (
              <button
                type="button"
                onClick={() => void beginTurn(lastAnswerRef.current)}
                className="font-semibold underline outline-none hover:no-underline focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
              >
                {t("retryTurn")}
              </button>
            )}
          </div>
        )}

        {/* Idle nudge / silent-STT escape hatch. Only when nothing more urgent
            (turn error, dropped realtime) is already offering the user a next
            step. Voice: gently offer to switch to typing. Text: soft reassurance. */}
        {idleHint && !turnError && !realtimeLost && (
          effectiveMode === "voice" ? (
            <div
              role="status"
              className="mx-auto max-w-xl rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2.5 text-center shadow-sm"
            >
              <p className="text-xs font-semibold text-[var(--text-primary)]">{t("idleHintTitle")}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-secondary)]">
                {t("idleHintVoiceBody")}
              </p>
              <div className="mt-2 flex justify-center">
                <Button variant="secondary" size="sm" onClick={degradeToText}>
                  <Keyboard aria-hidden weight="bold" className="size-4" />
                  {t("idleSwitchToText")}
                </Button>
              </div>
            </div>
          ) : (
            <p
              role="status"
              className="mx-auto max-w-xl text-center text-xs leading-relaxed text-[var(--text-muted)]"
            >
              {t("idleHintTextBody")}
            </p>
          )
        )}

        {/* Server voice tier: calm, non-alarming notice when narration or
            transcription is temporarily unavailable. Captions/text always work. */}
        {effectiveMode === "voice" && serverVoiceActive && voiceNotice && (
          <p
            role="status"
            className="mx-auto max-w-xl rounded-lg bg-[var(--bg-subtle)] px-3 py-2 text-center text-xs leading-relaxed text-[var(--text-muted)]"
          >
            {voiceNotice === "tts"
              ? t("serverVoiceTtsUnavailable")
              : voiceNotice === "stt"
                ? t("serverVoiceSttUnavailable")
                : t("serverVoiceMicDenied")}
          </p>
        )}

        {effectiveMode === "text" ? (
          <TextAnswerBar
            value={textDraft}
            onChange={setTextDraft}
            disabled={phase === "thinking" || phase === "interviewer_speaking" || phase === "ending"}
            onSubmit={() => {
              const v = textDraft.trim();
              if (!v) return;
              setTextDraft("");
              void beginTurn(v);
            }}
          />
        ) : useRelay ? (
          <RelayAnswerBar
            speaking={relaySpeaking}
            connecting={realtimeConnecting}
            disabled={realtimeConnecting || phase === "ending"}
            onToggleSpeak={toggleRelaySpeak}
            onSwitchToText={degradeToText}
          />
        ) : serverVoiceActive ? (
          <ServerVoiceAnswerBar
            value={textDraft}
            onChange={setTextDraft}
            recording={recording}
            transcribing={transcribing}
            recorderSupported={recorderSupported}
            onToggleRecord={toggleRecord}
            recordDisabled={
              !recording && (phase === "thinking" || phase === "ending" || transcribing)
            }
            sendDisabled={
              phase === "thinking" ||
              phase === "interviewer_speaking" ||
              phase === "ending" ||
              recording ||
              transcribing
            }
            textDisabled={phase === "ending"}
            onSubmit={() => {
              const v = textDraft.trim();
              if (!v) return;
              setTextDraft("");
              setVoiceNotice(null);
              void beginTurn(v);
            }}
          />
        ) : (
          <div className="flex items-center justify-center gap-2 text-xs text-[var(--text-muted)]">
            <MicLevelMeter
              getLevel={() => geminiRef.current?.level ?? controllerRef.current?.level ?? 0}
              active={phase === "listening"}
              reduced={reduced}
            />
            <span>{phase === "listening" ? t("listeningLabel") : t("micLevelLabel")}</span>
          </div>
        )}

        <div className="flex items-center justify-center gap-2 pt-1">
          <CameraToggleButton camera={camera} />
          <Button
            variant="primaryRed"
            size="md"
            onClick={finalize}
            disabled={phase === "ending"}
            aria-label={t("endCta")}
          >
            <PhoneDisconnect aria-hidden weight="fill" className="size-4" />
            {phase === "ending" ? t("endingLabel") : t("endCta")}
          </Button>
        </div>
        <p className="text-center text-[11px] text-[var(--text-muted)]">{t("disclaimer")}</p>
      </div>
    </div>
  );
}

/** Small state pill for the room top bar (dot colour encodes the phase). */
function StatusPill({ state, label }: { state: AvatarState; label: string }) {
  const tone =
    state === "speaking"
      ? "var(--content-info)"
      : state === "listening"
        ? "var(--content-success)"
        : state === "thinking"
          ? "var(--content-warning)"
          : "var(--text-muted)";
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-2.5 py-0.5">
      <span aria-hidden className="size-2 shrink-0 rounded-full" style={{ backgroundColor: tone }} />
      <span className="truncate text-[11px] font-semibold text-[var(--text-secondary)]">{label}</span>
    </span>
  );
}

/** Three-dot "thinking" bubble shown over the avatar between turns. */
function ThinkingDots({ reduced, label }: { reduced: boolean; label: string }) {
  return (
    <div className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2">
      <span
        className="inline-flex items-center gap-1 rounded-full bg-black/45 px-2.5 py-1.5 backdrop-blur-sm"
        role="status"
        aria-label={label}
      >
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            aria-hidden
            className={cn("size-1.5 rounded-full bg-white/85", !reduced && "animate-bounce")}
            style={!reduced ? { animationDelay: `${i * 150}ms`, animationDuration: "1s" } : undefined}
          />
        ))}
      </span>
    </div>
  );
}

/** Round camera on/off toggle for the controls bar (mirrors the PiP tile). */
function CameraToggleButton({ camera }: { camera: ReturnType<typeof useSelfViewCamera> }) {
  const t = useTranslations("jobs.mockInterview");
  const on = camera.status === "on" || camera.status === "starting";
  const unsupported = camera.status === "unsupported" || !camera.supported;
  return (
    <button
      type="button"
      onClick={camera.toggle}
      disabled={unsupported}
      aria-pressed={on}
      aria-label={on ? t("cameraDisable") : t("cameraEnable")}
      title={on ? t("cameraDisable") : t("cameraEnable")}
      className={cn(
        "inline-flex h-10 items-center gap-2 rounded-full border px-3.5 text-sm font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 disabled:cursor-not-allowed disabled:opacity-50",
        on
          ? "border-[var(--brand-primary)] bg-[var(--brand-primary)] text-[var(--text-inverted)]"
          : "border-[var(--border-strong)] bg-[var(--surface-card)] text-[var(--text-secondary)] hover:border-[var(--text-muted)]",
      )}
    >
      {on ? (
        <VideoCamera aria-hidden weight="fill" className="size-4" />
      ) : (
        <VideoCameraSlash aria-hidden weight="regular" className="size-4" />
      )}
      <span className="hidden sm:inline">{t("cameraLabel")}</span>
    </button>
  );
}

function TextAnswerBar({
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}) {
  const t = useTranslations("jobs.mockInterview");
  return (
    <div className="mx-auto flex max-w-xl items-end gap-2 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 shadow-sm focus-within:border-[var(--field-focus-border)]">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!disabled) onSubmit();
          }
        }}
        placeholder={t("textAnswerPlaceholder")}
        aria-label={t("textAnswerPlaceholder")}
        rows={1}
        disabled={disabled}
        className="max-h-32 flex-1 resize-none bg-transparent py-1.5 text-sm leading-relaxed text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] disabled:opacity-60"
      />
      <Button
        variant="primary"
        size="sm"
        onClick={onSubmit}
        disabled={disabled || !value.trim()}
        aria-label={t("sendAnswer")}
      >
        <ArrowRight aria-hidden weight="bold" className="size-4" />
      </Button>
    </div>
  );
}

/**
 * Server voice answer bar: record (MediaRecorder → server STT) OR type. The
 * transcript lands in the editable textarea for the student to REVIEW before
 * sending — never auto-submitted. Typing is always available as the a11y floor.
 */
function ServerVoiceAnswerBar({
  value,
  onChange,
  onSubmit,
  recording,
  transcribing,
  recorderSupported,
  onToggleRecord,
  recordDisabled,
  sendDisabled,
  textDisabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  recording: boolean;
  transcribing: boolean;
  recorderSupported: boolean;
  onToggleRecord: () => void;
  recordDisabled: boolean;
  sendDisabled: boolean;
  textDisabled: boolean;
}) {
  const t = useTranslations("jobs.mockInterview");
  return (
    <div className="mx-auto max-w-xl space-y-2">
      <div className="flex items-end gap-2 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 shadow-sm focus-within:border-[var(--field-focus-border)]">
        {recorderSupported && (
          <button
            type="button"
            onClick={onToggleRecord}
            disabled={recordDisabled}
            aria-pressed={recording}
            aria-label={recording ? t("serverVoiceStop") : t("serverVoiceRecord")}
            className={cn(
              "relative flex size-9 shrink-0 items-center justify-center rounded-full outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 disabled:cursor-not-allowed disabled:opacity-50",
              recording
                ? "bg-[var(--brand-red)] text-white"
                : "bg-[var(--bg-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]",
            )}
          >
            {recording && (
              <span
                aria-hidden
                className="pointer-events-none absolute inset-0 animate-ping rounded-full bg-[var(--brand-red)]/40"
              />
            )}
            {recording ? (
              <Stop aria-hidden weight="fill" className="relative size-4" />
            ) : (
              <Microphone aria-hidden weight="fill" className="relative size-4" />
            )}
          </button>
        )}
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!sendDisabled && value.trim()) onSubmit();
            }
          }}
          placeholder={t("textAnswerPlaceholder")}
          aria-label={t("textAnswerPlaceholder")}
          rows={1}
          disabled={textDisabled}
          className="max-h-32 flex-1 resize-none bg-transparent py-1.5 text-sm leading-relaxed text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] disabled:opacity-60"
        />
        <Button
          variant="primary"
          size="sm"
          onClick={onSubmit}
          disabled={sendDisabled || !value.trim()}
          aria-label={t("sendAnswer")}
        >
          <ArrowRight aria-hidden weight="bold" className="size-4" />
        </Button>
      </div>
      <p
        className="flex items-center justify-center gap-1.5 text-center text-[11px] text-[var(--text-muted)]"
        aria-live="polite"
      >
        {transcribing ? (
          <>
            <CircleNotch aria-hidden weight="bold" className="size-3.5 animate-spin" />
            {t("serverVoiceTranscribing")}
          </>
        ) : recording ? (
          <>
            <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-[var(--brand-red)]" />
            {t("serverVoiceRecording")}
          </>
        ) : recorderSupported ? (
          t("serverVoiceHintBar")
        ) : (
          t("serverVoiceTypeHint")
        )}
      </p>
    </div>
  );
}

/**
 * Relay (Tier V3) push-to-talk control: one prominent mic button the student
 * taps to speak and taps again to finish (`aria-pressed` reflects the state).
 * There is no text answer box in this tier — captions are the a11y floor — but a
 * "type instead" escape hatch always drops to the text tier.
 */
function RelayAnswerBar({
  speaking,
  connecting,
  disabled,
  onToggleSpeak,
  onSwitchToText,
}: {
  speaking: boolean;
  connecting: boolean;
  disabled: boolean;
  onToggleSpeak: () => void;
  onSwitchToText: () => void;
}) {
  const t = useTranslations("jobs.mockInterview");
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-2.5">
      <button
        type="button"
        onClick={onToggleSpeak}
        disabled={disabled}
        aria-pressed={speaking}
        aria-label={speaking ? t("relaySpeakStop") : t("relaySpeakStart")}
        className={cn(
          "relative flex size-14 items-center justify-center rounded-full outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 disabled:cursor-not-allowed disabled:opacity-50",
          speaking
            ? "bg-[var(--brand-red)] text-white"
            : "bg-[var(--bg-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]",
        )}
      >
        {speaking && (
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0 animate-ping rounded-full bg-[var(--brand-red)]/40"
          />
        )}
        {speaking ? (
          <Stop aria-hidden weight="fill" className="relative size-6" />
        ) : (
          <Microphone aria-hidden weight="fill" className="relative size-6" />
        )}
      </button>
      <p
        className="text-center text-[11px] leading-relaxed text-[var(--text-muted)]"
        aria-live="polite"
      >
        {connecting
          ? t("realtimeConnectingLabel")
          : speaking
            ? t("relayHintSpeaking")
            : t("relayHintIdle")}
      </p>
      <button
        type="button"
        onClick={onSwitchToText}
        className="inline-flex items-center gap-1.5 rounded text-[11px] font-semibold text-[var(--text-muted)] outline-none transition-colors hover:text-[var(--text-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <Keyboard aria-hidden weight="bold" className="size-3.5" />
        {t("idleSwitchToText")}
      </button>
    </div>
  );
}

/** Small live mic-level bar for the voice tier (browser voice or realtime). */
function MicLevelMeter({
  getLevel,
  active,
  reduced,
}: {
  getLevel: () => number;
  active: boolean;
  reduced: boolean;
}) {
  const barRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (reduced) return;
    let raf = 0;
    const loop = () => {
      const level = active ? getLevel() : 0;
      if (barRef.current) {
        barRef.current.style.width = `${Math.round(6 + level * 26)}px`;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [active, reduced, getLevel]);

  return (
    <span className="flex items-center gap-1.5">
      {active ? (
        <Microphone aria-hidden weight="fill" className="size-3.5 text-[var(--brand-primary)]" />
      ) : (
        <MicrophoneSlash aria-hidden weight="regular" className="size-3.5 text-[var(--text-muted)]" />
      )}
      <span
        aria-hidden
        className="inline-block h-1.5 rounded-full bg-[var(--brand-primary)]/70"
        style={{ width: "6px" }}
        ref={barRef}
      />
    </span>
  );
}
