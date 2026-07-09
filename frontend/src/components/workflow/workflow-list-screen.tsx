"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Archive, ChevronRight, FileText, Pause, PauseCircle, Play, Plus, Workflow } from "lucide-react";

import { Button, Modal, useToast } from "@/components/ui";
import {
  Card,
  EmptyState,
  KpiRow,
  KpiTile,
  PageHeader,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import {
  ApiError,
  workflowsApi,
  type WorkflowFlow,
  type WorkflowOwnerType,
  type WorkflowStatus,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

const nf = new Intl.NumberFormat();

const STATUS_CHIP_TONE: Record<WorkflowStatus, ChipTone> = {
  DRAFT: "neutral",
  ACTIVE: "success",
  PAUSED: "warning",
  ARCHIVED: "neutral",
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

  const flows = query.data ?? [];
  const counts = useMemo(() => {
    const c: Record<WorkflowStatus, number> = { ACTIVE: 0, DRAFT: 0, PAUSED: 0, ARCHIVED: 0 };
    for (const f of query.data ?? []) c[f.status] += 1;
    return c;
  }, [query.data]);

  function statusLabel(status: WorkflowStatus): string {
    if (status === "ACTIVE") return t("statusActive");
    if (status === "PAUSED") return t("statusPaused");
    if (status === "ARCHIVED") return t("statusArchived");
    return t("statusDraft");
  }

  const header = (
    <PageHeader
      title={t(ownerType === "partner" ? "titlePartner" : "title")}
      description={t(ownerType === "partner" ? "subtitlePartner" : "subtitle")}
      actions={
        <Link href={`${base}/new`}>
          <Button variant="primary">
            <Plus className="size-4" strokeWidth={2} />
            {t("newFlow")}
          </Button>
        </Link>
      }
    />
  );

  if (query.isError) {
    const err = query.error;
    if (err instanceof ApiError && (err.isPermissionError || err.isAuthError)) {
      return (
        <>
          {header}
          <EmptyState kind="permission" title={t("permissionDeniedTitle")} description={t("permissionDeniedBody")} />
        </>
      );
    }
    return (
      <>
        {header}
        <EmptyState
          kind="error"
          title={t("loadErrorTitle")}
          description={err instanceof ApiError ? getMessage(err) : undefined}
          action={<Button variant="secondary" onClick={() => query.refetch()}>{t("cancel")}</Button>}
        />
      </>
    );
  }

  const loading = query.isLoading;
  const showValue = (n: number) => (loading ? "—" : nf.format(n));

  return (
    <>
      {header}

      <div className="space-y-4">
        <KpiRow cols={4}>
          <KpiTile label={t("statusActive")} value={showValue(counts.ACTIVE)} icon={Play} />
          <KpiTile label={t("statusDraft")} value={showValue(counts.DRAFT)} icon={FileText} />
          <KpiTile label={t("statusPaused")} value={showValue(counts.PAUSED)} icon={PauseCircle} />
          <KpiTile label={t("statusArchived")} value={showValue(counts.ARCHIVED)} icon={Archive} />
        </KpiRow>

        {loading ? (
          <div className="space-y-2" aria-busy="true">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-16 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
            ))}
          </div>
        ) : flows.length === 0 ? (
          <EmptyState
            kind="empty"
            icon={Workflow}
            title={t("listEmptyTitle")}
            description={t("listEmptyBody")}
          />
        ) : (
          <Card className="overflow-hidden">
            <ul className="divide-y divide-border">
              {flows.map((flow) => (
                <li key={flow.id} className="flex items-center gap-3 px-4 py-3">
                  <Link
                    href={`${base}/${flow.id}`}
                    className="group flex min-w-0 flex-1 items-center gap-3 outline-none"
                    data-testid={`workflow-row-${flow.id}`}
                  >
                    <span
                      aria-hidden
                      className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-[var(--bg-muted)] text-muted-foreground"
                    >
                      <Workflow className="size-4" strokeWidth={1.8} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="type-small block truncate font-semibold text-foreground group-hover:text-[var(--brand-primary)]">
                        {flow.name}
                      </span>
                      <span className="type-caption block truncate text-muted-foreground">
                        {flow.trigger_type}
                        {flow.version > 1 ? ` · v${flow.version}` : ""}
                      </span>
                    </span>
                  </Link>

                  <StatusChip tone={STATUS_CHIP_TONE[flow.status]} size="sm" className="hidden sm:inline-flex">
                    {statusLabel(flow.status)}
                  </StatusChip>

                  <div className="flex shrink-0 items-center gap-1">
                    {flow.status === "ACTIVE" && (
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={pause.isPending && pause.variables === flow.id}
                        onClick={() => pause.mutate(flow.id)}
                      >
                        <Pause className="size-4" strokeWidth={1.8} />
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
                    <Link
                      href={`${base}/${flow.id}`}
                      aria-label={flow.name}
                      className="hidden size-8 items-center justify-center rounded-lg text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)] sm:inline-flex"
                    >
                      <ChevronRight className="size-4" strokeWidth={1.8} />
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

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
