"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Megaphone, Info } from "@phosphor-icons/react";
import {
  Button,
  Input,
  Modal,
  Select,
  StatusBadge,
  useToast,
} from "@/components/ui";
import {
  ApiError,
  advertisingApi,
  eventsApi,
  jobsApi,
  type AdPackage,
  type AdTargetType,
  type CreatePlacementBody,
  type Placement,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { useAdvertisingLabels, PLACEMENT_TYPE_TONE } from "@/lib/advertising/labels";
import { deriveWindow, formatVnd, formatWindow } from "@/lib/advertising/format";

interface TargetOption {
  key: string;
  target_type: AdTargetType;
  target_id: string;
  title: string;
}

/** Default start = today (date input value, yyyy-mm-dd). */
function todayInput(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * Create/edit a sponsored placement (ADR-0009). Picks one of the partner's OWN
 * jobs/events as the target, a pricing package, a start date (the window end is
 * derived from the package duration), and requires the MANDATORY non-removable
 * disclosure acknowledgement before "Send request" (drives `disclosure_confirmed`;
 * a 422 disclosure error is surfaced inline). "Save draft" stores without
 * submitting. On success the parent list is invalidated.
 */
export function PlacementFormModal({
  open,
  onClose,
  /** When set, edit this draft/rejected placement; otherwise create new. */
  placement,
  /** target_ids that already have a live placement — excluded in create mode. */
  inflightTargetIds,
}: {
  open: boolean;
  onClose: () => void;
  placement?: Placement | null;
  inflightTargetIds: Set<string>;
}) {
  const t = useTranslations("advertising");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();
  const labels = useAdvertisingLabels();
  const isEdit = !!placement;

  const [targetKey, setTargetKey] = useState("");
  const [packageId, setPackageId] = useState("");
  const [startDate, setStartDate] = useState(todayInput());
  const [disclosure, setDisclosure] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [disclosureError, setDisclosureError] = useState<string | null>(null);

  /* Pricing tiers. */
  const packagesQuery = useQuery({
    queryKey: ["advertising", "packages"],
    queryFn: () => advertisingApi.listPackages(),
    enabled: open,
    retry: false,
  });

  /* The partner's own jobs + events as targets. */
  const jobsQuery = useQuery({
    queryKey: ["advertising", "targets", "jobs"],
    queryFn: () => jobsApi.listMine({ limit: 50 }),
    enabled: open,
    retry: false,
  });
  const eventsQuery = useQuery({
    queryKey: ["advertising", "targets", "events"],
    queryFn: () => eventsApi.listMine({ limit: 50 }),
    enabled: open,
    retry: false,
  });

  const targets: TargetOption[] = useMemo(() => {
    const jobs = (jobsQuery.data?.data ?? []).map((j) => ({
      key: `job:${j.id}`,
      target_type: "job" as const,
      target_id: j.id,
      title: j.title,
    }));
    const events = (eventsQuery.data?.data ?? []).map((e) => ({
      key: `event:${e.id}`,
      target_type: "event" as const,
      target_id: e.id,
      title: e.title,
    }));
    return [...jobs, ...events];
  }, [jobsQuery.data, eventsQuery.data]);

  /* Reset form whenever it opens (create vs edit prefill). */
  useEffect(() => {
    if (!open) return;
    setFieldError(null);
    setDisclosureError(null);
    if (placement) {
      setTargetKey(`${placement.target_type}:${placement.target_id}`);
      setPackageId(placement.package_id);
      setStartDate((placement.start_at ?? new Date().toISOString()).slice(0, 10));
      setDisclosure(placement.disclosure_confirmed);
    } else {
      setTargetKey("");
      setPackageId("");
      setStartDate(todayInput());
      setDisclosure(false);
    }
  }, [open, placement]);

  const selectedPackage: AdPackage | null =
    packagesQuery.data?.find((p) => p.id === packageId) ?? null;
  const startIso = startDate ? new Date(`${startDate}T00:00:00`).toISOString() : null;
  const derived = deriveWindow(startIso, selectedPackage?.duration_days ?? null);
  const selectedTarget = targets.find((o) => o.key === targetKey) ?? null;

  function buildBody(confirm: boolean): CreatePlacementBody | null {
    if (!selectedTarget) {
      setFieldError(t("form.targetRequired"));
      return null;
    }
    if (!selectedPackage) {
      setFieldError(t("form.packageRequired"));
      return null;
    }
    if (!startIso) {
      setFieldError(t("form.startRequired"));
      return null;
    }
    setFieldError(null);
    return {
      target_type: selectedTarget.target_type,
      target_id: selectedTarget.target_id,
      placement_type: selectedPackage.placement_type,
      package_id: selectedPackage.id,
      start_at: startIso,
      disclosure_confirmed: confirm,
    };
  }

  function handleError(e: unknown) {
    const reason =
      e instanceof ApiError && typeof e.details?.reason === "string"
        ? (e.details.reason as string)
        : undefined;
    if (reason === "disclosure_required") {
      setDisclosureError(t("form.disclosureRequired"));
      return;
    }
    if (reason === "active_placement_limit") {
      toast.show({
        tone: "error",
        title: t("errors.limitTitle"),
        description: t("errors.limitBody"),
      });
      return;
    }
    if (reason === "placement_exists") {
      toast.show({
        tone: "error",
        title: t("errors.existsTitle"),
        description: t("errors.existsBody"),
      });
      return;
    }
    if (reason === "version_conflict" || (e instanceof ApiError && e.isConflict)) {
      toast.show({
        tone: "error",
        title: t("errors.conflictTitle"),
        description: t("errors.conflictBody"),
      });
      void qc.invalidateQueries({ queryKey: ["advertising", "placements"] });
      onClose();
      return;
    }
    if (e instanceof ApiError && e.isNotFound) {
      toast.show({
        tone: "error",
        title: t("errors.targetGoneTitle"),
        description: t("errors.targetGoneBody"),
      });
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  /** Persist (create or update) then optionally submit. Body is pre-validated. */
  const save = useMutation({
    mutationFn: async ({
      body,
      submit,
    }: {
      body: CreatePlacementBody;
      submit: boolean;
    }) => {
      let saved: Placement;
      if (placement) {
        saved = await advertisingApi.updatePlacement(placement.id, {
          placement_type: body.placement_type,
          package_id: body.package_id,
          start_at: body.start_at,
          disclosure_confirmed: body.disclosure_confirmed,
          version: placement.version,
        });
      } else {
        saved = await advertisingApi.createPlacement(body);
      }
      if (submit) {
        saved = await advertisingApi.submitPlacement(saved.id, {
          disclosure_confirmed: true,
          version: saved.version,
        });
      }
      return saved;
    },
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["advertising", "placements"] });
      toast.show({
        tone: "success",
        title: vars.submit ? t("toast.submitted") : t("toast.savedDraft"),
      });
      onClose();
    },
    onError: handleError,
  });

  function onSaveDraft() {
    const body = buildBody(disclosure);
    if (!body) return;
    save.mutate({ body, submit: false });
  }

  function onSubmit() {
    if (!disclosure) {
      setDisclosureError(t("form.disclosureRequired"));
      return;
    }
    setDisclosureError(null);
    const body = buildBody(true);
    if (!body) return;
    save.mutate({ body, submit: true });
  }

  const targetsLoading = jobsQuery.isPending || eventsQuery.isPending;
  const currentTargetId = placement?.target_id ?? null;
  const targetOptions = useMemo(() => {
    const placeholder = { value: "", label: t("form.targetPlaceholder") };
    const opts = targets.map((o: TargetOption) => {
      // In create mode, mark targets that already have a live placement.
      const blocked =
        !isEdit &&
        inflightTargetIds.has(o.target_id) &&
        o.target_id !== currentTargetId;
      const typeLabel = labels.targetType(o.target_type);
      return {
        value: o.key,
        label: blocked
          ? `${o.title} — ${typeLabel} (${t("form.targetInUse")})`
          : `${o.title} — ${typeLabel}`,
        disabled: blocked,
      };
    });
    return [placeholder, ...opts];
  }, [targets, isEdit, inflightTargetIds, currentTargetId, labels, t]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEdit ? t("form.editTitle") : t("form.createTitle")}
      description={t("form.subtitle")}
      size="md"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={save.isPending}>
            {tc("cancel")}
          </Button>
          <Button
            variant="secondary"
            loading={save.isPending && save.variables?.submit === false}
            disabled={save.isPending}
            onClick={onSaveDraft}
          >
            {t("form.saveDraft")}
          </Button>
          <Button
            variant="primary"
            loading={save.isPending && save.variables?.submit === true}
            disabled={save.isPending || !disclosure}
            onClick={onSubmit}
          >
            <Megaphone aria-hidden weight="bold" className="size-4" />
            {t("form.sendRequest")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {/* Target picker */}
        <Select
          label={t("form.targetLabel")}
          required
          value={targetKey}
          disabled={isEdit}
          onChange={(e) => {
            setTargetKey(e.target.value);
            setFieldError(null);
          }}
          options={targetOptions}
          help={
            targetsLoading
              ? tc("loading")
              : targets.length === 0
                ? t("form.noTargets")
                : isEdit
                  ? t("form.targetLockedHint")
                  : t("form.targetHint")
          }
        />

        {/* Package picker */}
        <Select
          label={t("form.packageLabel")}
          required
          value={packageId}
          onChange={(e) => {
            setPackageId(e.target.value);
            setFieldError(null);
          }}
          options={[
            { value: "", label: t("form.packagePlaceholder") },
            ...(packagesQuery.data ?? []).map((p) => ({
              value: p.id,
              label: `${p.name} · ${p.placement_type_label} · ${formatVnd(p.price_amount, p.currency, locale)} · ${t("form.days", { count: p.duration_days })}`,
            })),
          ]}
          help={packagesQuery.isPending ? tc("loading") : undefined}
        />

        {/* Selected package summary */}
        {selectedPackage && (
          <div className="rounded-xl border border-white/50 bg-white/70 px-3.5 py-3 backdrop-blur-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <StatusBadge tone={PLACEMENT_TYPE_TONE[selectedPackage.placement_type]}>
                {selectedPackage.placement_type_label}
              </StatusBadge>
              <span className="text-sm font-bold text-[var(--text-primary)]">
                {formatVnd(selectedPackage.price_amount, selectedPackage.currency, locale)}
              </span>
            </div>
            <p className="mt-1.5 text-xs text-[var(--text-secondary)]">
              {t("form.windowPreview", {
                window: formatWindow(derived.start, derived.end, locale),
              })}
            </p>
          </div>
        )}

        {/* Start date */}
        <Input
          type="date"
          label={t("form.startLabel")}
          required
          min={todayInput()}
          value={startDate}
          onChange={(e) => {
            setStartDate(e.target.value);
            setFieldError(null);
          }}
          help={t("form.startHint")}
        />

        {fieldError && (
          <p className="text-xs font-medium text-[var(--brand-red)]" role="alert">
            {fieldError}
          </p>
        )}

        {/* Mandatory disclosure acknowledgement */}
        <div
          className={`rounded-xl border px-3.5 py-3 ${
            disclosureError
              ? "border-[var(--brand-red)] bg-[var(--red-50)]"
              : "border-[var(--amber-600)]/40 bg-[var(--amber-100)]"
          }`}
        >
          <label className="flex items-start gap-2.5 text-sm">
            <input
              type="checkbox"
              checked={disclosure}
              required
              aria-required="true"
              aria-invalid={disclosureError ? true : undefined}
              aria-describedby="disclosure-desc"
              onChange={(e) => {
                setDisclosure(e.target.checked);
                if (e.target.checked) setDisclosureError(null);
              }}
              className="mt-0.5 size-4 shrink-0 rounded border-[var(--border-default)] text-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            />
            <span id="disclosure-desc" className="text-[var(--text-primary)]">
              <span className="inline-flex items-center gap-1.5 font-semibold">
                <span className="flex size-5 shrink-0 items-center justify-center rounded icon-chip-warning shadow-sm">
                  <Info aria-hidden weight="duotone" className="size-3 text-white" />
                </span>
                {t("form.disclosureLabel")}
              </span>
              <span className="mt-0.5 block text-xs text-[var(--text-secondary)]">
                {t("form.disclosureHelp")}
              </span>
            </span>
          </label>
          {disclosureError && (
            <p className="mt-1.5 text-xs font-medium text-[var(--brand-red)]" role="alert">
              {disclosureError}
            </p>
          )}
        </div>
      </div>
    </Modal>
  );
}
