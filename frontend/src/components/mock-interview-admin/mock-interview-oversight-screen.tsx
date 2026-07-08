"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  CaretRight,
  ChartBar,
  ChatCircleDots,
  CheckCircle,
  ClockCountdown,
  Flag,
  Keyboard,
  Microphone,
  ShieldWarning,
  SlidersHorizontal,
  Timer,
  UserSound,
  Users,
  WarningCircle,
} from "@phosphor-icons/react";
import { Button, EmptyState, Modal, Skeleton, SegmentedControl } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { CoachingReport } from "@/components/jobs/mock-interview/coaching-report";
import { useAuthStore } from "@/stores/auth-store";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  ApiError,
  mockInterviewApi,
  type MockInterviewFlaggedItem,
  type MockInterviewModality,
  type MockInterviewStatus,
} from "@/lib/api";

const MODALITY_KEY: Record<MockInterviewModality, string> = {
  voice: "modalityVoice",
  text: "modalityText",
  realtime: "modalityRealtime",
};

const MODALITY_ICON: Record<MockInterviewModality, typeof Microphone> = {
  voice: Microphone,
  realtime: Microphone,
  text: Keyboard,
};

const STATUS_KEY: Record<MockInterviewStatus, string> = {
  active: "statusActive",
  completed: "statusCompleted",
  aborted: "statusAborted",
  expired: "statusExpired",
};

