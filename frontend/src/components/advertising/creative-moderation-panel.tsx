"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, XCircle, AlertTriangle, Image as ImageIcon, Lock } from "lucide-react";
import {
  Button,
  Select,
  Textarea,
  DisclosureLabel,
  useToast,
} from "@/components/ui";
import { Card, StatusChip, EmptyState, type ChipTone } from "@/components/kit";
import {
  ApiError,
  advertisingApi,
  PRIMARY_CREATIVE_SLOTS,
  type CreativeModerationStatus,
  type CreativeSlot,
  type DisclosureClass,
  type Placement,
  type PlacementCreative,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { CreativeImage } from "./creative-preview";

const DISCLOSURE_CLASS_OPTIONS: DisclosureClass[] = [
  "paid_sponsored",
  "university_curated",
  "strategic_partner",
  "featured",
];

/** Creative review state → StatusChip tone (never colour-only; always labelled). */
function creativeChipTone(status: CreativeModerationStatus | string): ChipTone {
  if (status === "approved") return "success";
  if (status === "rejected") return "danger";
  return "warning";
}

/**
 * University creative moderation (spec §6 university flow): creative preview, the
 * polished disclosure label, a missing/broken-asset inspector, per-creative
 * approve/reject (reject reason required), and inventory-class relabel that
 * surfaces the paid-immutable 409 honestly — a PAID placement's disclosure can
 * never be relabelled to a non-paid editorial/partnership class. Renders inline
 * inside the oversight review DetailSheet (no nested modal stacking).
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
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="type-h3 flex items-center gap-2 text-[var(--text-primary)]">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-info">
            <ImageIcon aria-hidden className="size-3.5" strokeWidth={2} />
          </span>
          {t("creativesTitle")}
        </h3>
        {placement.disclosure && (
          <DisclosureLabel disclosure={placement.disclosure} />
        )}
      </div>

      {/* Inventory-class relabel. */}
      <Card padded className="space-y-2">
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
          <p className="flex items-start gap-1.5 text-xs text-[var(--text-secondary)]">
            <span className="flex size-4 shrink-0 items-center justify-center rounded icon-chip-warning">
              <Lock aria-hidden className="size-2.5" strokeWidth={2.2} />
            </span>
            {t("relabelPaidLockHint")}
          </p>
        )}
        {relabelError && (
          <p
            role="alert"
            className="rounded-lg border border-[var(--content-danger)]/30 bg-[var(--content-danger-soft)] px-2.5 py-1.5 text-xs font-medium text-[var(--content-danger)]"
          >
            {relabelError}
          </p>
        )}
      </Card>

      {/* Missing approved-asset inspector. */}
      {missing.length > 0 && (
        <div className="flex items-start gap-2.5 rounded-xl border border-[var(--content-warning)]/30 bg-[var(--content-warning-soft)] px-3.5 py-3">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-warning">
            <AlertTriangle aria-hidden className="size-3.5" strokeWidth={2} />
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
        <EmptyState title={t("creativeNoneBody")} />
      ) : (
        <ul className="space-y-3">
          {creatives.map((c) => (
            <Card key={c.id} className="p-3">
              <div className="flex gap-3">
                <div className="h-24 w-32 shrink-0 overflow-hidden rounded-lg border border-border">
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
                      <StatusChip tone="neutral" size="sm">
                        {tcr("primaryBadge")}
                      </StatusChip>
                    )}
                    <StatusChip
                      tone={creativeChipTone(c.moderation_status)}
                      size="sm"
                    >
                      {c.moderation_status_label}
                    </StatusChip>
                  </div>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    {c.alt ?? tcr("noAlt")}
                  </p>
                  <p className="mt-0.5 font-mono text-[11px] tabular-nums text-[var(--text-muted)]">
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
                    <p className="mt-1 text-xs text-[var(--content-danger)]">
                      {tcr("rejectedNote", { note: c.moderation_note })}
                    </p>
                  )}
                </div>
              </div>

              {/* Inline review actions. */}
              {rejectingId === c.id ? (
                <div className="mt-3 space-y-2">
                  <Textarea
                    label={t("creativeRejectReasonLabel")}
                    required
                    rows={2}
                    value={rejectNote}
                    error={rejectError ?? undefined}
                    onChange={(e) => {
                      setRejectNote(e.target.value);
                      if (rejectError) setRejectError(null);
                    }}
                  />
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
                      <CheckCircle2 aria-hidden className="size-4" strokeWidth={2} />
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
                      <XCircle aria-hidden className="size-4" strokeWidth={2} />
                      {t("rejectCreative")}
                    </Button>
                  )}
                </div>
              )}
            </Card>
          ))}
        </ul>
      )}
    </div>
  );
}
