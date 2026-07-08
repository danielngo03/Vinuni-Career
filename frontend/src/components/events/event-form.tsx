"use client";

import { useForm } from "react-hook-form";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { FloppyDisk } from "@phosphor-icons/react";
import {
  Button,
  Input,
  Select,
  Textarea,
  useToast,
} from "@/components/ui";
import { zodResolver } from "@/lib/validation/resolver";
import {
  eventFormSchema,
  EVENT_FORM_DEFAULTS,
  type EventFormValues,
} from "@/lib/validation/events";
import { useApiErrorMessage, applyFieldErrors } from "@/lib/auth/use-api-error";
import { useEventLabels } from "@/lib/events/labels";
import { parseTags } from "@/lib/jobs/format";
import {
  ApiError,
  eventsApi,
  EVENT_TYPES,
  EVENT_FORMATS,
  EVENT_VISIBILITIES,
  type EventCreateBody,
  type OwnerEventDetail,
} from "@/lib/api";

/** Convert an ISO datetime to a `datetime-local` input value (local tz). */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Convert a `datetime-local` value to ISO, or null when blank. */
function toIso(value: string | null | undefined): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

function toBody(v: EventFormValues): EventCreateBody {
  const online = v.format === "online";
  return {
    title: v.title.trim(),
    description: v.description.trim(),
    event_type: v.event_type,
    format: v.format,
    cover_image_path: v.cover_image_path?.trim() || null,
    venue_name: online ? null : v.venue_name?.trim() || null,
    venue_address: online ? null : v.venue_address?.trim() || null,
    starts_at: toIso(v.starts_at) ?? new Date(v.starts_at).toISOString(),
    ends_at: toIso(v.ends_at) ?? new Date(v.ends_at).toISOString(),
    registration_opens_at: toIso(v.registration_opens_at),
    registration_closes_at: toIso(v.registration_closes_at),
    capacity: v.capacity?.trim() ? Number(v.capacity) : null,
    visibility: v.visibility,
    tags: parseTags(v.tags),
  };
}

function detailToValues(ev: OwnerEventDetail): EventFormValues {
  return {
    title: ev.title,
    description: ev.description,
    event_type: ev.event_type as EventFormValues["event_type"],
    format: ev.format as EventFormValues["format"],
    venue_name: ev.venue?.name ?? "",
    venue_address: ev.venue?.address ?? "",
    cover_image_path: ev.cover_image_url ?? "",
    starts_at: toLocalInput(ev.starts_at),
    ends_at: toLocalInput(ev.ends_at),
    registration_opens_at: toLocalInput(ev.registration_opens_at),
    registration_closes_at: toLocalInput(ev.registration_closes_at),
    capacity: ev.capacity != null ? String(ev.capacity) : "",
    visibility: ev.visibility,
    tags: ev.tags.join(", "),
  };
}

interface EventFormProps {
  mode: "create" | "edit";
  /** Existing event for edit mode (provides version + prefill). */
  event?: OwnerEventDetail;
  onSuccess: (event: OwnerEventDetail) => void;
  onCancel?: () => void;
}

