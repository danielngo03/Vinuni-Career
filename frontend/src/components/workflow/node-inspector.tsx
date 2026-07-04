"use client";

import { useTranslations } from "next-intl";
import { Input, Select } from "@/components/ui";
import { ADVISORY_NODE_TYPES } from "@/lib/api";
import type { FlowNode } from "@/lib/api/workflows";

export interface NodeInspectorProps {
  node: FlowNode | null;
  onChange: (nodeId: string, data: Record<string, unknown>) => void;
  onClose: () => void;
}

export function NodeInspector({ node, onChange, onClose }: NodeInspectorProps) {
  const t = useTranslations("workflowBuilder");
  if (!node) return null;

  const setField = (key: string, value: unknown) => onChange(node.id, { ...node.data, [key]: value });

  return (
    <aside
      className="w-72 shrink-0 space-y-3 rounded-2xl border border-[var(--border-subtle)] bg-white/90 p-4 shadow-sm"
      data-testid="node-inspector"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{String(node.data.label ?? node.type)}</h3>
        <button type="button" onClick={onClose} aria-label={t("cancel")} className="text-xs text-[var(--text-muted)]">
          ×
        </button>
      </div>

      {ADVISORY_NODE_TYPES.has(node.type) && (
        <p
          className="rounded-lg border border-dashed border-[var(--teal-500)]/50 bg-[var(--teal-50)] px-3 py-2 text-xs font-medium text-[var(--teal-700)]"
          data-testid="inspector-advisory-note"
        >
          {t("advisoryNote")}
        </p>
      )}

      {node.type === "condition" && (
        <Input
          label="Expression"
          value={String(node.data.expression ?? "")}
          onChange={(e) => setField("expression", e.target.value)}
          placeholder="{{fraud_score}} > 0.70"
          data-testid="inspector-condition-expression"
        />
      )}

      {node.type === "human_review" && (
        <>
          <Select
            label={t("paletteTitle")}
            value={String(node.data.assignee_mode ?? "queue")}
            onChange={(e) => setField("assignee_mode", e.target.value)}
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
              data-testid="inspector-assignee-user-id"
            />
          ) : (
            <Input
              label="Department ID"
              value={String(node.data.assignee_department_id ?? "")}
              onChange={(e) => setField("assignee_department_id", e.target.value)}
              data-testid="inspector-assignee-department-id"
            />
          )}
          <Input
            label="SLA (hours)"
            type="number"
            value={String(node.data.sla_hours ?? 24)}
            onChange={(e) => setField("sla_hours", Number(e.target.value))}
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
          data-testid="inspector-action"
        />
      )}

      {(node.type === "wait") && (
        <Input
          label={t("waitHoursLabel")}
          type="number"
          value={String(node.data.hours ?? 24)}
          onChange={(e) => setField("hours", Number(e.target.value))}
          data-testid="inspector-wait-hours"
        />
      )}

      {node.type === "assign_owner" && (
        <Input
          label={t("assignOwnerLabel")}
          value={String(node.data.owner_user_id ?? "")}
          onChange={(e) => setField("owner_user_id", e.target.value)}
          placeholder={t("assignOwnerPlaceholder")}
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
            data-testid="inspector-template-key"
          />
          <Select
            label={t("channelLabel")}
            value={String(node.data.channel ?? "email")}
            onChange={(e) => setField("channel", e.target.value)}
            data-testid="inspector-channel"
            options={[
              { value: "email", label: t("channelEmail") },
              { value: "in_app", label: t("channelInApp") },
            ]}
          />
        </>
      )}

      {node.type === "create_task" && (
        <Input
          label={t("taskDescriptionLabel")}
          value={String(node.data.description ?? "")}
          onChange={(e) => setField("description", e.target.value)}
          data-testid="inspector-task-description"
        />
      )}

      {node.type === "move_candidate" && (
        <Input
          label={t("targetStageLabel")}
          value={String(node.data.target_stage ?? "")}
          onChange={(e) => setField("target_stage", e.target.value)}
          placeholder="interview"
          data-testid="inspector-target-stage"
        />
      )}

      {node.type === "request_approval" && (
        <Input
          label={t("approverDepartmentLabel")}
          value={String(node.data.approver_department_id ?? "")}
          onChange={(e) => setField("approver_department_id", e.target.value)}
          data-testid="inspector-approver-department"
        />
      )}

      {node.type === "ai_suggestion" && (
        <Input
          label={t("aiSuggestionPromptLabel")}
          value={String(node.data.prompt_key ?? "")}
          onChange={(e) => setField("prompt_key", e.target.value)}
          placeholder="screen_candidate_fit"
          data-testid="inspector-ai-prompt-key"
        />
      )}

      {node.type === "webhook" && (
        <Input
          label={t("webhookUrlLabel")}
          value={String(node.data.url ?? "")}
          onChange={(e) => setField("url", e.target.value)}
          placeholder="https://…"
          data-testid="inspector-webhook-url"
        />
      )}
    </aside>
  );
}
