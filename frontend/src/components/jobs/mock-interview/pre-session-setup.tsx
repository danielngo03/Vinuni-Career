"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowClockwise,
  CheckCircle,
  FileText,
  Keyboard,
  LockSimple,
  Microphone,
  Sparkle,
  Star,
  Target,
  VideoCamera,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, Skeleton } from "@/components/ui";
import { FitScoreRing } from "@/components/jobs/fit-score-ring";
import {
  mockInterviewApi,
  type MockInterviewPrepCv,
} from "@/lib/api";
import { fitTextColor, fitTier } from "@/lib/cv/fit";
import {
  detectVoiceSupport,
  queryMicPermission,
  type MicPermission,
} from "@/lib/mock-interview/voice-controller";
import { cn } from "@/lib/utils";
import { InterviewHistory } from "./interview-history";
import { RoundStepper } from "./round-indicator";

export type AnswerMode = "voice" | "text";

/** Known createSession failure surfaced as a calm, actionable state. */
export type StartBlock =
  | { kind: "quota_daily" }
  | { kind: "quota_weekly" }
  | { kind: "active_session"; sessionId: string | null }
  | { kind: "no_cv" }
  | { kind: "generic" };

interface Props {
  jobId: string;
  locale: string;
  starting: boolean;
  startBlock: StartBlock | null;
  onStart: (opts: {
    cvId: string | null;
    mode: AnswerMode;
    serverVoice?: boolean;
    realtimeRelay?: boolean;
  }) => void;
  onOpenSession: (id: string) => void;
  onResumeActive: (sessionId: string | null) => void;
  onDiscardActive: () => void;
  discarding: boolean;
}

