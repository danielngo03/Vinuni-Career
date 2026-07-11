"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, Plus } from "lucide-react";
import { Button, Input, Modal, Select, Textarea, useToast } from "@/components/ui";
import {
  DataTable,
  EmptyState,
  FilterBar,
  StatusChip,
  type ChipTone,
  type ColumnDef,
} from "@/components/kit";
import { cn } from "@/lib/utils";
import { CareerServicesShell } from "./career-services-shell";
import { CareerServicesPermissionGate } from "./permission-gate";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  APPOINTMENT_MODES,
  careerServicesApi,
  type AppointmentMode,
  type AppointmentStatus,
  type CareerServicesAppointment,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const STATUS_TONE: Record<AppointmentStatus, ChipTone> = {
  requested: "warning",
  confirmed: "info",
  completed: "success",
  cancelled: "neutral",
  no_show: "danger",
};

const NEXT_STATUS: Record<AppointmentStatus, AppointmentStatus[]> = {
  requested: ["confirmed", "cancelled"],
  confirmed: ["completed", "no_show", "cancelled"],
  completed: [],
  cancelled: [],
  no_show: [],
};

const STATUS_FILTERS: (AppointmentStatus | "")[] = [
  "",
  "requested",
  "confirmed",
  "completed",
  "cancelled",
  "no_show",
];

