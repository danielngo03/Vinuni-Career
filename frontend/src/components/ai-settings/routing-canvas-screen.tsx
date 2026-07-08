"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { CheckCircle, WarningCircle, ShieldWarning, SignIn } from "@phosphor-icons/react";

import {
  Button,
  EmptyState,
  Input,
  Modal,
  Select,
  StatusBadge,
  useToast,
  type StatusTone,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  AI_MODEL_FAMILIES,
  aiRoutingApi,
  type AiModelFamily,
  type AiRoutingGraphRecord,
  type RoutingGraph,
  type RoutingGraphStatus,
} from "@/lib/api";
import type { FlowGraph, FlowNode } from "@/lib/api/workflows";
import { FlowCanvas, type NodeTypeDef } from "@/components/workflow/flow-canvas";
import { NodePalette } from "@/components/workflow/node-palette";

const EMPTY_FLOW_GRAPH: FlowGraph = { nodes: [], edges: [] };

const STATUS_TONE: Record<RoutingGraphStatus, StatusTone> = {
  DRAFT: "draft",
  ACTIVE: "active",
  ARCHIVED: "closed",
};

/**
 * A routing graph's node `type` is the backend contract value `"provider"`,
 * which is not part of `WorkflowNodeType`. `FlowCanvas` (reused as-is from the
 * Workflow Canvas Phase B plan, not modified here) is typed against
 * `WorkflowNodeType`, so this screen renders provider nodes on the canvas
 * using the existing generic `"action"` node type as a stand-in — a follow-up
 * can add a dedicated `ProviderNode` component (see the plan's "Explicitly
 * out of scope" section). These two functions are the only place the
 * "action" (canvas) <-> "provider" (backend) translation happens.
 */
function toFlowGraph(graph: RoutingGraph, providerLabel: string): FlowGraph {
  return {
    nodes: graph.nodes.map((n) => ({
      id: n.id,
      type: "action",
      data: { provider_id: n.data.provider_id, order: n.data.order, label: providerLabel },
      position: n.position,
    })),
    edges: graph.edges.map((e) => ({ source: e.source, target: e.target })),
  };
}

function toRoutingGraph(graph: FlowGraph): RoutingGraph {
  const providerNodes = graph.nodes.filter((n) => n.type === "action");
  return {
    nodes: providerNodes.map((n, index) => ({
      id: n.id,
      type: "provider",
      data: {
        provider_id: typeof n.data.provider_id === "string" ? n.data.provider_id : "",
        order: typeof n.data.order === "number" ? n.data.order : index,
      },
      position: n.position,
    })),
    edges: graph.edges.map((e) => ({ source: e.source, target: e.target, kind: "fallback" })),
  };
}

function statusLabel(t: ReturnType<typeof useTranslations>, status: RoutingGraphStatus): string {
  if (status === "ACTIVE") return t("routingStatusActive");
  if (status === "ARCHIVED") return t("routingStatusArchived");
  return t("routingStatusDraft");
}

/** Minimal inline editor for the selected provider node's fields. Intentionally
 * plain text/number inputs, not a provider search/select control — see the
 * plan's "Explicitly out of scope" section (ProviderCatalogPicker deferred). */
function ProviderNodeInspector({
  node,
  onChange,
  onClose,
  t,
}: {
  node: FlowNode | null;
  onChange: (nodeId: string, data: Record<string, unknown>) => void;
  onClose: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  if (!node) return null;
  const setField = (key: string, value: unknown) => onChange(node.id, { ...node.data, [key]: value });
  return (
    <aside
      className="w-72 shrink-0 space-y-3 rounded-2xl border border-[var(--border-subtle)] bg-white/90 p-4 shadow-sm"
      data-testid="routing-node-inspector"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t("routingProviderNode")}</h3>
        <button
          type="button"
          onClick={onClose}
          aria-label={t("routingCancel")}
          className="text-xs text-[var(--text-muted)]"
        >
          ×
        </button>
      </div>
      <Input
        label="Provider ID"
        value={String(node.data.provider_id ?? "")}
        onChange={(e) => setField("provider_id", e.target.value)}
        data-testid="inspector-provider-id"
      />
      <Input
        label="Order"
        type="number"
        min={0}
        value={String(node.data.order ?? 0)}
        onChange={(e) => setField("order", Number(e.target.value))}
        data-testid="inspector-provider-order"
      />
    </aside>
  );
}

