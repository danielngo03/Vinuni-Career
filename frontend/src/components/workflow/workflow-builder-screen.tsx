"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { Warning } from "@phosphor-icons/react";

import {
  Button,
  EmptyState,
  Modal,
  StatusBadge,
  Tabs,
  TabPanel,
  useToast,
  type StatusTone,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  workflowsApi,
  type DryRunResult,
  type FlowGraph,
  type WorkflowOwnerType,
  type WorkflowStatus,
} from "@/lib/api";
import { FlowCanvas, type NodeTypeDef } from "./flow-canvas";
import { NodeInspector } from "./node-inspector";
import { NodePalette } from "./node-palette";
import { FailedNodeTasksPanel } from "./failed-node-tasks-panel";
import { DryRunTrail } from "./dry-run-trail";
import { missingCapabilitiesForGraph } from "./node-capabilities";
import { useMyCapabilities } from "./use-my-capabilities";

const EMPTY_GRAPH: FlowGraph = { nodes: [], edges: [] };

const STATUS_TONE: Record<WorkflowStatus, StatusTone> = {
  DRAFT: "draft",
  ACTIVE: "active",
  PAUSED: "pending",
  ARCHIVED: "closed",
};

function nodeTypeDefs(
  t: ReturnType<typeof useTranslations>,
  ownerType: WorkflowOwnerType,
): NodeTypeDef[] {
  const shared: NodeTypeDef[] = [
    { type: "trigger", label: t("nodeTrigger"), defaultData: { trigger_type: "system.student_registered" } },
    { type: "condition", label: t("nodeCondition"), defaultData: { expression: "" } },
    { type: "wait", label: t("nodeWait"), defaultData: { hours: 24 } },
  ];
  const partnerOnly: NodeTypeDef[] = [
    { type: "assign_owner", label: t("nodeAssignOwner"), defaultData: {} },
    { type: "move_candidate", label: t("nodeMoveCandidate"), defaultData: {} },
    { type: "ai_suggestion", label: t("nodeAiSuggestion"), defaultData: {} },
    { type: "webhook", label: t("nodeWebhook"), defaultData: {} },
  ];
  const universityOnly: NodeTypeDef[] = [
    { type: "human_review", label: t("nodeHumanReview"), defaultData: { assignee_mode: "queue", sla_hours: 24 } },
    { type: "action", label: t("nodeAction"), defaultData: { action: "" } },
  ];
  const common: NodeTypeDef[] = [
    { type: "send_notification", label: t("nodeSendNotification"), defaultData: { channel: "email" } },
    { type: "create_task", label: t("nodeCreateTask"), defaultData: {} },
    { type: "request_approval", label: t("nodeRequestApproval"), defaultData: {} },
    { type: "end", label: t("nodeEnd"), defaultData: {} },
  ];
  return ownerType === "partner"
    ? [...shared, ...partnerOnly, ...common]
    : [...shared, ...universityOnly, ...common];
}

function statusLabel(t: ReturnType<typeof useTranslations>, status: WorkflowStatus): string {
  if (status === "ACTIVE") return t("statusActive");
  if (status === "PAUSED") return t("statusPaused");
  if (status === "ARCHIVED") return t("statusArchived");
  return t("statusDraft");
}

export interface WorkflowBuilderScreenProps {
  flowId: string | "new";
  ownerType: WorkflowOwnerType;
}

