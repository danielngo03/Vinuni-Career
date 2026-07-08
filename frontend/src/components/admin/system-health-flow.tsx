"use client";

/**
 * Pipeline flow diagram for System Health.
 *
 * Renders a horizontal left→right SVG showing:
 *   Scheduler → Jobs → Queue (Celery/Redis) → Outbox → Delivered
 *
 * Each node is colored by health:
 *   teal  = healthy
 *   amber = backlog / pending
 *   red   = failed / down
 *   gray  = unknown / null
 *
 * Uses CSS custom properties (design tokens) only — no ad-hoc colors.
 * No chart library required; pure typed SVG + CSS.
 */

import { useTranslations } from "next-intl";
import type { SystemHealthJobs, SystemHealthQueues } from "@/lib/api/system-health";
import type { OutboxHealth } from "@/lib/api/system-health";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/* Types                                                                       */
/* -------------------------------------------------------------------------- */

type NodeHealth = "healthy" | "warn" | "error" | "unknown";

/* -------------------------------------------------------------------------- */
/* Health helpers                                                              */
/* -------------------------------------------------------------------------- */

function nodeColor(health: NodeHealth): {
  fill: string;
  border: string;
  dot: string;
  text: string;
} {
  switch (health) {
    case "healthy":
      return {
        fill: "var(--teal-50)",
        border: "var(--teal-500)",
        dot: "var(--teal-600)",
        text: "var(--teal-700)",
      };
    case "warn":
      return {
        fill: "var(--amber-50)",
        border: "var(--amber-500)",
        dot: "var(--amber-600)",
        text: "var(--amber-700)",
      };
    case "error":
      return {
        fill: "var(--red-50)",
        border: "var(--red-600)",
        dot: "var(--red-600)",
        text: "var(--red-600)",
      };
    default:
      return {
        fill: "var(--bg-muted)",
        border: "var(--border-strong)",
        dot: "var(--text-muted)",
        text: "var(--text-muted)",
      };
  }
}

/* -------------------------------------------------------------------------- */
/* Data derivation from API responses                                          */
/* -------------------------------------------------------------------------- */

function deriveSchedulerHealth(jobs: SystemHealthJobs | undefined): NodeHealth {
  if (!jobs) return "unknown";
  const list = jobs.jobs ?? [];
  if (list.length === 0) return "unknown";
  const hasError = list.some((j) => j.last_status === "error");
  if (hasError) return "error";
  const allNeverRun = list.every((j) => j.never_run);
  if (allNeverRun) return "unknown";
  return "healthy";
}

function deriveJobsHealth(jobs: SystemHealthJobs | undefined): NodeHealth {
  if (!jobs) return "unknown";
  const list = jobs.jobs ?? [];
  if (list.length === 0) return "unknown";
  const errCount = list.filter((j) => j.last_status === "error").length;
  if (errCount > 0) return "error";
  const neverCount = list.filter((j) => j.never_run).length;
  if (neverCount === list.length) return "unknown";
  return "healthy";
}

function deriveQueueHealth(queues: SystemHealthQueues | undefined): NodeHealth {
  if (!queues) return "unknown";
  if (queues.redis === "down") return "error";
  if (!queues.broker_configured) return "warn";
  const depth = queues.celery_default_queue_depth;
  if (depth !== null && depth > 50) return "warn";
  return "healthy";
}

function deriveOutboxHealth(outbox: OutboxHealth | undefined): NodeHealth {
  if (!outbox) return "unknown";
  if ((outbox.failed ?? 0) > 0 || (outbox.dead ?? 0) > 0) return "error";
  if ((outbox.pending ?? 0) > 0) return "warn";
  return "healthy";
}

function deriveDeliveredHealth(outbox: OutboxHealth | undefined): NodeHealth {
  if (!outbox) return "unknown";
  // "Delivered" is just the sent bucket — treat as healthy if it has items
  if ((outbox.sent ?? 0) > 0) return "healthy";
  return "unknown";
}

