"use client";

import { useQuery } from "@tanstack/react-query";
import { ShieldAlert, Sparkles, UserCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { Input, Select, Textarea, type SelectOption } from "@/components/ui";
import { DetailSheet, DetailSheetSection } from "@/components/kit";
import {
  ADVISORY_NODE_TYPES,
  CONSEQUENTIAL_NODE_TYPES,
  HUMAN_CONFIRM_NODE_TYPES,
  organizationApi,
  templateAdminApi,
} from "@/lib/api";
import type { FlowNode, WorkflowNodeType } from "@/lib/api/workflows";
import { nodeSoft, nodeVisual } from "./node-visuals";

/** Node types that expose editable configuration in the inspector. */
const CONFIGURABLE_NODE_TYPES: ReadonlySet<WorkflowNodeType> = new Set([
  "trigger",
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
  "ai_screen_application",
  "auto_advance_on_gate",
  "notify",
  "jd_pdf_to_draft",
]);

/**
 * Leak-safe flow variables an automation node can reference (mirrors the backend
 * `_SAFE_VAR_KEYS`). Used to populate variable pickers so authors choose a real
 * variable name instead of typing raw keys/ids.
 */
const FLOW_VARIABLES = [
  "application_id",
  "job_id",
  "org_id",
  "screen_recommendation",
  "screen_score",
  "screen_band",
] as const;

export interface NodeInspectorProps {
  node: FlowNode | null;
  onChange: (nodeId: string, data: Record<string, unknown>) => void;
  onClose: () => void;
  /** When the flow is not DRAFT the canvas + inspector are read-only. */
  readOnly?: boolean;
  /** Start-event options for the trigger node (owner-type specific). */
  triggerOptions?: SelectOption[];
  /**
   * The flow's start event is fixed at creation (the update API does not accept a
   * new trigger). Locked for any already-saved flow; editable only for a new flow.
   */
  triggerLocked?: boolean;
}

/**
 * Node inspector (v10) — the right-edge {@link DetailSheet} that opens when a
 * node is selected on the canvas. Per-node configuration lives in sectioned
 * form controls; consequential/AI/human-confirm nodes surface their notice so an
 * author understands what happens on activation. Every edit flows through
 * `onChange`, keeping the canvas the single source of truth. Read-only flows
 * render the fields disabled.
 */
export function NodeInspector({
  node,
  onChange,
  onClose,
  readOnly = false,
  triggerOptions = [],
  triggerLocked = false,
}: NodeInspectorProps) {
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
      {node && (
        <InspectorFields
          node={node}
          onChange={onChange}
          readOnly={readOnly}
          triggerOptions={triggerOptions}
          triggerLocked={triggerLocked}
          t={t}
        />
      )}
    </DetailSheet>
  );
}

/** A coloured advisory/consequential/human-confirm banner at the top of the sheet. */
function NoticeBanner({
  icon: Icon,
  bg,
  color,
  children,
  testId,
}: {
  icon: typeof Sparkles;
  bg: string;
  color: string;
  children: React.ReactNode;
  testId: string;
}) {
  return (
    <div
      className="flex items-start gap-2.5 px-5 py-4"
      style={{ background: bg }}
      data-testid={testId}
    >
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" strokeWidth={2} style={{ color }} />
      <p className="type-small font-medium" style={{ color }}>
        {children}
      </p>
    </div>
  );
}