export function AppointmentsScreen() {
  const t = useTranslations("careerServices");
  const locale = useLocale();
  const toast = useToast();
  const getErrorMessage = useApiErrorMessage();
  const qc = useQueryClient();

  const [statusFilter, setStatusFilter] = React.useState<AppointmentStatus | "">("");
  const [createOpen, setCreateOpen] = React.useState(false);
  const [studentId, setStudentId] = React.useState("");
  const [counselorId, setCounselorId] = React.useState("");
  const [scheduledAt, setScheduledAt] = React.useState("");
  const [duration, setDuration] = React.useState(30);
  const [mode, setMode] = React.useState<AppointmentMode>("in_person");
  const [location, setLocation] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [bookingConflict, setBookingConflict] = React.useState(false);

  const [statusTarget, setStatusTarget] = React.useState<{
    item: CareerServicesAppointment;
    next: AppointmentStatus;
  } | null>(null);
  const [cancelReason, setCancelReason] = React.useState("");

  const query = useQuery({
    queryKey: ["career-services", "appointments", locale, statusFilter],
    queryFn: () => careerServicesApi.listAppointments(locale, { status: statusFilter }),
    retry: false,
  });

  const refresh = () =>
    qc.invalidateQueries({ queryKey: ["career-services", "appointments"] });

  const closeCreate = () => {
    setCreateOpen(false);
    setStudentId("");
    setCounselorId("");
    setScheduledAt("");
    setLocation("");
    setNotes("");
    setBookingConflict(false);
  };

  const book = useMutation({
    mutationFn: () =>
      careerServicesApi.bookAppointment(
        {
          student_id: studentId.trim(),
          counselor_id: counselorId.trim(),
          scheduled_at: new Date(scheduledAt).toISOString(),
          duration_minutes: duration,
          mode,
          location: location.trim() || null,
          notes: notes.trim() || null,
        },
        locale,
      ),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("appointments.bookedToast") });
      closeCreate();
      refresh();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.isConflict) {
        setBookingConflict(true);
        return;
      }
      toast.show({ tone: "error", title: getErrorMessage(error) });
    },
  });

  const updateStatus = useMutation({
    mutationFn: () =>
      careerServicesApi.updateAppointmentStatus(
        statusTarget!.item.id,
        {
          status: statusTarget!.next,
          cancel_reason: statusTarget!.next === "cancelled" ? cancelReason.trim() : undefined,
        },
        locale,
      ),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("appointments.updatedToast") });
      setStatusTarget(null);
      setCancelReason("");
      refresh();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.isConflict) {
        toast.show({ tone: "error", title: t("appointments.slotTakenError") });
        return;
      }
      toast.show({ tone: "error", title: getErrorMessage(error) });
    },
  });

  const appointments = query.data ?? [];
  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("appointments.permissionBody")} />
    ) : null;

  const bookButton = (
    <Button onClick={() => setCreateOpen(true)} size="sm">
      <Plus className="size-4" strokeWidth={2} />
      {t("appointments.book")}
    </Button>
  );

  const columns: ColumnDef<CareerServicesAppointment, unknown>[] = [
    {
      id: "when",
      header: t("appointments.colWhen"),
      cell: ({ row }) => (
        <div className="min-w-0">
          <p className="font-semibold text-foreground">{formatDateTime(row.original.scheduled_at, locale)}</p>
          <p className="type-caption text-muted-foreground">
            {t("appointments.durationMinutes", { count: row.original.duration_minutes })} · {row.original.mode_label}
          </p>
        </div>
      ),
    },
    {
      accessorKey: "student_id",
      header: t("appointments.colStudent"),
      cell: ({ row }) => <span className="font-mono text-xs text-foreground">{row.original.student_id}</span>,
    },
    {
      accessorKey: "counselor_id",
      header: t("appointments.colCounselor"),
      cell: ({ row }) => <span className="font-mono text-xs text-foreground">{row.original.counselor_id}</span>,
    },
    {
      accessorKey: "status",
      header: t("appointments.colStatus"),
      cell: ({ row }) => (
        <div className="min-w-0">
          <StatusChip tone={STATUS_TONE[row.original.status]}>{row.original.status_label}</StatusChip>
          {row.original.cancel_reason && (
            <p className="mt-1 max-w-[200px] truncate type-caption text-muted-foreground">
              {row.original.cancel_reason}
            </p>
          )}
        </div>
      ),
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => (
        <div className="flex flex-wrap items-center justify-end gap-1">
          {NEXT_STATUS[row.original.status].map((next) => (
            <Button
              key={next}
              variant="ghost"
              size="sm"
              onClick={() => setStatusTarget({ item: row.original, next })}
            >
              {t(`appointmentStatus.${next}`)}
            </Button>
          ))}
        </div>
      ),
    },
  ];

  return (
    <CareerServicesShell
      title={t("appointments.title")}
      description={t("appointments.subtitle")}
      actions={!permissionState ? bookButton : undefined}
    >
      {permissionState ?? (
        <div className="space-y-4">
          <FilterBar>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("appointments.filterStatus")}>
              {STATUS_FILTERS.map((s) => {
                const active = statusFilter === s;
                return (
                  <button
                    key={s || "all"}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setStatusFilter(s)}
                    className={cn(
                      "inline-flex items-center rounded-full border px-3 py-1 text-[0.8125rem] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
                      active
                        ? "border-transparent bg-foreground text-[var(--surface-card)]"
                        : "border-border bg-card text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {s === "" ? t("appointments.allStatuses") : t(`appointmentStatus.${s}`)}
                  </button>
                );
              })}
            </div>
          </FilterBar>

          <DataTable
            columns={columns}
            data={appointments}
            getRowId={(r) => r.id}
            loading={query.isPending}
            empty={
              <EmptyState
                kind="empty"
                icon={CalendarCheck}
                title={t("appointments.emptyTitle")}
                description={t("appointments.emptyBody")}
              />
            }
          />
        </div>
      )}

      {/* Book appointment */}
      <Modal
        open={createOpen}
        onClose={closeCreate}
        title={t("appointments.bookTitle")}
        size="md"
        footer={
          <>
            <Button variant="ghost" onClick={closeCreate} disabled={book.isPending}>
              {t("cancel")}
            </Button>
            <Button
              loading={book.isPending}
              disabled={!studentId.trim() || !counselorId.trim() || !scheduledAt}
              onClick={() => {
                setBookingConflict(false);
                book.mutate();
              }}
            >
              {t("appointments.book")}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {bookingConflict && (
            <p
              role="alert"
              className="rounded-lg px-3.5 py-2.5 text-sm font-medium"
              style={{ background: "var(--content-danger-soft)", color: "var(--content-danger)" }}
            >
              {t("appointments.slotTakenError")}
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label={t("appointments.studentIdLabel")}
              required
              help={t("cohorts.studentIdHelp")}
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
            />
            <Input
              label={t("appointments.counselorIdLabel")}
              required
              help={t("cvReview.counselorIdHelp")}
              value={counselorId}
              onChange={(e) => setCounselorId(e.target.value)}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label={t("appointments.whenLabel")}
              type="datetime-local"
              required
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
            />
            <Input
              label={t("appointments.durationLabel")}
              type="number"
              min={5}
              max={240}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value) || 30)}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Select
              label={t("appointments.modeLabel")}
              value={mode}
              onChange={(e) => setMode(e.target.value as AppointmentMode)}
              options={APPOINTMENT_MODES.map((m) => ({ value: m, label: t(`appointmentMode.${m}`) }))}
            />
            <Input
              label={t("appointments.locationLabel")}
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder={
                mode === "in_person"
                  ? t("appointments.locationPlaceholder")
                  : t("appointments.linkPlaceholder")
              }
            />
          </div>
          <Textarea
            label={t("appointments.notesLabel")}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
          />
        </div>
      </Modal>

      {/* Status change */}
      <Modal
        open={!!statusTarget}
        onClose={() => setStatusTarget(null)}
        title={statusTarget ? t(`appointmentStatus.${statusTarget.next}`) : ""}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setStatusTarget(null)} disabled={updateStatus.isPending}>
              {t("cancel")}
            </Button>
            <Button
              loading={updateStatus.isPending}
              disabled={statusTarget?.next === "cancelled" && !cancelReason.trim()}
              onClick={() => updateStatus.mutate()}
            >
              {t("save")}
            </Button>
          </>
        }
      >
        {statusTarget?.next === "cancelled" ? (
          <Textarea
            label={t("appointments.cancelReasonLabel")}
            required
            help={t("appointments.cancelReasonHelp")}
            value={cancelReason}
            onChange={(e) => setCancelReason(e.target.value)}
            rows={3}
          />
        ) : (
          <p className="text-sm text-muted-foreground">
            {t("appointments.confirmStatusChange", {
              status: statusTarget ? t(`appointmentStatus.${statusTarget.next}`) : "",
            })}
          </p>
        )}
      </Modal>
    </CareerServicesShell>
  );
}
