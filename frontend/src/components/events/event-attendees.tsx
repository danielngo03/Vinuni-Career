"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CheckCircle2, Clock, Users } from "lucide-react";
import { Button, useToast } from "@/components/ui";
import {
  DataTable,
  type ColumnDef,
  EmptyState,
  KpiRow,
  KpiTile,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { useEventLabels } from "@/lib/events/labels";
import { formatDateTime } from "@/lib/format";
import { ApiError, eventsApi, type EventAttendee, type RegistrationState } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

const nf = new Intl.NumberFormat();

const REG_CHIP: Record<RegistrationState, ChipTone> = {
  confirmed: "success",
  waitlisted: "warning",
  cancelled: "neutral",
  attended: "emerald",
  no_show: "danger",
};

/**
 * Attendee list + check-in (organizer-only, ADR-0008 §3). The organizer
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

  const rows = React.useMemo(() => query.data ?? [], [query.data]);
  const hasEmail = React.useMemo(() => rows.some((r) => r.email != null), [rows]);
  const confirmedCount = rows.filter((r) => r.status === "confirmed").length;
  const attendedCount = rows.filter((r) => r.status === "attended").length;
  const waitlistedCount = rows.filter((r) => r.status === "waitlisted").length;

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError || err.isNotFound) {
      return (
        <EmptyState
          kind={err.isAuthError ? "auth" : "permission"}
          title={err.isAuthError ? tStates("authTitle") : tStates("permissionTitle")}
          description={err.isAuthError ? tStates("authBody") : t("permissionBody")}
        />
      );
    }
    return (
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
    );
  }

  const columns: ColumnDef<EventAttendee, unknown>[] = [
    {
      accessorKey: "display_name",
      header: t("colName"),
      cell: ({ row }) => <span className="font-medium text-foreground">{row.original.display_name}</span>,
    },
    ...(hasEmail
      ? [
          {
            accessorKey: "email",
            header: t("colEmail"),
            cell: ({ row }) => <span className="text-muted-foreground">{row.original.email || "—"}</span>,
          } as ColumnDef<EventAttendee, unknown>,
        ]
      : []),
    {
      accessorKey: "status",
      header: t("colStatus"),
      cell: ({ row }) => (
        <StatusChip tone={REG_CHIP[row.original.status] ?? "neutral"} dot>
          {labels.registrationState(row.original.status, row.original.status_label)}
        </StatusChip>
      ),
    },
    {
      accessorKey: "registered_at",
      header: t("colRegistered"),
      cell: ({ row }) => (
        <span className="type-small text-muted-foreground">{formatDateTime(row.original.registered_at, locale)}</span>
      ),
    },
    {
      id: "actions",
      header: "",
      meta: { align: "right" },
      cell: ({ row }) => {
        const r = row.original;
        if (r.status === "attended") {
          return (
            <span
              className="inline-flex items-center gap-1 type-small font-medium"
              style={{ color: "var(--content-success)" }}
            >
              <CheckCircle2 className="size-4" strokeWidth={1.9} />
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
              <CheckCircle2 className="size-4" strokeWidth={1.8} />
              {t("checkIn")}
            </Button>
          );
        }
        return <span className="type-small text-muted-foreground">—</span>;
      },
    },
  ];

  return (
    <div className="space-y-4">
      {rows.length > 0 && (
        <KpiRow cols={4}>
          <KpiTile label={t("statTotal")} value={nf.format(rows.length)} icon={Users} />
          <KpiTile label={t("statConfirmed")} value={nf.format(confirmedCount)} icon={CheckCircle2} />
          <KpiTile label={t("statAttended")} value={nf.format(attendedCount)} icon={CalendarCheck} />
          <KpiTile label={t("statWaitlisted")} value={nf.format(waitlistedCount)} icon={Clock} />
        </KpiRow>
      )}
      <DataTable
        columns={columns}
        data={rows}
        getRowId={(r) => r.registration_id}
        loading={query.isPending}
        empty={<EmptyState kind="empty" title={t("emptyTitle")} description={t("emptyBody")} />}
      />
    </div>
  );
}
