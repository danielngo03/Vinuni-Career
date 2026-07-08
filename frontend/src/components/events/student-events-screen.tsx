"use client";

import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarCheck,
  CalendarBlank,
  CheckCircle,
  MapPin,
  VideoCamera,
  Hourglass,
  WarningCircle,
  SignIn,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import {
  Button,
  EmptyState,
  Skeleton,
  StatusBadge,
  useToast,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { SummaryPanel } from "@/components/students/summary-panel";
import { useEventLabels, REGISTRATION_STATE_TONE } from "@/lib/events/labels";
import { formatEventWhen } from "@/lib/events/format";
import {
  ApiError,
  eventsApi,
  type MyEventRegistration,
} from "@/lib/api";

const MINE_KEY = ["events", "registrations", "mine"] as const;

type EventInsightKey =
  | "insightComingUp"
  | "insightWaitlisted"
  | "insightGoodCalendar"
  | "insightNoEvents";

function deriveMyEventInsights(
  total: number,
  confirmed: number,
  waitlisted: number,
): EventInsightKey[] {
  const out: EventInsightKey[] = [];
  if (confirmed >= 2) out.push("insightGoodCalendar");
  else if (confirmed === 1) out.push("insightComingUp");
  if (waitlisted > 0) out.push("insightWaitlisted");
  if (total === 0) out.push("insightNoEvents");
  return out.slice(0, 2);
}

/**
 * Student "My Events": the caller's own event registrations with their personal
 * status (confirmed / waitlisted+position / attended / no-show), a cancel action
 * for active registrations, and a deep link to each event detail. Never shows
 * any other registrant's identity (PII rule — the attendee list is organizer
 * only, a later slice).
 */
export function StudentEventsScreen() {
  const t = useTranslations("events");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useEventLabels();
  const queryClient = useQueryClient();
  const toast = useToast();

  const query = useQuery({
    queryKey: MINE_KEY,
    queryFn: () => eventsApi.myRegistrations(),
    retry: false,
  });

  const cancelMut = useMutation({
    mutationFn: (eventId: string) => eventsApi.cancelRegistration(eventId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MINE_KEY });
      toast.show({
        tone: "success",
        title: t("toast.cancelledTitle"),
        description: t("toast.cancelledBody"),
      });
    },
    onError: () => {
      toast.show({
        tone: "error",
        title: tStates("errorTitle"),
        description: tStates("errorBody"),
      });
    },
  });

  const rows = query.data ?? [];
  const confirmedCount = rows.filter((r) => r.status === "confirmed").length;
  const waitlistedCount = rows.filter((r) => r.status === "waitlisted").length;

  if (query.isError && query.error instanceof ApiError && query.error.isAuthError) {
    return (
      <>
        <PageHeader title={t("myEventsTitle")} description={t("myEventsSubtitle")} />
        <EmptyState
          kind="auth"
          icon={SignIn}
          title={tStates("authTitle")}
          description={tStates("authBody")}
        />
      </>
    );
  }

  return (
    <>
      <PageHeader title={t("myEventsTitle")} description={t("myEventsSubtitle")} />

      {!query.isPending && !query.isError && rows.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="marketplace-card rounded-[12px] px-4 py-3.5">
            <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
              <CalendarBlank aria-hidden weight="duotone" className="size-[18px]" />
            </div>
            <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{rows.length}</p>
            <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statTotal")}</p>
          </div>
          <div className="marketplace-card rounded-[12px] px-4 py-3.5">
            <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-success shadow-sm">
              <CheckCircle aria-hidden weight="duotone" className="size-[18px]" />
            </div>
            <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{confirmedCount}</p>
            <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statConfirmed")}</p>
          </div>
          <div className="marketplace-card rounded-[12px] px-4 py-3.5">
            <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-warning shadow-sm">
              <Hourglass aria-hidden weight="duotone" className="size-[18px]" />
            </div>
            <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{waitlistedCount}</p>
            <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statWaitlisted")}</p>
          </div>
        </div>
      )}

      {!query.isPending && !query.isError && (
        <SummaryPanel
          title={tc("summaryTitle")}
          items={deriveMyEventInsights(
            rows.length,
            confirmedCount,
            waitlistedCount,
          ).map((key) => t(key))}
        />
      )}

      {query.isPending ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 w-full rounded-[12px]" />
          ))}
        </div>
      ) : query.isError ? (
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
      ) : rows.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={CalendarCheck}
          title={t("myEventsEmptyTitle")}
          description={t("myEventsEmptyBody")}
          action={
            <Link href="/events">
              <Button variant="primary">
                <CalendarBlank aria-hidden weight="bold" className="size-4" />
                {t("browseEvents")}
              </Button>
            </Link>
          }
        />
      ) : (
        <ul className="space-y-3">
          {rows.map((reg) => (
            <RegistrationRow
              key={reg.registration_id}
              reg={reg}
              locale={locale}
              labels={labels}
              onCancel={() => cancelMut.mutate(reg.event.id)}
              cancelling={
                cancelMut.isPending && cancelMut.variables === reg.event.id
              }
            />
          ))}
        </ul>
      )}
    </>
  );
}

