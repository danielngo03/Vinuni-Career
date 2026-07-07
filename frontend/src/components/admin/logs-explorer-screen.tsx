"use client";

import { useState, useCallback, useRef, useMemo } from "react";
import { useTranslations, useLocale } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ClipboardText,
  ListMagnifyingGlass,
  WarningCircle,
  DownloadSimple,
  ArrowSquareOut,
} from "@phosphor-icons/react";
import {
  Sheet,
  EmptyState,
  Skeleton,
  Button,
  Input,
  SegmentedControl,
  StatusBadge,
  useToast,
  type StatusTone,
} from "@/components/ui";
import { auditLogApi, type AuditRow, type AuditLogParams } from "@/lib/api/audit-log";
import {
  aiOpsApi,
  type AiOpsEvent,
  type AiOpsEventStatus,
} from "@/lib/api/ai-ops";
import { formatDateTime, formatRelativeTime } from "@/lib/format";
import { formatUsd, formatLatency } from "./ai-ops-helpers";
import { env } from "@/lib/env";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/* Types / constants                                                           */
/* -------------------------------------------------------------------------- */

type LogSource = "system" | "ai" | "recent";

const STATUS_TONE: Record<AiOpsEventStatus, StatusTone> = {
  success: "active",
  error: "rejected",
  fallback: "pending",
  rate_limited: "draft",
  timeout: "closed",
};

/* -------------------------------------------------------------------------- */
/* Shared sub-components (reused across views)                                 */
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