export function PreSessionSetup({
  jobId,
  locale,
  starting,
  startBlock,
  onStart,
  onOpenSession,
  onResumeActive,
  onDiscardActive,
  discarding,
}: Props) {
  const t = useTranslations("jobs.mockInterview");

  const prep = useQuery({
    queryKey: ["mock-interview", "prep", jobId, locale],
    queryFn: () => mockInterviewApi.prep(jobId, locale),
    retry: false,
    staleTime: 60_000,
  });

  const support = useMemo(() => detectVoiceSupport(), []);
  const [micPerm, setMicPerm] = useState<MicPermission>("unknown");
  useEffect(() => {
    let alive = true;
    void queryMicPermission().then((p) => {
      if (alive) setMicPerm(p);
    });
    return () => {
      alive = false;
    };
  }, []);

  // Both server-mediated tiers (turn-based server voice, and the true full-duplex
  // realtime relay) only need a mic — not browser SpeechRecognition — so voice
  // mode is usable on browsers without STT when the server advertises either.
  const realtimeRelayAvailable = prep.data?.realtime_relay === true;
  const serverVoiceAvailable = prep.data?.server_voice === true;
  const voiceModeAvailable =
    support.voiceReady ||
    (support.getUserMedia && (realtimeRelayAvailable || serverVoiceAvailable));

  const [mode, setMode] = useState<AnswerMode>(support.voiceReady ? "voice" : "text");
  // If the mic is known-denied, default to text (voice is still selectable).
  useEffect(() => {
    if (voiceModeAvailable && micPerm === "denied") setMode("text");
  }, [voiceModeAvailable, micPerm]);

  const [selectedCvId, setSelectedCvId] = useState<string | null>(null);
  const recommendedId = prep.data?.recommended_cv_id ?? prep.data?.cvs[0]?.cv_id ?? null;
  useEffect(() => {
    setSelectedCvId((prev) =>
      prev && prep.data?.cvs.some((c) => c.cv_id === prev) ? prev : recommendedId,
    );
  }, [prep.data, recommendedId]);

  const voiceNotice: { tone: "amber" | "muted"; text: string } | null = !voiceModeAvailable
    ? { tone: "amber", text: t("micUnsupportedNotice") }
    : micPerm === "denied"
      ? { tone: "amber", text: t("micDeniedNotice") }
      : mode === "voice" && micPerm !== "granted"
        ? { tone: "muted", text: t("micPromptNotice") }
        : null;

  const hasCvs = !!prep.data && prep.data.cvs.length > 0;

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 lg:py-8">
      {/* ---- Hero: sets the stage (the one restrained brand-blue gradient) ---- */}
      <section
        className="relative overflow-hidden rounded-[20px] px-5 py-6 sm:px-7 sm:py-7"
        style={{ background: "var(--hero-gradient)", color: "var(--hero-gradient-fg)" }}
      >
        <div className="relative max-w-2xl">
          <p className="kicker text-white/70">{t("setupKicker")}</p>
          <h1 className="type-h1 mt-1.5 text-white">{t("setupTitle")}</h1>
          <p className="type-body mt-1.5 max-w-lg text-white/80">{t("setupSubtitle")}</p>
          {prep.data?.job && (
            <p className="mt-3 inline-flex max-w-full items-center gap-1.5 rounded-full bg-white/12 px-3 py-1 text-xs font-semibold text-white ring-1 ring-inset ring-white/15 backdrop-blur-sm">
              <span className="truncate">{prep.data.job.title}</span>
              {prep.data.job.company_name ? (
                <>
                  <span aria-hidden className="text-white/50">·</span>
                  <span className="truncate font-normal text-white/80">
                    {prep.data.job.company_name}
                  </span>
                </>
              ) : null}
            </p>
          )}

          {/* at-a-glance facts */}
          <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5">
            <HeroFact icon={Target} label={t("factTailored")} />
            <HeroFact icon={LockSimple} label={t("factPrivate")} />
            <HeroFact icon={Sparkle} label={t("factCoaching")} />
          </ul>

          {/* multi-round plan (optional; hidden when absent) */}
          {prep.data?.rounds && prep.data.rounds.length > 0 && (
            <div className="mt-5 border-t border-white/15 pt-4">
              <RoundStepper
                variant="hero"
                rounds={prep.data.rounds}
                current={prep.data.current_round}
              />
            </div>
          )}
        </div>
      </section>

      {startBlock && (
        <div className="mt-6">
          <StartBlockPanel
            block={startBlock}
            onStartText={() =>
              onStart({ cvId: selectedCvId, mode: "text", serverVoice: false, realtimeRelay: false })
            }
            onResumeActive={onResumeActive}
            onDiscardActive={onDiscardActive}
            discarding={discarding}
            starting={starting}
          />
        </div>
      )}

      {prep.isPending ? (
        <SetupSkeleton />
      ) : prep.isError ? (
        <div
          role="alert"
          className="mt-6 flex flex-col items-start gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-5 py-6"
        >
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
            <WarningCircle aria-hidden weight="duotone" className="size-5 text-[var(--brand-red)]" />
            {t("prepLoadError")}
          </p>
          <Button variant="secondary" size="sm" onClick={() => prep.refetch()} disabled={prep.isFetching}>
            <ArrowClockwise aria-hidden weight="bold" className="size-4" />
            {t("retry")}
          </Button>
        </div>
      ) : !hasCvs ? (
        <div className="mt-6 flex flex-col items-start gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-5 py-6">
          <span className="flex size-11 items-center justify-center rounded-2xl icon-chip-neutral">
            <FileText aria-hidden weight="duotone" className="size-5" />
          </span>
          <div>
            <h2 className="text-base font-bold text-[var(--text-primary)]">{t("cvNoneTitle")}</h2>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">{t("cvNoneBody")}</p>
          </div>
          <Link href="/student/cv">
            <Button variant="primary" size="sm">
              {t("cvNoneCta")}
            </Button>
          </Link>
        </div>
      ) : (
        <>
          <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px] lg:items-start">
            {/* Main column: choose CV + answer mode */}
            <div className="min-w-0 space-y-6">
              {/* CV picker */}
              <section aria-labelledby="mi-cv-title">
                <div className="mb-3">
                  <h2 id="mi-cv-title" className="type-h3 text-[var(--text-primary)]">
                    {t("cvPickerTitle")}
                  </h2>
                  <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{t("cvPickerSubtitle")}</p>
                </div>
                {prep.data.signal === "low_signal" && (
                  <p className="mb-3 flex items-start gap-1.5 rounded-lg bg-[var(--amber-50)] px-3 py-2 text-xs leading-relaxed text-[var(--amber-700)]">
                    <WarningCircle aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0" />
                    {t("lowSignalNote")}
                  </p>
                )}
                <ul className="space-y-2.5" role="radiogroup" aria-label={t("cvPickerTitle")}>
                  {prep.data.cvs.map((cv) => (
                    <CvCard
                      key={cv.cv_id}
                      cv={cv}
                      selected={selectedCvId === cv.cv_id}
                      onSelect={() => setSelectedCvId(cv.cv_id)}
                    />
                  ))}
                </ul>
              </section>

              {/* Mode toggle */}
              <section aria-labelledby="mi-mode-title">
                <h2 id="mi-mode-title" className="type-h3 text-[var(--text-primary)]">
                  {t("modeTitle")}
                </h2>
                <div className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                  <ModeCard
                    icon={Microphone}
                    label={t("modeVoice")}
                    hint={t("modeVoiceHint")}
                    selected={mode === "voice"}
                    disabled={!voiceModeAvailable}
                    onSelect={() => setMode("voice")}
                  />
                  <ModeCard
                    icon={Keyboard}
                    label={t("modeText")}
                    hint={t("modeTextHint")}
                    selected={mode === "text"}
                    onSelect={() => setMode("text")}
                  />
                </div>
                {voiceNotice && (
                  <p
                    className={cn(
                      "mt-3 flex items-start gap-1.5 rounded-lg px-3 py-2 text-xs leading-relaxed",
                      voiceNotice.tone === "amber"
                        ? "bg-[var(--amber-50)] text-[var(--amber-700)]"
                        : "bg-[var(--bg-subtle)] text-[var(--text-muted)]",
                    )}
                  >
                    {voiceNotice.tone === "amber" && (
                      <WarningCircle aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0" />
                    )}
                    {voiceNotice.text}
                  </p>
                )}
                {mode === "voice" && !voiceNotice && realtimeRelayAvailable ? (
                  <p className="mt-3 text-xs leading-relaxed text-[var(--text-muted)]">
                    {t("relaySetupHint")}
                  </p>
                ) : mode === "voice" && !voiceNotice && serverVoiceAvailable ? (
                  <p className="mt-3 text-xs leading-relaxed text-[var(--text-muted)]">
                    {t("serverVoiceHint")}
                  </p>
                ) : null}
              </section>
            </div>

            {/* Rail: device readiness + the confident start */}
            <aside className="lg:sticky lg:top-4">
              <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                <h2 className="kicker mb-3">{t("readinessTitle")}</h2>
                <ul className="space-y-3">
                  <DeviceRow
                    icon={Microphone}
                    label={t("readinessMic")}
                    status={
                      !voiceModeAvailable
                        ? { text: t("readinessMicUnsupported"), tone: "muted" }
                        : micPerm === "denied"
                          ? { text: t("readinessMicBlocked"), tone: "amber" }
                          : micPerm === "granted"
                            ? { text: t("readinessMicReady"), tone: "teal" }
                            : { text: t("readinessMicAsk"), tone: "muted" }
                    }
                  />
                  <DeviceRow
                    icon={VideoCamera}
                    label={t("readinessCamera")}
                    status={{ text: t("readinessCameraOptional"), tone: "muted" }}
                  />
                </ul>
                <p className="mt-3 flex items-start gap-1.5 border-t border-[var(--border-subtle)] pt-3 text-[11px] leading-relaxed text-[var(--text-muted)]">
                  <LockSimple aria-hidden weight="fill" className="mt-0.5 size-3 shrink-0" />
                  {t("readinessPrivacy")}
                </p>
              </div>

              <Button
                variant="primary"
                size="lg"
                fullWidth
                className="mt-4"
                loading={starting}
                disabled={starting || !selectedCvId}
                onClick={() =>
                  onStart({
                    cvId: selectedCvId,
                    mode,
                    serverVoice: serverVoiceAvailable,
                    realtimeRelay: realtimeRelayAvailable,
                  })
                }
              >
                {mode === "voice" ? (
                  <Microphone aria-hidden weight="bold" className="size-4" />
                ) : (
                  <Keyboard aria-hidden weight="bold" className="size-4" />
                )}
                {starting ? t("startingCta") : t("startCta")}
              </Button>
              <p className="mt-2.5 text-center text-[11px] leading-relaxed text-[var(--text-muted)]">
                {t("disclaimer")}
              </p>
            </aside>
          </div>
        </>
      )}

      {/* Past sessions */}
      <div className="mt-10 border-t border-[var(--border-default)] pt-7">
        <InterviewHistory onOpen={onOpenSession} />
      </div>
    </div>
  );
}

