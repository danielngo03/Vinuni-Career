"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarCheck,
  CheckCircle,
  DownloadSimple,
  Hourglass,
  LightbulbFilament,
  ShieldWarning,
  SignIn,
  Sparkle,
  UsersThree,
  WarningCircle,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  StatusBadge,
  useToast,
  type Column,
} from "@/components/ui";
import {
  useEventLabels,
  REGISTRATION_STATE_TONE,
} from "@/lib/events/labels";
import { formatDateTime } from "@/lib/format";
import { ApiError, eventsApi, type EventAttendee } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

type AttendeeInsightKey =
  | "insightCheckInPending"
  | "insightHighAttendance"
  | "insightWaitlistPresent"
  | "insightLowCheckin"
  | "insightEventComplete";

function deriveAttendeeInsights(
  total: number,
  confirmed: number,
  attended: number,
  waitlisted: number,
): AttendeeInsightKey[] {
  const out: AttendeeInsightKey[] = [];
  if (total === 0) return out;
  const attendanceRate = total > 0 ? attended / total : 0;
  if (attended > 0 && confirmed === 0) out.push("insightEventComplete");
  else if (confirmed > 0) out.push("insightCheckInPending");
  if (attendanceRate >= 0.7 && attended > 0) out.push("insightHighAttendance");
  else if (confirmed > 0 && attended < confirmed * 0.5 && attended > 0) out.push("insightLowCheckin");
  if (waitlisted > 0) out.push("insightWaitlistPresent");
  return out.slice(0, 2);
}

/**
 * Attendee list + check-in (organizer-only surface, ADR-0008 §3). The organizer
 * projection carries `email`; the column renders only when at least one row
 * exposes it. Check-in marks `confirmed → attended` (idempotent).
 */
