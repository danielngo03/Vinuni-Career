"use client";

import { Info, WarningCircle } from "@phosphor-icons/react";
import type { ParsedTable } from "./markdown-table";
import {
  hasBody,
  isAnalyzed,
  type AnalysisTable,
  type AttachmentAnalysis,
} from "./chat-analysis";
import { DataTable } from "./data-table";
import { ChatChart } from "./chat-chart";

/** Structured `analyze_attachment` result: summary, insights, real tables, and
 * code-split charts, plus honest "couldn't analyze" / "degraded" states. No
 * provider/model/token/PII is ever shown (the payload is already leakage-safe).
 */
export function AttachmentAnalysis({
  analysis,
  t,
}: {
  analysis: AttachmentAnalysis;
  t: (k: string) => string;
}) {
  // Backend could not turn the file into an analysis — be honest, offer a hint.
  if (!isAnalyzed(analysis)) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-2.5">
        <WarningCircle
          aria-hidden
          weight="fill"
          className="mt-0.5 size-4 shrink-0 text-[var(--text-muted)]"
        />
        <div className="min-w-0 text-xs leading-relaxed text-[var(--text-secondary)]">
          <p className="font-semibold text-[var(--text-primary)]">
            {t("analysisFailedTitle")}
          </p>
          <p className="mt-0.5">{analysis.summary.trim() || t("analysisFailedBody")}</p>
        </div>
      </div>
    );
  }

  // Analyzed but empty (nothing to visualise) — nothing to add below the reply.
  if (!hasBody(analysis)) return null;

  return (
    <div className="space-y-2">
      {analysis.degraded && (
        <div className="flex items-center gap-1.5 rounded-md bg-[var(--bg-subtle)] px-2.5 py-1.5 text-[11px] text-[var(--text-muted)]">
          <Info aria-hidden weight="fill" className="size-3 shrink-0" />
          <span>{t("analysisDegraded")}</span>
        </div>
      )}

      {analysis.summary.trim() && (
        <p className="text-xs leading-relaxed text-[var(--text-secondary)]">
          {analysis.summary.trim()}
        </p>
      )}

      {analysis.insights.length > 0 && (
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("analysisInsights")}
          </p>
          <ul className="space-y-0.5">
            {analysis.insights.map((insight, i) => (
              <li key={i} className="flex gap-1.5 text-xs text-[var(--text-secondary)]">
                <span aria-hidden className="mt-1 size-1 shrink-0 rounded-full bg-[var(--text-muted)]" />
                <span>{insight}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {analysis.tables.map((table, i) => (
        <DataTable key={`t-${i}`} table={toParsedTable(table)} caption={table.title.trim() || undefined} />
      ))}

      {analysis.charts.map((chart, i) => (
        <ChatChart
          key={`c-${i}`}
          chart={chart}
          title={chart.title.trim() || t("chartFallback")}
          srTableLabel={t("chartData")}
        />
      ))}
    </div>
  );
}

/** Adapt a structured analysis table into the shared `<DataTable>` shape. */
function toParsedTable(table: AnalysisTable): ParsedTable {
  return { headers: table.columns, rows: table.rows, aligns: [] };
}
