"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, PlusCircle } from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  Input,
  Modal,
  Select,
  StatusBadge,
  Textarea,
  useToast,
  type Column,
} from "@/components/ui";
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

const STATUS_TONE: Record<AppointmentStatus, "pending" | "active" | "accepted" | "closed" | "rejected"> = {
  requested: "pending",
  confirmed: "active",
  completed: "accepted",
  cancelled: "closed",
  no_show: "rejected",
};

const NEXT_STATUS: Record<AppointmentStatus, AppointmentStatus[]> = {
  requested: ["confirmed", "cancelled"],
  confirmed: ["completed", "no_show", "cancelled"],
  completed: [],
  cancelled: [],
  no_show: [],
};

export function AppointmentsScreen() {
  const t = useTranslations("careerServices");
  const locale = useLocale();
  const toast = useToast();
  const getErrorMessage = useApiErrorMessage();
  const qc = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<AppointmentStatus | "">("");
  const [createOpen, setCreateOpen] = useState(false);
  const [studentId, setStudentId] = useState("");
  const [counselorId, setCounselorId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [duration, setDuration] = useState(30);
  const [mode, setMode] = useState<AppointmentMode>("in_person");
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");
  const [bookingConflict, setBookingConflict] = useState(false);

  const [statusTarget, setStatusTarget] = useState<{
    item: CareerServicesAppointment;
    next: AppointmentStatus;
  } | null>(null);
  const [cancelReason, setCancelReason] = useState("");

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

  const appointments = useMemo(() => query.data ?? [], [query.data]);
  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("appointments.permissionBody")} />
    ) : null;

  const columns: Column<CareerServicesAppointment>[] = [
    {
      key: "when",
      header: t("appointments.colWhen"),
      cell: (r) => (
        <div>
          <p className="font-semibold">{formatDateTime(r.scheduled_at, locale)}</p>
          <p className="text-xs text-[var(--text-muted)]">
            {t("appointments.durationMinutes", { count: r.duration_minutes })} · {r.mode_label}
          </p>
        </div>
      ),
    },
    {
      key: "student",
      header: t("appointments.colStudent"),
      cell: (r) => <span className="font-mono text-xs">{r.student_id}</span>,
    },
    {
      key: "counselor",
      header: t("appointments.colCounselor"),
      cell: (r) => <span className="font-mono text-xs">{r.counselor_id}</span>,
    },
    {
      key: "status",
      header: t("appointments.colStatus"),
      cell: (r) => (
        <div>
          <StatusBadge tone={STATUS_TONE[r.status]}>{r.status_label}</StatusBadge>
          {r.cancel_reason && (
            <p className="mt-1 max-w-[200px] truncate text-xs text-[var(--text-muted)]">
              {r.cancel_reason}
            </p>
          )}
        </div>
      ),
    },
    {
      key: "actions",
      header: t("appointments.colActions"),
      cell: (r) => (
        <div className="flex flex-wrap gap-1.5">
          {NEXT_STATUS[r.status].map((next) => (
            <Button
              key={next}
              variant="ghost"
              size="xs"
              onClick={() => setStatusTarget({ item: r, next })}
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
      actions={
        !permissionState && (
          <div className="flex items-center gap-2">
            <Select
              aria-label={t("appointments.filterStatus")}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as AppointmentStatus | "")}
              options={[
                { value: "", label: t("appointments.allStatuses") },
                { value: "requested", label: t("appointmentStatus.requested") },
                { value: "confirmed", label: t("appointmentStatus.confirmed") },
                { value: "completed", label: t("appointmentStatus.completed") },
                { value: "cancelled", label: t("appointmentStatus.cancelled") },
                { value: "no_show", label: t("appointmentStatus.no_show") },
              ]}
            />
            <Button onClick={() => setCreateOpen(true)}>
              <PlusCircle aria-hidden weight="bold" className="size-4" />
              {t("appointments.book")}
            </Button>
          </div>
        )
      }
    >
      {permissionState ?? (
        <DataTable
          columns={columns}
          rows={appointments}
          getRowId={(r) => r.id}
          loading={query.isLoading}
          caption={t("appointments.title")}
          empty={{
            kind: "empty",
            icon: CalendarCheck,
            title: t("appointments.emptyTitle"),
            description: t("appointments.emptyBody"),
          }}
        />
      )}

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
              className="rounded-lg border border-[var(--brand-red)]/30 bg-[var(--red-50)] px-3.5 py-2.5 text-sm font-medium text-[var(--brand-red)]"
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
          <p className="text-sm text-[var(--text-secondary)]">
            {t("appointments.confirmStatusChange", {
              status: statusTarget ? t(`appointmentStatus.${statusTarget.next}`) : "",
            })}
          </p>
        )}
      </Modal>
    </CareerServicesShell>
  );
}