export function EventAttendees({ eventId }: { eventId: string }) {
  const t = useTranslations("eventsManage.attendees");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useEventLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const query = useQuery({
    queryKey: ["events", "attendees", eventId],
    queryFn: () => eventsApi.listRegistrations(eventId),
    retry: false,
  });

  const checkIn = useMutation({
    mutationFn: (rid: string) => eventsApi.checkIn(eventId, rid),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("checkedInToast") });
      void qc.invalidateQueries({ queryKey: ["events", "attendees", eventId] });
      void qc.invalidateQueries({ queryKey: ["events", "owned", eventId] });
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const exportCsv = useMutation({
    mutationFn: () => eventsApi.exportAttendees(eventId),
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename ?? `attendees-${eventId}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const rows = useMemo(() => query.data ?? [], [query.data]);
  const hasEmail = useMemo(
    () => rows.some((r) => r.email !== undefined && r.email !== null),
    [rows],
  );
  const confirmedCount = rows.filter((r) => r.status === "confirmed").length;
  const attendedCount = rows.filter((r) => r.status === "attended").length;
  const waitlistedCount = rows.filter((r) => r.status === "waitlisted").length;

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError || err.isNotFound) {
      return (
        <EmptyState
          kind={err.isAuthError ? "auth" : "permission"}
          icon={err.isAuthError ? SignIn : ShieldWarning}
          title={err.isAuthError ? tStates("authTitle") : tStates("permissionTitle")}
          description={err.isAuthError ? tStates("authBody") : t("permissionBody")}
        />
      );
    }
    return (
      <EmptyState
        kind="error"
        icon={WarningCircle}
        title={tStates("errorTitle")}
        description={tStates("errorBody")}
        action={
          <Button variant="secondary" onClick={() => query.refetch()}>
            {tc("retry")}
          </Button>
        }
      />
    );
  }

  const columns: Column<EventAttendee>[] = [
    {
      key: "name",
      header: t("colName"),
      cell: (r) => (
        <span className="font-medium text-[var(--text-primary)]">
          {r.display_name}
        </span>
      ),
    },
    ...(hasEmail
      ? [
          {
            key: "email",
            header: t("colEmail"),
            cell: (r: EventAttendee) => (
              <span className="text-[var(--text-secondary)]">{r.email || "—"}</span>
            ),
          } as Column<EventAttendee>,
        ]
      : []),
    {
      key: "status",
      header: t("colStatus"),
      cell: (r) => (
        <StatusBadge tone={REGISTRATION_STATE_TONE[r.status] ?? "info"}>
          {labels.registrationState(r.status, r.status_label)}
        </StatusBadge>
      ),
    },
    {
      key: "registered",
      header: t("colRegistered"),
      cell: (r) => (
        <span className="text-[var(--text-secondary)]">
          {formatDateTime(r.registered_at, locale)}
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (r) => {
        if (r.status === "attended") {
          return (
            <span className="inline-flex items-center gap-1 text-sm font-medium text-[var(--teal-600)]">
              <CheckCircle aria-hidden weight="fill" className="size-4" />
              {t("checkedIn")}
            </span>
          );
        }
        if (r.status === "confirmed") {
          return (
            <Button
              variant="secondary"
              size="sm"
              loading={checkIn.isPending && checkIn.variables === r.registration_id}
              onClick={() => checkIn.mutate(r.registration_id)}
            >
              <CheckCircle aria-hidden weight="bold" className="size-4" />
              {t("checkIn")}
            </Button>
          );
        }
        return <span className="text-sm text-[var(--text-muted)]">—</span>;
      },
    },
  ];

  return (
    <div className="space-y-4">
      {rows.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-2xl border border-white/60 bg-white/85 px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-xl transition-all hover:-translate-y-0.5">
            <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
              <UsersThree aria-hidden weight="duotone" className="size-4.5 text-white" />
            </div>
            <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{rows.length}</p>
            <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statTotal")}</p>
          </div>
          <div className="rounded-2xl border border-white/60 bg-white/85 px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-xl transition-all hover:-translate-y-0.5">
            <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-success shadow-sm">
              <CheckCircle aria-hidden weight="duotone" className="size-4.5 text-white" />
            </div>
            <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{confirmedCount}</p>
            <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statConfirmed")}</p>
          </div>
          <div className="rounded-2xl border border-white/60 bg-white/85 px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-xl transition-all hover:-translate-y-0.5">
            <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-success shadow-sm">
              <CalendarCheck aria-hidden weight="duotone" className="size-4.5 text-white" />
            </div>
            <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{attendedCount}</p>
            <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statAttended")}</p>
          </div>
          <div className="rounded-2xl border border-white/60 bg-white/85 px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-xl transition-all hover:-translate-y-0.5">
            <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-warning shadow-sm">
              <Hourglass aria-hidden weight="duotone" className="size-4.5 text-white" />
            </div>
            <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{waitlistedCount}</p>
            <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statWaitlisted")}</p>
          </div>
        </div>
      )}
      {(() => {
        const insights = !query.isPending && rows.length > 0
          ? deriveAttendeeInsights(rows.length, confirmedCount, attendedCount, waitlistedCount)
          : [];
        if (insights.length === 0) return null;
        return (
          <section
            className="rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-4 backdrop-blur-xl"
            aria-label={t("aiInsightsTitle")}
          >
            <h2 className="mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
              </span>
              {t("aiInsightsTitle")}
            </h2>
            <ul className="space-y-1.5">
              {insights.map((key) => (
                <li key={key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                  {t(key)}
                </li>
              ))}
            </ul>
          </section>
        );
      })()}
      {rows.length > 0 && (
        <div className="flex justify-end">
          <Button
            variant="secondary"
            size="sm"
            loading={exportCsv.isPending}
            onClick={() => exportCsv.mutate()}
          >
            <DownloadSimple aria-hidden weight="bold" className="size-4" />
            {t("exportCsv")}
          </Button>
        </div>
      )}
      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(r) => r.registration_id}
        loading={query.isPending}
        caption={t("title")}
        empty={{
          kind: "empty",
          icon: UsersThree,
          title: t("emptyTitle"),
          description: t("emptyBody"),
        }}
      />
    </div>
  );
}