function HeroFact({ icon: Icon, label }: { icon: React.ElementType; label: string }) {
  return (
    <li className="flex items-center gap-1.5 text-xs font-medium text-white/85">
      <Icon aria-hidden weight="fill" className="size-3.5 shrink-0 text-white/70" />
      {label}
    </li>
  );
}

function DeviceRow({
  icon: Icon,
  label,
  status,
}: {
  icon: React.ElementType;
  label: string;
  status: { text: string; tone: "teal" | "amber" | "muted" };
}) {
  const dot =
    status.tone === "teal"
      ? "bg-[var(--teal-500)]"
      : status.tone === "amber"
        ? "bg-[var(--amber-500)]"
        : "bg-[var(--border-strong)]";
  const textColor =
    status.tone === "teal"
      ? "text-[var(--teal-700)]"
      : status.tone === "amber"
        ? "text-[var(--amber-700)]"
        : "text-[var(--text-muted)]";
  return (
    <li className="flex items-center gap-2.5">
      <span
        aria-hidden
        className="flex size-8 shrink-0 items-center justify-center rounded-lg icon-chip-neutral"
      >
        <Icon weight="duotone" className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold text-[var(--text-primary)]">{label}</p>
        <p className={cn("mt-0.5 flex items-center gap-1.5 text-[11px] font-medium", textColor)}>
          <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", dot)} />
          {status.text}
        </p>
      </div>
    </li>
  );
}

