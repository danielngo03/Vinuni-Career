"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CalendarBlank,
  Eye,
  Info,
  MagnifyingGlass,
  PaperPlaneTilt,
  PencilSimple,
  ShieldWarning,
  SignIn,
  Trash,
  UsersThree,
  WarningCircle,
  XCircle,
  Ticket,
  ChartBar,
  ClockCountdown,
  Sparkle,
  LightbulbFilament,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { Link, useRouter } from "@/i18n/navigation";
import {
  Button,
  EmptyState,
  Modal,
  Skeleton,
  StatusBadge,
  SponsoredLabel,
  Tabs,
  TabPanel,
  useToast,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { EventForm } from "./event-form";
import { EventAttendees } from "./event-attendees";
import {
  useEventLabels,
  EVENT_STATUS_TONE,
  EVENT_MODERATION_TONE,
} from "@/lib/events/labels";
import { formatEventWhen } from "@/lib/events/format";
import { formatDateTime } from "@/lib/format";
import { ApiError, eventsApi } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

type ConfirmKind = "submit" | "cancel" | "delete" | null;

export function PartnerEventDetailScreen({ eventId }: { eventId: string }) {
  const t = useTranslations("eventsManage");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useEventLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const router = useRouter();
  const getMessage = useApiErrorMessage();

  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmKind>(null);
  const [tab, setTab] = useState<"overview" | "attendees">("overview");

  const query = useQuery({
    queryKey: ["events", "owned", eventId],
    queryFn: () => eventsApi.getOwned(eventId),
    retry: false,
  });

  const event = query.data;

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["events", "owned", eventId] });
    void qc.invalidateQueries({ queryKey: ["events", "mine"] });
  }

  function handleError(e: unknown) {
    const reason =
      e instanceof ApiError && typeof e.details?.reason === "string"
        ? e.details.reason
        : undefined;
    if (reason === "version_conflict" || (e instanceof ApiError && e.code === "CONFLICT")) {
      toast.show({ tone: "error", title: t("conflictToast"), description: t("conflictBody") });
      refresh();
      return;
    }
    if (reason === "illegal_transition") {
      toast.show({ tone: "error", title: t("illegalTransitionToast") });
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const submit = useMutation({
    mutationFn: () => eventsApi.submit(eventId, event?.version),
    onSuccess: () => {
      setConfirm(null);
      toast.show({ tone: "success", title: t("submittedToast") });
      refresh();
    },
    onError: handleError,
  });

  const cancel = useMutation({
    mutationFn: () => eventsApi.cancel(eventId, event?.version),
    onSuccess: () => {
      setConfirm(null);
      toast.show({ tone: "success", title: t("cancelledToast") });
      refresh();
    },
    onError: handleError,
  });

  const remove = useMutation({
    mutationFn: () => eventsApi.remove(eventId),
    onSuccess: () => {
      setConfirm(null);
      toast.show({ tone: "success", title: t("deletedToast") });
      void qc.invalidateQueries({ queryKey: ["events", "mine"] });
      router.push("/partner/events");
    },
    onError: handleError,
  });

  const backLink = (
    <Link
      href="/partner/events"
      className="mb-4 inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      <ArrowLeft aria-hidden weight="bold" className="size-4" />
      {t("backToEvents")}
    </Link>
  );

  /* ---- Non-data states ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isNotFound) {
      return (
        <>
          {backLink}
          <EmptyState
            kind="empty"
            icon={MagnifyingGlass}
            title={t("notFoundTitle")}
            description={t("ownerNotFoundBody")}
            action={
              <Link href="/partner/events">
                <Button variant="secondary">{t("backToEvents")}</Button>
              </Link>
            }
          />
        </>
      );
    }
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {backLink}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? t("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
    return (
      <>
        {backLink}
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
      </>
    );
  }

  if (query.isPending || !event) {
    return (
      <>
        {backLink}
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="mt-3 h-4 w-1/3" />
        <Skeleton className="mt-6 h-48 w-full" />
      </>
    );
  }

  const canEdit = event.status === "draft" || event.status === "rejected";
  const canSubmit = event.status === "draft" || event.status === "rejected";
  const canCancel = event.status === "published";
  const canDelete = ["draft", "rejected", "cancelled", "completed"].includes(event.status);
  const showAttendees = ["published", "cancelled", "completed"].includes(event.status);
  const venue = event.venue;

  if (editing) {
    return (
      <>
        {backLink}
        <PageHeader title={t("editTitle")} description={t("editSubtitle")} />
        <div className="rounded-2xl border border-[var(--border-default)] bg-white p-6">
          <EventForm
            mode="edit"
            event={event}
            onSuccess={(updated) => {
              setEditing(false);
              qc.setQueryData(["events", "owned", eventId], updated);
              void qc.invalidateQueries({ queryKey: ["events", "mine"] });
            }}
            onCancel={() => setEditing(false)}
          />
        </div>
      </>
    );
  }

  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      {event.status === "published" && (
        <Link href={`/events/${event.id}`} target="_blank">
          <Button variant="ghost" size="sm">
            <Eye aria-hidden weight="duotone" className="size-4" />
            {t("preview")}
          </Button>
        </Link>
      )}
      {canEdit && (
        <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
          <PencilSimple aria-hidden weight="bold" className="size-4" />
          {tc("edit")}
        </Button>
      )}
      {canSubmit && (
        <Button variant="primary" size="sm" onClick={() => setConfirm("submit")}>
          <PaperPlaneTilt aria-hidden weight="bold" className="size-4" />
          {t("submitForReview")}
        </Button>
      )}
      {canCancel && (
        <Button variant="secondary" size="sm" onClick={() => setConfirm("cancel")}>
          <XCircle aria-hidden weight="bold" className="size-4" />
          {t("cancelEvent")}
        </Button>
      )}
      {canDelete && (
        <Button variant="danger" size="sm" onClick={() => setConfirm("delete")}>
          <Trash aria-hidden weight="bold" className="size-4" />
          {tc("delete")}
        </Button>
      )}
    </div>
  );

  const tabsId = "partner-event-detail";

  return (
    <>
      {backLink}
      <PageHeader title={event.title} actions={actions} />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <StatusBadge tone={EVENT_STATUS_TONE[event.status] ?? "info"}>
          {labels.status(event.status, event.status_label)}
        </StatusBadge>
        <StatusBadge tone={EVENT_MODERATION_TONE[event.moderation_status] ?? "info"}>
          {t("moderationLabel")}: {labels.moderation(event.moderation_status, event.moderation_status_label)}
        </StatusBadge>
        <StatusBadge tone="info">
          {t("visibilityLabel")}: {labels.visibility(event.visibility)}
        </StatusBadge>
        {event.is_sponsored && <SponsoredLabel label={t("sponsored")} />}
      </div>

      {/* Event key-metric tiles */}
      <EventStatTiles
        registrationCount={event.registration_count}
        capacity={event.capacity}
        startsAt={event.starts_at}
      />

      {/* AI Event Detail Insights */}
      {event.status === "published" && (() => {
        const insights: string[] = [];
        const fillPct = event.capacity != null && event.capacity > 0
          ? Math.round((event.registration_count / event.capacity) * 100)
          : null;
        const daysLeft = Math.ceil((new Date(event.starts_at).getTime() - Date.now()) / 86_400_000);

        if (fillPct !== null && fillPct >= 80) {
          insights.push(t("insightAlmostFull", { pct: fillPct }));
        } else if (event.registration_count === 0) {
          insights.push(t("insightNoRegistrations"));
        } else {
          insights.push(t("insightRegistrations", { count: event.registration_count }));
        }
        if (daysLeft >= 0 && daysLeft <= 7) {
          insights.push(t("insightEventSoon", { days: daysLeft }));
        } else if (daysLeft > 7) {
          insights.push(t("insightEventUpcoming", { days: daysLeft }));
        }

        return (
          <div className={cn(
            "mb-6 rounded-2xl border p-4",
            "border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 ",
          )}>
            <p className="mb-3 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
              </span>
              {t("aiDetailInsightsTitle")}
            </p>
            <ul className="space-y-1.5">
              {insights.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--ai-accent)]" />
                  {s}
                </li>
              ))}
            </ul>
          </div>
        );
      })()}

      {/* Rejection / moderation note */}
      {event.status === "rejected" && event.moderation_note && (
        <div
          role="alert"
          className="mb-6 rounded-2xl border border-[var(--red-400)]/40 bg-[var(--red-50)] p-4"
        >
          <p className="text-sm font-semibold text-[var(--brand-red)]">
            {t("rejectionReasonTitle")}
          </p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-[var(--text-secondary)]">
            {event.moderation_note}
          </p>
          <p className="mt-2 text-xs text-[var(--text-muted)]">{t("rejectionHint")}</p>
        </div>
      )}

      {event.status === "pending_review" && (
        <div
          role="status"
          className="mb-6 rounded-2xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] p-4 text-sm text-[var(--amber-700)]"
        >
          {t("pendingReviewHint")}
        </div>
      )}

      {event.status === "cancelled" && (
        <div
          role="status"
          className="mb-6 flex items-start gap-2 rounded-2xl border border-[var(--border-default)] bg-white p-4 text-sm text-[var(--text-secondary)] "
        >
          <Info aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0" />
          {t("cancelledHint")}
        </div>
      )}

      <Tabs
        items={[
          { value: "overview", label: t("tabOverview"), icon: <CalendarBlank aria-hidden weight="duotone" className="size-4" /> },
          ...(showAttendees
            ? [{ value: "attendees", label: t("tabAttendees"), icon: <UsersThree aria-hidden weight="duotone" className="size-4" /> }]
            : []),
        ]}
        value={tab}
        onValueChange={(v) => setTab(v as "overview" | "attendees")}
        ariaLabel={t("tabsLabel")}
        idBase={tabsId}
        className="mb-5"
      />

      <TabPanel tabsId={tabsId} value="overview" active={tab === "overview"}>
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Meta label={t("type")}>
            {labels.eventType(event.event_type, event.event_type_label)}
          </Meta>
          <Meta label={t("format")}>
            {labels.format(event.format, event.format_label)}
          </Meta>
          <Meta label={t("when")}>
            {formatEventWhen(event.starts_at, event.ends_at, locale)}
          </Meta>
          <Meta label={t("where")}>
            {event.format === "online"
              ? t("onlineEvent")
              : venue
                ? [venue.name, venue.address].filter(Boolean).join(" · ") || "—"
                : "—"}
          </Meta>
          <Meta label={t("capacity")}>
            {event.capacity != null ? event.capacity : t("unlimited")}
          </Meta>
          <Meta label={t("registrations")}>{event.registration_count}</Meta>
          <Meta label={t("registrationCloses")}>
            {event.registration_closes_at
              ? formatDateTime(event.registration_closes_at, locale)
              : t("closesAtStart")}
          </Meta>
          <Meta label={t("created")}>{formatDateTime(event.created_at, locale)}</Meta>
        </dl>

        <section className="mt-6">
          <h2 className="mb-2 text-lg font-bold tracking-tight text-[var(--text-primary)]">
            {t("about")}
          </h2>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--text-secondary)]">
            {event.description}
          </p>
        </section>

        {event.tags.length > 0 && (
          <section className="mt-6">
            <h2 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">
              {t("tags")}
            </h2>
            <ul className="flex flex-wrap gap-1.5">
              {event.tags.map((s) => (
                <li
                  key={s}
                  className="rounded-full border border-[var(--border-default)] bg-white px-3 py-1 text-xs font-medium text-[var(--text-secondary)] "
                >
                  {s}
                </li>
              ))}
            </ul>
          </section>
        )}
      </TabPanel>

      {showAttendees && (
        <TabPanel tabsId={tabsId} value="attendees" active={tab === "attendees"}>
          <div className="mb-3 flex items-start gap-2 rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5 text-xs text-[var(--text-secondary)] ">
            <Info aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0" />
            {t("attendees.privacyNote")}
          </div>
          <EventAttendees eventId={eventId} />
        </TabPanel>
      )}

      {/* Confirm modals */}
      <Modal
        open={confirm === "submit"}
        onClose={() => setConfirm(null)}
        title={t("submitConfirmTitle")}
        description={t("submitConfirmBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)}>
              {tc("cancel")}
            </Button>
            <Button variant="primary" loading={submit.isPending} onClick={() => submit.mutate()}>
              {t("submitForReview")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("submitConfirmNote")}</p>
      </Modal>

      <Modal
        open={confirm === "cancel"}
        onClose={() => setConfirm(null)}
        title={t("cancelConfirmTitle")}
        description={t("cancelConfirmBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)}>
              {tc("cancel")}
            </Button>
            <Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate()}>
              {t("cancelEvent")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("cancelConfirmNote")}</p>
      </Modal>

      <Modal
        open={confirm === "delete"}
        onClose={() => setConfirm(null)}
        title={t("deleteConfirmTitle")}
        description={t("deleteConfirmBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)}>
              {tc("cancel")}
            </Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
              {tc("delete")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("deleteConfirmNote")}</p>
      </Modal>
    </>
  );
}

function EventStatTiles({
  registrationCount,
  capacity,
  startsAt,
}: {
  registrationCount: number;
  capacity: number | null;
  startsAt: string;
}) {
  const fillPct =
    capacity && capacity > 0 ? Math.min(100, Math.round((registrationCount / capacity) * 100)) : null;

  const now = Date.now();
  const start = new Date(startsAt).getTime();
  const daysToEvent = Math.max(0, Math.ceil((start - now) / 86_400_000));
  const isPast = start < now;

  return (
    <div className="mb-5 grid grid-cols-3 gap-3">
      <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5 hover:shadow-[0_6px_20px_rgba(11,34,57,0.09)]">
        <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
          <Ticket aria-hidden weight="duotone" className="size-4.5 text-white" />
        </div>
        <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{registrationCount}</p>
        <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">Registrations</p>
      </div>
      <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5 hover:shadow-[0_6px_20px_rgba(11,34,57,0.09)]">
        <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-success shadow-sm">
          <ChartBar aria-hidden weight="duotone" className="size-4.5 text-white" />
        </div>
        <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">
          {fillPct !== null ? `${fillPct}%` : "—"}
        </p>
        <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">
          {capacity !== null ? `Fill rate (of ${capacity})` : "Unlimited capacity"}
        </p>
      </div>
      <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5 hover:shadow-[0_6px_20px_rgba(11,34,57,0.09)]">
        <div className={`mb-2.5 flex size-9 items-center justify-center rounded-xl shadow-sm ${isPast ? "icon-chip-neutral" : "icon-chip-info"}`}>
          <ClockCountdown aria-hidden weight="duotone" className="size-4.5 text-white" />
        </div>
        <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">
          {isPast ? "—" : daysToEvent}
        </p>
        <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">
          {isPast ? "Event passed" : "Days to event"}
        </p>
      </div>
    </div>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5 ">
      <dt className="text-xs font-medium text-[var(--text-muted)]">{label}</dt>
      <dd className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">{children}</dd>
    </div>
  );
}
