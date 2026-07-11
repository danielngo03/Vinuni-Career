"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { OctagonAlert } from "lucide-react";
import { Button, EmptyState, Input, Select, Skeleton, useToast } from "@/components/ui";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  SectionLabel,
} from "@/components/kit";
import { ApiError, organizationApi } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

export function OwnershipTab() {
  const t = useTranslations("team.ownership");
  const tc = useTranslations("common");
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [transferOpen, setTransferOpen] = React.useState(false);
  const [targetId, setTargetId] = React.useState("");
  const [confirmText, setConfirmText] = React.useState("");
  const [confirmError, setConfirmError] = React.useState<string | null>(null);

  const ownershipQuery = useQuery({ queryKey: ["org", "ownership"], queryFn: () => organizationApi.getOwnership(), retry: false });
  const membersQuery = useQuery({ queryKey: ["org", "members"], queryFn: () => organizationApi.listMembers(), retry: false });

  const members = membersQuery.data?.data;
  const activeMembers = React.useMemo(() => (members ?? []).filter((m) => m.status === "active"), [members]);
  const ownerId = ownershipQuery.data?.owner_membership_id ?? null;
  const owner = (members ?? []).find((m) => m.id === ownerId);

  const transfer = useMutation({
    mutationFn: () => organizationApi.transferOwnership({ target_membership_id: targetId, confirm: true }),
    onSuccess: () => {
      setTransferOpen(false);
      setTargetId("");
      setConfirmText("");
      toast.show({ tone: "success", title: t("transferredToast") });
      void qc.invalidateQueries({ queryKey: ["org", "ownership"] });
    },
    onError: (e) => {
      const reason = e instanceof ApiError && typeof e.details?.reason === "string" ? e.details.reason : undefined;
      if (reason === "not_owner") return toast.show({ tone: "error", title: t("notOwnerError") });
      if (reason === "target_not_active") return toast.show({ tone: "error", title: t("targetNotActiveError") });
      if (reason === "already_owner") return toast.show({ tone: "error", title: t("alreadyOwnerError") });
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  if (ownershipQuery.isError && ownershipQuery.error instanceof ApiError && ownershipQuery.error.isPermissionError) {
    return (
      <Card>
        <CardHeader>
          <div>
            <CardTitle>{t("title")}</CardTitle>
            <CardDescription>{t("intro")}</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <EmptyState kind="permission" title={t("permissionBody")} />
        </CardContent>
      </Card>
    );
  }

  const confirmPhrase = t("confirmPhrase");
  const confirmMatches = confirmText.trim() === confirmPhrase;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("title")}</CardTitle>
          <CardDescription>{t("intro")}</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {ownershipQuery.isPending || membersQuery.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : (
          <div className="flex flex-col gap-4 rounded-xl border border-border bg-[var(--bg-subtle)] p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <SectionLabel>{t("currentOwner")}</SectionLabel>
              <p className="mt-1 font-semibold text-foreground">
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
          <div
            className="mt-5 space-y-4 rounded-xl border p-4"
            style={{ borderColor: "var(--content-danger)", background: "var(--content-danger-soft)" }}
          >
            <div className="flex items-start gap-2 text-[0.8125rem]" style={{ color: "var(--content-danger)" }}>
              <OctagonAlert aria-hidden className="mt-0.5 size-5 shrink-0" strokeWidth={1.9} />
              <p>{t("transferWarning")}</p>
            </div>

            <Select
              label={t("selectMember")}
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              options={[
                { value: "", label: t("selectPlaceholder") },
                ...activeMembers.filter((m) => m.id !== ownerId).map((m) => ({ value: m.id, label: m.full_name || m.user_email })),
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
      </CardContent>
    </Card>
  );
}