/** m:ss for a duration in seconds. */
function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${rem.toString().padStart(2, "0")}`;
}

/**
 * University oversight for the AI mock-interview feature. Aggregate usage +
 * safety monitoring for all staff; a superadmin-only sub-section reviews
 * flagged sessions via the audited (pseudonymized-by-default) transcript.
 * Never surfaces provider/model internals or student PII.
 */
export function MockInterviewOversightScreen() {
  const t = useTranslations("mockInterviewOversight");
  const tStates = useTranslations("states");
  const isSuperadmin = useAuthStore((s) => s.user?.isSuperadmin ?? false);

  const [days, setDays] = useState("30");

  const statsQuery = useQuery({
    queryKey: ["mock-interview", "admin", "stats", days],
    queryFn: () => mockInterviewApi.adminStats(Number(days)),
    retry: false,
  });
  const configQuery = useQuery({
    queryKey: ["mock-interview", "admin", "config"],
    queryFn: () => mockInterviewApi.adminConfig(),
    retry: false,
  });

  const rangeOptions = [
    { value: "7", label: t("range7") },
    { value: "30", label: t("range30") },
    { value: "90", label: t("range90") },
  ];

  /* ---- Permission / auth state (backend enforces university-only) ---- */
  if (statsQuery.isError && statsQuery.error instanceof ApiError) {
    const err = statsQuery.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader title={t("title")} />
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={ShieldWarning}
            title={
              err.isPermissionError
                ? tStates("permissionTitle")
                : tStates("authTitle")
            }
            description={
              err.isPermissionError ? t("permissionBody") : tStates("authBody")
            }
          />
        </>
      );
    }
  }

  const stats = statsQuery.data;

  return (
    <>
      <PageHeader
        title={t("title")}
        actions={
          <SegmentedControl
            value={days}
            onValueChange={setDays}
            options={rangeOptions}
            ariaLabel={t("rangeLabel")}
            size="sm"
          />
        }
      />
      <p className="mb-5 -mt-2 max-w-2xl text-sm text-[var(--text-secondary)]">
        {t("subtitle")}
      </p>

      {/* Provenance / privacy note — aggregate only, audited access. */}
      <p className="mb-5 flex items-start gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-3 text-sm text-[var(--text-secondary)]">
        <ShieldWarning
          aria-hidden
          weight="duotone"
          className="mt-0.5 size-4 shrink-0 text-[var(--teal-600)]"
        />
        {t("privacyNote")}
      </p>

      {statsQuery.isError ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("loadErrorTitle")}
          description={t("loadErrorBody")}
          action={
            <Button
              variant="secondary"
              onClick={() => statsQuery.refetch()}
              disabled={statsQuery.isFetching}
            >
              {t("retry")}
            </Button>
          }
        />
      ) : (
        <>
          {/* KPI strip */}
          <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <StatCard
              label={t("statTotal")}
              value={stats ? String(stats.total) : "—"}
              loading={statsQuery.isPending}
              icon={ChartBar}
            />
            <StatCard
              label={t("statCompletionRate")}
              value={stats ? `${Math.round(stats.completion_rate * 100)}%` : "—"}
              loading={statsQuery.isPending}
              icon={CheckCircle}
              tone="icon-chip-success"
            />
            <StatCard
              label={t("statDistinctStudents")}
              value={stats ? String(stats.distinct_students) : "—"}
              loading={statsQuery.isPending}
              icon={Users}
            />
            <StatCard
              label={t("statAvgQuestions")}
              value={stats ? formatAvg(stats.avg_questions) : "—"}
              loading={statsQuery.isPending}
              icon={ChatCircleDots}
            />
            <StatCard
              label={t("statAvgDuration")}
              value={stats ? formatDuration(stats.avg_duration_seconds) : "—"}
              loading={statsQuery.isPending}
              icon={ClockCountdown}
            />
            <StatCard
              label={t("statFlagged")}
              value={stats ? String(stats.flagged) : "—"}
              loading={statsQuery.isPending}
              icon={Flag}
              tone={
                stats && stats.flagged > 0
                  ? "icon-chip-warning"
                  : "icon-chip-neutral"
              }
              emphasize={!!stats && stats.flagged > 0}
            />
          </div>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <OutcomeAndModality stats={stats} loading={statsQuery.isPending} />
            <EffectiveLimits
              config={configQuery.data}
              loading={configQuery.isPending}
              isError={configQuery.isError}
              onRetry={() => configQuery.refetch()}
              retrying={configQuery.isFetching}
            />
          </div>

          {isSuperadmin && <FlaggedSection />}
        </>
      )}
    </>
  );
}

function formatAvg(n: number): string {
  return (Math.round(n * 10) / 10).toString();
}

/* ------------------------------- stat card ------------------------------ */

function StatCard({
  label,
  value,
  loading,
  icon: Icon,
  tone = "icon-chip-primary",
  emphasize = false,
}: {
  label: string;
  value: string;
  loading: boolean;
  icon: typeof Microphone;
  tone?: string;
  emphasize?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-3.5">
      <div
        className={cn(
          "mb-2.5 flex size-9 items-center justify-center rounded-xl",
          tone,
        )}
      >
        <Icon aria-hidden weight="duotone" className="size-[18px]" />
      </div>
      <p
        className={cn(
          "text-2xl font-black tracking-tight tabular-nums",
          emphasize ? "text-[var(--amber-700)]" : "text-[var(--text-primary)]",
        )}
      >
        {loading ? "…" : value}
      </p>
      <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">
        {label}
      </p>
    </div>
  );
}

/* --------------------------- outcome + modality ------------------------- */

function OutcomeAndModality({
  stats,
  loading,
}: {
  stats:
    | { completed: number; aborted: number; active: number; by_modality: Partial<Record<MockInterviewModality, number>> }
    | undefined;
  loading: boolean;
}) {
  const t = useTranslations("mockInterviewOversight");
  const tMi = useTranslations("jobs.mockInterview");

  const modalityEntries = stats
    ? (Object.entries(stats.by_modality).filter(
        ([, n]) => typeof n === "number",
      ) as Array<[MockInterviewModality, number]>)
    : [];

  return (
    <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5">
      <h2 className="mb-3 flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
        <ChartBar aria-hidden weight="duotone" className="size-4 text-[var(--text-secondary)]" />
        {t("outcomeTitle")}
      </h2>
      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-5 w-full rounded" />
          <Skeleton className="h-5 w-2/3 rounded" />
        </div>
      ) : (
        <ul className="space-y-1.5">
          <OutcomeRow label={t("outcomeCompleted")} value={stats?.completed ?? 0} tone="text-[var(--teal-700)]" />
          <OutcomeRow label={t("outcomeActive")} value={stats?.active ?? 0} tone="text-[var(--amber-700)]" />
          <OutcomeRow label={t("outcomeAborted")} value={stats?.aborted ?? 0} tone="text-[var(--text-muted)]" />
        </ul>
      )}

      <h3 className="mb-2.5 mt-5 kicker">{t("modalityTitle")}</h3>
      {loading ? (
        <Skeleton className="h-5 w-1/2 rounded" />
      ) : modalityEntries.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">{t("modalityEmpty")}</p>
      ) : (
        <ul className="space-y-1.5">
          {modalityEntries.map(([modality, count]) => {
            const Icon = MODALITY_ICON[modality] ?? ChatCircleDots;
            return (
              <li
                key={modality}
                className="flex items-center justify-between gap-3 text-sm"
              >
                <span className="inline-flex items-center gap-1.5 text-[var(--text-secondary)]">
                  <Icon aria-hidden weight="duotone" className="size-4 text-[var(--text-muted)]" />
                  {tMi(MODALITY_KEY[modality] ?? "modalityText")}
                </span>
                <span className="font-semibold tabular-nums text-[var(--text-primary)]">
                  {count}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function OutcomeRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: string;
}) {
  return (
    <li className="flex items-center justify-between gap-3 text-sm">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className={cn("font-semibold tabular-nums", tone)}>{value}</span>
    </li>
  );
}

/* ---------------------------- effective limits -------------------------- */

function EffectiveLimits({
  config,
  loading,
  isError,
  onRetry,
  retrying,
}: {
  config:
    | {
        daily_session_cap: number;
        weekly_session_cap: number;
        max_session_seconds: number;
        max_questions: number;
        target_questions: number;
        realtime_voice_enabled: boolean;
      }
    | undefined;
  loading: boolean;
  isError: boolean;
  onRetry: () => void;
  retrying: boolean;
}) {
  const t = useTranslations("mockInterviewOversight");

  return (
    <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5">
      <div className="mb-1 flex items-center gap-1.5">
        <SlidersHorizontal aria-hidden weight="duotone" className="size-4 text-[var(--text-secondary)]" />
        <h2 className="text-sm font-bold text-[var(--text-primary)]">
          {t("limitsTitle")}
        </h2>
      </div>
      <p className="mb-4 text-xs text-[var(--text-muted)]">{t("limitsSubtitle")}</p>

      {loading ? (
        <div className="space-y-2.5">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-5 w-full rounded" />
          ))}
        </div>
      ) : isError || !config ? (
        <div className="flex flex-col items-start gap-2">
          <p className="text-sm text-[var(--text-muted)]">{t("loadErrorBody")}</p>
          <Button variant="secondary" size="sm" onClick={onRetry} disabled={retrying}>
            {t("retry")}
          </Button>
        </div>
      ) : (
        <dl className="divide-y divide-[var(--border-subtle)]">
          <LimitRow label={t("limitDaily")} value={String(config.daily_session_cap)} />
          <LimitRow label={t("limitWeekly")} value={String(config.weekly_session_cap)} />
          <LimitRow
            label={t("limitSessionLength")}
            value={t("minutesValue", {
              minutes: Math.round(config.max_session_seconds / 60),
            })}
          />
          <LimitRow label={t("limitMaxQuestions")} value={String(config.max_questions)} />
          <LimitRow label={t("limitTargetQuestions")} value={String(config.target_questions)} />
          <div className="flex items-center justify-between gap-3 py-2.5">
            <dt className="inline-flex items-center gap-1.5 text-sm text-[var(--text-secondary)]">
              <Timer aria-hidden weight="duotone" className="size-4 text-[var(--text-muted)]" />
              {t("limitRealtime")}
            </dt>
            <dd>
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold",
                  config.realtime_voice_enabled
                    ? "border-[var(--teal-500)]/40 bg-[var(--teal-50)] text-[var(--teal-700)]"
                    : "border-[var(--border-default)] bg-[var(--bg-muted)] text-[var(--text-muted)]",
                )}
              >
                {config.realtime_voice_enabled ? t("realtimeOn") : t("realtimeOff")}
              </span>
            </dd>
          </div>
        </dl>
      )}
    </section>
  );
}

function LimitRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <dt className="text-sm text-[var(--text-secondary)]">{label}</dt>
      <dd className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">
        {value}
      </dd>
    </div>
  );
}

/* --------------------------- flagged (superadmin) ----------------------- */

function FlaggedSection() {
  const t = useTranslations("mockInterviewOversight");
  const locale = useLocale();
  const [openId, setOpenId] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["mock-interview", "admin", "flagged"],
    queryFn: () => mockInterviewApi.adminFlagged(50),
    retry: false,
  });

  return (
    <section className="mt-6" aria-labelledby="mi-flagged-title">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h2
          id="mi-flagged-title"
          className="flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]"
        >
          <Flag aria-hidden weight="duotone" className="size-4 text-[var(--amber-600)]" />
          {t("flaggedTitle")}
        </h2>
        <span className="rounded-full border border-[var(--border-default)] bg-[var(--bg-muted)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {t("flaggedSuperadminOnly")}
        </span>
      </div>
      <p className="mb-3 max-w-2xl text-xs text-[var(--text-muted)]">
        {t("flaggedSubtitle")}
      </p>

      {query.isPending ? (
        <ul className="space-y-2" aria-hidden>
          {[0, 1, 2].map((i) => (
            <li key={i}>
              <Skeleton className="h-14 w-full rounded-xl" />
            </li>
          ))}
        </ul>
      ) : query.isError ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("flaggedErrorTitle")}
          action={
            <Button
              variant="secondary"
              onClick={() => query.refetch()}
              disabled={query.isFetching}
            >
              {t("retry")}
            </Button>
          }
        />
      ) : query.data.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={CheckCircle}
          title={t("flaggedEmptyTitle")}
          description={t("flaggedEmptyBody")}
        />
      ) : (
        <ul className="space-y-2">
          {query.data.map((item) => (
            <FlaggedRow
              key={item.session_id}
              item={item}
              locale={locale}
              onOpen={() => setOpenId(item.session_id)}
            />
          ))}
        </ul>
      )}

      <TranscriptModal
        sessionId={openId}
        onClose={() => setOpenId(null)}
      />
    </section>
  );
}

function FlaggedRow({
  item,
  locale,
  onOpen,
}: {
  item: MockInterviewFlaggedItem;
  locale: string;
  onOpen: () => void;
}) {
  const t = useTranslations("mockInterviewOversight");
  const tMi = useTranslations("jobs.mockInterview");
  const Icon = MODALITY_ICON[item.modality] ?? ChatCircleDots;
  const date = formatDateTime(item.created_at, locale);
  const status: MockInterviewStatus = STATUS_KEY[item.status] ? item.status : "completed";

  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-3 text-left outline-none transition-colors hover:border-[var(--text-muted)] hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <span
          aria-hidden
          className="flex size-8 shrink-0 items-center justify-center rounded-lg icon-chip-warning"
        >
          <Icon weight="duotone" className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-data text-xs font-semibold text-[var(--text-primary)]">
            {t("sessionLabel")} {item.session_id.slice(0, 8)}
          </p>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-[var(--text-muted)]">
            <span>{date}</span>
            <span aria-hidden>·</span>
            <span>{tMi(MODALITY_KEY[item.modality] ?? "modalityText")}</span>
            <span aria-hidden>·</span>
            <span>{tMi(STATUS_KEY[status])}</span>
            {item.question_count > 0 && (
              <>
                <span aria-hidden>·</span>
                <span>{t("questionsShort", { count: item.question_count })}</span>
              </>
            )}
            {item.share_opt_in && (
              <span className="rounded-full bg-[var(--teal-50)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--teal-700)]">
                {t("sharedBadge")}
              </span>
            )}
          </div>
        </div>
        <span className="flex shrink-0 items-center gap-1 text-xs font-semibold text-[var(--brand-primary)]">
          {t("flaggedReview")}
          <CaretRight aria-hidden weight="bold" className="size-3.5" />
        </span>
      </button>
    </li>
  );
}

/* ----------------------------- transcript modal ------------------------- */

function TranscriptModal({
  sessionId,
  onClose,
}: {
  sessionId: string | null;
  onClose: () => void;
}) {
  const t = useTranslations("mockInterviewOversight");

  const query = useQuery({
    queryKey: ["mock-interview", "admin", "transcript", sessionId],
    queryFn: () => mockInterviewApi.adminTranscript(sessionId as string),
    enabled: !!sessionId,
    retry: false,
  });

  const data = query.data;
  const isFull = data?.mode === "full";

  return (
    <Modal
      open={!!sessionId}
      onClose={onClose}
      title={t("transcriptTitle")}
      size="lg"
      closeLabel={t("close")}
    >
      {query.isPending ? (
        <div className="flex min-h-[30vh] items-center justify-center" role="status">
          <span
            aria-hidden
            className="size-8 animate-spin rounded-full border-4 border-[var(--bg-muted)] border-t-[var(--brand-primary)]"
          />
          <span className="sr-only">{t("transcriptTitle")}</span>
        </div>
      ) : query.isError || !data ? (
        <div className="flex flex-col items-start gap-3 py-6">
          <p className="text-sm text-[var(--text-secondary)]">
            {t("transcriptLoadError")}
          </p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => query.refetch()}
            disabled={query.isFetching}
          >
            {t("retry")}
          </Button>
        </div>
      ) : (
        <div className="space-y-5">
          {/* Mode disclosure — pseudonymized by default; full access is audited. */}
          <div
            className={cn(
              "flex items-start gap-2 rounded-xl border px-3.5 py-2.5 text-xs leading-relaxed",
              isFull
                ? "border-[var(--amber-600)]/30 bg-[var(--amber-50)] text-[var(--amber-700)]"
                : "border-[var(--border-default)] bg-[var(--bg-muted)] text-[var(--text-secondary)]",
            )}
          >
            {isFull ? (
              <ShieldWarning aria-hidden weight="fill" className="mt-0.5 size-4 shrink-0" />
            ) : (
              <ShieldWarning aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--teal-600)]" />
            )}
            <span>
              <span className="font-semibold">
                {isFull ? t("modeFull") : t("modeRedacted")}
              </span>
              {" — "}
              {isFull ? t("modeFullHint") : t("modeRedactedHint")}
            </span>
          </div>

          {/* Transcript */}
          <section aria-label={t("transcriptTitle")}>
            {data.transcript.length === 0 ? (
              <p className="py-6 text-center text-sm text-[var(--text-muted)]">
                {t("transcriptEmpty")}
              </p>
            ) : (
              <ol className="space-y-4">
                {data.transcript.map((turn) => {
                  const isInterviewer = turn.speaker === "interviewer";
                  return (
                    <li key={turn.seq} className="flex items-start gap-3">
                      <span
                        aria-hidden
                        className={cn(
                          "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full",
                          isInterviewer ? "icon-chip-primary" : "icon-chip-info",
                        )}
                      >
                        {isInterviewer ? (
                          <ChatCircleDots weight="duotone" className="size-4" />
                        ) : (
                          <UserSound weight="duotone" className="size-4" />
                        )}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="kicker mb-0.5">
                          {isInterviewer ? t("interviewerLabel") : t("candidateLabel")}
                        </p>
                        <p className="whitespace-pre-line text-sm leading-relaxed text-[var(--text-secondary)]">
                          {turn.text}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>

          {/* Score-free coaching report (shared renderer). */}
          {data.report && (
            <section
              aria-label={t("reportSectionTitle")}
              className="border-t border-[var(--border-default)] pt-5"
            >
              <h3 className="mb-3 kicker">{t("reportSectionTitle")}</h3>
              <CoachingReport report={data.report} />
            </section>
          )}
        </div>
      )}
    </Modal>
  );
}
