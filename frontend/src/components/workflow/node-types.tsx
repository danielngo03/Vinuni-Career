"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Sparkle } from "@phosphor-icons/react";
import type { WorkflowNodeType } from "@/lib/api/workflows";
import { ADVISORY_NODE_TYPES } from "@/lib/api/workflows";

const NODE_STYLES: Record<WorkflowNodeType, { bg: string; border: string }> = {
  trigger: { bg: "bg-emerald-50", border: "border-emerald-400" },
  condition: { bg: "bg-amber-50", border: "border-amber-400" },
  human_review: { bg: "bg-sky-50", border: "border-sky-400" },
  action: { bg: "bg-violet-50", border: "border-violet-400" },
  delay: { bg: "bg-slate-50", border: "border-slate-400" },
  wait: { bg: "bg-slate-50", border: "border-slate-400" },
  end: { bg: "bg-rose-50", border: "border-rose-400" },
  assign_owner: { bg: "bg-violet-50", border: "border-violet-400" },
  send_notification: { bg: "bg-blue-50", border: "border-blue-400" },
  create_task: { bg: "bg-violet-50", border: "border-violet-400" },
  move_candidate: { bg: "bg-violet-50", border: "border-violet-400" },
  request_approval: { bg: "bg-sky-50", border: "border-sky-400" },
  ai_suggestion: { bg: "bg-teal-50", border: "border-teal-400" },
  webhook: { bg: "bg-slate-50", border: "border-slate-500" },
};

function GenericNode({ data, type }: NodeProps) {
  const nodeType = type as WorkflowNodeType;
  const style = NODE_STYLES[nodeType] ?? NODE_STYLES.action;
  const isAdvisory = ADVISORY_NODE_TYPES.has(nodeType);
  return (
    <div
      className={`rounded-xl border-2 px-4 py-2 text-sm font-medium shadow-sm ${style.border} ${style.bg} ${
        isAdvisory ? "border-dashed" : ""
      }`}
      data-node-advisory={isAdvisory ? "true" : undefined}
    >
      <Handle type="target" position={Position.Top} />
      <span className="flex items-center gap-1.5">
        {isAdvisory && (
          <Sparkle
            aria-hidden
            weight="fill"
            className="size-3.5 shrink-0 text-[var(--teal-600)]"
          />
        )}
        {String(data.label ?? type)}
      </span>
      <Handle type="source" position={Position.Bottom} />
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
];

export const REACT_FLOW_NODE_TYPES = Object.fromEntries(
  ALL_NODE_TYPES.map((type) => [type, GenericNode]),
);
