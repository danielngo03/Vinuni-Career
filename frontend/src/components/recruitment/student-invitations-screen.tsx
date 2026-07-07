"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  EnvelopeSimple,
  Buildings,
  CheckCircle,
  Sparkle,
  XCircle,
  Clock,
  ArrowRight,
  Hourglass,
  Handshake,
} from "@phosphor-icons/react";
import { useRouter } from "@/i18n/navigation";
import {
  Button,
  EmptyState,
  InsightPanel,
  Modal,
  Skeleton,
  StatusBadge,
  useToast,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { ApiError, invitationsApi, type JobInvitation } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { InsightTone, StatusTone } from "@/components/ui";

function statusTone(status: string): StatusTone {
  if (status === "pending") return "pending";
  if (status === "accepted") return "accepted";
  if (status === "declined") return "closed";
  return "draft"; // expired
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function InvitationCard({
  inv,
  onAccept,
  onDecline,
  accepting,
  declining,
}: {
  inv: JobInvitation;
  onAccept: () => void;
  onDecline: () => void;
  accepting: boolean;
  declining: boolean;
}) {
  const t = useTranslations("jobInvitations");
  const isPending = inv.status === "pending";
  const isExpired = inv.status === "expired";

  // Build localised status label
  const statusKey = `status${inv.status.charAt(0).toUpperCase()}${inv.status.slice(1)}` as
    | "statusPending"
    | "statusAccepted"
    | "statusDeclined"
    | "statusExpired";

  return (
    <article className="rounded-2xl border border-[var(--border-default)] bg-white shadow-[var(--shadow-sm)] overflow-hidden transition-shadow hover:shadow-[var(--shadow-md)]">
      {/* Header */}
      <div className="flex items-start gap-3 px-5 pt-5 pb-3">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
          <Buildings weight="duotone" className="size-6" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)] mb-0.5">
            {inv.company_name}
          </p>
          <h3 className="text-base font-semibold text-[var(--text-primary)] leading-snug">
            {inv.job_title}
          </h3>
        </div>
        <StatusBadge tone={statusTone(inv.status)}>{t(statusKey)}</StatusBadge>
      </div>

      {/* Message */}
      {inv.message && (
        <div className="mx-5 mb-3 rounded-xl border border-[var(--border-default)] bg-[var(--bg-muted)] px-4 py-3 text-sm text-[var(--text-secondary)] leading-relaxed">
          {inv.message}
        </div>
      )}

      {/* Meta */}
      <div className="flex items-center gap-3 px-5 pb-4 text-xs text-[var(--text-muted)]">
        <span className="inline-flex items-center gap-1">
          <Clock aria-hidden weight="duotone" className="size-3.5" />
          {isExpired
            ? t("expired")
            : inv.responded_at
              ? t("responded", { date: formatDate(inv.responded_at) })
              : t("expiresAt", { date: formatDate(inv.expires_at) })}
        </span>
      </div>

      {/* Actions — only for pending */}
      {isPending && (
        <div className="flex items-center gap-2 border-t border-[var(--border-default)] bg-[var(--bg-muted)] px-5 py-3.5">
          <Button
            size="sm"
            variant="primary"
            onClick={onAccept}
            disabled={accepting || declining}
            className="flex items-center gap-1.5"
          >
            <CheckCircle aria-hidden weight="fill" className="size-4" />
            {t("accept")}
            <ArrowRight aria-hidden weight="bold" className="size-3.5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onDecline}
            disabled={accepting || declining}
            className="text-[var(--text-muted)]"
          >
            <XCircle aria-hidden weight="duotone" className="size-4 mr-1" />
            {t("decline")}
          </Button>
        </div>
      )}
    </article>
  );
}

function InvitationsSkeleton() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="rounded-2xl border border-[var(--border-default)] bg-white p-5 space-y-3"
        >
          <div className="flex items-start gap-3">
            <Skeleton className="size-11 rounded-xl shrink-0" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-3 w-1/4" />
              <Skeleton className="h-5 w-2/3" />
            </div>
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
          <Skeleton className="h-14 rounded-xl" />
          <Skeleton className="h-3 w-1/3" />
        </div>
      ))}
    </div>
  );
}

type InvitationInsightKey =
  | "insightRespondMany"
  | "insightRespondSoon"
  | "insightAcceptedNext"
  | "insightAllResolved"
  | "insightVisible";

function deriveInvitationInsights(
  invitations: { status: string }[],
): InvitationInsightKey[] {
  const out: InvitationInsightKey[] = [];
  const pending = invitations.filter((i) => i.status === "pending").length;
  const accepted = invitations.filter((i) => i.status === "accepted").length;

  if (pending > 2) out.push("insightRespondMany");
  else if (pending > 0) out.push("insightRespondSoon");
  if (accepted > 0 && pending === 0) out.push("insightAcceptedNext");
  if (invitations.length > 0 && pending === 0 && accepted === 0) out.push("insightAllResolved");
  if (out.length === 0 && invitations.length >= 3) out.push("insightVisible");
  return out.slice(0, 2);
}

const INVITATION_INSIGHT_TONE: Record<InvitationInsightKey, InsightTone> = {
  insightRespondMany: "warning",
  insightRespondSoon: "warning",
  insightAcceptedNext: "success",
  insightAllResolved: "success",
  insightVisible: "success",
};