export function WorkflowBuilderScreen({ flowId, ownerType }: WorkflowBuilderScreenProps) {
  const t = useTranslations("workflowBuilder");
  const toast = useToast();
  const getMessage = useApiErrorMessage();
  const router = useRouter();
  const queryClient = useQueryClient();
  const isNew = flowId === "new";
  const base = ownerType === "partner" ? "/partner/workflow" : "/university/workflow";

  const [graph, setGraph] = useState<FlowGraph>(EMPTY_GRAPH);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [activateOpen, setActivateOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [dryRunResult, setDryRunResult] = useState<DryRunResult | null>(null);
  const [activateBlockedMissing, setActivateBlockedMissing] = useState<string[] | null>(null);
  const [name] = useState("");
  const [tab, setTab] = useState("builder");

  const query = useQuery({
    queryKey: ["workflows", ownerType, "detail", flowId],
    queryFn: () => workflowsApi.get(flowId),
    enabled: !isNew,
    retry: false,
  });

  const capabilities = useMyCapabilities();

  const flow = query.data;
  const effectiveGraph = isNew ? graph : (flow?.graph ?? EMPTY_GRAPH);
  const effectiveName = isNew ? name : (flow?.name ?? "");
  const status: WorkflowStatus = flow?.status ?? "DRAFT";
  const readOnly = status !== "DRAFT";
  const canActivate = status === "DRAFT" || status === "PAUSED";

  const defs = useMemo(() => nodeTypeDefs(t, ownerType), [t, ownerType]);

  const preCheckMissing = useMemo(
    () =>
      capabilities.resolved
        ? missingCapabilitiesForGraph(effectiveGraph, capabilities.granted, capabilities.isSuperadmin)
        : [],
    [effectiveGraph, capabilities],
  );

  function handleError(e: unknown) {
    if (e instanceof ApiError && e.isConflict) {
      toast.show({ tone: "error", title: t("conflictTitle"), description: t("conflictBody") });
      void query.refetch();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const invalidateDetail = (updated: { id: string }) =>
    queryClient.setQueryData(["workflows", ownerType, "detail", updated.id], updated);

  const save = useMutation({
    mutationFn: async () => {
      if (isNew) {
        return workflowsApi.create({
          name: name || "Untitled workflow",
          trigger_type: "system.student_registered",
          graph,
        });
      }
      return workflowsApi.update(flowId, { graph: effectiveGraph });
    },
    onSuccess: (saved) => {
      invalidateDetail(saved);
      toast.show({ tone: "success", title: t("save") });
      if (isNew) router.replace(`${base}/${saved.id}`);
    },
    onError: handleError,
  });

  const activate = useMutation({
    mutationFn: () => workflowsApi.activate(flowId),
    onSuccess: (updated) => {
      invalidateDetail(updated);
      setActivateOpen(false);
      setActivateBlockedMissing(null);
      toast.show({ tone: "success", title: t("statusActive") });
    },
    onError: (e) => {
      setActivateOpen(false);
      if (
        e instanceof ApiError &&
        e.isValidation &&
        e.details?.reason === "missing_capabilities" &&
        Array.isArray(e.details.missing_capabilities)
      ) {
        setActivateBlockedMissing(e.details.missing_capabilities as string[]);
        return;
      }
      handleError(e);
    },
  });

  const pause = useMutation({
    mutationFn: () => workflowsApi.pause(flowId),
    onSuccess: (updated) => {
      invalidateDetail(updated);
      toast.show({ tone: "success", title: t("pauseSuccess") });
    },
    onError: handleError,
  });

  const archive = useMutation({
    mutationFn: () => workflowsApi.archive(flowId),
    onSuccess: (updated) => {
      invalidateDetail(updated);
      setArchiveOpen(false);
      toast.show({ tone: "success", title: t("archiveSuccess") });
    },
    onError: (e) => {
      setArchiveOpen(false);
      handleError(e);
    },
  });

  const clone = useMutation({
    mutationFn: () => workflowsApi.clone(flowId),
    onSuccess: (created) => {
      toast.show({ tone: "success", title: t("cloneSuccess") });
      router.push(`${base}/${created.id}`);
    },
    onError: handleError,
  });

  const dryRun = useMutation({
    mutationFn: () => workflowsApi.test(flowId),
    onSuccess: (result) => {
      setDryRunResult(result);
      setTestOpen(true);
      setTab("test");
    },
    onError: handleError,
  });

  if (!isNew && query.isError) {
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
          action={<Button variant="secondary" onClick={() => query.refetch()}>{t("cancel")}</Button>}
        />
      </>
    );
  }

  if (!isNew && !flow) {
    return (
      <>
        <PageHeader title={t("title")} />
        <div className="space-y-4" aria-busy="true">
          {[0, 1].map((i) => (
            <div
              key={i}
              className="h-32 animate-pulse rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)]"
            />
          ))}
        </div>
      </>
    );
  }

  const selectedNode = effectiveGraph.nodes.find((n) => n.id === selectedNodeId) ?? null;

  return (
    <>
      <PageHeader
        title={effectiveName || t("title")}
        description={t(ownerType === "partner" ? "subtitlePartner" : "subtitle")}
        actions={
          <div className="flex flex-wrap gap-2">
            <StatusBadge tone={STATUS_TONE[status]}>{statusLabel(t, status)}</StatusBadge>
            {!isNew && (
              <Button variant="secondary" loading={dryRun.isPending} onClick={() => dryRun.mutate()}>
                {t("testFlow")}
              </Button>
            )}
            <Button variant="secondary" loading={save.isPending} disabled={readOnly} onClick={() => save.mutate()}>
              {save.isPending ? t("saving") : t("save")}
            </Button>
            {!isNew && status === "ACTIVE" && (
              <Button variant="secondary" loading={pause.isPending} onClick={() => pause.mutate()}>
                {t("pause")}
              </Button>
            )}
            {!isNew && status === "ACTIVE" && (
              <Button variant="ghost" onClick={() => setArchiveOpen(true)}>
                {t("archive")}
              </Button>
            )}
            {!isNew && status !== "DRAFT" && (
              <Button variant="secondary" loading={clone.isPending} onClick={() => clone.mutate()}>
                {t("clone")}
              </Button>
            )}
            {!isNew && canActivate && (
              <Button variant="primary" onClick={() => setActivateOpen(true)}>
                {t("activate")}
              </Button>
            )}
          </div>
        }
      />

      {readOnly && (
        <p className="mb-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 py-2.5 text-sm text-[var(--text-secondary)]">
          {t("readOnlyNotice")}
        </p>
      )}

      {canActivate && capabilities.resolved && preCheckMissing.length > 0 && (
        <div
          className="mb-4 flex items-start gap-2.5 rounded-xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] px-4 py-3 text-sm text-[var(--amber-700)]"
          role="alert"
          data-testid="activation-precheck-warning"
        >
          <Warning aria-hidden weight="fill" className="mt-0.5 size-4 shrink-0" />
          <span>
            {t("missingCapabilitiesPrefix")}{" "}
            <strong>{preCheckMissing.join(", ")}</strong>
          </span>
        </div>
      )}

      <Tabs
        idBase="workflow-detail"
        ariaLabel={t("title")}
        value={tab}
        onValueChange={setTab}
        items={[
          { value: "builder", label: t("tabBuilder") },
          { value: "test", label: t("tabTest") },
          { value: "tasks", label: t("tabTasks") },
          { value: "history", label: t("tabHistory") },
        ]}
      />

      <TabPanel tabsId="workflow-detail" value="builder" active={tab === "builder"}>
        <div className="flex gap-4">
          <NodePalette defs={defs} title={t("paletteTitle")} />
          <div className="flex-1">
            <FlowCanvas
              graph={effectiveGraph}
              nodeTypeDefs={defs}
              readOnly={readOnly}
              onNodeClick={setSelectedNodeId}
              onGraphChange={(next) => {
                setGraph(next);
                if (!isNew && flow) queryClient.setQueryData(["workflows", ownerType, "detail", flowId], { ...flow, graph: next });
              }}
            />
          </div>
          <NodeInspector
            node={selectedNode}
            onClose={() => setSelectedNodeId(null)}
            onChange={(nodeId, data) => {
              const nextNodes = effectiveGraph.nodes.map((n) => (n.id === nodeId ? { ...n, data } : n));
              setGraph({ ...effectiveGraph, nodes: nextNodes });
            }}
          />
        </div>
      </TabPanel>

      <TabPanel tabsId="workflow-detail" value="test" active={tab === "test"}>
        {dryRunResult ? (
          <DryRunTrail result={dryRunResult} />
        ) : (
          <EmptyState
            kind="empty"
            title={t("noDryRunYetTitle")}
            description={t("noDryRunYetBody")}
            action={
              !isNew ? (
                <Button variant="primary" loading={dryRun.isPending} onClick={() => dryRun.mutate()}>
                  {t("testFlow")}
                </Button>
              ) : undefined
            }
          />
        )}
      </TabPanel>

      <TabPanel tabsId="workflow-detail" value="tasks" active={tab === "tasks"}>
        <FailedNodeTasksPanel flowId={isNew ? null : flowId} />
      </TabPanel>

      <TabPanel tabsId="workflow-detail" value="history" active={tab === "history"}>
        <EmptyState
          kind="empty"
          title={t("executionHistoryUnavailableTitle")}
          description={t("executionHistoryUnavailableBody")}
        />
      </TabPanel>

      <Modal
        open={activateOpen}
        onClose={() => setActivateOpen(false)}
        title={t("activateConfirmTitle")}
        description={t("activateConfirmBody")}
        size="sm"
        closeLabel={t("cancel")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setActivateOpen(false)}>{t("cancel")}</Button>
            <Button variant="primary" loading={activate.isPending} onClick={() => activate.mutate()}>
              {t("activateConfirmAction")}
            </Button>
          </>
        }
      >
        {capabilities.resolved && preCheckMissing.length > 0 ? (
          <p className="text-sm text-[var(--amber-700)]" data-testid="activate-modal-precheck">
            {t("missingCapabilitiesPrefix")} <strong>{preCheckMissing.join(", ")}</strong>
          </p>
        ) : (
          <></>
        )}
      </Modal>

      <Modal
        open={archiveOpen}
        onClose={() => setArchiveOpen(false)}
        title={t("archiveConfirmTitle")}
        description={t("archiveConfirmBody")}
        size="sm"
        closeLabel={t("cancel")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setArchiveOpen(false)}>{t("cancel")}</Button>
            <Button variant="danger" loading={archive.isPending} onClick={() => archive.mutate()}>
              {t("archiveConfirmAction")}
            </Button>
          </>
        }
      >
        <></>
      </Modal>

      <Modal
        open={Boolean(activateBlockedMissing)}
        onClose={() => setActivateBlockedMissing(null)}
        title={t("activationBlockedTitle")}
        description={t("activationBlockedBody")}
        size="sm"
        closeLabel={t("cancel")}
        footer={<Button variant="primary" onClick={() => setActivateBlockedMissing(null)}>{t("cancel")}</Button>}
      >
        <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--text-secondary)]" data-testid="activation-blocked-list">
          {(activateBlockedMissing ?? []).map((cap) => (
            <li key={cap}>{cap}</li>
          ))}
        </ul>
      </Modal>

      <Modal
        open={testOpen}
        onClose={() => setTestOpen(false)}
        title={t("dryRunResultTitle")}
        description={t("dryRunResultBody")}
        size="lg"
        closeLabel={t("cancel")}
        footer={<Button variant="primary" onClick={() => setTestOpen(false)}>{t("cancel")}</Button>}
      >
        {dryRunResult && <DryRunTrail result={dryRunResult} />}
      </Modal>
    </>
  );
}