function CvCard({
  cv,
  selected,
  onSelect,
}: {
  cv: MockInterviewPrepCv;
  selected: boolean;
  onSelect: () => void;
}) {
  const t = useTranslations("jobs.mockInterview");
  const tier = fitTier(cv.score);
  const tierLabel = tier === "strong" ? t("fitStrong") : tier === "mid" ? t("fitGood") : t("fitFair");
  return (
    <li>
      <button
        type="button"
        role="radio"
        aria-checked={selected}
        onClick={onSelect}
        className={cn(
          "flex w-full items-center gap-3.5 rounded-2xl border px-4 py-3.5 text-left outline-none transition-[border-color,box-shadow] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
          selected
            ? "border-[var(--brand-primary)] bg-[var(--surface-card)] shadow-[0_2px_8px_rgba(15,23,42,0.06)] ring-1 ring-inset ring-[var(--brand-primary)]/25"
            : "border-[var(--border-default)] bg-[var(--surface-card)] hover:border-[var(--border-strong)]",
        )}
      >
        <span
          className="flex shrink-0 flex-col items-center gap-1"
          title={t("cvMatchLabel")}
          aria-label={t("cvMatchAria", { score: cv.score })}
        >
          <FitScoreRing score={cv.score} size="md" />
          <span
            aria-hidden
            className="text-[9px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]"
          >
            {t("cvMatchLabel")}
          </span>
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-[var(--text-primary)]" title={cv.title}>
            {cv.title}
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {cv.is_recommended && (
              <span className="inline-flex items-center gap-1 rounded-full bg-[var(--teal-50)] px-2 py-0.5 text-[11px] font-semibold text-[var(--teal-700)]">
                <Star aria-hidden weight="fill" className="size-3" />
                {t("recommendedBadge")}
              </span>
            )}
            <span
              className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-subtle)] px-2 py-0.5 text-[11px] font-medium"
              style={{ color: fitTextColor(cv.score) }}
            >
              <CheckCircle aria-hidden weight="fill" className="size-3" />
              {tierLabel}
            </span>
          </div>
        </div>
        <span
          aria-hidden
          className={cn(
            "flex size-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors",
            selected ? "border-[var(--brand-primary)]" : "border-[var(--border-strong)]",
          )}
        >
          {selected && <span className="size-2.5 rounded-full bg-[var(--brand-primary)]" />}
        </span>
      </button>
    </li>
  );
}