/** Mono text helper used throughout sheets */
function Mono({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="font-mono text-xs"
      style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
    >
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Audit diff helpers                                                          */
/* -------------------------------------------------------------------------- */

function DiffSection({
  label,
  data,
  nullLabel,
}: {
  label: string;
  data: Record<string, unknown> | null;
  nullLabel: string;
}) {
  if (!data || Object.keys(data).length === 0) {
    return (
      <div>
        <p className="mb-1 text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {label}
        </p>
        <p className="text-sm text-[var(--text-secondary)]">{nullLabel}</p>
      </div>
    );
  }
  return (
    <div>
      <p className="mb-1.5 text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </p>
      <dl className="space-y-1 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3">
        {Object.entries(data).map(([key, value]) => (
          <div key={key} className="flex flex-wrap gap-x-2">
            <dt
              className="font-mono text-[0.65rem] font-semibold text-[var(--text-secondary)]"
              style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
            >
              {key}:
            </dt>
            <dd
              className="break-all font-mono text-[0.65rem] text-[var(--text-primary)]"
              style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
            >
              {value === null || value === undefined
                ? "null"
                : typeof value === "object"
                  ? JSON.stringify(value)
                  : String(value)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function DiffHighlight({
  before,
  after,
  noDiffLabel,
}: {
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  noDiffLabel: string;
}) {
  const allKeys = new Set([
    ...Object.keys(before ?? {}),
    ...Object.keys(after ?? {}),
  ]);
  const changed = [...allKeys].filter((k) => {
    const bv = JSON.stringify((before ?? {})[k] ?? null);
    const av = JSON.stringify((after ?? {})[k] ?? null);
    return bv !== av;
  });

  if (changed.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">{noDiffLabel}</p>;
  }

  return (
    <dl className="space-y-1.5 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3">
      {changed.map((key) => {
        const bv = (before ?? {})[key];
        const av = (after ?? {})[key];
        return (
          <div key={key} className="grid grid-cols-[auto_1fr_1fr] gap-x-2">
            <dt
              className="col-span-1 font-mono text-[0.65rem] font-semibold text-[var(--text-secondary)]"
              style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
            >
              {key}
            </dt>
            <dd
              className="break-all font-mono text-[0.65rem] text-[var(--brand-red)] line-through opacity-70"
              style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
              title="Before"
            >
              {bv === null || bv === undefined
                ? "null"
                : typeof bv === "object"
                  ? JSON.stringify(bv)
                  : String(bv)}
            </dd>
            <dd
              className="break-all font-mono text-[0.65rem] text-[var(--color-success)]"
              style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
              title="After"
            >
              {av === null || av === undefined
                ? "null"
                : typeof av === "object"
                  ? JSON.stringify(av)
                  : String(av)}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

/* -------------------------------------------------------------------------- */
/* Audit detail sheet                                                          */
/* -------------------------------------------------------------------------- */

function AuditDetailSheet({
  row,
  onClose,
}: {
  row: AuditRow | null;
  onClose: () => void;
}) {
  const t = useTranslations("adminConsole.audit.sheet");
  const locale = useLocale();
  if (!row) return null;
  const hasBoth = row.before !== null && row.after !== null;

  return (
    <Sheet
      open={row !== null}
      onClose={onClose}
      title={t("title")}
      closeLabel={t("closeLabel")}
    >
      <div className="space-y-0">
        <DetailRow label={t("labelId")}>
          <Mono>{row.id}</Mono>
        </DetailRow>
        <DetailRow label={t("labelOccurredAt")}>
          {formatDateTime(row.occurred_at, locale)}
        </DetailRow>
        <DetailRow label={t("labelAction")}>
          <Mono>{row.action}</Mono>
        </DetailRow>
        <DetailRow label={t("labelResourceType")}>{row.resource_type}</DetailRow>
        <DetailRow label={t("labelResourceId")}>
          <Mono>{row.resource_id ?? t("nullValue")}</Mono>
        </DetailRow>
        {row.actor_email && (
          <DetailRow label={t("labelActorEmail")}>{row.actor_email}</DetailRow>
        )}
        <DetailRow label={t("labelActorId")}>
          <Mono>{row.actor_id ?? t("nullValue")}</Mono>
        </DetailRow>
        {row.actor_org_id && (
          <DetailRow label={t("labelActorOrgId")}>
            <Mono>{row.actor_org_id}</Mono>
          </DetailRow>
        )}
      </div>
      <div className="mt-5 space-y-4">
        {hasBoth ? (
          <>
            <DiffHighlight
              before={row.before}
              after={row.after}
              noDiffLabel={t("noDiff")}
            />
            <DiffSection label={t("labelBefore")} data={row.before} nullLabel={t("nullValue")} />
            <DiffSection label={t("labelAfter")} data={row.after} nullLabel={t("nullValue")} />
          </>
        ) : (
          <>
            <DiffSection label={t("labelBefore")} data={row.before} nullLabel={t("nullValue")} />
            <DiffSection label={t("labelAfter")} data={row.after} nullLabel={t("nullValue")} />
          </>
        )}
      </div>
    </Sheet>
  );
}

/* -------------------------------------------------------------------------- */
/* AI detail sheet                                                             */
/* -------------------------------------------------------------------------- */

function TokenBreakdownBar({
  promptTokens,
  completionTokens,
  labelPrompt,
  labelCompletion,
}: {
  promptTokens: number | null;
  completionTokens: number | null;
  labelPrompt: string;
  labelCompletion: string;
}) {
  if (promptTokens == null && completionTokens == null) return null;
  const p = promptTokens ?? 0;
  const c = completionTokens ?? 0;
  const total = p + c;
  if (total === 0) return null;
  const promptPct = Math.round((p / total) * 100);
  const completionPct = 100 - promptPct;

  return (
    <div className="mt-3 mb-1">
      <div
        className="flex h-2 w-full overflow-hidden rounded-full"
        role="img"
        aria-label={`${labelPrompt}: ${p.toLocaleString()} / ${labelCompletion}: ${c.toLocaleString()}`}
      >
        <div className="h-full bg-[var(--gray-700)]" style={{ width: `${promptPct}%` }} />
        <div className="h-full bg-[var(--gray-300)]" style={{ width: `${completionPct}%` }} />
      </div>
      <div className="mt-1.5 flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <span className="inline-block size-2 rounded-sm bg-[var(--gray-700)]" />
          <span className="text-[0.65rem] text-[var(--text-muted)]">
            {labelPrompt}: <span className="font-semibold tabular-nums text-[var(--text-secondary)]">{p.toLocaleString()}</span>
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="inline-block size-2 rounded-sm bg-[var(--gray-300)]" />
          <span className="text-[0.65rem] text-[var(--text-muted)]">
            {labelCompletion}: <span className="font-semibold tabular-nums text-[var(--text-secondary)]">{c.toLocaleString()}</span>
          </span>
        </div>
      </div>
    </div>
  );
}

function StatGrid({ items }: { items: { label: string; value: React.ReactNode }[] }) {
  return (
    <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-4">
      {items.map(({ label, value }) => (
        <div key={label} className="flex flex-col gap-0.5">
          <span className="text-[0.6rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {label}
          </span>
          <span
            className="font-mono text-sm font-semibold tabular-nums text-[var(--text-primary)]"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {value}
          </span>
        </div>
      ))}
    </div>
  );
}

function AiDetailSheet({
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

  const totalTokens =
    event.prompt_tokens != null && event.completion_tokens != null
      ? event.prompt_tokens + event.completion_tokens
      : null;

  return (
    <Sheet
      open={event !== null}
      onClose={onClose}
      title={t("sheet.title")}
      closeLabel={t("sheet.closeLabel")}
    >
      <div className="space-y-0">
        <DetailRow label={t("sheet.labelId")}>
          <Mono>{event.id}</Mono>
        </DetailRow>
        <DetailRow label={t("sheet.labelCreatedAt")}>
          {formatDateTime(event.created_at, locale)}
        </DetailRow>
        <DetailRow label={t("sheet.labelTaskType")}>{event.task_type}</DetailRow>
        <DetailRow label={t("sheet.labelAlias")}>
          <Mono>{event.alias}</Mono>
        </DetailRow>
        <DetailRow label={t("sheet.labelModel")}>
          <Mono>{event.model ?? "—"}</Mono>
        </DetailRow>
        <DetailRow label={t("sheet.labelStatus")}>
          <StatusBadge tone={STATUS_TONE[event.status]}>
            {t(`status.${event.status}`)}
          </StatusBadge>
        </DetailRow>
      </div>

      <StatGrid
        items={[
          { label: t("sheet.labelCost"), value: formatUsd(event.cost_usd ?? NaN) },
          { label: t("sheet.labelLatency"), value: formatLatency(event.latency_ms ?? NaN) },
          {
            label: t("sheet.labelTotalTokens"),
            value: totalTokens != null ? totalTokens.toLocaleString() : "—",
          },
          {
            label: t("sheet.labelPromptTokens"),
            value: event.prompt_tokens != null ? event.prompt_tokens.toLocaleString() : "—",
          },
        ]}
      />

      <TokenBreakdownBar
        promptTokens={event.prompt_tokens}
        completionTokens={event.completion_tokens}
        labelPrompt={t("sheet.labelPromptTokens")}
        labelCompletion={t("sheet.labelCompletionTokens")}
      />

      {event.langfuse_trace_id && (
        <div className="mt-4 space-y-0">
          <DetailRow label={t("sheet.labelTraceId")}>
            <Mono>{event.langfuse_trace_id}</Mono>
          </DetailRow>
        </div>
      )}

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
            <p id="langfuse-disabled-reason" className="mt-1.5 text-xs text-[var(--text-muted)]">
              {!hasLangfuseUrl ? t("sheet.langfuseNotConfigured") : t("sheet.masked")}
            </p>
          </div>
        )}
      </div>
    </Sheet>
  );
}

/* -------------------------------------------------------------------------- */
/* Left tonal stripe                                                           */
/* -------------------------------------------------------------------------- */

/**
 * Left stripe per row:
 *   system (audit) → gray
 *   ai success     → teal
 *   ai error       → red
 *   ai other       → amber/yellow
 */
function LogStripe({ category, status }: { category: "system" | "ai"; status?: AiOpsEventStatus }) {
  if (category === "system") {
    return <span className="block w-0.5 shrink-0 self-stretch rounded-full bg-[var(--gray-300)]" aria-hidden />;
  }
  const color =
    status === "success"
      ? "bg-[var(--color-success)]"
      : status === "error"
        ? "bg-[var(--brand-red)]"
        : "bg-[var(--color-amber,#f59e0b)]";
  return <span className={cn("block w-0.5 shrink-0 self-stretch rounded-full", color)} aria-hidden />;
}

/* -------------------------------------------------------------------------- */
/* Category badge for Recent view                                              */
/* -------------------------------------------------------------------------- */

function CategoryBadge({ category }: { category: "system" | "ai" }) {
  const t = useTranslations("adminConsole.logs");
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-1.5 py-0.5 text-[0.6rem] font-semibold uppercase tracking-wide",
        category === "system"
          ? "bg-[var(--bg-subtle)] text-[var(--text-muted)]"
          : "bg-[var(--bg-teal,#f0fdfa)] text-[var(--color-teal,#0d9488)]",
      )}
    >
      {category === "system" ? t("categorySystem") : t("categoryAi")}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Reusable log table shell                                                    */
/* -------------------------------------------------------------------------- */

interface LogTableColumn<T> {
  key: string;
  header: string;
  align?: "left" | "right";
  cell: (row: T) => React.ReactNode;
}

function LogTable<T extends { id: string | number }>({
  ariaLabel,
  caption,
  columns,
  rows,
  onRowClick,
  getRowAriaLabel,
  loading,
}: {
  ariaLabel: string;
  caption: string;
  columns: LogTableColumn<T>[];
  rows: T[];
  onRowClick: (row: T) => void;
  getRowAriaLabel: (row: T) => string;
  loading?: boolean;
}) {
  return (
    <div
      className="overflow-x-auto rounded-xl border border-white/60 bg-white/82 backdrop-blur-md"
      role="region"
      aria-label={ariaLabel}
    >
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
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
          {rows.map((row) => (
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
              aria-label={getRowAriaLabel(row)}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={cn(
                    "px-3.5 py-2.5 text-[var(--text-primary)]",
                    col.align === "right" ? "text-right" : "text-left",
                  )}
                >
                  {col.cell(row)}
                </td>
              ))}
            </tr>
          ))}
          {loading && rows.length > 0 && (
            <tr>
              <td colSpan={columns.length} className="px-3.5 py-2.5">
                <Skeleton className="h-4 w-full" />
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* System (Audit) view                                                         */
/* -------------------------------------------------------------------------- */

function SystemView() {
  const t = useTranslations("adminConsole.audit");
  const locale = useLocale();
  const { show: showToast } = useToast();

  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [actorId, setActorId] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");

  const [debouncedFilters, setDebouncedFilters] = useState<AuditLogParams>({});
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [allRows, setAllRows] = useState<AuditRow[]>([]);

  const applyFilters = useCallback((next: AuditLogParams) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedFilters(next);
      setCursor(undefined);
      setAllRows([]);
    }, 250);
  }, []);

  const buildFilters = useCallback(
    (overrides: Partial<{ action: string; resourceType: string; actorId: string; since: string; until: string }>) => ({
      action: (overrides.action ?? action) || undefined,
      resource_type: (overrides.resourceType ?? resourceType) || undefined,
      actor_id: (overrides.actorId ?? actorId) || undefined,
      since: (overrides.since ?? since) || undefined,
      until: (overrides.until ?? until) || undefined,
    }),
    [action, resourceType, actorId, since, until],
  );

  const query = useQuery({
    queryKey: ["audit-log", debouncedFilters, cursor] as const,
    queryFn: () => auditLogApi.list({ ...debouncedFilters, cursor, limit: 50 }),
    staleTime: 60_000,
    retry: 1,
  });

  const rowsToShow: AuditRow[] = (() => {
    if (!query.data) return allRows;
    if (!cursor) return query.data.items;
    const existing = new Set(allRows.map((r) => r.id));
    const fresh = query.data.items.filter((r) => !existing.has(r.id));
    return [...allRows, ...fresh];
  })();

  const handleLoadMore = useCallback(() => {
    if (query.data?.next_cursor) {
      setAllRows(rowsToShow);
      setCursor(query.data.next_cursor);
    }
  }, [query.data?.next_cursor, rowsToShow]);

  const [selectedRow, setSelectedRow] = useState<AuditRow | null>(null);
  const [exporting, setExporting] = useState(false);

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const blob = await auditLogApi.exportCsv({
        action: action || undefined,
        resource_type: resourceType || undefined,
        actor_id: actorId || undefined,
        since: since || undefined,
        until: until || undefined,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "audit-log.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showToast({ tone: "success", title: t("exportSuccess") });
    } catch {
      showToast({ tone: "error", title: t("exportError") });
    } finally {
      setExporting(false);
    }
  }, [action, resourceType, actorId, since, until, showToast, t]);

  const columns: LogTableColumn<AuditRow>[] = [
    {
      key: "stripe",
      header: "",
      cell: () => (
        <span className="flex items-center">
          <LogStripe category="system" />
        </span>
      ),
    },
    {
      key: "occurred_at",
      header: t("col.time"),
      cell: (row) => (
        <span className="whitespace-nowrap text-xs text-[var(--text-secondary)]">
          {formatDateTime(row.occurred_at, locale)}
        </span>
      ),
    },
    {
      key: "actor",
      header: t("col.actor"),
      cell: (row) => (
        <span className="text-xs text-[var(--text-primary)]">
          {row.actor_email ?? row.actor_id ?? "—"}
        </span>
      ),
    },
    {
      key: "action",
      header: t("col.action"),
      cell: (row) => (
        <Mono>
          <span className="text-xs font-semibold text-[var(--text-primary)]">{row.action}</span>
        </Mono>
      ),
    },
    {
      key: "resource",
      header: t("col.resource"),
      cell: (row) => (
        <div className="flex flex-col gap-0.5">
          <span className="text-xs font-semibold text-[var(--text-primary)]">{row.resource_type}</span>
          {row.resource_id && (
            <span
              className="font-mono text-[0.65rem] text-[var(--text-muted)]"
              style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
            >
              {row.resource_id.length > 20
                ? `${row.resource_id.slice(0, 8)}…${row.resource_id.slice(-4)}`
                : row.resource_id}
            </span>
          )}
        </div>
      ),
    },
  ];

  if (query.isPending && rowsToShow.length === 0) {
    return <Skeleton className="h-64 w-full" />;
  }

  if (query.isError && rowsToShow.length === 0) {
    return (
      <EmptyState
        kind="error"
        icon={WarningCircle}
        title={t("errorTitle")}
        description={t("errorBody")}
        action={
          <button
            type="button"
            onClick={() => { setCursor(undefined); setAllRows([]); }}
            className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
          >
            {t("retry")}
          </button>
        }
      />
    );
  }

  return (
    <>
      {/* Filter bar */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 flex-1">
          <div>
            <label
              htmlFor="log-audit-action"
              className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
            >
              {t("filter.action")}
            </label>
            <Input
              id="log-audit-action"
              value={action}
              onChange={(e) => {
                setAction(e.target.value);
                applyFilters(buildFilters({ action: e.target.value }));
              }}
              placeholder={t("filter.actionPlaceholder")}
            />
          </div>
          <div>
            <label
              htmlFor="log-audit-resource-type"
              className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
            >
              {t("filter.resourceType")}
            </label>
            <Input
              id="log-audit-resource-type"
              value={resourceType}
              onChange={(e) => {
                setResourceType(e.target.value);
                applyFilters(buildFilters({ resourceType: e.target.value }));
              }}
              placeholder={t("filter.resourceTypePlaceholder")}
            />
          </div>
          <div>
            <label
              htmlFor="log-audit-actor-id"
              className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
            >
              {t("filter.actorId")}
            </label>
            <Input
              id="log-audit-actor-id"
              value={actorId}
              onChange={(e) => {
                setActorId(e.target.value);
                applyFilters(buildFilters({ actorId: e.target.value }));
              }}
              placeholder={t("filter.actorIdPlaceholder")}
            />
          </div>
          <div className="flex gap-2">
            <div className="flex-1">
              <label
                htmlFor="log-audit-since"
                className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
              >
                {t("filter.since")}
              </label>
              <Input
                id="log-audit-since"
                type="date"
                value={since}
                onChange={(e) => {
                  setSince(e.target.value);
                  if (debounceRef.current) clearTimeout(debounceRef.current);
                  setDebouncedFilters(buildFilters({ since: e.target.value }));
                  setCursor(undefined);
                  setAllRows([]);
                }}
              />
            </div>
            <div className="flex-1">
              <label
                htmlFor="log-audit-until"
                className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
              >
                {t("filter.until")}
              </label>
              <Input
                id="log-audit-until"
                type="date"
                value={until}
                onChange={(e) => {
                  setUntil(e.target.value);
                  if (debounceRef.current) clearTimeout(debounceRef.current);
                  setDebouncedFilters(buildFilters({ until: e.target.value }));
                  setCursor(undefined);
                  setAllRows([]);
                }}
              />
            </div>
          </div>
        </div>
        <Button
          variant="secondary"
          onClick={() => void handleExport()}
          loading={exporting}
          className="shrink-0"
        >
          <DownloadSimple aria-hidden weight="bold" className="size-4" />
          {t("exportCsv")}
        </Button>
      </div>

      {/* Table */}
      {rowsToShow.length === 0 && !query.isPending ? (
        <EmptyState
          kind="empty"
          icon={ClipboardText}
          title={t("emptyTitle")}
          description={t("emptyBody")}
        />
      ) : (
        <LogTable
          ariaLabel={t("pageTitle")}
          caption={t("pageTitle")}
          columns={columns}
          rows={rowsToShow}
          onRowClick={setSelectedRow}
          getRowAriaLabel={(row) => `${row.action} — ${row.resource_type}`}
          loading={query.isPending}
        />
      )}

      {query.data?.next_cursor && (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" onClick={handleLoadMore} loading={query.isFetching}>
            {t("loadMore")}
          </Button>
        </div>
      )}

      <AuditDetailSheet row={selectedRow} onClose={() => setSelectedRow(null)} />
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* AI Logs view                                                                */
/* -------------------------------------------------------------------------- */

function AiLogsView() {
  const t = useTranslations("adminConsole.aiOps.traces");
  const tLogs = useTranslations("adminConsole.logs");
  const locale = useLocale();

  const [taskType, setTaskType] = useState("");
  const [status, setStatus] = useState("");
  const [debouncedTaskType, setDebouncedTaskType] = useState<string | undefined>(undefined);
  const [debouncedStatus, setDebouncedStatus] = useState<AiOpsEventStatus | undefined>(undefined);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [allEvents, setAllEvents] = useState<AiOpsEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<AiOpsEvent | null>(null);

  const query = useQuery({
    queryKey: ["ai-ops", "events", debouncedTaskType, debouncedStatus, cursor] as const,
    queryFn: () =>
      aiOpsApi.events({
        cursor,
        limit: 50,
        task_type: debouncedTaskType,
        status: debouncedStatus,
      }),
    staleTime: 30_000,
    retry: 1,
  });

  const eventsToShow: AiOpsEvent[] = (() => {
    if (!query.data) return allEvents;
    if (!cursor) return query.data.items;
    const existing = new Set(allEvents.map((e) => e.id));
    const fresh = query.data.items.filter((e) => !existing.has(e.id));
    return [...allEvents, ...fresh];
  })();

  const handleLoadMore = useCallback(() => {
    if (query.data?.next_cursor) {
      setAllEvents(eventsToShow);
      setCursor(query.data.next_cursor);
    }
  }, [query.data?.next_cursor, eventsToShow]);

  const applyDebounce = useCallback((tt: string, st: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedTaskType(tt || undefined);
      setDebouncedStatus(st ? (st as AiOpsEventStatus) : undefined);
      setCursor(undefined);
      setAllEvents([]);
    }, 250);
  }, []);

  const columns: LogTableColumn<AiOpsEvent>[] = [
    {
      key: "stripe",
      header: "",
      cell: (row) => (
        <span className="flex items-center">
          <LogStripe category="ai" status={row.status} />
        </span>
      ),
    },
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
          <span className="text-xs font-semibold text-[var(--text-primary)]">{row.task_type}</span>
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
          {row.prompt_tokens != null && row.completion_tokens != null
            ? (row.prompt_tokens + row.completion_tokens).toLocaleString()
            : "—"}
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
          {formatUsd(row.cost_usd ?? NaN)}
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
          {formatLatency(row.latency_ms ?? NaN)}
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
    return <Skeleton className="h-64 w-full" />;
  }

  if (query.isError && eventsToShow.length === 0) {
    return (
      <EmptyState
        kind="error"
        icon={WarningCircle}
        title={t("errorTitle")}
        description={t("errorBody")}
        action={
          <button
            type="button"
            onClick={() => { setCursor(undefined); setAllEvents([]); }}
            className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
          >
            {tLogs("retry")}
          </button>
        }
      />
    );
  }

  return (
    <>
      {/* Filter bar */}
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label
            htmlFor="log-ai-task-type"
            className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
          >
            {tLogs("filter.taskType")}
          </label>
          <Input
            id="log-ai-task-type"
            value={taskType}
            onChange={(e) => {
              setTaskType(e.target.value);
              applyDebounce(e.target.value, status);
            }}
            placeholder={tLogs("filter.taskTypePlaceholder")}
          />
        </div>
        <div>
          <label
            htmlFor="log-ai-status"
            className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
          >
            {tLogs("filter.status")}
          </label>
          <Input
            id="log-ai-status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              applyDebounce(taskType, e.target.value);
            }}
            placeholder={tLogs("filter.statusPlaceholder")}
          />
        </div>
      </div>

      {/* Table */}
      {eventsToShow.length === 0 && !query.isPending ? (
        <EmptyState
          kind="empty"
          icon={ListMagnifyingGlass}
          title={t("emptyTitle")}
          description={t("emptyBody")}
        />
      ) : (
        <LogTable
          ariaLabel={t("panelTitle")}
          caption={t("panelTitle")}
          columns={columns}
          rows={eventsToShow}
          onRowClick={setSelectedEvent}
          getRowAriaLabel={(row) => `${row.task_type} — ${row.status}`}
          loading={query.isPending}
        />
      )}

      {query.data?.next_cursor && (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" onClick={handleLoadMore} loading={query.isFetching}>
            {t("loadMore")}
          </Button>
        </div>
      )}

      <AiDetailSheet event={selectedEvent} onClose={() => setSelectedEvent(null)} />
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Merged row type for Recent (All) view                                       */
/* -------------------------------------------------------------------------- */

interface MergedRow {
  id: string;
  ts: string; // ISO timestamp for sorting
  category: "system" | "ai";
  auditRow?: AuditRow;
  aiEvent?: AiOpsEvent;
}

/* -------------------------------------------------------------------------- */
/* Recent (All) view                                                           */
/* -------------------------------------------------------------------------- */

function RecentAllView({ since, until }: { since?: string; until?: string }) {
  const t = useTranslations("adminConsole.logs");
  const tAudit = useTranslations("adminConsole.audit");
  const tAi = useTranslations("adminConsole.aiOps.traces");
  const locale = useLocale();

  const [selectedAudit, setSelectedAudit] = useState<AuditRow | null>(null);
  const [selectedAi, setSelectedAi] = useState<AiOpsEvent | null>(null);

  const auditQuery = useQuery({
    queryKey: ["audit-log-recent", since, until] as const,
    queryFn: () =>
      auditLogApi.list({
        limit: 25,
        since: since || undefined,
        until: until || undefined,
      }),
    staleTime: 30_000,
    retry: 1,
  });

  const aiQuery = useQuery({
    queryKey: ["ai-ops-events-recent"] as const,
    queryFn: () => aiOpsApi.events({ limit: 25 }),
    staleTime: 30_000,
    retry: 1,
  });

  // Merge and sort by timestamp descending
  const merged: MergedRow[] = useMemo(() => {
    const rows: MergedRow[] = [];

    for (const row of auditQuery.data?.items ?? []) {
      rows.push({
        id: `audit-${row.id}`,
        ts: row.occurred_at,
        category: "system",
        auditRow: row,
      });
    }

    for (const event of aiQuery.data?.items ?? []) {
      rows.push({
        id: `ai-${event.id}`,
        ts: event.created_at,
        category: "ai",
        aiEvent: event,
      });
    }

    return rows.sort((a, b) => (a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0));
  }, [auditQuery.data, aiQuery.data]);

  const isLoading = (auditQuery.isPending || aiQuery.isPending) && merged.length === 0;
  const hasError = (auditQuery.isError || aiQuery.isError) && merged.length === 0;

  const columns: LogTableColumn<MergedRow>[] = [
    {
      key: "stripe",
      header: "",
      cell: (row) => (
        <span className="flex items-center">
          <LogStripe category={row.category} status={row.aiEvent?.status} />
        </span>
      ),
    },
    {
      key: "ts",
      header: t("col.time"),
      cell: (row) => (
        <div className="flex flex-col gap-0.5">
          <span className="whitespace-nowrap text-xs text-[var(--text-secondary)]">
            {formatDateTime(row.ts, locale)}
          </span>
          <span className="text-[0.6rem] text-[var(--text-muted)]">
            {formatRelativeTime(row.ts, locale)}
          </span>
        </div>
      ),
    },
    {
      key: "category",
      header: t("col.category"),
      cell: (row) => <CategoryBadge category={row.category} />,
    },
    {
      key: "summary",
      header: t("col.summary"),
      cell: (row) => {
        if (row.auditRow) {
          return (
            <div className="flex flex-col gap-0.5">
              <span
                className="font-mono text-xs font-semibold text-[var(--text-primary)]"
                style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
              >
                {row.auditRow.action}
              </span>
              <span className="text-[0.65rem] text-[var(--text-muted)]">
                {row.auditRow.resource_type}
                {row.auditRow.actor_email ? ` · ${row.auditRow.actor_email}` : ""}
              </span>
            </div>
          );
        }
        if (row.aiEvent) {
          return (
            <div className="flex flex-col gap-0.5">
              <span className="text-xs font-semibold text-[var(--text-primary)]">
                {row.aiEvent.task_type}
              </span>
              <span className="text-[0.65rem] text-[var(--text-muted)]">
                {row.aiEvent.alias}
              </span>
            </div>
          );
        }
        return null;
      },
    },
    {
      key: "meta",
      header: t("col.meta"),
      cell: (row) => {
        if (row.aiEvent) {
          return (
            <StatusBadge tone={STATUS_TONE[row.aiEvent.status]}>
              {tAi(`status.${row.aiEvent.status}`)}
            </StatusBadge>
          );
        }
        return null;
      },
    },
  ];

  if (isLoading) {
    return <Skeleton className="h-64 w-full" />;
  }

  if (hasError) {
    return (
      <EmptyState
        kind="error"
        icon={WarningCircle}
        title={t("errorTitle")}
        description={t("errorBody")}
      />
    );
  }

  const partialError = auditQuery.isError || aiQuery.isError;

  return (
    <>
      {/* Partial error notice */}
      {partialError && (
        <div className="mb-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-3 py-2 text-xs text-[var(--text-muted)]">
          {auditQuery.isError && <span>{tAudit("errorTitle")} · </span>}
          {aiQuery.isError && <span>{tAi("errorTitle")} · </span>}
          {t("partialError")}
        </div>
      )}

      {/* Recent-only notice */}
      <p className="mb-3 text-xs text-[var(--text-muted)]">{t("recentNote")}</p>

      {merged.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={ClipboardText}
          title={t("emptyTitle")}
          description={t("emptyBody")}
        />
      ) : (
        <LogTable
          ariaLabel={t("recentTitle")}
          caption={t("recentTitle")}
          columns={columns}
          rows={merged}
          onRowClick={(row) => {
            if (row.auditRow) setSelectedAudit(row.auditRow);
            if (row.aiEvent) setSelectedAi(row.aiEvent);
          }}
          getRowAriaLabel={(row) =>
            row.auditRow
              ? `${row.auditRow.action} — ${row.auditRow.resource_type}`
              : row.aiEvent
                ? `${row.aiEvent.task_type} — ${row.aiEvent.status}`
                : "Log entry"
          }
          loading={auditQuery.isFetching || aiQuery.isFetching}
        />
      )}

      <AuditDetailSheet row={selectedAudit} onClose={() => setSelectedAudit(null)} />
      <AiDetailSheet event={selectedAi} onClose={() => setSelectedAi(null)} />
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Main screen                                                                 */
/* -------------------------------------------------------------------------- */

export function LogsExplorerScreen() {
  const t = useTranslations("adminConsole.logs");

  const [source, setSource] = useState<LogSource>("recent");

  /* Shared time-range for the Recent view */
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");

  const options = [
    { value: "recent" as const, label: t("sourceRecent") },
    { value: "system" as const, label: t("sourceSystem") },
    { value: "ai" as const, label: t("sourceAi") },
  ];

  return (
    <div className="marketplace-card rounded-[12px] p-5">
      {/* Header */}
      <div className="mb-5">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="flex items-center gap-2 text-lg font-bold tracking-tight text-[var(--text-primary)]">
              <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
                <ClipboardText aria-hidden weight="duotone" className="size-4" />
              </span>
              {t("pageTitle")}
            </h1>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {t("pageSubtitle")}
            </p>
          </div>

          <SegmentedControl
            value={source}
            onValueChange={(v) => setSource(v as LogSource)}
            options={options}
            ariaLabel={t("sourceAriaLabel")}
            size="sm"
          />
        </div>

        {/* Shared time-range filter — visible in Recent view only */}
        {source === "recent" && (
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label
                htmlFor="logs-shared-since"
                className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
              >
                {t("filter.since")}
              </label>
              <Input
                id="logs-shared-since"
                type="date"
                value={since}
                onChange={(e) => setSince(e.target.value)}
              />
            </div>
            <div>
              <label
                htmlFor="logs-shared-until"
                className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
              >
                {t("filter.until")}
              </label>
              <Input
                id="logs-shared-until"
                type="date"
                value={until}
                onChange={(e) => setUntil(e.target.value)}
              />
            </div>
          </div>
        )}
      </div>

      {/* View panel */}
      {source === "system" && <SystemView />}
      {source === "ai" && <AiLogsView />}
      {source === "recent" && (
        <RecentAllView
          since={since || undefined}
          until={until || undefined}
        />
      )}
    </div>
  );
}
