"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CalendarClock,
  CalendarDays,
  Eye,
  Gauge,
  Info,
  Pencil,
  Send,
  Ticket,
  Trash2,
  Users,
  XCircle,
} from "lucide-react";
import { Link, useRouter } from "@/i18n/navigation";
import { Button, Modal, Skeleton, SponsoredLabel, Tabs, TabPanel, useToast } from "@/components/ui";
import {
  Card,
  EmptyState,
  KpiRow,
  KpiTile,
  PageHeader,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { EventForm } from "./event-form";
import { EventAttendees } from "./event-attendees";
import { useEventLabels } from "@/lib/events/labels";
import { formatEventWhen } from "@/lib/events/format";
import { formatDateTime } from "@/lib/format";
import { ApiError, eventsApi } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

type ConfirmKind = "submit" | "cancel" | "delete" | null;

const EVENT_STATUS_CHIP: Record<string, ChipTone> = {
  draft: "neutral",
  pending_review: "warning",
  published: "success",
  cancelled: "neutral",
  completed: "sky",
  rejected: "danger",
};

const EVENT_MODERATION_CHIP: Record<string, ChipTone> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
  flagged: "violet",
};

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

  const [editing, setEditing] = React.useState(false);
  const [confirm, setConfirm] = React.useState<ConfirmKind>(null);
  const [tab, setTab] = React.useState<"overview" | "attendees">("overview");

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
      e instanceof ApiError && typeof e.details?.reason === "string" ? e.details.reason : undefined;
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
      className="mb-4 inline-flex items-center gap-1.5 rounded-lg type-small font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
    >
      <ArrowLeft className="size-4" strokeWidth={1.8} />
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
        <PageHeader title={t("editTitle")} subtitle={t("editSubtitle")} />
        <Card padded>
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
        </Card>
      </>
    );
  }

  const actions = (
    <>
      {event.status === "published" && (
        <Link href={`/events/${event.slug}`} target="_blank">
          <Button variant="ghost" size="sm">
            <Eye className="size-4" strokeWidth={1.8} />
            {t("preview")}
          </Button>
        </Link>
      )}
      {canEdit && (
        <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
          <Pencil className="size-4" strokeWidth={1.8} />
          {tc("edit")}
        </Button>
      )}
      {canSubmit && (
        <Button variant="primary" size="sm" onClick={() => setConfirm("submit")}>
          <Send className="size-4" strokeWidth={1.8} />
          {t("submitForReview")}
        </Button>
      )}
      {canCancel && (
        <Button variant="secondary" size="sm" onClick={() => setConfirm("cancel")}>
          <XCircle className="size-4" strokeWidth={1.8} />
          {t("cancelEvent")}
        </Button>
      )}
      {canDelete && (
        <Button variant="danger" size="sm" onClick={() => setConfirm("delete")}>
          <Trash2 className="size-4" strokeWidth={1.8} />
          {tc("delete")}
        </Button>
      )}
    </>
  );

  const tabsId = "partner-event-detail";

  return (
    <>
      {backLink}
      <PageHeader
        title={event.title}
        actions={actions}
        meta={
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusChip tone={EVENT_STATUS_CHIP[event.status] ?? "neutral"} dot>
              {labels.status(event.status, event.status_label)}
            </StatusChip>
            <StatusChip tone={EVENT_MODERATION_CHIP[event.moderation_status] ?? "neutral"}>
              {t("moderationLabel")}: {labels.moderation(event.moderation_status, event.moderation_status_label)}
            </StatusChip>
            <StatusChip tone="info">
              {t("visibilityLabel")}: {labels.visibility(event.visibility)}
            </StatusChip>
            {event.is_sponsored && <SponsoredLabel label={t("sponsored")} />}
          </div>
        }
      />

      <EventStatTiles registrationCount={event.registration_count} capacity={event.capacity} startsAt={event.starts_at} />

      {/* Rejection / moderation notices */}
      {event.status === "rejected" && event.moderation_note && (
        <div
          role="alert"
          className="mb-6 rounded-xl border border-border px-4 py-3"
          style={{ background: "var(--content-danger-soft)" }}
        >
          <p className="type-small font-semibold" style={{ color: "var(--content-danger)" }}>
            {t("rejectionReasonTitle")}
          </p>
          <p className="mt-1 whitespace-pre-wrap type-small text-foreground">{event.moderation_note}</p>
          <p className="mt-2 type-caption text-muted-foreground">{t("rejectionHint")}</p>
        </div>
      )}

      {event.status === "pending_review" && (
        <div
          role="status"
          className="mb-6 rounded-xl border border-border px-4 py-3 type-small"
          style={{ background: "var(--content-warning-soft)", color: "var(--content-warning)" }}
        >
          {t("pendingReviewHint")}
        </div>
      )}

      {event.status === "cancelled" && (
        <div
          role="status"
          className="mb-6 flex items-start gap-2 rounded-xl border border-border bg-card px-4 py-3 type-small text-muted-foreground"
        >
          <Info className="mt-0.5 size-4 shrink-0" strokeWidth={1.8} />
          {t("cancelledHint")}
        </div>
      )}

      <Tabs
        items={[
          { value: "overview", label: t("tabOverview"), icon: <CalendarDays aria-hidden className="size-4" /> },
          ...(showAttendees
            ? [{ value: "attendees", label: t("tabAttendees"), icon: <Users aria-hidden className="size-4" /> }]
            : []),
        ]}
        value={tab}
        onValueChange={(v) => setTab(v as "overview" | "attendees")}
        ariaLabel={t("tabsLabel")}
        idBase={tabsId}
        className="mb-5"
      />

      <TabPanel tabsId={tabsId} value="overview" active={tab === "overview"}>
        <Card padded>
          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Meta label={t("type")}>{labels.eventType(event.event_type, event.event_type_label)}</Meta>
            <Meta label={t("format")}>{labels.format(event.format, event.format_label)}</Meta>
            <Meta label={t("when")}>{formatEventWhen(event.starts_at, event.ends_at, locale)}</Meta>
            <Meta label={t("where")}>
              {event.format === "online"
                ? t("onlineEvent")
                : venue
                  ? [venue.name, venue.address].filter(Boolean).join(" · ") || "—"
                  : "—"}
            </Meta>
            <Meta label={t("capacity")}>{event.capacity != null ? event.capacity : t("unlimited")}</Meta>
            <Meta label={t("registrations")}>{event.registration_count}</Meta>
            <Meta label={t("registrationCloses")}>
              {event.registration_closes_at ? formatDateTime(event.registration_closes_at, locale) : t("closesAtStart")}
            </Meta>
            <Meta label={t("created")}>{formatDateTime(event.created_at, locale)}</Meta>
          </dl>
        </Card>

        <Card padded className="mt-4">
          <h2 className="type-h3 text-foreground">{t("about")}</h2>
          <p className="mt-2 whitespace-pre-wrap type-body text-muted-foreground">{event.description}</p>

          {event.tags.length > 0 && (
            <div className="mt-5">
              <h3 className="type-caption mb-2 font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                {t("tags")}
              </h3>
              <ul className="flex flex-wrap gap-1.5">
                {event.tags.map((s) => (
                  <li key={s}>
                    <StatusChip tone="neutral">{s}</StatusChip>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      </TabPanel>

      {showAttendees && (
        <TabPanel tabsId={tabsId} value="attendees" active={tab === "attendees"}>
          <div className="mb-3 flex items-start gap-2 rounded-xl border border-border bg-card px-3.5 py-2.5 type-caption text-muted-foreground">
            <Info className="mt-0.5 size-4 shrink-0" strokeWidth={1.8} />
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
        <p className="type-small text-muted-foreground">{t("submitConfirmNote")}</p>
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
        <p className="type-small text-muted-foreground">{t("cancelConfirmNote")}</p>
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
        <p className="type-small text-muted-foreground">{t("deleteConfirmNote")}</p>
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
  const t = useTranslations("eventsManage");
  const fillPct =
    capacity && capacity > 0 ? Math.min(100, Math.round((registrationCount / capacity) * 100)) : null;

  const now = Date.now();
  const start = new Date(startsAt).getTime();
  const daysToEvent = Math.max(0, Math.ceil((start - now) / 86_400_000));
  const isPast = start < now;

  return (
    <KpiRow cols={3} className="mb-6">
      <KpiTile label={t("stat.registrations")} value={String(registrationCount)} icon={Ticket} />
      <KpiTile
        label={t("stat.fillRate")}
        value={fillPct !== null ? `${fillPct}%` : "—"}
        icon={Gauge}
        hint={capacity !== null ? t("stat.fillRateOf", { capacity }) : t("stat.unlimitedCapacity")}
      />
      <KpiTile
        label={t("stat.daysToEvent")}
        value={isPast ? "—" : String(daysToEvent)}
        icon={CalendarClock}
        hint={isPast ? t("stat.eventPassed") : undefined}
      />
    </KpiRow>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-[var(--bg-subtle)] px-3.5 py-2.5">
      <dt className="type-caption text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 type-small font-semibold text-foreground">{children}</dd>
    </div>
  );
}
