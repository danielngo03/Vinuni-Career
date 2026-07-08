"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Handshake, WarningCircle } from "@phosphor-icons/react";
import { Button, Modal, useToast } from "@/components/ui";
import { ApiError, applicationsApi, type PartnerOffer } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { OfferCard } from "./offer-panel/offer-card";
import { OfferFormModal } from "./offer-panel/offer-form-modal";
import { isLive } from "./offer-panel/utils";

/**
 * Partner-internal offer management (ADR-0007). Lives inside the partner
 * candidate detail Sheet (alongside the scorecard + interview panels). NEVER
 * rendered on any student surface — the student sees only their own offer card.
 *
 * Lifecycle: draft → submit → approve → send → accepted | declined | expired |
 * rescinded. Editable only while `draft`. Sending an offer to an anonymous
 * applicant requires an already-accepted reveal (`409 reveal_required`),
 * reusing the same reveal deep-link as interview scheduling.
 */
export function PartnerOfferPanel({
  applicationId,
  canCreate,
  anonUnrevealed,
  revealPending,
  onRequestReveal,
}: {
  applicationId: string;
  /** Offer creation is only valid while the candidate is actively under review. */
  canCreate: boolean;
  /** True while the applicant is anonymous and the reveal is not yet accepted. */
  anonUnrevealed: boolean;
  /** True when a reveal request is already pending the student's response. */
  revealPending: boolean;
  /** Opens the existing reveal-request flow (deep-link from the blocked state). */
  onRequestReveal: () => void;
}) {
  const t = useTranslations("offers");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const apiError = useApiErrorMessage();

  const listKey = useMemo(
    () => ["applications", "offers", applicationId] as const,
    [applicationId],
  );

  const query = useQuery({
    queryKey: listKey,
    queryFn: () => applicationsApi.listOffers(applicationId),
    retry: false,
  });

  const offers = query.data?.offers ?? [];
  // Prefer the LIVE offer; else the most recent terminal one (latest created).
  const liveOffer = offers.find((o) => isLive(o.status)) ?? null;
  const latestTerminal =
    offers.length > 0 ? offers[offers.length - 1] : null;
  const current = liveOffer ?? latestTerminal;

  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<PartnerOffer | null>(null);
  const [rescindTarget, setRescindTarget] = useState<PartnerOffer | null>(null);

  function invalidate() {
    void qc.invalidateQueries({ queryKey: listKey });
    void qc.invalidateQueries({
      queryKey: ["applications", "partnerDetail", applicationId],
    });
    void qc.invalidateQueries({ queryKey: ["applications", "pipeline"] });
  }

  /** Shared 409 handling for the status-transition actions (submit/approve/send/rescind). */
  function handleActionError(e: unknown) {
    if (e instanceof ApiError && e.isConflict) {
      const reason = e.details?.reason;
      if (reason === "offer_not_approved") {
        toast.show({ tone: "warning", title: t("notApprovedToast") });
      } else if (reason === "reveal_required") {
        toast.show({ tone: "warning", title: t("revealRequiredToast") });
      } else if (reason === "offer_exists") {
        toast.show({ tone: "warning", title: t("offerExistsToast") });
      } else if (reason === "offer_not_editable") {
        toast.show({ tone: "warning", title: t("notEditableToast") });
      } else {
        toast.show({ tone: "warning", title: t("conflictToast") });
      }
      invalidate();
      return;
    }
    toast.show({ tone: "error", title: apiError(e) });
  }

  const submitMutation = useMutation({
    mutationFn: (o: PartnerOffer) =>
      applicationsApi.submitOffer(o.id, o.version),
    onSuccess: () => {
      invalidate();
      toast.show({ tone: "success", title: t("submittedToast") });
    },
    onError: handleActionError,
  });

  const approveMutation = useMutation({
    mutationFn: (vars: { o: PartnerOffer; decision: "approve" | "reject" }) =>
      applicationsApi.approveOffer(vars.o.id, vars.decision, vars.o.version),
    onSuccess: (_d, vars) => {
      invalidate();
      toast.show({
        tone: "success",
        title:
          vars.decision === "approve"
            ? t("approvedToast")
            : t("rejectedBackToast"),
      });
    },
    onError: handleActionError,
  });

  const sendMutation = useMutation({
    mutationFn: (o: PartnerOffer) => applicationsApi.sendOffer(o.id, o.version),
    onSuccess: () => {
      invalidate();
      toast.show({ tone: "success", title: t("sentToast") });
    },
    onError: handleActionError,
  });

  const rescindMutation = useMutation({
    mutationFn: (o: PartnerOffer) =>
      applicationsApi.rescindOffer(o.id, o.version),
    onSuccess: () => {
      setRescindTarget(null);
      invalidate();
      toast.show({ tone: "success", title: t("rescindedToast") });
    },
    onError: (e) => {
      setRescindTarget(null);
      handleActionError(e);
    },
  });

  const header = (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-success shadow-sm">
          <Handshake aria-hidden weight="duotone" className="size-4 text-white" />
        </span>
        <h3 className="text-base font-bold text-[var(--text-primary)]">
          {t("panelTitle")}
        </h3>
      </div>
      <span className="text-xs font-medium text-[var(--text-muted)]">
        {t("partnerOnly")}
      </span>
    </div>
  );

  if (query.isPending) {
    return (
      <section aria-label={t("panelTitle")} className="space-y-3">
        {header}
        <div
          className="h-24 animate-pulse rounded-xl bg-[var(--bg-muted)]"
          aria-hidden
        />
      </section>
    );
  }

  if (query.isError) {
    const permission =
      query.error instanceof ApiError && query.error.isPermissionError;
    return (
      <section aria-label={t("panelTitle")} className="space-y-3">
        {header}
        <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3.5 ">
          <p className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <WarningCircle
              aria-hidden
              weight="duotone"
              className="size-4 text-[var(--text-muted)]"
            />
            {permission ? t("noPermission") : t("loadError")}
          </p>
          {!permission && (
            <Button
              variant="secondary"
              size="sm"
              className="mt-2"
              onClick={() => query.refetch()}
            >
              {tc("retry")}
            </Button>
          )}
        </div>
      </section>
    );
  }

  const busy =
    submitMutation.isPending ||
    approveMutation.isPending ||
    sendMutation.isPending;

  return (
    <section aria-label={t("panelTitle")} className="space-y-3">
      {header}

      {current ? (
        <OfferCard
          offer={current}
          locale={locale}
          busy={busy}
          anonUnrevealed={anonUnrevealed}
          revealPending={revealPending}
          onRequestReveal={onRequestReveal}
          onEdit={() => setEditTarget(current)}
          onSubmit={() => submitMutation.mutate(current)}
          onApprove={() =>
            approveMutation.mutate({ o: current, decision: "approve" })
          }
          onReject={() =>
            approveMutation.mutate({ o: current, decision: "reject" })
          }
          onSend={() => sendMutation.mutate(current)}
          onRescind={() => setRescindTarget(current)}
        />
      ) : (
        <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3.5 ">
          <p className="text-sm text-[var(--text-secondary)]">
            {canCreate ? t("emptyBody") : t("emptyBlocked")}
          </p>
        </div>
      )}

      {/* Create CTA — only when there is no LIVE offer and the app is active. */}
      {canCreate && !liveOffer && (
        <Button variant="primary" size="sm" onClick={() => setFormOpen(true)}>
          <Handshake aria-hidden weight="bold" className="size-4" />
          {current ? t("createAnotherCta") : t("createCta")}
        </Button>
      )}

      {/* Create modal */}
      <OfferFormModal
        open={formOpen}
        mode="create"
        applicationId={applicationId}
        onClose={() => setFormOpen(false)}
        onDone={(toastKey) => {
          setFormOpen(false);
          invalidate();
          toast.show({ tone: "success", title: t(toastKey) });
        }}
        onHandledConflict={(e) => {
          setFormOpen(false);
          handleActionError(e);
        }}
      />

      {/* Edit modal (draft only) */}
      <OfferFormModal
        open={!!editTarget}
        mode="edit"
        applicationId={applicationId}
        offer={editTarget ?? undefined}
        onClose={() => setEditTarget(null)}
        onDone={(toastKey) => {
          setEditTarget(null);
          invalidate();
          toast.show({ tone: "success", title: t(toastKey) });
        }}
        onHandledConflict={(e) => {
          setEditTarget(null);
          handleActionError(e);
        }}
      />

      {/* Rescind confirm modal (no confirm()). */}
      <Modal
        open={!!rescindTarget}
        onClose={
          rescindMutation.isPending ? () => {} : () => setRescindTarget(null)
        }
        title={t("rescindTitle")}
        description={t("rescindDescription")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setRescindTarget(null)}
              disabled={rescindMutation.isPending}
            >
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={rescindMutation.isPending}
              onClick={() =>
                rescindTarget && rescindMutation.mutate(rescindTarget)
              }
            >
              {t("rescindConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">
          {rescindTarget?.status === "sent"
            ? t("rescindSentNote")
            : t("rescindNote")}
        </p>
      </Modal>
    </section>
  );
}
