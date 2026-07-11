"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { AlertTriangle } from "lucide-react";

import { Button, useToast } from "@/components/ui";
import { EmptyState, StatusChip } from "@/components/kit";
import { formatRelativeTime } from "@/lib/format";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { ApiError, workflowsApi, type FailedNodeTask } from "@/lib/api";

/**
 * Recoverable-task queue for nodes that failed during a REAL (non-simulated)
 * execution — never silently drops a candidate/application/notification
 * (docs/PARTNER_RBAC_ANALYTICS_SPEC.md "Failed nodes create recoverable
 * tasks"). When `flowId` is given, only that flow's tasks are shown;
 * otherwise all open tasks the caller can see are shown.
 */
export function FailedNodeTasksPanel({ flowId }: { flowId: string | null }) {
  const t = useTranslations("workflowBuilder");
  const locale = useLocale();
  const toast = useToast();
  const getMessage = useApiErrorMessage();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["workflows", "tasks", "open"],
    queryFn: () => workflowsApi.listTasks("open"),
    enabled: flowId !== null,
    retry: false,
  });

  const resolve = useMutation({
    mutationFn: ({ id, resolution }: { id: string; resolution: "resolved" | "dismissed" }) =>
      workflowsApi.resolveTask(id, resolution),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows", "tasks"] });
      toast.show({ tone: "success", title: t("taskResolved") });
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  if (flowId === null) {
    return (
      <EmptyState kind="empty" title={t("tasksUnavailableForNewTitle")} description={t("tasksUnavailableForNewBody")} />
    );
  }

  if (query.isError) {
    const err = query.error;
    if (err instanceof ApiError && (err.isPermissionError || err.isAuthError)) {
      return <EmptyState kind="permission" title={t("permissionDeniedTitle")} description={t("permissionDeniedBody")} />;
    }
    return (
      <EmptyState
        kind="error"
        title={t("loadErrorTitle")}
        action={<Button variant="secondary" onClick={() => query.refetch()}>{t("cancel")}</Button>}
      />
    );
  }

  const allTasks = query.data ?? [];
  const tasks = allTasks.filter((task) => task.flow_id === flowId);

  if (tasks.length === 0 && !query.isLoading) {
    return <EmptyState kind="empty" title={t("noTasksTitle")} description={t("noTasksBody")} />;
  }

  return (
    <ul className="space-y-2.5" data-testid="failed-node-tasks">
      {tasks.map((task: FailedNodeTask) => (
        <li
          key={task.id}
          className="flex items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-sm)]"
          data-testid={`failed-task-${task.id}`}
        >
          <span
            aria-hidden
            className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg"
            style={{ background: "var(--content-danger-soft)", color: "var(--content-danger)" }}
          >
            <AlertTriangle className="size-4" strokeWidth={1.9} />
          </span>
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <StatusChip tone="danger" size="sm">
                {t("dryRunStepStatus.failed")}
              </StatusChip>
              <span className="type-caption text-muted-foreground">
                {formatRelativeTime(task.created_at, locale)}
              </span>
            </div>
            <p className="type-small font-semibold text-foreground">
              {t("failedNodeLabel", { node: task.node_id })}
            </p>
            <p className="type-small text-muted-foreground">{task.user_safe_error}</p>
          </div>
          <div className="flex shrink-0 flex-col gap-1.5 sm:flex-row">
            <Button
              variant="secondary"
              size="sm"
              loading={resolve.isPending && resolve.variables?.id === task.id && resolve.variables.resolution === "resolved"}
              onClick={() => resolve.mutate({ id: task.id, resolution: "resolved" })}
            >
              {t("taskResolveAction")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              loading={resolve.isPending && resolve.variables?.id === task.id && resolve.variables.resolution === "dismissed"}
              onClick={() => resolve.mutate({ id: task.id, resolution: "dismissed" })}
            >
              {t("taskDismissAction")}
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
