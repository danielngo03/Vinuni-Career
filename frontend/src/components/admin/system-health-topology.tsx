"use client";

/**
 * Service topology diagram for System Health.
 *
 * Renders a small hub-and-spoke SVG showing the App at the center
 * connected to DB, Redis, Celery broker nodes, each with a status dot.
 *
 * Colors:
 *   teal dot = ok
 *   red dot  = down
 *   gray dot = unknown
 *
 * Uses CSS custom properties (design tokens) only — no ad-hoc colors.
 */

import { useTranslations } from "next-intl";
import type { SystemHealthQueues, SystemHealthServices } from "@/lib/api/system-health";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/* Types                                                                       */
/* -------------------------------------------------------------------------- */

type NodeStatus = "ok" | "down" | "unknown";

/* -------------------------------------------------------------------------- */
/* Color helpers                                                               */
/* -------------------------------------------------------------------------- */

function statusFill(status: NodeStatus): string {
  if (status === "ok") return "var(--teal-600)";
  if (status === "down") return "var(--red-600)";
  return "var(--text-muted)";
}

function statusBorder(status: NodeStatus): string {
  if (status === "ok") return "var(--teal-500)";
  if (status === "down") return "var(--red-600)";
  return "var(--border-strong)";
}

function statusBg(status: NodeStatus): string {
  if (status === "ok") return "var(--teal-50)";
  if (status === "down") return "var(--red-50)";
  return "var(--bg-muted)";
}

/* -------------------------------------------------------------------------- */
/* Geometry helpers                                                            */
/* -------------------------------------------------------------------------- */

function toRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

function polarToXY(cx: number, cy: number, radius: number, angleDeg: number) {
  const rad = toRad(angleDeg - 90); // -90 so 0deg = top
  return {
    x: cx + radius * Math.cos(rad),
    y: cy + radius * Math.sin(rad),
  };
}

/* -------------------------------------------------------------------------- */
/* Props                                                                       */
/* -------------------------------------------------------------------------- */

interface SystemHealthTopologyProps {
  services?: SystemHealthServices;
  queues?: SystemHealthQueues;
  isLoading?: boolean;
  className?: string;
}

/* -------------------------------------------------------------------------- */
/* SVG constants                                                               */
/* -------------------------------------------------------------------------- */

const SVG_SIZE = 260;
const CX = SVG_SIZE / 2;
const CY = SVG_SIZE / 2;
const HUB_R = 28; // center "App" hub radius
const SPOKE_RADIUS = 88; // distance from center to satellite node
const SAT_R = 22; // satellite node circle radius

/* -------------------------------------------------------------------------- */
/* Skeleton                                                                   */
/* -------------------------------------------------------------------------- */

