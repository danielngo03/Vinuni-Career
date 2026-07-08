"use client";

import dynamic from "next/dynamic";
import { ChartBar } from "@phosphor-icons/react";
import type { AnalysisChart } from "./chat-analysis";
import { chartToTable } from "./chat-analysis";

/**
 * Recharts is heavy, so the actual SVG renderer is code-split into its own
 * chunk and loaded lazily ONLY when a chart appears. `next/dynamic` with
 * `ssr: false` keeps Recharts out of the main chat/assistant bundle — the
 * assistant is mounted globally in the university shell, so the composer,
 * message list, and markdown/table rendering must stay lean.
 */
const ChatChartImpl = dynamic(
  () => import("./chat-chart-impl").then((m) => m.ChatChartImpl),
  {
    ssr: false,
    loading: () => (
      <div
        className="flex h-[200px] w-full items-center justify-center rounded-md bg-[var(--bg-subtle)]"
        aria-hidden
      >
        <ChartBar
          className="size-5 animate-pulse text-[var(--text-muted)]"
          weight="duotone"
        />
      </div>
    ),
  },
);

/**
 * Accessible chart card. The SVG is decorative (`aria-hidden`); screen readers
 * get an equivalent, visually-hidden data table so the numbers are never
 * color-only. Numeric labels are rendered on the visual chart too.
 */
export function ChatChart({
  chart,
  title,
  srTableLabel,
}: {
  chart: AnalysisChart;
  /** Already-resolved, non-empty title (localized default applied upstream). */
  title: string;
  /** Localized label for the screen-reader data table (e.g. "Chart data"). */
  srTableLabel: string;
}) {
  const fallback = chartToTable(chart);

  return (
    <figure className="my-1 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] p-2.5">
      <figcaption className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-secondary)]">
        <ChartBar aria-hidden weight="bold" className="size-3 text-[var(--text-muted)]" />
        {title}
      </figcaption>
      <div aria-hidden className="h-[200px] w-full">
        <ChatChartImpl chart={chart} />
      </div>
      {/* Screen-reader equivalent — the visual chart above is decorative. */}
      <table className="sr-only">
        <caption>{`${srTableLabel}: ${title}`}</caption>
        <thead>
          <tr>
            {fallback.columns.map((col, i) => (
              <th key={i} scope="col">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {fallback.rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, c) => (
                <td key={c}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
