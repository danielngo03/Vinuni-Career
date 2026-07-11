"use client";

import type { ElementType } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { ShieldAlert, Sparkles, UserCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import type { WorkflowNodeType } from "@/lib/api/workflows";
import {
  ADVISORY_NODE_TYPES,
  CONSEQUENTIAL_NODE_TYPES,
  HUMAN_CONFIRM_NODE_TYPES,
} from "@/lib/api/workflows";
import { nodeSoft, nodeVisual } from "./node-visuals";

/**
 * A small trailing badge that tells the author, at a glance, that a step is not
 * a plain automatic action. Three semantics, one badge slot:
 *  - advisory (AI): always pauses for a human before acting.
 *  - human-confirm: prepares a proposal and pauses for confirm-create (no publish).
 *  - consequential: runs autonomously ONLY after RBAC-gated activation.
 * `title`/`aria-label` come from the caller so the copy stays i18n-backed.
 */
type NodeBadge = { icon: ElementType; color: string } | null;

function nodeBadge(nodeType: WorkflowNodeType): NodeBadge {
  if (ADVISORY_NODE_TYPES.has(nodeType)) {
    return { icon: Sparkles, color: "var(--content-ai)" };
  }
  if (HUMAN_CONFIRM_NODE_TYPES.has(nodeType)) {
    return { icon: UserCheck, color: "var(--viz-orange)" };
  }
  if (CONSEQUENTIAL_NODE_TYPES.has(nodeType)) {
    return { icon: ShieldAlert, color: "var(--content-warning)" };
  }
  return null;
}

const HANDLE_STYLE = {
  width: 9,
  height: 9,
  background: "var(--border-strong)",
  border: "2px solid var(--surface-card)",
} as const;

function GenericNode({ data, type, selected }: NodeProps) {
  const t = useTranslations("workflowBuilder");
  const nodeType = type as WorkflowNodeType;
  const { icon: Icon, accent } = nodeVisual(nodeType);
  const badge = nodeBadge(nodeType);
  const badgeLabel = ADVISORY_NODE_TYPES.has(nodeType)
    ? t("badgeAdvisory")
    : HUMAN_CONFIRM_NODE_TYPES.has(nodeType)
      ? t("badgeHumanConfirm")
      : CONSEQUENTIAL_NODE_TYPES.has(nodeType)
        ? t("badgeConsequential")
        : "";

  return (
    <div
      className={cn(
        "flex min-w-[172px] items-center gap-2.5 rounded-lg border border-l-[3px] border-border bg-card px-3 py-2 transition-shadow",
        !selected && "hover:shadow-[var(--shadow-md)]",
      )}
      style={{
        // Category accent lives on the left border; a colored ring marks selection.
        borderLeftColor: accent,
        boxShadow: selected ? `0 0 0 2px ${accent}` : "var(--shadow-sm)",
      }}
      data-node-advisory={ADVISORY_NODE_TYPES.has(nodeType) ? "true" : undefined}
    >
      <Handle type="target" position={Position.Top} style={HANDLE_STYLE} />

      <span
        aria-hidden
        className="flex size-7 shrink-0 items-center justify-center rounded-md"
        style={{ background: nodeSoft(accent), color: accent }}
      >
        <Icon className="size-4" strokeWidth={1.9} />
      </span>

      <span className="type-small min-w-0 flex-1 truncate font-semibold text-foreground">
        {String(data.label ?? type)}
      </span>

      {badge && (
        <badge.icon
          role="img"
          aria-label={badgeLabel}
          className="size-3.5 shrink-0"
          strokeWidth={2}
          style={{ color: badge.color }}
        >
          <title>{badgeLabel}</title>
        </badge.icon>
      )}

      <Handle type="source" position={Position.Bottom} style={HANDLE_STYLE} />
    </div>
  );
}

const ALL_NODE_TYPES: WorkflowNodeType[] = [
  "trigger",
  "condition",
  "human_review",
  "action",
  "delay",
  "wait",
  "end",
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
];

export const REACT_FLOW_NODE_TYPES = Object.fromEntries(
  ALL_NODE_TYPES.map((type) => [type, GenericNode]),
);
