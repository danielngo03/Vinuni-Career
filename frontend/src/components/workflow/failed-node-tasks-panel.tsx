"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { WarningCircle } from "@phosphor-icons/react";

import { Button, EmptyState, useToast } from "@/components/ui";
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
    <ul className="space-y-2" data-testid="failed-node-tasks">
      {tasks.map((task: FailedNodeTask) => (
        <li
          key={task.id}
          className="flex items-start gap-3 rounded-xl border border-[var(--brand-red)]/25 bg-[var(--red-50)] px-4 py-3"
          data-testid={`failed-task-${task.id}`}
        >
          <WarningCircle aria-hidden weight="fill" className="mt-0.5 size-4 shrink-0 text-[var(--brand-red)]" />
          <div className="min-w-0 flex-1 space-y-1">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {t("failedNodeLabel", { node: task.node_id })}
            </p>
            <p className="text-sm text-[var(--text-secondary)]">{task.user_safe_error}</p>
          </div>
          <div className="flex shrink-0 gap-1.5">
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
