"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { ArrowRight, Keyboard, Microphone, MicrophoneSlash, PhoneDisconnect } from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import {
  mockInterviewApi,
  type MockInterviewSession,
  type RecordTurnInput,
} from "@/lib/api";
import { VoiceController } from "@/lib/mock-interview/voice-controller";
import { GeminiLiveClient } from "@/lib/mock-interview/gemini-live-client";
import { usePrefersReducedMotion } from "@/lib/hooks/use-mount-animation";
import { cn } from "@/lib/utils";
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
  onRequestEnd: (payload: { duration_seconds: number; turns?: RecordTurnInput[] }) => void;
}

/**
 * The "Room": a single presence orb, subtitle-style captions, a question
 * timeline, a quiet countdown + counter, and an End control. Drives the voice
 * controller (STT → SSE turn → TTS) or a text answer box. Captions are the
 * accessibility layer for the voice conversation.
 */
export function LiveSession({ session, mode, locale, onRequestEnd }: Props) {
  const t = useTranslations("jobs.mockInterview");
  const reduced = usePrefersReducedMotion();

  const target = Math.max(1, session.caps.target_questions || session.caps.max_questions || 1);

  // Realtime (Tier V2) is active only when the server hands out a descriptor.
  // Its visible countdown never exceeds the hard live-voice duration cap.
  const realtime = session.realtime;
  const initialSeconds =
    realtime && realtime.duration_cap_s > 0
      ? Math.min(session.caps.max_session_seconds, realtime.duration_cap_s)
      : session.caps.max_session_seconds;

  const [effectiveMode, setEffectiveMode] = useState<AnswerMode>(mode);
  const [degraded, setDegraded] = useState(false);
  const [phase, setPhase] = useState<Phase>(mode === "voice" ? "interviewer_speaking" : "listening");
  const [currentQuestion, setCurrentQuestion] = useState(session.opening.text);
  const [interviewerStreaming, setInterviewerStreaming] = useState<string | null>(null);
  const [candidateCaption, setCandidateCaption] = useState("");
  const [questionCount, setQuestionCount] = useState(1);
  const [timeLeft, setTimeLeft] = useState(initialSeconds);
  const [turnError, setTurnError] = useState(false);
  const [idleHint, setIdleHint] = useState(false);
  const [textDraft, setTextDraft] = useState("");
  // Realtime-only presentation states (unused on the V1/text path).
  const [realtimeConnecting, setRealtimeConnecting] = useState(!!realtime);
  const [realtimeLost, setRealtimeLost] = useState(false);

  const phaseRef = useRef<Phase>(phase);
  const effectiveModeRef = useRef<AnswerMode>(effectiveMode);
  const controllerRef = useRef<VoiceController | null>(null);
  const geminiRef = useRef<GeminiLiveClient | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const interviewerBufRef = useRef("");
  const lastAnswerRef = useRef("");
  const startedAtRef = useRef<number>(Date.now());
  const endedRef = useRef(false);
  const turnsRef = useRef<RecordTurnInput[]>([]);
  const orbRef = useRef<HTMLDivElement>(null);

  const setPhaseNow = useCallback((next: Phase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);

  useEffect(() => {
    effectiveModeRef.current = effectiveMode;
  }, [effectiveMode]);

  /* ------------------------------ end session ----------------------------- */
  const finalize = useCallback(() => {
    if (endedRef.current) return;
    endedRef.current = true;
    const duration = Math.round((Date.now() - startedAtRef.current) / 1000);
    abortRef.current?.abort();
    controllerRef.current?.dispose();
    setPhaseNow("ending");

    const gemini = geminiRef.current;
    if (gemini) {
      // Realtime: stop (releases mic, flushes remaining turns) BEFORE ending so
      // the coaching report sees the full transcript. Turns are already
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
  }, [onRequestEnd, setPhaseNow]);

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
            if (evt.ended) {
              finalize();
              return;
            }
            if (effectiveModeRef.current === "voice" && controllerRef.current) {
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
    [session.session_id, finalize, setPhaseNow],
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

  /* ---------------------------- voice lifecycle --------------------------- */
  useEffect(() => {
    // Realtime (Tier V2) owns the voice tier when a descriptor is present; the
    // browser STT/TTS controller must not also grab the mic.
    if (realtime && effectiveMode === "voice") return;
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

  /* ---------------------------- orb animation ----------------------------- */
  useEffect(() => {
    if (reduced) return; // static orb under reduced motion
    let raf = 0;
    let scale = 1;
    const loop = () => {
      let goalTarget = 1;
      const p = phaseRef.current;
      if (effectiveModeRef.current === "voice" && p === "listening") {
        goalTarget = 1 + (geminiRef.current?.level ?? controllerRef.current?.level ?? 0) * 0.22;
      } else if (p === "interviewer_speaking") {
        goalTarget = 1.05 + 0.05 * (0.5 + 0.5 * Math.sin(performance.now() / 320));
      } else if (p === "thinking") {
        goalTarget = 1.02 + 0.02 * (0.5 + 0.5 * Math.sin(performance.now() / 600));
      }
      scale += (goalTarget - scale) * 0.12;
      if (orbRef.current) {
        orbRef.current.style.transform = `scale(${scale.toFixed(3)})`;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [reduced]);

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

  const bigCaption = interviewerStreaming ?? currentQuestion;
  const lastMinute = timeLeft <= 60;
  const announceMinutes = Math.ceil(timeLeft / 60);

  return (
    <div className="mx-auto flex min-h-[calc(100vh-var(--topbar-height))] max-w-3xl flex-col px-4 py-6">
      {/* Quiet top row: counter + countdown */}
      <div className="flex items-center justify-between">
        <span className="font-data text-xs text-[var(--text-muted)]">
          {t("questionCounter", { current: Math.min(questionCount, target), target })}
        </span>
        <span
          className={cn(
            "font-data text-xs tabular-nums",
            lastMinute ? "text-[var(--brand-red)]" : "text-[var(--text-muted)]",
          )}
          aria-hidden
        >
          {formatClock(timeLeft)}
        </span>
        {/* Coarse, non-chatty SR announcement for the countdown. */}
        <span aria-live="polite" className="sr-only">
          {lastMinute ? t("timeLastMinute") : t("timeLeftAnnounce", { minutes: announceMinutes })}
        </span>
      </div>

      {/* Center stage */}
      <div className="flex flex-1 flex-col items-center justify-center gap-8 py-8 text-center">
        {/* Presence orb */}
        <div className="relative flex size-44 items-center justify-center sm:size-52">
          <div
            aria-hidden
            className={cn(
              "absolute inset-0 rounded-full blur-2xl transition-opacity duration-500",
              phase === "interviewer_speaking" ? "opacity-70" : "opacity-40",
            )}
            style={{
              background:
                "radial-gradient(circle at 50% 45%, var(--gray-500) 0%, transparent 70%)",
            }}
          />
          <div
            ref={orbRef}
            role="img"
            aria-label={t("orbAria")}
            className="relative size-36 rounded-full sm:size-44"
            style={{
              background:
                "radial-gradient(circle at 50% 42%, var(--text-primary) 0%, var(--gray-600) 46%, var(--gray-800) 72%, transparent 78%)",
              boxShadow: "0 12px 48px rgba(0,0,0,0.22)",
              transform: "scale(1)",
              transition: reduced ? "none" : undefined,
            }}
          />
          {/* Status ring label */}
          <span className="pointer-events-none absolute -bottom-1 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-0.5 text-[11px] font-semibold text-[var(--text-secondary)] shadow-sm">
            {statusLabel}
          </span>
        </div>

        {/* Captions — the accessibility layer */}
        <div className="w-full max-w-xl space-y-3" aria-live="polite">
          <p className="kicker">{t("interviewerLabel")}</p>
          <p
            className="text-balance text-xl font-semibold leading-snug text-[var(--text-primary)] sm:text-2xl"
            style={{ fontFamily: "var(--font-sans)" }}
          >
            {bigCaption}
          </p>
          {candidateCaption && (
            <div className="pt-1">
              <p className="kicker">{t("youLabel")}</p>
              <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">
                {candidateCaption}
              </p>
            </div>
          )}
        </div>

        {/* Question timeline */}
        <div
          className="flex items-center gap-1.5"
          role="img"
          aria-label={t("timelineAria", { current: Math.min(questionCount, target), target })}
        >
          {Array.from({ length: target }).map((_, i) => (
            <span
              key={i}
              className={cn(
                "h-1.5 rounded-full transition-all duration-300",
                i < questionCount ? "w-6 bg-[var(--brand-primary)]" : "w-3 bg-[var(--bg-muted)]",
              )}
            />
          ))}
        </div>
      </div>

      {/* Bottom controls */}
      <div className="mt-2 space-y-3">
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

        <div className="flex justify-center pt-1">
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
