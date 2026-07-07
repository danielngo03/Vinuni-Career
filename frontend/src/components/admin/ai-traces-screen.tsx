"use client";

import { useState, useCallback } from "react";
import { useTranslations, useLocale } from "next-intl";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowSquareOut,
  WarningCircle,
  ListMagnifyingGlass,
} from "@phosphor-icons/react";
import {
  Sheet,
  StatusBadge,
  EmptyState,
  Skeleton,
  Button,
  type Column,
  type StatusTone,
} from "@/components/ui";
import {
  aiOpsApi,
  type AiOpsEvent,
  type AiOpsEventStatus,
  type AiOpsRange,
} from "@/lib/api/ai-ops";
import { formatDateTime } from "@/lib/format";
import { formatUsd, formatLatency } from "./ai-ops-helpers";
import { env } from "@/lib/env";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/* Status badge mapping                                                       */
/* -------------------------------------------------------------------------- */

const STATUS_TONE: Record<AiOpsEventStatus, StatusTone> = {
  success: "active",
  error: "rejected",
  fallback: "pending",
  rate_limited: "draft",
  timeout: "closed",
};

/* -------------------------------------------------------------------------- */
/* Detail sheet                                                               */
/* -------------------------------------------------------------------------- */

function DetailRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5 py-2.5 border-b border-[var(--border-subtle)] last:border-0">
      <span className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </span>
      <span className="text-sm text-[var(--text-primary)] break-all">
        {children}
      </span>
    </div>
  );
}

function TraceDetailSheet({
  event,
  onClose,
}: {
  event: AiOpsEvent | null;
  onClose: () => void;
}) {
  const t = useTranslations("adminConsole.aiOps.traces");
  const locale = useLocale();

  if (!event) return null;

  const hasTraceId = Boolean(event.langfuse_trace_id);
  const hasLangfuseUrl = Boolean(env.langfuseBaseUrl);
  const canOpenLangfuse = hasTraceId && hasLangfuseUrl;

  const langfuseHref =
    canOpenLangfuse && event.langfuse_trace_id && env.langfuseBaseUrl
      ? `${env.langfuseBaseUrl}/trace/${event.langfuse_trace_id}`
      : undefined;

  return (
    <Sheet
      open={event !== null}
      onClose={onClose}
      title={t("sheet.title")}
      closeLabel={t("sheet.closeLabel")}
    >
      <div className="space-y-0">
        <DetailRow label={t("sheet.labelId")}>
          <span
            className="font-mono text-xs"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {event.id}
          </span>
        </DetailRow>

        <DetailRow label={t("sheet.labelCreatedAt")}>
          {formatDateTime(event.created_at, locale)}
        </DetailRow>

        <DetailRow label={t("sheet.labelTaskType")}>
          {event.task_type}
        </DetailRow>

        <DetailRow label={t("sheet.labelAlias")}>
          <span
            className="font-mono text-xs"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {event.alias}
          </span>
        </DetailRow>

        <DetailRow label={t("sheet.labelModel")}>
          {event.model ?? t("sheet.masked")}
        </DetailRow>

        <DetailRow label={t("sheet.labelStatus")}>
          <StatusBadge tone={STATUS_TONE[event.status]}>
            {t(`status.${event.status}`)}
          </StatusBadge>
        </DetailRow>

        <DetailRow label={t("sheet.labelPromptTokens")}>
          <span
            className="font-mono tabular-nums"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {event.prompt_tokens.toLocaleString()}
          </span>
        </DetailRow>

        <DetailRow label={t("sheet.labelCompletionTokens")}>
          <span
            className="font-mono tabular-nums"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {event.completion_tokens.toLocaleString()}
          </span>
        </DetailRow>

        <DetailRow label={t("sheet.labelTotalTokens")}>
          <span
            className="font-mono tabular-nums"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {(event.prompt_tokens + event.completion_tokens).toLocaleString()}
          </span>
        </DetailRow>

        <DetailRow label={t("sheet.labelCost")}>
          <span
            className="font-mono tabular-nums"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {formatUsd(event.cost_usd)}
          </span>
        </DetailRow>

        <DetailRow label={t("sheet.labelLatency")}>
          <span
            className="font-mono tabular-nums"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {formatLatency(event.latency_ms)}
          </span>
        </DetailRow>

        {event.langfuse_trace_id && (
          <DetailRow label={t("sheet.labelTraceId")}>
            <span
              className="font-mono text-xs"
              style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
            >
              {event.langfuse_trace_id}
            </span>
          </DetailRow>
        )}
      </div>

      <div className="mt-5">
        {canOpenLangfuse && langfuseHref ? (
          <a
            href={langfuseHref}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-xl bg-[var(--brand-primary)] px-4 py-2 text-sm font-semibold text-white shadow-sm transition-opacity hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/50"
          >
            <ArrowSquareOut aria-hidden weight="bold" className="size-4" />
            {t("sheet.openInLangfuse")}
          </a>
        ) : (
          <div
            title={
              !hasLangfuseUrl
                ? t("sheet.langfuseNotConfigured")
                : !hasTraceId
                  ? t("sheet.masked")
                  : undefined
            }
          >
            <button
              type="button"
              disabled
              aria-disabled="true"
              aria-describedby="langfuse-disabled-reason"
              className="inline-flex cursor-not-allowed items-center gap-2 rounded-xl bg-[var(--bg-subtle)] px-4 py-2 text-sm font-semibold text-[var(--text-muted)] opacity-60"
            >
              <ArrowSquareOut aria-hidden weight="bold" className="size-4" />
              {t("sheet.openInLangfuse")}
            </button>
            <p
              id="langfuse-disabled-reason"
              className="mt-1.5 text-xs text-[var(--text-muted)]"
            >
              {!hasLangfuseUrl
                ? t("sheet.langfuseNotConfigured")
                : t("sheet.masked")}
            </p>
          </div>
        )}
      </div>
    </Sheet>
  );
}