function RegistrationRow({
  reg,
  locale,
  labels,
  onCancel,
  cancelling,
}: {
  reg: MyEventRegistration;
  locale: string;
  labels: ReturnType<typeof useEventLabels>;
  onCancel: () => void;
  cancelling: boolean;
}) {
  const t = useTranslations("events");
  const event = reg.event;
  const online = event.format === "online";
  const canCancel = reg.status === "confirmed" || reg.status === "waitlisted";

  return (
    <li className="marketplace-card rounded-[12px] p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <Link
          href={`/events/${event.id}`}
          className="min-w-0 flex-1 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
        >
          <span className="inline-flex items-center rounded-full bg-[var(--blue-50)] px-2.5 py-0.5 text-xs font-semibold text-[var(--brand-primary)]">
            {labels.eventType(event.event_type, event.event_type_label)}
          </span>
          <h3 className="mt-2 truncate text-base font-bold text-[var(--text-primary)]">
            {event.title}
          </h3>
          <dl className="mt-1.5 flex flex-col gap-1 text-xs text-[var(--text-secondary)] sm:flex-row sm:flex-wrap sm:gap-x-4">
            <div className="flex items-center gap-1.5">
              <CalendarBlank
                aria-hidden
                weight="duotone"
                className="size-3.5 shrink-0 text-[var(--text-muted)]"
              />
              <dt className="sr-only">{t("when")}</dt>
              <dd>{formatEventWhen(event.starts_at, event.ends_at, locale)}</dd>
            </div>
            <div className="flex items-center gap-1.5">
              {online ? (
                <VideoCamera
                  aria-hidden
                  weight="duotone"
                  className="size-3.5 shrink-0 text-[var(--text-muted)]"
                />
              ) : (
                <MapPin
                  aria-hidden
                  weight="duotone"
                  className="size-3.5 shrink-0 text-[var(--text-muted)]"
                />
              )}
              <dt className="sr-only">{t("where")}</dt>
              <dd className="truncate">
                {online
                  ? t("online")
                  : (event.venue?.name ??
                    labels.format(event.format, event.format_label))}
              </dd>
            </div>
          </dl>
        </Link>

        <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
          <StatusBadge tone={REGISTRATION_STATE_TONE[reg.status]}>
            {reg.status === "waitlisted" && (
              <Hourglass aria-hidden weight="duotone" className="size-3" />
            )}
            {labels.registrationState(reg.status, reg.status_label)}
          </StatusBadge>
          {reg.status === "waitlisted" && reg.waitlist_position != null && (
            <span className="text-xs font-semibold text-[var(--amber-700)]">
              {t("waitlistedPosition", { position: reg.waitlist_position })}
            </span>
          )}
          {canCancel && (
            <Button variant="ghost" loading={cancelling} onClick={onCancel}>
              {reg.status === "waitlisted"
                ? t("leaveWaitlist")
                : t("cancelRegistration")}
            </Button>
          )}
        </div>
      </div>
    </li>
  );
}
