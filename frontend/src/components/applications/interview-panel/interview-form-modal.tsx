"use client";

import { useEffect, useId, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import {
  Button,
  Input,
  Modal,
  Select,
  Textarea,
  useToast,
  type SelectOption,
} from "@/components/ui";
import { useInterviewLabels } from "@/lib/applications/labels";
import {
  ApiError,
  applicationsApi,
  INTERVIEW_MODES,
  type Interview,
  type InterviewMode,
  type ScheduleInterviewBody,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { MemberMultiSelect } from "./member-multi-select";
import {
  EMPTY_INTERVIEW_FORM,
  localToIso,
  toLocalInput,
  type InterviewFormState,
} from "./utils";

export function InterviewFormModal({
  open,
  mode,
  applicationId,
  interview,
  onClose,
  onSuccess,
  onInterviewExists,
}: {
  open: boolean;
  mode: "create" | "edit";
  applicationId: string;
  interview?: Interview;
  onClose: () => void;
  onSuccess: () => void;
  onInterviewExists: () => void;
}) {
  const t = useTranslations("interviews");
  const tc = useTranslations("common");
  const labels = useInterviewLabels();
  const toast = useToast();
  const apiError = useApiErrorMessage();
  const fieldId = useId();

  const [form, setForm] = useState<InterviewFormState>(EMPTY_INTERVIEW_FORM);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // Reset/prefill when the modal (re)opens.
  useEffect(() => {
    if (!open) return;
    if (mode === "edit" && interview) {
      setForm({
        mode: (interview.mode as InterviewMode) ?? "onsite",
        scheduledAt: toLocalInput(interview.scheduled_at),
        durationMinutes: interview.duration_minutes ?? 60,
        location: interview.location ?? "",
        meetingLink: interview.meeting_link ?? "",
        title: interview.title ?? "",
        notes: interview.notes ?? "",
        assigneeIds: interview.assignees.map((a) => a.user_id),
      });
    } else {
      setForm(EMPTY_INTERVIEW_FORM);
    }
    setFieldErrors({});
  }, [open, mode, interview]);

  function update<K extends keyof InterviewFormState>(
    key: K,
    value: InterviewFormState[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  const submit = useMutation({
    mutationFn: () => {
      const iso = localToIso(form.scheduledAt);
      if (mode === "edit" && interview) {
        return applicationsApi.rescheduleInterview(applicationId, interview.id, {
          scheduled_at: iso ?? undefined,
          mode: form.mode,
          location: form.mode === "onsite" ? form.location.trim() : null,
          meeting_link:
            form.mode === "online" ? form.meetingLink.trim() : null,
          title: form.title.trim() || null,
          notes: form.notes.trim() || null,
          version: interview.version,
        });
      }
      const body: ScheduleInterviewBody = {
        mode: form.mode,
        scheduled_at: iso as string,
        duration_minutes: form.durationMinutes,
        assignee_ids: form.assigneeIds,
        location: form.mode === "onsite" ? form.location.trim() : null,
        meeting_link: form.mode === "online" ? form.meetingLink.trim() : null,
        title: form.title.trim() || null,
        notes: form.notes.trim() || null,
      };
      return applicationsApi.scheduleInterview(applicationId, body);
    },
    onSuccess,
    onError: (e) => {
      if (e instanceof ApiError) {
        if (e.isValidation) {
          const field =
            typeof e.details?.field === "string" ? e.details.field : null;
          if (field) {
            const key =
              field === "meeting_link"
                ? "meetingLink"
                : field === "assignee_ids"
                  ? "assigneeIds"
                  : field;
            setFieldErrors((prev) => ({ ...prev, [key]: t("fieldInvalid") }));
            return;
          }
          setFieldErrors((prev) => ({ ...prev, _form: t("fieldInvalid") }));
          return;
        }
        if (e.isConflict) {
          const reason = e.details?.reason;
          if (reason === "interview_exists") return onInterviewExists();
          if (reason === "version_conflict") {
            toast.show({ tone: "warning", title: t("conflictToast") });
            onClose();
            return;
          }
          // illegal_transition / other 409s
          toast.show({ tone: "warning", title: t("notSchedulableToast") });
          onClose();
          return;
        }
      }
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

  // Client-side validation mirrors the server's field rules.
  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!form.scheduledAt || !localToIso(form.scheduledAt)) {
      errs.scheduledAt = t("whenRequired");
    }
    if (form.mode === "onsite" && !form.location.trim()) {
      errs.location = t("locationRequired");
    }
    if (form.mode === "online" && !form.meetingLink.trim()) {
      errs.meetingLink = t("linkRequired");
    }
    if (form.durationMinutes < 5) {
      errs.durationMinutes = t("durationInvalid");
    }
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  function handleSubmit() {
    if (!validate()) return;
    submit.mutate();
  }

  const modeOptions: SelectOption[] = INTERVIEW_MODES.map((m) => ({
    value: m,
    label: labels.mode(m),
  }));

  return (
    <Modal
      open={open}
      onClose={submit.isPending ? () => {} : onClose}
      title={mode === "edit" ? t("rescheduleTitle") : t("scheduleTitle")}
      description={
        mode === "edit" ? t("rescheduleDescription") : t("scheduleDescription")
      }
      size="md"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submit.isPending}>
            {tc("cancel")}
          </Button>
          <Button
            variant="primary"
            loading={submit.isPending}
            onClick={handleSubmit}
          >
            {mode === "edit" ? t("rescheduleSubmit") : t("scheduleSubmit")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Select
          label={t("modeLabel")}
          required
          options={modeOptions}
          value={form.mode}
          error={fieldErrors.mode}
          onChange={(e) => update("mode", e.target.value as InterviewMode)}
        />

        <Input
          type="datetime-local"
          label={t("whenLabel")}
          required
          value={form.scheduledAt}
          error={fieldErrors.scheduledAt}
          onChange={(e) => update("scheduledAt", e.target.value)}
        />

        <Input
          type="number"
          label={t("durationLabel")}
          required
          min={5}
          max={600}
          step={5}
          value={String(form.durationMinutes)}
          error={fieldErrors.durationMinutes}
          help={t("durationHelp")}
          onChange={(e) =>
            update("durationMinutes", Number(e.target.value) || 0)
          }
        />

        {/* Conditional: onsite -> location, online -> meeting link. */}
        {form.mode === "onsite" && (
          <Input
            label={t("locationLabel")}
            required
            maxLength={500}
            value={form.location}
            error={fieldErrors.location}
            placeholder={t("locationPlaceholder")}
            onChange={(e) => update("location", e.target.value)}
          />
        )}
        {form.mode === "online" && (
          <Input
            type="url"
            label={t("linkLabel")}
            required
            maxLength={1000}
            value={form.meetingLink}
            error={fieldErrors.meetingLink}
            help={t("linkHelp")}
            placeholder={t("linkPlaceholder")}
            onChange={(e) => update("meetingLink", e.target.value)}
          />
        )}
        {form.mode === "phone" && (
          <p className="rounded-lg border border-white/50 bg-white/70 px-3 py-2 text-xs text-[var(--text-secondary)] backdrop-blur-sm">
            {t("phoneHint")}
          </p>
        )}

        <Input
          label={t("titleLabel")}
          maxLength={150}
          value={form.title}
          placeholder={t("titlePlaceholder")}
          onChange={(e) => update("title", e.target.value)}
        />

        {/* Assignees are only set on schedule; on edit use "edit assignees". */}
        {mode === "create" && (
          <MemberMultiSelect
            idBase={fieldId}
            selected={form.assigneeIds}
            onChange={(ids) => update("assigneeIds", ids)}
          />
        )}

        <Textarea
          label={t("notesLabel")}
          rows={2}
          maxLength={2000}
          value={form.notes}
          placeholder={t("notesPlaceholder")}
          onChange={(e) => update("notes", e.target.value)}
        />

        {fieldErrors._form && (
          <p role="alert" className="text-xs font-medium text-[var(--brand-red)]">
            {fieldErrors._form}
          </p>
        )}
      </div>
    </Modal>
  );
}
