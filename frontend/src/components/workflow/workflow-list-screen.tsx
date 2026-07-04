"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { Button, EmptyState, Modal, StatusBadge, useToast, type StatusTone } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import {
  ApiError,
  workflowsApi,
  type WorkflowFlow,
  type WorkflowOwnerType,
  type WorkflowStatus,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

const STATUS_TONE: Record<WorkflowStatus, StatusTone> = {
  DRAFT: "draft",
  ACTIVE: "active",
  PAUSED: "pending",
  ARCHIVED: "closed",
};

export interface WorkflowListScreenProps {
  /** Which persona owns these flows — drives the route prefix and copy. */
  ownerType: WorkflowOwnerType;
}

export function WorkflowListScreen({ ownerType }: WorkflowListScreenProps) {
  const t = useTranslations("workflowBuilder");
  const getMessage = useApiErrorMessage();
  const toast = useToast();
  const queryClient = useQueryClient();
  const base = ownerType === "partner" ? "/partner/workflow" : "/university/workflow";
  const [archiveTarget, setArchiveTarget] = useState<WorkflowFlow | null>(null);

  const query = useQuery({
    queryKey: ["workflows", ownerType, "list"],
    queryFn: () => workflowsApi.list(),
    retry: false,
  });

  function statusLabel(status: WorkflowStatus): string {
    if (status === "ACTIVE") return t("statusActive");
    if (status === "PAUSED") return t("statusPaused");
    if (status === "ARCHIVED") return t("statusArchived");
    return t("statusDraft");
  }

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["workflows", ownerType] });

  const pause = useMutation({
    mutationFn: (id: string) => workflowsApi.pause(id),
    onSuccess: () => {
      invalidate();
      toast.show({ tone: "success", title: t("pauseSuccess") });
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const clone = useMutation({
    mutationFn: (id: string) => workflowsApi.clone(id),
    onSuccess: (created) => {
      invalidate();
      toast.show({ tone: "success", title: t("cloneSuccess") });
      window.location.assign(`${base}/${created.id}`);
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const archive = useMutation({
    mutationFn: (id: string) => workflowsApi.archive(id),
    onSuccess: () => {
      invalidate();
      setArchiveTarget(null);
      toast.show({ tone: "success", title: t("archiveSuccess") });
    },
    onError: (e) => {
      setArchiveTarget(null);
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  if (query.isError) {
    const err = query.error;
    if (err instanceof ApiError && (err.isPermissionError || err.isAuthError)) {
      return (
        <>
          <PageHeader title={t("title")} />
          <EmptyState kind="permission" title={t("permissionDeniedTitle")} description={t("permissionDeniedBody")} />
        </>
      );
    }
    return (
      <>
        <PageHeader title={t("title")} />
        <EmptyState
          kind="error"
          title={t("loadErrorTitle")}
          description={err instanceof ApiError ? getMessage(err) : undefined}
          action={<Button variant="secondary" onClick={() => query.refetch()}>{t("cancel")}</Button>}
        />
      </>
    );
  }

  const flows = query.data ?? [];

  return (
    <>
      <PageHeader
        title={t(ownerType === "partner" ? "titlePartner" : "title")}
        description={t(ownerType === "partner" ? "subtitlePartner" : "subtitle")}
        actions={
          <Link href={`${base}/new`}>
            <Button variant="primary">{t("newFlow")}</Button>
          </Link>
        }
      />
      {flows.length === 0 && !query.isLoading ? (
        <EmptyState kind="empty" title={t("listEmptyTitle")} description={t("listEmptyBody")} />
      ) : (
        <ul className="space-y-2">
          {flows.map((flow) => (
            <li
              key={flow.id}
              className="flex items-center justify-between gap-3 rounded-xl border border-[var(--border-subtle)] bg-white/90 px-4 py-3 shadow-sm"
              data-testid={`workflow-row-${flow.id}`}
            >
              <Link href={`${base}/${flow.id}`} className="flex min-w-0 flex-1 items-center gap-3">
                <span className="min-w-0 truncate font-medium">{flow.name}</span>
                <StatusBadge tone={STATUS_TONE[flow.status]}>{statusLabel(flow.status)}</StatusBadge>
                {flow.version > 1 && (
                  <span className="shrink-0 text-xs text-[var(--text-muted)]">v{flow.version}</span>
                )}
              </Link>
              <div className="flex shrink-0 items-center gap-1.5">
                {flow.status === "ACTIVE" && (
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={pause.isPending && pause.variables === flow.id}
                    onClick={() => pause.mutate(flow.id)}
                  >
                    {t("pause")}
                  </Button>
                )}
                {flow.status === "ACTIVE" && (
                  <Button variant="ghost" size="sm" onClick={() => setArchiveTarget(flow)}>
                    {t("archive")}
                  </Button>
                )}
                {(flow.status === "DRAFT" || flow.status === "PAUSED" || flow.status === "ARCHIVED") && (
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={clone.isPending && clone.variables === flow.id}
                    onClick={() => clone.mutate(flow.id)}
                  >
                    {t("clone")}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal
        open={Boolean(archiveTarget)}
        onClose={() => setArchiveTarget(null)}
        title={t("archiveConfirmTitle")}
        description={t("archiveConfirmBody")}
        size="sm"
        closeLabel={t("cancel")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setArchiveTarget(null)}>{t("cancel")}</Button>
            <Button
              variant="danger"
              loading={archive.isPending}
              onClick={() => archiveTarget && archive.mutate(archiveTarget.id)}
            >
              {t("archiveConfirmAction")}
            </Button>
          </>
        }
      >
        <></>
      </Modal>
    </>
  );
}
