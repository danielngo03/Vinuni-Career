"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Crown, ShieldWarning, WarningOctagon } from "@phosphor-icons/react";
import {
  Button,
  EmptyState,
  Input,
  Select,
  Skeleton,
  useToast,
} from "@/components/ui";
import { SectionCard } from "@/components/settings/section-card";
import { ApiError, organizationApi } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

export function OwnershipTab() {
  const t = useTranslations("team.ownership");
  const tc = useTranslations("common");
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [transferOpen, setTransferOpen] = useState(false);
  const [targetId, setTargetId] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const ownershipQuery = useQuery({
    queryKey: ["org", "ownership"],
    queryFn: () => organizationApi.getOwnership(),
    retry: false,
  });
  const membersQuery = useQuery({
    queryKey: ["org", "members"],
    queryFn: () => organizationApi.listMembers(),
    retry: false,
  });

  const members = membersQuery.data?.data;
  const activeMembers = useMemo(
    () => (members ?? []).filter((m) => m.status === "active"),
    [members],
  );
  const ownerId = ownershipQuery.data?.owner_membership_id ?? null;
  const owner = (members ?? []).find((m) => m.id === ownerId);

  const transfer = useMutation({
    mutationFn: () =>
      organizationApi.transferOwnership({
        target_membership_id: targetId,
        confirm: true,
      }),
    onSuccess: () => {
      setTransferOpen(false);
      setTargetId("");
      setConfirmText("");
      toast.show({ tone: "success", title: t("transferredToast") });
      void qc.invalidateQueries({ queryKey: ["org", "ownership"] });
    },
    onError: (e) => {
      const reason =
        e instanceof ApiError && typeof e.details?.reason === "string"
          ? e.details.reason
          : undefined;
      if (reason === "not_owner") {
        toast.show({ tone: "error", title: t("notOwnerError") });
        return;
      }
      if (reason === "target_not_active") {
        toast.show({ tone: "error", title: t("targetNotActiveError") });
        return;
      }
      if (reason === "already_owner") {
        toast.show({ tone: "error", title: t("alreadyOwnerError") });
        return;
      }
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  if (ownershipQuery.isError && ownershipQuery.error instanceof ApiError) {
    const err = ownershipQuery.error;
    if (err.isPermissionError) {
      return (
        <SectionCard title={t("title")} description={t("intro")} icon={Crown} iconGradient="icon-chip-primary">
          <EmptyState kind="permission" icon={ShieldWarning} title={t("permissionBody")} />
        </SectionCard>
      );
    }
  }

  const confirmPhrase = t("confirmPhrase");
  const confirmMatches = confirmText.trim() === confirmPhrase;

  return (
    <SectionCard title={t("title")} description={t("intro")} icon={Crown} iconGradient="icon-chip-primary">
      {ownershipQuery.isPending || membersQuery.isPending ? (
        <Skeleton className="h-16 w-full" />
      ) : (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
              {t("currentOwner")}
            </p>
            <p className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
              {owner ? owner.full_name || owner.user_email : t("unknown")}
            </p>
          </div>
          <Button
            variant="secondary"
            onClick={() => {
              setTargetId("");
              setConfirmText("");
              setConfirmError(null);
              setTransferOpen(true);
            }}
          >
            {t("transferCta")}
          </Button>
        </div>
      )}

      {transferOpen && (
        <div className="mt-5 space-y-4 rounded-xl border border-[var(--brand-red)]/30 bg-[var(--red-50)]/40 p-4">
          <div className="flex items-start gap-2 text-sm text-[var(--brand-red)]">
            <WarningOctagon aria-hidden weight="fill" className="mt-0.5 size-5 shrink-0" />
            <p>{t("transferWarning")}</p>
          </div>

          <Select
            label={t("selectMember")}
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            options={[
              { value: "", label: t("selectPlaceholder") },
              ...activeMembers
                .filter((m) => m.id !== ownerId)
                .map((m) => ({ value: m.id, label: m.full_name || m.user_email })),
            ]}
          />

          <Input
            label={t("confirmLabel", { phrase: confirmPhrase })}
            placeholder={t("confirmPlaceholder")}
            value={confirmText}
            onChange={(e) => {
              setConfirmText(e.target.value);
              if (confirmError) setConfirmError(null);
            }}
            error={confirmError ?? undefined}
          />

          <div className="flex justify-end gap-3">
            <Button variant="ghost" onClick={() => setTransferOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              disabled={!targetId}
              loading={transfer.isPending}
              onClick={() => {
                if (!confirmMatches) {
                  setConfirmError(t("confirmMismatch"));
                  return;
                }
                transfer.mutate();
              }}
            >
              {t("transferConfirm")}
            </Button>
          </div>
        </div>
      )}
    </SectionCard>
  );
}
