"use client";

import { useTranslations } from "next-intl";
import {
  CheckCircle,
  PaperPlaneTilt,
  PencilSimple,
  Prohibit,
  SealCheck,
  ThumbsDown,
  UserFocus,
} from "@phosphor-icons/react";
import { Button, StatusBadge } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import { OFFER_STATUS_TONE, useOfferLabels } from "@/lib/applications/labels";
import type { PartnerOffer } from "@/lib/api";
import { isLive } from "./utils";

export function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      <dt className="text-xs font-medium text-[var(--text-muted)]">{label}</dt>
      <dd className="min-w-0 text-[var(--text-primary)]">{children}</dd>
    </div>
  );
}

export function OfferCard({
  offer,
  locale,
  busy,
  anonUnrevealed,
  revealPending,
  onRequestReveal,
  onEdit,
  onSubmit,
  onApprove,
  onReject,
  onSend,
  onRescind,
}: {
  offer: PartnerOffer;
  locale: string;
  busy: boolean;
  anonUnrevealed: boolean;
  revealPending: boolean;
  onRequestReveal: () => void;
  onEdit: () => void;
  onSubmit: () => void;
  onApprove: () => void;
  onReject: () => void;
  onSend: () => void;
  onRescind: () => void;
}) {
  const t = useTranslations("offers");
  const labels = useOfferLabels();
  const status = offer.status;
  // Sending an approved offer to a still-anonymous applicant is blocked until the
  // reveal handshake is accepted (ADR-0007 §5) — mirror the interview posture.
  const sendBlockedByReveal = status === "approved" && anonUnrevealed;

  return (
    <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface)] backdrop-blur-md p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-[var(--text-primary)]">
          {offer.position_title}
        </span>
        <StatusBadge tone={OFFER_STATUS_TONE[status] ?? "info"}>
          {labels.status(status, offer.status_label)}
        </StatusBadge>
      </div>

      <dl className="mt-2.5 space-y-1.5 text-sm">
        {offer.department && (
          <Row label={t("departmentLabel")}>{offer.department}</Row>
        )}
        {/* Comp is recruiter + owning-student only (decrypted for the partner). */}
        <Row label={t("compLabel")}>
          {offer.comp_summary ?? (
            <span className="text-[var(--text-muted)]">{t("compNotSet")}</span>
          )}
        </Row>
        {offer.start_date && (
          <Row label={t("startDateLabel")}>
            {formatDateTime(offer.start_date, locale)}
          </Row>
        )}
        <Row label={t("deadlineLabel")}>
          {formatDateTime(offer.expiry_date, locale)}
        </Row>
        {offer.benefits_summary && (
          <Row label={t("benefitsLabel")}>
            <span className="whitespace-pre-wrap">{offer.benefits_summary}</span>
          </Row>
        )}
        {offer.terms_notes && (
          <Row label={t("termsLabel")}>
            <span className="whitespace-pre-wrap">{offer.terms_notes}</span>
          </Row>
        )}
      </dl>

      {/* Status-specific guidance. */}
      {status === "pending_approval" && (
        <p className="mt-2.5 text-xs text-[var(--text-muted)]">
          {t("pendingHint")}
        </p>
      )}
      {status === "sent" && (
        <p className="mt-2.5 text-xs text-[var(--text-muted)]">{t("sentHint")}</p>
      )}
      {status === "accepted" && (
        <p className="mt-2.5 flex items-center gap-1.5 text-xs font-semibold text-[var(--teal-600)]">
          <SealCheck aria-hidden weight="duotone" className="size-4" />
          {t("acceptedHint")}
        </p>
      )}
      {status === "declined" && (
        <p className="mt-2.5 flex items-center gap-1.5 text-xs text-[var(--brand-red)]">
          <ThumbsDown aria-hidden weight="duotone" className="size-4" />
          {t("declinedHint")}
        </p>
      )}
      {status === "expired" && (
        <p className="mt-2.5 text-xs text-[var(--text-muted)]">
          {t("expiredHint")}
        </p>
      )}
      {status === "rescinded" && (
        <p className="mt-2.5 text-xs text-[var(--text-muted)]">
          {t("rescindedHint")}
        </p>
      )}

      {/* Send blocked by an outstanding reveal (approved + anonymous). */}
      {sendBlockedByReveal && (
        <div
          role="status"
          className="mt-3 rounded-xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] p-3"
        >
          <p className="flex items-start gap-2 text-sm font-semibold text-[var(--text-primary)]">
            <UserFocus
              aria-hidden
              weight="duotone"
              className="mt-0.5 size-4 shrink-0 text-[var(--amber-700)]"
            />
            {t("sendRevealBlockedTitle")}
          </p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {t("sendRevealBlockedBody")}
          </p>
          {revealPending ? (
            <p className="mt-2 text-xs font-medium text-[var(--amber-700)]">
              {t("revealBlockedPending")}
            </p>
          ) : (
            <Button
              variant="secondary"
              size="sm"
              className="mt-2.5"
              onClick={onRequestReveal}
            >
              <UserFocus aria-hidden weight="bold" className="size-4" />
              {t("revealBlockedCta")}
            </Button>
          )}
        </div>
      )}

      {/* Actions per status. */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {status === "draft" && (
          <>
            <Button variant="secondary" size="sm" disabled={busy} onClick={onEdit}>
              <PencilSimple aria-hidden weight="bold" className="size-4" />
              {t("editCta")}
            </Button>
            <Button variant="primary" size="sm" loading={busy} onClick={onSubmit}>
              <PaperPlaneTilt aria-hidden weight="bold" className="size-4" />
              {t("submitCta")}
            </Button>
          </>
        )}
        {status === "pending_approval" && (
          <>
            <Button variant="primary" size="sm" loading={busy} onClick={onApprove}>
              <CheckCircle aria-hidden weight="bold" className="size-4" />
              {t("approveCta")}
            </Button>
            <Button variant="ghost" size="sm" disabled={busy} onClick={onReject}>
              <PencilSimple aria-hidden weight="bold" className="size-4" />
              {t("rejectBackCta")}
            </Button>
          </>
        )}
        {status === "approved" && !sendBlockedByReveal && (
          <Button variant="primary" size="sm" loading={busy} onClick={onSend}>
            <PaperPlaneTilt aria-hidden weight="bold" className="size-4" />
            {t("sendCta")}
          </Button>
        )}
        {isLive(status) && (
          <Button variant="ghost" size="sm" disabled={busy} onClick={onRescind}>
            <Prohibit aria-hidden weight="bold" className="size-4" />
            {t("rescindCta")}
          </Button>
        )}
      </div>
    </div>
  );
}
