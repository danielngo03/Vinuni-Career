"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowClockwise,
  CheckCircle,
  FileText,
  Keyboard,
  Microphone,
  Star,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, Skeleton } from "@/components/ui";
import { FitScoreRing } from "@/components/jobs/fit-score-ring";
import {
  mockInterviewApi,
  type MockInterviewPrepCv,
} from "@/lib/api";
import {
  detectVoiceSupport,
  queryMicPermission,
  type MicPermission,
} from "@/lib/mock-interview/voice-controller";
import { cn } from "@/lib/utils";
import { InterviewHistory } from "./interview-history";

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
  onStart: (opts: { cvId: string | null; mode: AnswerMode }) => void;
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

  const [mode, setMode] = useState<AnswerMode>(support.voiceReady ? "voice" : "text");
  // If the mic is known-denied, default to text (voice is still selectable).
  useEffect(() => {
    if (support.voiceReady && micPerm === "denied") setMode("text");
  }, [support.voiceReady, micPerm]);

  const [selectedCvId, setSelectedCvId] = useState<string | null>(null);
  const recommendedId = prep.data?.recommended_cv_id ?? prep.data?.cvs[0]?.cv_id ?? null;
  useEffect(() => {
    setSelectedCvId((prev) =>
      prev && prep.data?.cvs.some((c) => c.cv_id === prev) ? prev : recommendedId,
    );
  }, [prep.data, recommendedId]);

  const voiceNotice: { tone: "amber" | "muted"; text: string } | null = !support.voiceReady
    ? { tone: "amber", text: t("micUnsupportedNotice") }
    : micPerm === "denied"
      ? { tone: "amber", text: t("micDeniedNotice") }
      : mode === "voice" && micPerm !== "granted"
        ? { tone: "muted", text: t("micPromptNotice") }
        : null;

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 lg:py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-extrabold tracking-tight text-[var(--text-primary)]">
          {t("setupTitle")}
        </h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">{t("setupSubtitle")}</p>
        {prep.data?.job && (
          <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
            {prep.data.job.title}
            {prep.data.job.company_name ? (
              <span className="font-normal text-[var(--text-muted)]">
                {" · "}
                {prep.data.job.company_name}
              </span>
            ) : null}
          </p>
        )}
      </header>

      {startBlock && (
        <StartBlockPanel
          block={startBlock}
          onStartText={() => onStart({ cvId: selectedCvId, mode: "text" })}
          onResumeActive={onResumeActive}
          onDiscardActive={onDiscardActive}
          discarding={discarding}
          starting={starting}
        />
      )}

      {prep.isPending ? (
        <SetupSkeleton />
      ) : prep.isError ? (
        <div
          role="alert"
          className="flex flex-col items-start gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-5 py-6"
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
      ) : prep.data.cvs.length === 0 ? (
        <div className="flex flex-col items-start gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-5 py-6">
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
        <div className="space-y-7">
          {/* CV picker */}
          <section aria-labelledby="mi-cv-title">
            <h2 id="mi-cv-title" className="text-sm font-bold text-[var(--text-primary)]">
              {t("cvPickerTitle")}
            </h2>
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{t("cvPickerSubtitle")}</p>
            {prep.data.signal === "low_signal" && (
              <p className="mt-2 flex items-start gap-1.5 rounded-lg bg-[var(--amber-50)] px-3 py-2 text-xs leading-relaxed text-[var(--amber-700)]">
                <WarningCircle aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0" />
                {t("lowSignalNote")}
              </p>
            )}
            <ul className="mt-3 space-y-2" role="radiogroup" aria-label={t("cvPickerTitle")}>
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
            <h2 id="mi-mode-title" className="text-sm font-bold text-[var(--text-primary)]">
              {t("modeTitle")}
            </h2>
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <ModeCard
                icon={Microphone}
                label={t("modeVoice")}
                hint={t("modeVoiceHint")}
                selected={mode === "voice"}
                disabled={!support.voiceReady}
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
          </section>

          {/* Start */}
          <div>
            <Button
              variant="primary"
              size="lg"
              fullWidth
              loading={starting}
              disabled={starting || !selectedCvId}
              onClick={() => onStart({ cvId: selectedCvId, mode })}
            >
              {starting ? t("startingCta") : t("startCta")}
            </Button>
            <p className="mt-3 text-center text-xs text-[var(--text-muted)]">{t("disclaimer")}</p>
          </div>
        </div>
      )}

      {/* Past sessions */}
      <div className="mt-10 border-t border-[var(--border-default)] pt-7">
        <InterviewHistory onOpen={onOpenSession} />
      </div>
    </div>
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
  return (
    <li>
      <button
        type="button"
        role="radio"
        aria-checked={selected}
        onClick={onSelect}
        className={cn(
          "flex w-full items-center gap-3.5 rounded-xl border px-4 py-3 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
          selected
            ? "border-[var(--brand-primary)] bg-[var(--surface-card)] ring-1 ring-inset ring-[var(--brand-primary)]/30"
            : "border-[var(--border-default)] bg-[var(--surface-card)] hover:border-[var(--border-strong)]",
        )}
      >
        <FitScoreRing score={cv.score} size="sm" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-[var(--text-primary)]" title={cv.title}>
            {cv.title}
          </p>
          <span
            className={cn(
              "mt-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold",
              cv.is_recommended
                ? "bg-[var(--teal-50)] text-[var(--teal-700)]"
                : "bg-[var(--bg-subtle)] text-[var(--text-secondary)]",
            )}
          >
            {cv.is_recommended ? (
              <>
                <Star aria-hidden weight="fill" className="size-3" />
                {t("recommendedBadge")}
              </>
            ) : (
              <>
                <CheckCircle aria-hidden weight="duotone" className="size-3" />
                {t("readyBadge")}
              </>
            )}
          </span>
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
        "flex items-start gap-3 rounded-xl border px-4 py-3 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
        disabled && "cursor-not-allowed opacity-50",
        selected
          ? "border-[var(--brand-primary)] bg-[var(--surface-card)] ring-1 ring-inset ring-[var(--brand-primary)]/30"
          : "border-[var(--border-default)] bg-[var(--surface-card)] hover:border-[var(--border-strong)]",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-lg",
          selected ? "icon-chip-primary" : "icon-chip-neutral",
        )}
      >
        <Icon weight="duotone" className="size-4" />
      </span>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-[var(--text-primary)]">{label}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-muted)]">{hint}</p>
      </div>
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
      className="mb-6 rounded-2xl border border-[var(--amber-600)]/30 bg-[var(--amber-50)] px-5 py-4"
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
    <div className="space-y-7">
      <div className="space-y-2">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Skeleton className="h-20 w-full rounded-xl" />
        <Skeleton className="h-20 w-full rounded-xl" />
      </div>
      <Skeleton className="h-11 w-full rounded-full" />
    </div>
  );
}
