import type { ElementType } from "react";
import {
  ArrowRightLeft,
  Bell,
  BellRing,
  ChevronsRight,
  Clock,
  Cog,
  FilePlus2,
  Flag,
  GitBranch,
  ListTodo,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Timer,
  UserCheck,
  UserPlus,
  Webhook,
  Zap,
} from "lucide-react";
import type { ChipTone } from "@/components/kit";
import type { WorkflowNodeType } from "@/lib/api/workflows";

/**
 * Shared v10 visual language for workflow nodes — the single source of truth
 * consumed by both the React-Flow custom node (`node-types.tsx`) and the
 * draggable palette (`node-palette.tsx`). The SHELL stays monochrome; each node
 * card is a mono card with a category-coded CONTENT accent (left bar + icon
 * chip). Categories follow docs/DESIGN.md §1.1.2 data-viz semantics:
 *   trigger → indigo · logic/wait → amber · action/notify/task → teal ·
 *   ai → content-ai · human/approval → orange · end → neutral.
 *   (No purple/violet in the builder UI — owner 2026-07-10.)
 */
export interface NodeVisual {
  icon: ElementType;
  /** CSS colour for the left accent bar + icon glyph. */
  accent: string;
  /** Matching StatusChip tone for category chips. */
  tone: ChipTone;
}

export const NODE_VISUALS: Record<WorkflowNodeType, NodeVisual> = {
  trigger: { icon: Zap, accent: "var(--viz-indigo)", tone: "indigo" },
  condition: { icon: GitBranch, accent: "var(--viz-amber)", tone: "amber" },
  wait: { icon: Clock, accent: "var(--viz-amber)", tone: "amber" },
  delay: { icon: Timer, accent: "var(--viz-amber)", tone: "amber" },
  action: { icon: Cog, accent: "var(--viz-teal)", tone: "teal" },
  send_notification: { icon: Bell, accent: "var(--viz-teal)", tone: "teal" },
  create_task: { icon: ListTodo, accent: "var(--viz-teal)", tone: "teal" },
  assign_owner: { icon: UserPlus, accent: "var(--viz-teal)", tone: "teal" },
  move_candidate: { icon: ArrowRightLeft, accent: "var(--viz-teal)", tone: "teal" },
  webhook: { icon: Webhook, accent: "var(--viz-teal)", tone: "teal" },
  ai_suggestion: { icon: Sparkles, accent: "var(--content-ai)", tone: "ai" },
  human_review: { icon: UserCheck, accent: "var(--viz-orange)", tone: "orange" },
  request_approval: { icon: ShieldCheck, accent: "var(--viz-orange)", tone: "orange" },
  end: { icon: Flag, accent: "var(--border-strong)", tone: "neutral" },
  // Recruiting-automation nodes (Wave 2B). AI screening reads as AI; auto-advance
  // + notify read as pipeline/notification actions (teal); JD→draft reads as a
  // human-review step (orange) because it always pauses for confirm-create.
  ai_screen_application: { icon: ScanSearch, accent: "var(--content-ai)", tone: "ai" },
  auto_advance_on_gate: { icon: ChevronsRight, accent: "var(--viz-teal)", tone: "teal" },
  notify: { icon: BellRing, accent: "var(--viz-teal)", tone: "teal" },
  jd_pdf_to_draft: { icon: FilePlus2, accent: "var(--viz-orange)", tone: "orange" },
};

/** Resolve a node's visual, falling back to the generic action look. */
export function nodeVisual(type: WorkflowNodeType): NodeVisual {
  return NODE_VISUALS[type] ?? NODE_VISUALS.action;
}

/** Soft tint derived from any accent colour (works for every token incl. neutral). */
export function nodeSoft(accent: string): string {
  return `color-mix(in srgb, ${accent} 16%, transparent)`;
}