/* -------------------------------------------------------------------------- */
/* Props                                                                       */
/* -------------------------------------------------------------------------- */

interface SystemHealthFlowProps {
  jobs?: SystemHealthJobs;
  queues?: SystemHealthQueues;
  outbox?: OutboxHealth;
  isLoading?: boolean;
  className?: string;
}

/* -------------------------------------------------------------------------- */
/* SVG node component                                                          */
/* -------------------------------------------------------------------------- */

const NODE_W = 120;
const NODE_H = 76;
const NODE_RX = 10;
const GAP = 52; // gap between nodes (connector area)
const TOTAL_NODES = 5;
const SVG_W = TOTAL_NODES * NODE_W + (TOTAL_NODES - 1) * GAP;
const SVG_H = NODE_H + 8; // small vertical breathing room
const CY = SVG_H / 2; // vertical center

function nodeX(index: number): number {
  return index * (NODE_W + GAP);
}

interface SvgNodeProps {
  index: number;
  label: string;
  health: NodeHealth;
  metaLine1: string;
  metaLine2?: string;
  tooltip: string;
}

function SvgNode({ index, label, health, metaLine1, metaLine2, tooltip }: SvgNodeProps) {
  const x = nodeX(index);
  const y = CY - NODE_H / 2;
  const colors = nodeColor(health);

  return (
    <g role="img" aria-label={tooltip}>
      <title>{tooltip}</title>
      {/* Card rect */}
      <rect
        x={x}
        y={y}
        width={NODE_W}
        height={NODE_H}
        rx={NODE_RX}
        ry={NODE_RX}
        fill={colors.fill}
        stroke={colors.border}
        strokeWidth={1.5}
      />
      {/* Status dot */}
      <circle
        cx={x + NODE_W - 14}
        cy={y + 13}
        r={4.5}
        fill={colors.dot}
      />
      {/* Node label */}
      <text
        x={x + 12}
        y={y + 17}
        fontSize={10}
        fontWeight={700}
        fontFamily="var(--font-sans)"
        fill="var(--text-primary)"
        letterSpacing={0.2}
      >
        {label}
      </text>
      {/* Meta line 1 */}
      <text
        x={x + 12}
        y={y + 38}
        fontSize={12}
        fontWeight={700}
        fontFamily="'JetBrains Mono', ui-monospace, monospace"
        fill={colors.text}
        letterSpacing={-0.3}
      >
        {metaLine1}
      </text>
      {/* Meta line 2 (optional) */}
      {metaLine2 && (
        <text
          x={x + 12}
          y={y + 54}
          fontSize={9.5}
          fontWeight={500}
          fontFamily="var(--font-sans)"
          fill="var(--text-muted)"
        >
          {metaLine2}
        </text>
      )}
    </g>
  );
}

/* -------------------------------------------------------------------------- */
/* Arrow connector between nodes                                               */
/* -------------------------------------------------------------------------- */

function ArrowConnector({ fromIndex }: { fromIndex: number }) {
  const x1 = nodeX(fromIndex) + NODE_W;
  const x2 = nodeX(fromIndex + 1);

  // Animated pulse dot
  return (
    <g aria-hidden>
      <line
        x1={x1}
        y1={CY}
        x2={x2}
        y2={CY}
        stroke="var(--border-strong)"
        strokeWidth={1.5}
        strokeDasharray="4 3"
      />
      {/* Arrowhead */}
      <polygon
        points={`${x2},${CY} ${x2 - 7},${CY - 4} ${x2 - 7},${CY + 4}`}
        fill="var(--border-strong)"
      />
      {/* Animated dot travelling along the connector */}
      <circle r={3} fill="var(--text-muted)" opacity={0.7}>
        <animateMotion
          dur="2.4s"
          repeatCount="indefinite"
          path={`M${x1},${CY} L${x2 - 7},${CY}`}
        />
      </circle>
    </g>
  );
}