export function StudentInvitationsScreen() {
  const t = useTranslations("jobInvitations");
  const toast = useToast();
  const router = useRouter();
  const qc = useQueryClient();

  const [declineTarget, setDeclineTarget] = useState<JobInvitation | null>(null);
  const [respondingId, setRespondingId] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["student-invitations"],
    queryFn: () => invitationsApi.listMine({ status: "all" }),
    retry: false,
  });

  const respondMutation = useMutation({
    mutationFn: ({
      id,
      response,
    }: {
      id: string;
      response: "accepted" | "declined";
    }) => invitationsApi.respond(id, response),

    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: ["student-invitations"] });
      setRespondingId(null);
      setDeclineTarget(null);

      if (result.status === "accepted" && result.apply_url) {
        toast.show({ tone: "success", title: t("acceptedToast") });
        router.push(result.apply_url);
      } else {
        toast.show({ tone: "success", title: t("declinedToast") });
      }
    },

    onError: () => {
      setRespondingId(null);
      toast.show({ tone: "error", title: t("errorRespond") });
    },
  });

  function handleAccept(inv: JobInvitation) {
    setRespondingId(inv.id);
    respondMutation.mutate({ id: inv.id, response: "accepted" });
  }

  function handleDeclineConfirm() {
    if (!declineTarget) return;
    setRespondingId(declineTarget.id);
    respondMutation.mutate({ id: declineTarget.id, response: "declined" });
  }

  const invitations = query.data ?? [];
  const pending = invitations.filter((i) => i.status === "pending");
  const accepted = invitations.filter((i) => i.status === "accepted");
  const others = invitations.filter((i) => i.status !== "pending");
  const invInsights = deriveInvitationInsights(invitations);

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-8">
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
      />

      {/* Summary tiles — shown once data loads and there are invitations */}
      {!query.isPending && !query.isError && invitations.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-3.5 shadow-[var(--shadow-sm)] transition-all hover:-translate-y-0.5">
            <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-warning shadow-sm">
              <Hourglass aria-hidden weight="duotone" className="size-4.5" />
            </div>
            <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{pending.length}</p>
            <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statusPending")}</p>
          </div>
          <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-3.5 shadow-[var(--shadow-sm)] transition-all hover:-translate-y-0.5">
            <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-success shadow-sm">
              <Handshake aria-hidden weight="duotone" className="size-4.5" />
            </div>
            <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{accepted.length}</p>
            <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statusAccepted")}</p>
          </div>
          <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-3.5 shadow-[var(--shadow-sm)] transition-all hover:-translate-y-0.5">
            <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
              <EnvelopeSimple aria-hidden weight="duotone" className="size-4.5" />
            </div>
            <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{invitations.length}</p>
            <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statTotalReceived")}</p>
          </div>
        </div>
      )}

      {/* Invitation signals */}
      {!query.isPending && !query.isError && invitations.length > 0 && invInsights.length > 0 && (
        <InsightPanel
          title={t("aiInsightsTitle")}
          icon={<Sparkle aria-hidden weight="duotone" className="size-4" />}
          items={invInsights.map((key) => ({ label: t(key), tone: INVITATION_INSIGHT_TONE[key] }))}
        />
      )}

      {query.isPending && <InvitationsSkeleton />}

      {query.isError && (
        <EmptyState
          kind="error"
          title={t("errorLoad")}
          description={
            (query.error instanceof ApiError ? query.error.message : undefined) ?? ""
          }
        />
      )}

      {!query.isPending && !query.isError && invitations.length === 0 && (
        <EmptyState
          kind="empty"
          title={t("empty")}
          description={t("emptyBody")}
          icon={EnvelopeSimple}
        />
      )}

      {pending.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide">
            {t("statusPending")} · {pending.length}
          </h2>
          <div className="space-y-4">
            {pending.map((inv) => (
              <InvitationCard
                key={inv.id}
                inv={inv}
                onAccept={() => handleAccept(inv)}
                onDecline={() => setDeclineTarget(inv)}
                accepting={
                  respondingId === inv.id &&
                  respondMutation.variables?.response === "accepted"
                }
                declining={
                  respondingId === inv.id &&
                  respondMutation.variables?.response === "declined"
                }
              />
            ))}
          </div>
        </section>
      )}

      {others.length > 0 && (
        <section className={cn(pending.length > 0 && "pt-2")}>
          <h2 className="mb-3 text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide">
            {t("sectionHistory")}
          </h2>
          <div className="space-y-3">
            {others.map((inv) => (
              <InvitationCard
                key={inv.id}
                inv={inv}
                onAccept={() => {}}
                onDecline={() => {}}
                accepting={false}
                declining={false}
              />
            ))}
          </div>
        </section>
      )}

      {/* Decline confirm modal */}
      <Modal
        open={!!declineTarget}
        onClose={() => setDeclineTarget(null)}
        title={t("declineTitle")}
        description={t("declineBody")}
      >
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setDeclineTarget(null)}>
            {t("cancelInvite")}
          </Button>
          <Button
            variant="danger"
            onClick={handleDeclineConfirm}
            disabled={respondMutation.isPending}
          >
            {t("declineConfirm")}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
