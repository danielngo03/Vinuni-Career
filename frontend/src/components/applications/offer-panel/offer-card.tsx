"use client";

import { useTranslations } from "next-intl";
import {
  BadgeCheck,
  CheckCircle2,
  Eye,
  Pencil,
  Send,
  Ban,
  ThumbsDown,
} from "lucide-react";
import { Button } from "@/components/ui";
import { StatusChip } from "@/components/kit";
import { formatDateTime } from "@/lib/format";
import { useOfferLabels } from "@/lib/applications/labels";
import type { PartnerOffer } from "@/lib/api";
import { OFFER_STATUS_CHIP } from "../chip-tones";
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
      <dt className="type-caption text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-foreground">{children}</dd>
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
    <div className="rounded-lg border border-border bg-card p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="type-small font-semibold text-foreground">{offer.position_title}</span>
        <StatusChip tone={OFFER_STATUS_CHIP[status] ?? "neutral"}>
          {labels.status(status, offer.status_label)}
        </StatusChip>
      </div>

      <dl className="mt-2.5 space-y-1.5 type-small">
        {offer.department && <Row label={t("departmentLabel")}>{offer.department}</Row>}
        {/* Comp is recruiter + owning-student only (decrypted for the partner). */}
        <Row label={t("compLabel")}>
          {offer.comp_summary ?? (
            <span className="text-muted-foreground">{t("compNotSet")}</span>
          )}
        </Row>
        {offer.start_date && (
          <Row label={t("startDateLabel")}>{formatDateTime(offer.start_date, locale)}</Row>
        )}
        <Row label={t("deadlineLabel")}>{formatDateTime(offer.expiry_date, locale)}</Row>
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
        <p className="mt-2.5 type-caption text-muted-foreground">{t("pendingHint")}</p>
      )}
      {status === "sent" && (
        <p className="mt-2.5 type-caption text-muted-foreground">{t("sentHint")}</p>
      )}
      {status === "accepted" && (
        <p
          className="mt-2.5 flex items-center gap-1.5 type-caption font-semibold"
          style={{ color: "var(--content-success)" }}
        >
          <BadgeCheck aria-hidden className="size-4" strokeWidth={1.8} />
          {t("acceptedHint")}
        </p>
      )}
      {status === "declined" && (
        <p
          className="mt-2.5 flex items-center gap-1.5 type-caption"
          style={{ color: "var(--content-danger)" }}
        >
          <ThumbsDown aria-hidden className="size-4" strokeWidth={1.8} />
          {t("declinedHint")}
        </p>
      )}
      {status === "expired" && (
        <p className="mt-2.5 type-caption text-muted-foreground">{t("expiredHint")}</p>
      )}
      {status === "rescinded" && (
        <p className="mt-2.5 type-caption text-muted-foreground">{t("rescindedHint")}</p>
      )}

      {/* Send blocked by an outstanding reveal (approved + anonymous). */}
      {sendBlockedByReveal && (
        <div
          role="status"
          className="mt-3 rounded-lg p-3"
          style={{ background: "var(--content-warning-soft)" }}
        >
          <p className="flex items-start gap-2 type-small font-semibold text-foreground">
            <Eye
              aria-hidden
              className="mt-0.5 size-4 shrink-0"
              strokeWidth={1.8}
              style={{ color: "var(--content-warning)" }}
            />
            {t("sendRevealBlockedTitle")}
          </p>
          <p className="mt-1 type-caption text-muted-foreground">{t("sendRevealBlockedBody")}</p>
          {revealPending ? (
            <p
              className="mt-2 type-caption font-medium"
              style={{ color: "var(--content-warning)" }}
            >
              {t("revealBlockedPending")}
            </p>
          ) : (
            <Button variant="secondary" size="sm" className="mt-2.5" onClick={onRequestReveal}>
              <Eye aria-hidden className="size-4" strokeWidth={1.8} />
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
              <Pencil aria-hidden className="size-4" strokeWidth={1.8} />
              {t("editCta")}
            </Button>
            <Button variant="primary" size="sm" loading={busy} onClick={onSubmit}>
              <Send aria-hidden className="size-4" strokeWidth={1.8} />
              {t("submitCta")}
            </Button>
          </>
        )}
        {status === "pending_approval" && (
          <>
            <Button variant="primary" size="sm" loading={busy} onClick={onApprove}>
              <CheckCircle2 aria-hidden className="size-4" strokeWidth={1.8} />
              {t("approveCta")}
            </Button>
            <Button variant="ghost" size="sm" disabled={busy} onClick={onReject}>
              <Pencil aria-hidden className="size-4" strokeWidth={1.8} />
              {t("rejectBackCta")}
            </Button>
          </>
        )}
        {status === "approved" && !sendBlockedByReveal && (
          <Button variant="primary" size="sm" loading={busy} onClick={onSend}>
            <Send aria-hidden className="size-4" strokeWidth={1.8} />
            {t("sendCta")}
          </Button>
        )}
        {isLive(status) && (
          <Button variant="ghost" size="sm" disabled={busy} onClick={onRescind}>
            <Ban aria-hidden className="size-4" strokeWidth={1.8} />
            {t("rescindCta")}
          </Button>
        )}
      </div>
    </div>
  );
}