/* -------------------------------------------------------------------------- */
/* Main traces screen                                                         */
/* -------------------------------------------------------------------------- */

export function AiTracesScreen({ range }: { range: AiOpsRange }) {
  const t = useTranslations("adminConsole.aiOps.traces");
  const tAiOps = useTranslations("adminConsole.aiOps");
  const locale = useLocale();
  const qc = useQueryClient();

  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [allEvents, setAllEvents] = useState<AiOpsEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<AiOpsEvent | null>(null);
  const [loadedRange, setLoadedRange] = useState<AiOpsRange>(range);

  // When range changes, reset pagination
  const effectiveRange = range;
  const isRangeChanged = loadedRange !== effectiveRange;

  const query = useQuery({
    queryKey: ["ai-ops", "events", effectiveRange, cursor] as const,
    queryFn: () =>
      aiOpsApi.events({ range: effectiveRange, cursor, limit: 50 }),
    staleTime: 30_000,
    retry: 1,
  });

  // Sync allEvents after each successful fetch
  const syncedEvents = (() => {
    if (!query.data) return allEvents;
    if (isRangeChanged || !cursor) {
      return query.data.data;
    }
    // Append new page (dedup by id)
    const existing = new Set(allEvents.map((e) => e.id));
    const fresh = query.data.data.filter((e) => !existing.has(e.id));
    return [...allEvents, ...fresh];
  })();

  // Keep allEvents in sync (only state update path)
  const handleLoadMore = useCallback(() => {
    if (query.data?.next_cursor) {
      // Before advancing cursor, flush synced events
      setAllEvents(syncedEvents);
      setLoadedRange(effectiveRange);
      setCursor(query.data.next_cursor);
    }
  }, [query.data?.next_cursor, syncedEvents, effectiveRange]);

  // When range changes, reset
  const handleRangeReset = useCallback(() => {
    setCursor(undefined);
    setAllEvents([]);
    setLoadedRange(effectiveRange);
    void qc.invalidateQueries({ queryKey: ["ai-ops", "events"] });
  }, [effectiveRange, qc]);

  // If range changed since last load, trigger reset on next render cycle
  // We use a stable reference pattern: only reset when range actually changes
  const eventsToShow: AiOpsEvent[] =
    isRangeChanged && query.data ? query.data.data : syncedEvents;

  const columns: Column<AiOpsEvent>[] = [
    {
      key: "created_at",
      header: t("col.time"),
      cell: (row) => (
        <span className="whitespace-nowrap text-xs text-[var(--text-secondary)]">
          {formatDateTime(row.created_at, locale)}
        </span>
      ),
    },
    {
      key: "task_type",
      header: t("col.feature"),
      cell: (row) => (
        <div className="flex flex-col gap-0.5">
          <span className="text-xs font-semibold text-[var(--text-primary)]">
            {row.task_type}
          </span>
          <span
            className="font-mono text-[0.65rem] text-[var(--text-muted)]"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {row.alias}
          </span>
        </div>
      ),
    },
    {
      key: "model",
      header: t("col.model"),
      cell: (row) => (
        <span
          className="font-mono text-xs text-[var(--text-secondary)]"
          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
        >
          {row.model ?? "—"}
        </span>
      ),
    },
    {
      key: "tokens",
      header: t("col.tokens"),
      align: "right",
      cell: (row) => (
        <span
          className="font-mono text-xs tabular-nums text-[var(--text-secondary)]"
          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
        >
          {(row.prompt_tokens + row.completion_tokens).toLocaleString()}
        </span>
      ),
    },
    {
      key: "cost_usd",
      header: t("col.cost"),
      align: "right",
      cell: (row) => (
        <span
          className="font-mono text-xs tabular-nums text-[var(--text-secondary)]"
          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
        >
          {formatUsd(row.cost_usd)}
        </span>
      ),
    },
    {
      key: "latency_ms",
      header: t("col.latency"),
      align: "right",
      cell: (row) => (
        <span
          className="font-mono text-xs tabular-nums text-[var(--text-secondary)]"
          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
        >
          {formatLatency(row.latency_ms)}
        </span>
      ),
    },
    {
      key: "status",
      header: t("col.status"),
      cell: (row) => (
        <StatusBadge tone={STATUS_TONE[row.status]}>
          {t(`status.${row.status}`)}
        </StatusBadge>
      ),
    },
  ];

  if (query.isPending && eventsToShow.length === 0) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
          <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
            <ListMagnifyingGlass aria-hidden weight="duotone" className="size-4" />
          </span>
          {t("panelTitle")}
        </h2>
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (query.isError && eventsToShow.length === 0) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
          <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
            <ListMagnifyingGlass aria-hidden weight="duotone" className="size-4" />
          </span>
          {t("panelTitle")}
        </h2>
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              onClick={handleRangeReset}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {tAiOps("retry")}
            </button>
          }
        />
      </div>
    );
  }

  // Row click handler — inline so DataTable can wrap rows in button
  function onRowClick(row: AiOpsEvent) {
    setSelectedEvent(row);
  }

  const hasMore = Boolean(query.data?.next_cursor);

  return (
    <>
      <div className="marketplace-card rounded-[12px] p-5">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
          <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
            <ListMagnifyingGlass aria-hidden weight="duotone" className="size-4" />
          </span>
          {t("panelTitle")}
        </h2>

        {/* Clickable rows wrapper — DataTable doesn't natively support row onClick;
            we wrap the whole table and delegate via event target closest tr. */}
        <div
          className={cn(
            "overflow-x-auto rounded-xl border border-white/60 bg-white/82 backdrop-blur-md",
          )}
          role="region"
          aria-label={t("panelTitle")}
        >
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">{t("panelTitle")}</caption>
            <thead>
              <tr className="border-b border-white/40 bg-white/60">
                {columns.map((col) => (
                  <th
                    key={col.key}
                    scope="col"
                    className={cn(
                      "px-3.5 py-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]",
                      col.align === "right" ? "text-right" : "text-left",
                    )}
                  >
                    {col.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {eventsToShow.length === 0 && !query.isPending ? (
                <tr>
                  <td colSpan={columns.length} className="px-3.5 py-10 text-center text-sm text-[var(--text-muted)]">
                    {t("emptyTitle")}
                  </td>
                </tr>
              ) : null}
              {eventsToShow.map((row) => (
                <tr
                  key={row.id}
                  className="cursor-pointer border-b border-white/40 align-middle transition-colors last:border-0 hover:bg-white/60 focus-within:bg-white/60"
                  onClick={() => onRowClick(row)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onRowClick(row);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                  aria-label={`${row.task_type} — ${row.status}`}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        "px-3.5 py-2.5 text-[var(--text-primary)]",
                        col.align === "right" ? "text-right" : "text-left",
                      )}
                    >
                      {col.cell
                        ? col.cell(row)
                        : String((row as unknown as Record<string, unknown>)[col.key] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
              {query.isPending && eventsToShow.length > 0 && (
                <tr>
                  <td colSpan={columns.length} className="px-3.5 py-2.5">
                    <Skeleton className="h-4 w-full" />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {hasMore && (
          <div className="mt-4 flex justify-center">
            <Button
              variant="secondary"
              onClick={handleLoadMore}
              loading={query.isFetching}
            >
              {t("loadMore")}
            </Button>
          </div>
        )}
      </div>

      <TraceDetailSheet
        event={selectedEvent}
        onClose={() => setSelectedEvent(null)}
      />
    </>
  );
}