function TopologySkeleton({ ariaLabel }: { ariaLabel: string }) {
  return (
    <div
      className="animate-pulse rounded-xl"
      style={{
        background: "var(--bg-muted)",
        width: SVG_SIZE,
        height: SVG_SIZE,
        maxWidth: "100%",
      }}
      aria-busy="true"
      aria-label={ariaLabel}
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Main component                                                              */
/* -------------------------------------------------------------------------- */

export function SystemHealthTopology({
  services,
  queues,
  isLoading,
  className,
}: SystemHealthTopologyProps) {
  const t = useTranslations("adminConsole.systemHealth.topology");

  if (isLoading) return <TopologySkeleton ariaLabel={t("ariaLoading")} />;

  // Derive statuses from data
  const dbStatus: NodeStatus = services?.database ?? "unknown";
  const redisStatus: NodeStatus = services?.redis ?? "unknown";
  const brokerStatus: NodeStatus =
    queues?.broker_configured === true
      ? queues.redis === "ok"
        ? "ok"
        : "down"
      : queues?.broker_configured === false
        ? "down"
        : "unknown";
  const outboxStatus: NodeStatus =
    services?.outbox != null
      ? (services.outbox.failed ?? 0) > 0 || (services.outbox.dead ?? 0) > 0
        ? "down"
        : "ok"
      : "unknown";

  // Satellite nodes arranged around the hub at evenly spaced angles
  const satellites: Array<{ id: string; label: string; status: NodeStatus; angle: number }> = [
    { id: "db", label: t("nodeDb"), status: dbStatus, angle: 0 },      // top
    { id: "redis", label: t("nodeRedis"), status: redisStatus, angle: 90 },   // right
    { id: "celery", label: t("nodeCelery"), status: brokerStatus, angle: 180 }, // bottom
    { id: "outbox", label: t("nodeOutbox"), status: outboxStatus, angle: 270 }, // left
  ];

  // Overall system status for hub label
  const allOk = satellites.every((s) => s.status === "ok");
  const anyDown = satellites.some((s) => s.status === "down");
  const hubStatus: NodeStatus = anyDown ? "down" : allOk ? "ok" : "unknown";

  return (
    <div
      className={cn("flex items-center justify-center", className)}
      style={{ maxWidth: SVG_SIZE, margin: "0 auto" }}
    >
      <svg
        viewBox={`0 0 ${SVG_SIZE} ${SVG_SIZE}`}
        role="img"
        aria-label={t("ariaLabel")}
        style={{ width: "100%", height: "auto", display: "block" }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <title>{t("ariaLabel")}</title>

        {/* Spoke lines */}
        {satellites.map((node) => {
          const { x, y } = polarToXY(CX, CY, SPOKE_RADIUS, node.angle);
          // Shorten the line so it doesn't overlap circles
          const hubEdgeX = CX + ((x - CX) / SPOKE_RADIUS) * HUB_R;
          const hubEdgeY = CY + ((y - CY) / SPOKE_RADIUS) * HUB_R;
          const satEdgeX = x - ((x - CX) / SPOKE_RADIUS) * SAT_R;
          const satEdgeY = y - ((y - CY) / SPOKE_RADIUS) * SAT_R;

          return (
            <line
              key={node.id}
              x1={hubEdgeX}
              y1={hubEdgeY}
              x2={satEdgeX}
              y2={satEdgeY}
              stroke={
                node.status === "ok"
                  ? "var(--teal-100)"
                  : node.status === "down"
                    ? "var(--red-100)"
                    : "var(--border-strong)"
              }
              strokeWidth={1.5}
              strokeDasharray={node.status === "down" ? "4 3" : undefined}
            />
          );
        })}

        {/* Hub — center "App" node */}
        <circle
          cx={CX}
          cy={CY}
          r={HUB_R}
          fill={anyDown ? "var(--red-50)" : allOk ? "var(--teal-50)" : "var(--bg-muted)"}
          stroke={statusBorder(hubStatus)}
          strokeWidth={2}
        />
        {/* Hub label */}
        <text
          x={CX}
          y={CY - 4}
          textAnchor="middle"
          fontSize={9}
          fontWeight={700}
          fontFamily="var(--font-sans)"
          fill="var(--text-primary)"
          letterSpacing={0.3}
        >
          {t("hubApp")}
        </text>
        <text
          x={CX}
          y={CY + 9}
          textAnchor="middle"
          fontSize={8}
          fontWeight={500}
          fontFamily="var(--font-sans)"
          fill={statusFill(hubStatus)}
        >
          {hubStatus === "ok"
            ? t("statusOk")
            : hubStatus === "down"
              ? t("statusDown")
              : t("statusUnknown")}
        </text>

        {/* Satellite nodes */}
        {satellites.map((node) => {
          const { x, y } = polarToXY(CX, CY, SPOKE_RADIUS, node.angle);

          // Text label: position outside the circle
          const labelOffset = SAT_R + 13;
          const labelPos = polarToXY(CX, CY, SPOKE_RADIUS + labelOffset, node.angle);
          const textAnchor =
            Math.abs(node.angle - 90) < 30
              ? "start"
              : Math.abs(node.angle - 270) < 30
                ? "end"
                : "middle";

          // Status sub-label
          const subLabelPos = polarToXY(CX, CY, SPOKE_RADIUS + labelOffset + 11, node.angle);

          const statusLabel =
            node.status === "ok"
              ? t("statusOk")
              : node.status === "down"
                ? t("statusDown")
                : t("statusUnknown");
          return (
            <g key={node.id} role="img" aria-label={`${node.label}: ${statusLabel}`}>
              <title>{`${node.label}: ${statusLabel}`}</title>
              {/* Satellite circle */}
              <circle
                cx={x}
                cy={y}
                r={SAT_R}
                fill={statusBg(node.status)}
                stroke={statusBorder(node.status)}
                strokeWidth={1.5}
              />
              {/* Status dot inside satellite */}
              <circle
                cx={x}
                cy={y}
                r={5.5}
                fill={statusFill(node.status)}
              />
              {/* Node name label outside circle */}
              <text
                x={labelPos.x}
                y={labelPos.y}
                textAnchor={textAnchor}
                dominantBaseline="middle"
                fontSize={9.5}
                fontWeight={700}
                fontFamily="var(--font-sans)"
                fill="var(--text-primary)"
                letterSpacing={0.2}
              >
                {node.label}
              </text>
              {/* Status sub-label */}
              <text
                x={subLabelPos.x}
                y={subLabelPos.y}
                textAnchor={textAnchor}
                dominantBaseline="middle"
                fontSize={8.5}
                fontFamily="var(--font-sans)"
                fill={statusFill(node.status)}
              >
                {node.status === "ok"
                  ? t("statusOk")
                  : node.status === "down"
                    ? t("statusDown")
                    : t("statusUnknown")}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