export function EventForm({ mode, event, onSuccess, onCancel }: EventFormProps) {
  const t = useTranslations("eventsManage");
  const tf = useTranslations("eventsManage.form");
  const tv = useTranslations("eventsManage.validation");
  const tc = useTranslations("common");
  const labels = useEventLabels();
  const toast = useToast();
  const getMessage = useApiErrorMessage();

  const {
    register,
    handleSubmit,
    setError,
    watch,
    formState: { errors },
  } = useForm<EventFormValues>({
    resolver: zodResolver(eventFormSchema(tv)),
    defaultValues: event ? detailToValues(event) : EVENT_FORM_DEFAULTS,
  });

  const format = watch("format");
  const showVenue = format !== "online";

  const mutation = useMutation({
    mutationFn: (values: EventFormValues) => {
      const body = toBody(values);
      return mode === "create"
        ? eventsApi.create(body)
        : eventsApi.update(event!.id, { ...body, version: event!.version });
    },
    onSuccess: (updated) => {
      toast.show({
        tone: "success",
        title: mode === "create" ? t("createdToast") : t("savedToast"),
      });
      onSuccess(updated);
    },
    onError: (e) => {
      if (applyFieldErrors(e, setError)) return;
      const reason =
        e instanceof ApiError && typeof e.details?.reason === "string"
          ? e.details.reason
          : undefined;
      if (
        reason === "version_conflict" ||
        (e instanceof ApiError && e.code === "CONFLICT")
      ) {
        toast.show({
          tone: "error",
          title: t("conflictToast"),
          description: t("conflictBody"),
        });
        return;
      }
      if (reason === "not_editable") {
        toast.show({ tone: "error", title: t("notEditableToast") });
        return;
      }
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  const typeOptions = EVENT_TYPES.map((v) => ({
    value: v,
    label: labels.eventType(v),
  }));
  const formatOptions = EVENT_FORMATS.map((v) => ({
    value: v,
    label: labels.format(v),
  }));
  const visibilityOptions = EVENT_VISIBILITIES.map((v) => ({
    value: v,
    label: labels.visibility(v),
  }));

  return (
    <form
      className="space-y-8"
      onSubmit={handleSubmit((v) => mutation.mutate(v))}
      noValidate
    >
      {/* Basics */}
      <Fieldset legend={tf("basicsLegend")}>
        <Input
          label={tf("title")}
          required
          error={errors.title?.message}
          {...register("title")}
        />
        <Textarea
          label={tf("description")}
          required
          rows={6}
          error={errors.description?.message}
          {...register("description")}
        />
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <Select
            label={tf("eventType")}
            required
            error={errors.event_type?.message}
            options={typeOptions}
            {...register("event_type")}
          />
          <Select
            label={tf("format")}
            required
            error={errors.format?.message}
            options={formatOptions}
            {...register("format")}
          />
        </div>
        <Input
          label={tf("cover")}
          help={tf("coverHelp")}
          inputMode="url"
          error={errors.cover_image_path?.message}
          {...register("cover_image_path")}
        />
      </Fieldset>

      {/* Location */}
      <Fieldset legend={tf("locationLegend")}>
        {showVenue ? (
          <div className="grid grid-cols-1 gap-5">
            <Input
              label={tf("venueName")}
              required
              error={errors.venue_name?.message}
              {...register("venue_name")}
            />
            <Textarea
              label={tf("venueAddress")}
              rows={2}
              error={errors.venue_address?.message}
              {...register("venue_address")}
            />
          </div>
        ) : (
          <p className="rounded-xl border border-white/50 bg-white/70 px-3.5 py-3 text-sm text-[var(--text-secondary)] backdrop-blur-sm">
            {tf("onlineNote")}
          </p>
        )}
      </Fieldset>

      {/* Schedule & registration */}
      <Fieldset legend={tf("scheduleLegend")}>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <Input
            type="datetime-local"
            label={tf("startsAt")}
            required
            error={errors.starts_at?.message}
            {...register("starts_at")}
          />
          <Input
            type="datetime-local"
            label={tf("endsAt")}
            required
            error={errors.ends_at?.message}
            {...register("ends_at")}
          />
          <Input
            type="datetime-local"
            label={tf("registrationOpensAt")}
            help={tf("registrationOpensHelp")}
            error={errors.registration_opens_at?.message}
            {...register("registration_opens_at")}
          />
          <Input
            type="datetime-local"
            label={tf("registrationClosesAt")}
            help={tf("registrationClosesHelp")}
            error={errors.registration_closes_at?.message}
            {...register("registration_closes_at")}
          />
        </div>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <Input
            label={tf("capacity")}
            help={tf("capacityHelp")}
            inputMode="numeric"
            error={errors.capacity?.message}
            {...register("capacity")}
          />
          <Input
            label={tf("tags")}
            help={tf("tagsHelp")}
            error={errors.tags?.message}
            {...register("tags")}
          />
        </div>
        <Select
          label={tf("visibility")}
          help={tf("visibilityHelp")}
          error={errors.visibility?.message}
          options={visibilityOptions}
          {...register("visibility")}
        />
      </Fieldset>

      <div className="flex items-center justify-end gap-3 border-t border-white/40 pt-5">
        {onCancel && (
          <Button variant="ghost" onClick={onCancel} disabled={mutation.isPending}>
            {tc("cancel")}
          </Button>
        )}
        <Button type="submit" variant="primary" loading={mutation.isPending}>
          <FloppyDisk aria-hidden weight="bold" className="size-4" />
          {mode === "create" ? t("createDraft") : tc("save")}
        </Button>
      </div>
    </form>
  );
}

function Fieldset({
  legend,
  description,
  children,
}: {
  legend: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset className="overflow-hidden rounded-xl border border-white/50 bg-white/60 backdrop-blur-sm">
      <div className="border-b border-white/40 px-5 py-3">
        <legend className="text-sm font-bold tracking-tight text-[var(--text-primary)]">
          {legend}
        </legend>
        {description && (
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            {description}
          </p>
        )}
      </div>
      <div className="space-y-5 p-5">{children}</div>
    </fieldset>
  );
}