/* -------------------------------------------------------------------------- */
/* Skeleton state                                                              */
/* -------------------------------------------------------------------------- */

function FlowSkeleton({ ariaLabel }: { ariaLabel: string }) {
  return (
    <div
      className="h-24 w-full animate-pulse rounded-xl"
      style={{ background: "var(--bg-muted)" }}
      aria-busy="true"
      aria-label={ariaLabel}
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Main component                                                              */
/* -------------------------------------------------------------------------- */

export function SystemHealthFlow({
  jobs,
  queues,
  outbox,
  isLoading,
  className,
}: SystemHealthFlowProps) {
  const t = useTranslations("adminConsole.systemHealth.flow");

  if (isLoading) return <FlowSkeleton ariaLabel={t("ariaLoading")} />;

  const schedulerHealth = deriveSchedulerHealth(jobs);
  const jobsHealth = deriveJobsHealth(jobs);
  const queueHealth = deriveQueueHealth(queues);
  const outboxHealth = deriveOutboxHealth(outbox);
  const deliveredHealth = deriveDeliveredHealth(outbox);

  const jobList = jobs?.jobs ?? [];
  const errorJobCount = jobList.filter((j) => j.last_status === "error").length;
  const totalJobs = jobList.length;

  const queueDepth = queues?.celery_default_queue_depth;
  const redisStatus = queues?.redis ?? null;

  const pendingCount = outbox?.pending ?? 0;
  const failedCount = outbox?.failed ?? 0;
  const sentCount = outbox?.sent ?? 0;

  const nodes: Omit<SvgNodeProps, "index">[] = [
    {
      label: t("nodeScheduler"),
      health: schedulerHealth,
      metaLine1:
        schedulerHealth === "unknown"
          ? t("na")
          : schedulerHealth === "healthy"
            ? t("ok")
            : schedulerHealth === "error"
              ? t("error")
              : t("warn"),
      metaLine2: totalJobs > 0 ? t("jobsRegistered", { count: totalJobs }) : undefined,
      tooltip: t("tooltipScheduler"),
    },
    {
      label: t("nodeJobs"),
      health: jobsHealth,
      metaLine1:
        errorJobCount > 0
          ? t("errJobs", { count: errorJobCount })
          : totalJobs > 0
            ? t("allOk")
            : t("na"),
      metaLine2:
        totalJobs > 0
          ? t("totalJobs", { count: totalJobs })
          : undefined,
      tooltip: t("tooltipJobs"),
    },
    {
      label: t("nodeQueue"),
      health: queueHealth,
      metaLine1:
        queueDepth !== null && queueDepth !== undefined
          ? t("queueDepth", { depth: queueDepth })
          : t("na"),
      metaLine2: redisStatus !== null ? t("redis", { status: redisStatus }) : undefined,
      tooltip: t("tooltipQueue"),
    },
    {
      label: t("nodeOutbox"),
      health: outboxHealth,
      metaLine1:
        failedCount > 0
          ? t("outboxFailed", { count: failedCount })
          : t("outboxPending", { count: pendingCount }),
      metaLine2: failedCount > 0 ? t("pending", { count: pendingCount }) : undefined,
      tooltip: t("tooltipOutbox"),
    },
    {
      label: t("nodeDelivered"),
      health: deliveredHealth,
      metaLine1: t("sentCount", { count: sentCount }),
      tooltip: t("tooltipDelivered"),
    },
  ];

  return (
    <div className={cn("w-full", className)}>
      <svg
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        role="img"
        aria-label={t("ariaLabel")}
        style={{ width: "100%", maxWidth: "100%", height: "auto", display: "block" }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <title>{t("ariaLabel")}</title>
        {/* Connectors drawn first so nodes render on top */}
        {[0, 1, 2, 3].map((i) => (
          <ArrowConnector key={i} fromIndex={i} />
        ))}
        {/* Nodes */}
        {nodes.map((node, i) => (
          <SvgNode key={node.label} index={i} {...node} />
        ))}
      </svg>
    </div>
  );
}