function InspectorFields({
  node,
  onChange,
  readOnly,
  triggerOptions,
  triggerLocked,
  t,
}: {
  node: FlowNode;
  onChange: (nodeId: string, data: Record<string, unknown>) => void;
  readOnly: boolean;
  triggerOptions: SelectOption[];
  triggerLocked: boolean;
  t: ReturnType<typeof useTranslations>;
}) {
  const setField = (key: string, value: unknown) => onChange(node.id, { ...node.data, [key]: value });
  const hasConfig = CONFIGURABLE_NODE_TYPES.has(node.type);
  const isLlmScreen = node.type === "ai_screen_application" && node.data.mode === "llm";

  return (
    <>
      {ADVISORY_NODE_TYPES.has(node.type) && (
        <NoticeBanner
          icon={Sparkles}
          bg="var(--content-ai-soft)"
          color="var(--content-ai)"
          testId="inspector-advisory-note"
        >
          {t("advisoryNote")}
        </NoticeBanner>
      )}

      {HUMAN_CONFIRM_NODE_TYPES.has(node.type) && (
        <NoticeBanner
          icon={UserCheck}
          bg="var(--viz-orange-soft)"
          color="var(--viz-orange)"
          testId="inspector-human-confirm-note"
        >
          {t("humanConfirmNote")}
        </NoticeBanner>
      )}

      {CONSEQUENTIAL_NODE_TYPES.has(node.type) && (
        <NoticeBanner
          icon={ShieldAlert}
          bg="var(--content-warning-soft)"
          color="var(--content-warning)"
          testId="inspector-consequential-note"
        >
          {isLlmScreen ? `${t("consequentialNote")} ${t("aiCreditNote")}` : t("consequentialNote")}
        </NoticeBanner>
      )}

      {hasConfig && (
        <DetailSheetSection className="space-y-3">
          {node.type === "trigger" && (
            <Select
              label={t("triggerTypeLabel")}
              value={String(node.data.trigger_type ?? "system.student_registered")}
              onChange={(e) => setField("trigger_type", e.target.value)}
              disabled={readOnly || triggerLocked}
              help={triggerLocked ? t("triggerLockedHelp") : t("triggerTypeHelp")}
              data-testid="inspector-trigger-type"
              // Always keep the flow's current trigger selectable, even if it is a
              // legacy value outside this owner type's curated option list.
              options={
                triggerOptions.some((o) => o.value === node.data.trigger_type)
                  ? triggerOptions
                  : [
                      ...triggerOptions,
                      {
                        value: String(node.data.trigger_type ?? "system.student_registered"),
                        label: String(node.data.trigger_type ?? "system.student_registered"),
                      },
                    ]
              }
            />
          )}

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

          {node.type === "ai_screen_application" && (
            <AiScreenConfig node={node} setField={setField} readOnly={readOnly} t={t} />
          )}

          {node.type === "auto_advance_on_gate" && (
            <p className="type-small text-muted-foreground" data-testid="inspector-auto-advance-help">
              {t("autoAdvanceHelp")}
            </p>
          )}

          {node.type === "notify" && (
            <NotifyConfig node={node} setField={setField} readOnly={readOnly} t={t} />
          )}

          {node.type === "jd_pdf_to_draft" && (
            <p className="type-small text-muted-foreground" data-testid="inspector-jd-pdf-help">
              {t("jdPdfHelp")}
            </p>
          )}
        </DetailSheetSection>
      )}
    </>
  );
}

type SetField = (key: string, value: unknown) => void;
type T = ReturnType<typeof useTranslations>;

/**
 * `ai_screen_application` config: deterministic (free) vs LLM (metered) mode plus
 * ordered strong/consider thresholds, and an optional variable override for which
 * flow variable carries the application id. Branches: strong · consider · weak ·
 * not_computable.
 */
function AiScreenConfig({
  node,
  setField,
  readOnly,
  t,
}: {
  node: FlowNode;
  setField: SetField;
  readOnly: boolean;
  t: T;
}) {
  const mode = String(node.data.mode ?? "deterministic");
  return (
    <>
      <Select
        label={t("screenModeLabel")}
        value={mode}
        onChange={(e) => setField("mode", e.target.value)}
        disabled={readOnly}
        help={mode === "llm" ? t("screenModeLlmHelp") : t("screenModeDeterministicHelp")}
        data-testid="inspector-screen-mode"
        options={[
          { value: "deterministic", label: t("screenModeDeterministic") },
          { value: "llm", label: t("screenModeLlm") },
        ]}
      />
      <Input
        label={t("strongThresholdLabel")}
        type="number"
        min={0}
        max={100}
        value={String(node.data.strong_threshold ?? 80)}
        onChange={(e) => setField("strong_threshold", Number(e.target.value))}
        disabled={readOnly}
        data-testid="inspector-strong-threshold"
      />
      <Input
        label={t("considerThresholdLabel")}
        type="number"
        min={0}
        max={100}
        value={String(node.data.consider_threshold ?? 50)}
        onChange={(e) => setField("consider_threshold", Number(e.target.value))}
        disabled={readOnly}
        help={t("thresholdOrderHelp")}
        data-testid="inspector-consider-threshold"
      />
      <Select
        label={t("applicationVariableLabel")}
        value={String(node.data.application_id_variable ?? "")}
        onChange={(e) => setField("application_id_variable", e.target.value || undefined)}
        disabled={readOnly}
        help={t("applicationVariableHelp")}
        data-testid="inspector-application-variable"
        options={[
          { value: "", label: t("applicationVariableDefault") },
          ...FLOW_VARIABLES.map((v) => ({ value: v, label: v })),
        ]}
      />
    </>
  );
}

/**
 * `notify` config: an active notification template + a recipient resolution mode.
 * `assignee` needs no extra field; `user` picks a real org member (never a raw
 * UUID); `trigger_var` picks a flow variable that resolves to a user. Template
 * keys and members come from real APIs so the author never types opaque ids.
 */