export function RoutingCanvasScreen() {
  const t = useTranslations("aiSettings");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const toast = useToast();
  const getMessage = useApiErrorMessage();
  const queryClient = useQueryClient();

  const [taskFamily, setTaskFamily] = useState<AiModelFamily>("chat");
  const [graph, setGraph] = useState<FlowGraph>(EMPTY_FLOW_GRAPH);
  const [graphId, setGraphId] = useState<string | null>(null);
  const [graphStatus, setGraphStatus] = useState<RoutingGraphStatus>("DRAFT");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [activateOpen, setActivateOpen] = useState(false);

  const providerLabel = t("routingProviderNode");

  const graphsQuery = useQuery({
    queryKey: ["admin", "ai-routing-graphs", taskFamily],
    queryFn: () => aiRoutingApi.list(taskFamily),
    retry: false,
  });

  const canvasQuery = useQuery({
    queryKey: ["admin", "ai-routing-canvas", taskFamily],
    queryFn: () => aiRoutingApi.canvasView(taskFamily),
    retry: false,
  });

  // Load the most recently created graph for this task family into the
  // canvas whenever the family changes or the list refetches with a new
  // latest graph id.
  useEffect(() => {
    const latest: AiRoutingGraphRecord | undefined = graphsQuery.data?.[0];
    if (latest) {
      setGraphId(latest.id);
      setGraphStatus(latest.status);
      setGraph(toFlowGraph(latest.graph, providerLabel));
    } else if (graphsQuery.data && graphsQuery.data.length === 0) {
      setGraphId(null);
      setGraphStatus("DRAFT");
      setGraph(EMPTY_FLOW_GRAPH);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphsQuery.data]);

  const defs: NodeTypeDef[] = useMemo(
    () => [{ type: "action", label: providerLabel, defaultData: { provider_id: "", order: 0 } }],
    [providerLabel],
  );

  function handleError(e: unknown) {
    if (e instanceof ApiError && e.isConflict) {
      toast.show({ tone: "error", title: t("conflictTitle"), description: t("conflictBody") });
      void graphsQuery.refetch();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const save = useMutation({
    mutationFn: async () => {
      const body = toRoutingGraph(graph);
      if (!graphId) {
        return aiRoutingApi.create(taskFamily, body);
      }
      return aiRoutingApi.update(graphId, body);
    },
    onSuccess: (saved) => {
      setGraphId(saved.id);
      setGraphStatus(saved.status);
      queryClient.setQueryData(["admin", "ai-routing-graphs", taskFamily], (prev: AiRoutingGraphRecord[] | undefined) => {
        const others = (prev ?? []).filter((g) => g.id !== saved.id);
        return [saved, ...others];
      });
      toast.show({ tone: "success", title: t("routingSaved") });
    },
    onError: handleError,
  });

  const activate = useMutation({
    mutationFn: () => aiRoutingApi.activate(graphId as string),
    onSuccess: (activated) => {
      setGraphStatus(activated.status);
      setActivateOpen(false);
      queryClient.invalidateQueries({ queryKey: ["admin", "ai-routing-canvas", taskFamily] });
      queryClient.invalidateQueries({ queryKey: ["admin", "ai-routing-graphs", taskFamily] });
      toast.show({ tone: "success", title: t("routingActivated") });
    },
    onError: (e) => {
      setActivateOpen(false);
      handleError(e);
    },
  });

  const hasProviderNode = graph.nodes.some((n) => n.type === "action");
  const selectedNode = graph.nodes.find((n) => n.id === selectedNodeId) ?? null;

  /* ---- Permission / auth states for the live health panel ---- */
  if (canvasQuery.isError && canvasQuery.error instanceof ApiError) {
    const err = canvasQuery.error;
    if (err.isPermissionError || err.isAuthError) {
      const isAuth = err.isAuthError;
      return (
        <>
          <PageHeader title={t("routingCanvasTitle")} description={t("routingCanvasSubtitle")} />
          <EmptyState
            kind={isAuth ? "auth" : "permission"}
            icon={isAuth ? SignIn : ShieldWarning}
            title={isAuth ? tStates("authTitle") : tStates("permissionTitle")}
            description={isAuth ? tStates("authBody") : t("routingPermissionBody")}
          />
        </>
      );
    }
  }

  if (canvasQuery.isError) {
    return (
      <>
        <PageHeader title={t("routingCanvasTitle")} description={t("routingCanvasSubtitle")} />
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("routingLoadErrorTitle")}
          description={t("routingLoadErrorBody")}
          action={
            <Button variant="secondary" onClick={() => canvasQuery.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={t("routingCanvasTitle")}
        description={t("routingCanvasSubtitle")}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="w-40">
              <Select
                aria-label={t("routingTaskFamilyLabel")}
                value={taskFamily}
                onChange={(e) => {
                  setSelectedNodeId(null);
                  setTaskFamily(e.target.value as AiModelFamily);
                }}
                options={AI_MODEL_FAMILIES.map((f) => ({ value: f, label: t(`family.${f}`) }))}
              />
            </div>
            {graphId && <StatusBadge tone={STATUS_TONE[graphStatus]}>{statusLabel(t, graphStatus)}</StatusBadge>}
            <Button
              variant="secondary"
              loading={save.isPending}
              disabled={!hasProviderNode}
              onClick={() => save.mutate()}
            >
              {t("routingSave")}
            </Button>
            <Button
              variant="primary"
              disabled={!graphId || graphStatus === "ACTIVE"}
              loading={activate.isPending}
              onClick={() => setActivateOpen(true)}
            >
              {t("routingActivate")}
            </Button>
          </div>
        }
      />

      {!hasProviderNode && (
        <div className="mb-4 rounded-xl border border-[var(--border-subtle)] bg-white/80 px-4 py-3 text-sm text-[var(--text-secondary)]">
          <p className="font-semibold text-[var(--text-primary)]">{t("routingNoProviderTitle")}</p>
          <p>{t("routingNoProviderBody")}</p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[auto_1fr_260px]">
        <NodePalette defs={defs} title={t("routingPaletteTitle")} />

        <FlowCanvas
          graph={graph}
          nodeTypeDefs={defs}
          onNodeClick={setSelectedNodeId}
          onGraphChange={setGraph}
        />

        <aside
          className="space-y-2 rounded-2xl border border-[var(--border-subtle)] bg-white/90 p-4"
          data-testid="circuit-panel"
        >
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("routingHealthTitle")}
          </h3>
          {canvasQuery.isLoading ? (
            <div className="space-y-2" aria-busy="true">
              {[0, 1].map((i) => (
                <div key={i} className="h-8 animate-pulse rounded-lg bg-[var(--bg-subtle)]" />
              ))}
            </div>
          ) : (canvasQuery.data?.providers.length ?? 0) === 0 ? (
            <p className="text-xs text-[var(--text-muted)]">{t("routingHealthEmpty")}</p>
          ) : (
            (canvasQuery.data?.providers ?? []).map((p) => (
              <div key={p.provider_id} className="flex items-center justify-between gap-2 text-sm">
                <span className="min-w-0 truncate">{p.provider_internal ?? p.vendor_label}</span>
                <span
                  className={
                    p.circuit_state === "open"
                      ? "inline-flex shrink-0 items-center gap-1 text-rose-600"
                      : "inline-flex shrink-0 items-center gap-1 text-emerald-600"
                  }
                >
                  {p.circuit_state === "open" ? (
                    <WarningCircle aria-hidden weight="bold" className="size-3.5" />
                  ) : (
                    <CheckCircle aria-hidden weight="bold" className="size-3.5" />
                  )}
                  {p.circuit_state === "open" ? t("routingCircuitOpen") : t("routingCircuitClosed")}
                </span>
              </div>
            ))
          )}
          <p className="pt-2 text-[11px] text-[var(--text-muted)]">{t("routingPermissionBody")}</p>
        </aside>
      </div>

      <ProviderNodeInspector
        node={selectedNode}
        t={t}
        onClose={() => setSelectedNodeId(null)}
        onChange={(nodeId, data) => {
          setGraph((prev) => ({
            ...prev,
            nodes: prev.nodes.map((n) => (n.id === nodeId ? { ...n, data } : n)),
          }));
        }}
      />

      <Modal
        open={activateOpen}
        onClose={() => setActivateOpen(false)}
        title={t("routingActivateConfirmTitle")}
        description={t("routingActivateConfirmBody")}
        size="sm"
        closeLabel={t("routingCancel")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setActivateOpen(false)}>
              {t("routingCancel")}
            </Button>
            <Button variant="primary" loading={activate.isPending} onClick={() => activate.mutate()}>
              {t("routingActivateConfirmAction")}
            </Button>
          </>
        }
      >
        <></>
      </Modal>
    </>
  );
}
