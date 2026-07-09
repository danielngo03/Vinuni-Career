"use client";

import { Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { Input, Select, Textarea } from "@/components/ui";
import { DetailSheet, DetailSheetSection } from "@/components/kit";
import { ADVISORY_NODE_TYPES } from "@/lib/api";
import type { FlowNode, WorkflowNodeType } from "@/lib/api/workflows";
import { nodeSoft, nodeVisual } from "./node-visuals";

/** Node types that expose editable configuration in the inspector. */
const CONFIGURABLE_NODE_TYPES: ReadonlySet<WorkflowNodeType> = new Set([
  "condition",
  "human_review",
  "action",
  "wait",
  "assign_owner",
  "send_notification",
  "create_task",
  "move_candidate",
  "request_approval",
  "ai_suggestion",
  "webhook",
]);

export interface NodeInspectorProps {
  node: FlowNode | null;
  onChange: (nodeId: string, data: Record<string, unknown>) => void;
  onClose: () => void;
  /** When the flow is not DRAFT the canvas + inspector are read-only. */
  readOnly?: boolean;
}

/**
 * Node inspector (v10) — the right-edge {@link DetailSheet} that opens when a
 * node is selected on the canvas. Per-node configuration lives in sectioned
 * form controls; consequential/AI nodes surface their advisory notice. Every
 * edit flows through `onChange` (unchanged), keeping the canvas the single
 * source of truth. Read-only flows render the fields disabled.
 */
export function NodeInspector({ node, onChange, onClose, readOnly = false }: NodeInspectorProps) {
  const t = useTranslations("workflowBuilder");
  const visual = node ? nodeVisual(node.type) : null;
  const Icon = visual?.icon;

  return (
    <DetailSheet
      open={node !== null}
      onClose={onClose}
      title={node ? String(node.data.label ?? node.type) : ""}
      subtitle={node?.type}
      closeLabel={t("cancel")}
      avatar={
        Icon && visual ? (
          <span
            aria-hidden
            className="flex size-9 items-center justify-center rounded-lg"
            style={{ background: nodeSoft(visual.accent), color: visual.accent }}
          >
            <Icon className="size-5" strokeWidth={1.9} />
          </span>
        ) : undefined
      }
    >
      {node && <InspectorFields node={node} onChange={onChange} readOnly={readOnly} t={t} />}
    </DetailSheet>
  );
}

function InspectorFields({
  node,
  onChange,
  readOnly,
  t,
}: {
  node: FlowNode;
  onChange: (nodeId: string, data: Record<string, unknown>) => void;
  readOnly: boolean;
  t: ReturnType<typeof useTranslations>;
}) {
  const setField = (key: string, value: unknown) => onChange(node.id, { ...node.data, [key]: value });
  const hasConfig = CONFIGURABLE_NODE_TYPES.has(node.type);

  return (
    <>
      {ADVISORY_NODE_TYPES.has(node.type) && (
        <div
          className="flex items-start gap-2.5 px-5 py-4"
          style={{ background: "var(--content-ai-soft)" }}
          data-testid="inspector-advisory-note"
        >
          <Sparkles
            aria-hidden
            className="mt-0.5 size-4 shrink-0"
            strokeWidth={2}
            style={{ color: "var(--content-ai)" }}
          />
          <p className="type-small font-medium" style={{ color: "var(--content-ai)" }}>
            {t("advisoryNote")}
          </p>
        </div>
      )}

      {hasConfig && (
      <DetailSheetSection className="space-y-3">
        {node.type === "condition" && (
          <Textarea
            label="Expression"
            rows={3}
            value={String(node.data.expression ?? "")}
            onChange={(e) => setField("expression", e.target.value)}
            placeholder="{{fraud_score}} > 0.70"
            disabled={readOnly}
            data-testid="inspector-condition-expression"
          />
        )}

        {node.type === "human_review" && (
          <>
            <Select
              label={t("paletteTitle")}
              value={String(node.data.assignee_mode ?? "queue")}
              onChange={(e) => setField("assignee_mode", e.target.value)}
              disabled={readOnly}
              data-testid="inspector-assignee-mode"
              options={[
                { value: "person", label: t("assigneeModePerson") },
                { value: "queue", label: t("assigneeModeQueue") },
              ]}
            />
            {node.data.assignee_mode === "person" ? (
              <Input
                label="Assignee user ID"
                value={String(node.data.assignee_user_id ?? "")}
                onChange={(e) => setField("assignee_user_id", e.target.value)}
                disabled={readOnly}
                data-testid="inspector-assignee-user-id"
              />
            ) : (
              <Input
                label="Department ID"
                value={String(node.data.assignee_department_id ?? "")}
                onChange={(e) => setField("assignee_department_id", e.target.value)}
                disabled={readOnly}
                data-testid="inspector-assignee-department-id"
              />
            )}
            <Input
              label="SLA (hours)"
              type="number"
              value={String(node.data.sla_hours ?? 24)}
              onChange={(e) => setField("sla_hours", Number(e.target.value))}
              disabled={readOnly}
              data-testid="inspector-sla-hours"
            />
          </>
        )}

        {node.type === "action" && (
          <Input
            label="Action"
            value={String(node.data.action ?? "")}
            onChange={(e) => setField("action", e.target.value)}
            placeholder="auto_approve"
            disabled={readOnly}
            data-testid="inspector-action"
          />
        )}

        {node.type === "wait" && (
          <Input
            label={t("waitHoursLabel")}
            type="number"
            value={String(node.data.hours ?? 24)}
            onChange={(e) => setField("hours", Number(e.target.value))}
            disabled={readOnly}
            data-testid="inspector-wait-hours"
          />
        )}

        {node.type === "assign_owner" && (
          <Input
            label={t("assignOwnerLabel")}
            value={String(node.data.owner_user_id ?? "")}
            onChange={(e) => setField("owner_user_id", e.target.value)}
            placeholder={t("assignOwnerPlaceholder")}
            disabled={readOnly}
            data-testid="inspector-assign-owner"
          />
        )}

        {node.type === "send_notification" && (
          <>
            <Input
              label={t("templateKeyLabel")}
              value={String(node.data.template_key ?? "")}
              onChange={(e) => setField("template_key", e.target.value)}
              placeholder="application_status_changed"
              disabled={readOnly}
              data-testid="inspector-template-key"
            />
            <Select
              label={t("channelLabel")}
              value={String(node.data.channel ?? "email")}
              onChange={(e) => setField("channel", e.target.value)}
              disabled={readOnly}
              data-testid="inspector-channel"
              options={[
                { value: "email", label: t("channelEmail") },
                { value: "in_app", label: t("channelInApp") },
              ]}
            />
          </>
        )}

        {node.type === "create_task" && (
          <Textarea
            label={t("taskDescriptionLabel")}
            rows={3}
            value={String(node.data.description ?? "")}
            onChange={(e) => setField("description", e.target.value)}
            disabled={readOnly}
            data-testid="inspector-task-description"
          />
        )}

        {node.type === "move_candidate" && (
          <Input
            label={t("targetStageLabel")}
            value={String(node.data.target_stage ?? "")}
            onChange={(e) => setField("target_stage", e.target.value)}
            placeholder="interview"
            disabled={readOnly}
            data-testid="inspector-target-stage"
          />
        )}

        {node.type === "request_approval" && (
          <Input
            label={t("approverDepartmentLabel")}
            value={String(node.data.approver_department_id ?? "")}
            onChange={(e) => setField("approver_department_id", e.target.value)}
            disabled={readOnly}
            data-testid="inspector-approver-department"
          />
        )}

        {node.type === "ai_suggestion" && (
          <Input
            label={t("aiSuggestionPromptLabel")}
            value={String(node.data.prompt_key ?? "")}
            onChange={(e) => setField("prompt_key", e.target.value)}
            placeholder="screen_candidate_fit"
            disabled={readOnly}
            data-testid="inspector-ai-prompt-key"
          />
        )}

        {node.type === "webhook" && (
          <Input
            label={t("webhookUrlLabel")}
            value={String(node.data.url ?? "")}
            onChange={(e) => setField("url", e.target.value)}
            placeholder="https://…"
            disabled={readOnly}
            data-testid="inspector-webhook-url"
          />
        )}
      </DetailSheetSection>
      )}
    </>
  );
}
