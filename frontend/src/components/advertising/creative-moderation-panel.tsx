"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle,
  XCircle,
  WarningCircle,
  ImageSquare,
  LockKey,
} from "@phosphor-icons/react";
import {
  Button,
  Select,
  StatusBadge,
  DisclosureLabel,
  useToast,
} from "@/components/ui";
import {
  ApiError,
  advertisingApi,
  PRIMARY_CREATIVE_SLOTS,
  type CreativeSlot,
  type DisclosureClass,
  type Placement,
  type PlacementCreative,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { CreativeImage, creativeStatusTone } from "./creative-preview";

const DISCLOSURE_CLASS_OPTIONS: DisclosureClass[] = [
  "paid_sponsored",
  "university_curated",
  "strategic_partner",
  "featured",
];

/**
 * University creative moderation (spec §6 university flow): creative preview, the
 * polished disclosure label, a missing/broken-asset inspector, per-creative
 * approve/reject (reject reason required), and inventory-class relabel that
 * surfaces the paid-immutable 409 honestly — a PAID placement's disclosure can
 * never be relabelled to a non-paid editorial/partnership class. Renders inline
 * inside the oversight review modal (no nested modal stacking).
 */
export function CreativeModerationPanel({
  placement,
  onChanged,
}: {
  placement: Placement;
  onChanged: () => void;
}) {
  const t = useTranslations("advertisingOversight");
  const tcr = useTranslations("advertisingCreatives");
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const creatives = placement.creatives ?? [];
  const missing = (placement.missing_primary_slots ?? []) as CreativeSlot[];

  /* ---- Inventory-class relabel ---- */
  const [selectedClass, setSelectedClass] = useState<DisclosureClass | string>(
    placement.disclosure_class ?? "paid_sponsored",
  );
  const [relabelError, setRelabelError] = useState<string | null>(null);

  useEffect(() => {
    setSelectedClass(placement.disclosure_class ?? "paid_sponsored");
    setRelabelError(null);
  }, [placement.disclosure_class, placement.id]);

  function refresh() {
    onChanged();
    void qc.invalidateQueries({ queryKey: ["admin", "advertising"] });
  }

  const relabel = useMutation({
    mutationFn: (cls: DisclosureClass) =>
      advertisingApi.setDisclosureClass(placement.id, {
        disclosure_class: cls,
        version: placement.version,
      }),
    onSuccess: () => {
      setRelabelError(null);
      toast.show({ tone: "success", title: t("relabelSaved") });
      refresh();
    },
    onError: (e) => {
      // Revert the optimistic select.
      setSelectedClass(placement.disclosure_class ?? "paid_sponsored");
      const reason =
        e instanceof ApiError && typeof e.details?.reason === "string"
          ? e.details.reason
          : undefined;
      if (reason === "paid_disclosure_immutable") {
        setRelabelError(t("relabelPaidImmutable"));
        return;
      }
      if (e instanceof ApiError && e.isConflict) {
        toast.show({ tone: "error", title: t("relabelConflict") });
        refresh();
        return;
      }
      setRelabelError(getMessage(e));
    },
  });

  /* ---- Per-creative review ---- */
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectNote, setRejectNote] = useState("");
  const [rejectError, setRejectError] = useState<string | null>(null);

  const review = useMutation({
    mutationFn: (vars: {
      creative: PlacementCreative;
      decision: "approve" | "reject";
      note?: string;
    }) =>
      advertisingApi.reviewCreative(vars.creative.id, {
        decision: vars.decision,
        note: vars.note,
        version: vars.creative.version,
      }),
    onSuccess: (_data, vars) => {
      setRejectingId(null);
      setRejectNote("");
      setRejectError(null);
      toast.show({
        tone: "success",
        title:
          vars.decision === "approve"
            ? t("creativeApprovedToast")
            : t("creativeRejectedToast"),
      });
      refresh();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict) {
        toast.show({ tone: "error", title: t("relabelConflict") });
        setRejectingId(null);
        refresh();
        return;
      }
      setRejectError(getMessage(e));
    },
  });

  return (
    <div className="space-y-4 border-t border-[var(--border-default)] pt-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-success shadow-sm">
            <ImageSquare aria-hidden weight="duotone" className="size-3.5 text-white" />
          </span>
          {t("creativesTitle")}
        </h3>
        {placement.disclosure && (
          <DisclosureLabel disclosure={placement.disclosure} />
        )}
      </div>

      {/* Inventory-class relabel. */}
      <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 py-3 ">
        <Select
          label={t("relabelLabel")}
          value={selectedClass}
          onChange={(e) => {
            const cls = e.target.value as DisclosureClass;
            setSelectedClass(cls);
            setRelabelError(null);
            if (cls !== placement.disclosure_class) relabel.mutate(cls);
          }}
          disabled={relabel.isPending}
          options={DISCLOSURE_CLASS_OPTIONS.map((c) => ({
            value: c,
            label: tcr(`classes.${c}`),
          }))}
          help={t("relabelHelp")}
        />
        {placement.is_paid && (
          <p className="mt-2 flex items-start gap-1.5 text-xs text-[var(--text-secondary)]">
            <span className="flex size-4 shrink-0 items-center justify-center rounded icon-chip-warning shadow-sm">
              <LockKey aria-hidden weight="duotone" className="size-2.5 text-white" />
            </span>
            {t("relabelPaidLockHint")}
          </p>
        )}
        {relabelError && (
          <p
            role="alert"
            className="mt-2 rounded-lg border border-[var(--red-400)]/40 bg-[var(--red-50)] px-2.5 py-1.5 text-xs font-medium text-[var(--brand-red)]"
          >
            {relabelError}
          </p>
        )}
      </div>

      {/* Missing approved-asset inspector. */}
      {missing.length > 0 && (
        <div className="flex items-start gap-2.5 rounded-xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] px-3.5 py-3">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-warning shadow-sm">
            <WarningCircle aria-hidden weight="duotone" className="size-3.5 text-white" />
          </span>
          <div>
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {t("missingApprovedTitle")}
            </p>
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
              {t("missingApprovedBody", {
                slots: missing.map((s) => tcr(`slots.${s}`)).join(", "),
              })}
            </p>
          </div>
        </div>
      )}

      {/* Creative previews + review. */}
      {creatives.length === 0 ? (
        <p className="flex items-center gap-2.5 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 py-3 text-sm text-[var(--text-secondary)] ">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-success shadow-sm">
            <ImageSquare aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
          {t("creativeNoneBody")}
        </p>
      ) : (
        <ul className="space-y-3">
          {creatives.map((c) => (
            <li
              key={c.id}
              className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3"
            >
              <div className="flex gap-3">
                <div className="h-24 w-32 shrink-0 overflow-hidden rounded-lg border border-[var(--border-default)]">
                  <CreativeImage
                    src={c.image_url}
                    alt={c.alt}
                    focal={c.focal_point}
                    unavailableLabel={tcr("previewStaged")}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-[var(--text-primary)]">
                      {c.slot_label}
                    </span>
                    {PRIMARY_CREATIVE_SLOTS.includes(c.slot as CreativeSlot) && (
                      <span className="rounded bg-[var(--bg-subtle)] px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[var(--text-muted)]">
                        {tcr("primaryBadge")}
                      </span>
                    )}
                    <StatusBadge tone={creativeStatusTone(c.moderation_status)}>
                      {c.moderation_status_label}
                    </StatusBadge>
                  </div>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    {c.alt ?? tcr("noAlt")}
                  </p>
                  <p className="mt-0.5 font-mono text-[11px] text-[var(--text-muted)]">
                    {t("creativeFocal", {
                      x: Math.round(c.focal_point.x * 100),
                      y: Math.round(c.focal_point.y * 100),
                    })}
                  </p>
                  {c.click_target && (
                    <p className="mt-0.5 truncate text-[11px] text-[var(--text-muted)]">
                      {t("creativeClickTarget", { url: c.click_target })}
                    </p>
                  )}
                  {c.moderation_status === "rejected" && c.moderation_note && (
                    <p className="mt-1 text-xs text-[var(--brand-red)]">
                      {tcr("rejectedNote", { note: c.moderation_note })}
                    </p>
                  )}
                </div>
              </div>

              {/* Inline review actions. */}
              {rejectingId === c.id ? (
                <div className="mt-3 space-y-2">
                  <label
                    htmlFor={`creative-reject-${c.id}`}
                    className="block text-xs font-semibold text-[var(--text-primary)]"
                  >
                    {t("creativeRejectReasonLabel")}
                    <span className="ml-0.5 text-[var(--brand-red)]" aria-hidden>
                      *
                    </span>
                  </label>
                  <textarea
                    id={`creative-reject-${c.id}`}
                    rows={2}
                    value={rejectNote}
                    onChange={(e) => {
                      setRejectNote(e.target.value);
                      if (rejectError) setRejectError(null);
                    }}
                    aria-invalid={rejectError ? true : undefined}
                    aria-describedby={
                      rejectError ? `creative-reject-${c.id}-err` : undefined
                    }
                    className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-[var(--surface-card)] focus:ring-2 focus:ring-[var(--brand-primary)]/30"
                  />
                  {rejectError && (
                    <p
                      id={`creative-reject-${c.id}-err`}
                      role="alert"
                      className="text-xs font-medium text-[var(--brand-red)]"
                    >
                      {rejectError}
                    </p>
                  )}
                  <div className="flex items-center gap-2">
                    <Button
                      variant="danger"
                      size="sm"
                      loading={review.isPending}
                      onClick={() => {
                        if (!rejectNote.trim()) {
                          setRejectError(t("creativeRejectReasonRequired"));
                          return;
                        }
                        review.mutate({
                          creative: c,
                          decision: "reject",
                          note: rejectNote.trim(),
                        });
                      }}
                    >
                      {t("creativeRejectConfirm")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={review.isPending}
                      onClick={() => {
                        setRejectingId(null);
                        setRejectNote("");
                        setRejectError(null);
                      }}
                    >
                      {t("creativeRejectCancel")}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="mt-3 flex items-center gap-2">
                  {c.moderation_status !== "approved" && (
                    <Button
                      variant="primary"
                      size="sm"
                      loading={
                        review.isPending &&
                        review.variables?.creative.id === c.id &&
                        review.variables?.decision === "approve"
                      }
                      onClick={() =>
                        review.mutate({ creative: c, decision: "approve" })
                      }
                    >
                      <CheckCircle aria-hidden weight="bold" className="size-4" />
                      {t("approveCreative")}
                    </Button>
                  )}
                  {c.moderation_status !== "rejected" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setRejectingId(c.id);
                        setRejectNote("");
                        setRejectError(null);
                      }}
                    >
                      <XCircle aria-hidden weight="bold" className="size-4" />
                      {t("rejectCreative")}
                    </Button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