function ModeCard({
  icon: Icon,
  label,
  hint,
  selected,
  disabled,
  onSelect,
}: {
  icon: React.ElementType;
  label: string;
  hint: string;
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        "relative flex items-start gap-3 rounded-2xl border px-4 py-3.5 text-left outline-none transition-[border-color,box-shadow] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
        disabled && "cursor-not-allowed opacity-50",
        selected
          ? "border-[var(--brand-primary)] bg-[var(--surface-card)] shadow-[0_2px_8px_rgba(15,23,42,0.06)] ring-1 ring-inset ring-[var(--brand-primary)]/25"
          : "border-[var(--border-default)] bg-[var(--surface-card)] hover:border-[var(--border-strong)]",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-xl",
          selected ? "icon-chip-primary" : "icon-chip-neutral",
        )}
      >
        <Icon weight="duotone" className="size-[18px]" />
      </span>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-[var(--text-primary)]">{label}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-muted)]">{hint}</p>
      </div>
      {selected && (
        <CheckCircle
          aria-hidden
          weight="fill"
          className="absolute right-3 top-3 size-4 text-[var(--brand-primary)]"
        />
      )}
    </button>
  );
}

function StartBlockPanel({
  block,
  onStartText,
  onResumeActive,
  onDiscardActive,
  discarding,
  starting,
}: {
  block: StartBlock;
  onStartText: () => void;
  onResumeActive: (sessionId: string | null) => void;
  onDiscardActive: () => void;
  discarding: boolean;
  starting: boolean;
}) {
  const t = useTranslations("jobs.mockInterview");

  const config: { title: string; body: string } = (() => {
    switch (block.kind) {
      case "quota_daily":
        return { title: t("blockQuotaDailyTitle"), body: t("blockQuotaDailyBody") };
      case "quota_weekly":
        return { title: t("blockQuotaWeeklyTitle"), body: t("blockQuotaWeeklyBody") };
      case "active_session":
        return { title: t("blockActiveTitle"), body: t("blockActiveBody") };
      case "no_cv":
        return { title: t("blockNoCvTitle"), body: t("blockNoCvBody") };
      default:
        return { title: t("blockGenericTitle"), body: t("blockGenericBody") };
    }
  })();

  const isQuota = block.kind === "quota_daily" || block.kind === "quota_weekly";

  return (
    <div
      role="alert"
      className="rounded-2xl border border-[var(--amber-600)]/30 bg-[var(--amber-50)] px-5 py-4"
    >
      <div className="flex items-start gap-2.5">
        <WarningCircle aria-hidden weight="duotone" className="mt-0.5 size-5 shrink-0 text-[var(--amber-700)]" />
        <div className="min-w-0">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">{config.title}</h2>
          <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">{config.body}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {isQuota && (
              <Button variant="primary" size="sm" onClick={onStartText} loading={starting} disabled={starting}>
                <Keyboard aria-hidden weight="bold" className="size-4" />
                {t("blockQuotaTextCta")}
              </Button>
            )}
            {block.kind === "active_session" && (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => onResumeActive(block.sessionId)}
                  disabled={!block.sessionId}
                >
                  {t("blockActiveResume")}
                </Button>
                <Button variant="danger" size="sm" onClick={onDiscardActive} loading={discarding} disabled={discarding}>
                  {t("blockActiveDiscard")}
                </Button>
              </>
            )}
            {block.kind === "no_cv" && (
              <Link href="/student/cv">
                <Button variant="primary" size="sm">
                  {t("blockNoCvCta")}
                </Button>
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function SetupSkeleton() {
  return (
    <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="space-y-6">
        <div className="space-y-2.5">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-[72px] w-full rounded-2xl" />
          <Skeleton className="h-[72px] w-full rounded-2xl" />
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          <Skeleton className="h-[72px] w-full rounded-2xl" />
          <Skeleton className="h-[72px] w-full rounded-2xl" />
        </div>
      </div>
      <div className="space-y-4">
        <Skeleton className="h-[140px] w-full rounded-2xl" />
        <Skeleton className="h-11 w-full rounded-full" />
      </div>
    </div>
  );
}