function NotifyConfig({
  node,
  setField,
  readOnly,
  t,
}: {
  node: FlowNode;
  setField: SetField;
  readOnly: boolean;
  t: T;
}) {
  const recipientMode = String(node.data.recipient_mode ?? "assignee");
  const templateKey = String(node.data.template_key ?? "");

  const templatesQuery = useQuery({
    queryKey: ["workflow", "notify-templates"],
    queryFn: () => templateAdminApi.list({ status: "active" }),
    staleTime: 60_000,
    retry: false,
  });

  const membersQuery = useQuery({
    queryKey: ["workflow", "notify-members"],
    queryFn: () => organizationApi.listMembers(),
    enabled: recipientMode === "user",
    staleTime: 60_000,
    retry: false,
  });

  // Unique active template keys, keeping the current value selectable even if the
  // list has not loaded or no longer contains it.
  const templateKeyOptions: SelectOption[] = (() => {
    const keys = new Set<string>();
    for (const tpl of templatesQuery.data ?? []) keys.add(tpl.key);
    if (templateKey) keys.add(templateKey);
    return [...keys].sort().map((k) => ({ value: k, label: k }));
  })();

  const memberOptions: SelectOption[] = (membersQuery.data?.data ?? [])
    .filter((m) => m.user_id && m.status === "active")
    .map((m) => ({ value: m.user_id as string, label: m.full_name || m.user_email }));

  return (
    <>
      {templateKeyOptions.length > 0 ? (
        <Select
          label={t("templateKeyLabel")}
          value={templateKey}
          onChange={(e) => setField("template_key", e.target.value)}
          disabled={readOnly}
          help={t("notifyTemplateHelp")}
          data-testid="inspector-notify-template"
          options={[{ value: "", label: t("notifyTemplatePlaceholder") }, ...templateKeyOptions]}
        />
      ) : (
        <Input
          label={t("templateKeyLabel")}
          value={templateKey}
          onChange={(e) => setField("template_key", e.target.value)}
          placeholder="application_status_changed"
          disabled={readOnly}
          help={templatesQuery.isLoading ? undefined : t("notifyNoTemplatesHelp")}
          data-testid="inspector-notify-template-input"
        />
      )}

      <Select
        label={t("recipientModeLabel")}
        value={recipientMode}
        onChange={(e) => setField("recipient_mode", e.target.value)}
        disabled={readOnly}
        data-testid="inspector-recipient-mode"
        options={[
          { value: "assignee", label: t("recipientModeAssignee") },
          { value: "user", label: t("recipientModeUser") },
          { value: "trigger_var", label: t("recipientModeTriggerVar") },
        ]}
      />

      {recipientMode === "assignee" && (
        <p className="type-caption text-muted-foreground" data-testid="inspector-recipient-assignee-help">
          {t("recipientAssigneeHelp")}
        </p>
      )}

      {recipientMode === "user" && (
        <Select
          label={t("recipientUserLabel")}
          value={String(node.data.recipient_user_id ?? "")}
          onChange={(e) => setField("recipient_user_id", e.target.value)}
          disabled={readOnly}
          help={membersQuery.isError ? t("recipientUserErrorHelp") : undefined}
          data-testid="inspector-recipient-user"
          options={[
            { value: "", label: t("recipientUserPlaceholder") },
            ...memberOptions,
          ]}
        />
      )}

      {recipientMode === "trigger_var" && (
        <Select
          label={t("recipientVariableLabel")}
          value={String(node.data.recipient_variable ?? "")}
          onChange={(e) => setField("recipient_variable", e.target.value)}
          disabled={readOnly}
          help={t("recipientVariableHelp")}
          data-testid="inspector-recipient-variable"
          options={[
            { value: "", label: t("recipientVariablePlaceholder") },
            ...FLOW_VARIABLES.map((v) => ({ value: v, label: v })),
          ]}
        />
      )}

      <Select
        label={t("channelLabel")}
        value={String(node.data.channel ?? "email")}
        onChange={(e) => setField("channel", e.target.value)}
        disabled={readOnly}
        data-testid="inspector-notify-channel"
        options={[
          { value: "email", label: t("channelEmail") },
          { value: "in_app", label: t("channelInApp") },
        ]}
      />

      <Select
        label={t("localeLabel")}
        value={String(node.data.locale ?? "vi")}
        onChange={(e) => setField("locale", e.target.value)}
        disabled={readOnly}
        data-testid="inspector-notify-locale"
        options={[
          { value: "vi", label: t("localeVi") },
          { value: "en", label: t("localeEn") },
        ]}
      />
    </>
  );
}
