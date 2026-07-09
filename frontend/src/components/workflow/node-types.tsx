"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type { WorkflowNodeType } from "@/lib/api/workflows";
import { ADVISORY_NODE_TYPES } from "@/lib/api/workflows";
import { nodeSoft, nodeVisual } from "./node-visuals";

const HANDLE_STYLE = {
  width: 9,
  height: 9,
  background: "var(--border-strong)",
  border: "2px solid var(--surface-card)",
} as const;

function GenericNode({ data, type, selected }: NodeProps) {
  const nodeType = type as WorkflowNodeType;
  const { icon: Icon, accent } = nodeVisual(nodeType);
  const isAdvisory = ADVISORY_NODE_TYPES.has(nodeType);

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
      data-node-advisory={isAdvisory ? "true" : undefined}
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

      {isAdvisory && (
        <Sparkles
          aria-hidden
          className="size-3.5 shrink-0"
          strokeWidth={2}
          style={{ color: "var(--content-ai)" }}
        />
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
];

export const REACT_FLOW_NODE_TYPES = Object.fromEntries(
  ALL_NODE_TYPES.map((type) => [type, GenericNode]),
);
