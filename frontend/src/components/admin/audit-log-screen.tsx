"use client";

import { useState, useCallback, useRef } from "react";
import { useTranslations, useLocale } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ClipboardText, WarningCircle, DownloadSimple } from "@phosphor-icons/react";
import {
  Sheet,
  EmptyState,
  Skeleton,
  Button,
  Input,
  useToast,
} from "@/components/ui";
import { auditLogApi, type AuditRow, type AuditLogParams } from "@/lib/api/audit-log";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/* Before / After diff renderer                                                */
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

/* -------------------------------------------------------------------------- */
/* Changed-keys highlight                                                     */
/* -------------------------------------------------------------------------- */

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
    return (
      <p className="text-sm text-[var(--text-secondary)]">{noDiffLabel}</p>
    );
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
/* Detail row helper                                                           */
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

/* -------------------------------------------------------------------------- */
/* Detail sheet                                                                */
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
          <span
            className="font-mono text-xs"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {row.id}
          </span>
        </DetailRow>

        <DetailRow label={t("labelOccurredAt")}>
          {formatDateTime(row.occurred_at, locale)}
        </DetailRow>

        <DetailRow label={t("labelAction")}>
          <span
            className="font-mono text-xs"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {row.action}
          </span>
        </DetailRow>

        <DetailRow label={t("labelResourceType")}>
          {row.resource_type}
        </DetailRow>

        <DetailRow label={t("labelResourceId")}>
          <span
            className="font-mono text-xs"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {row.resource_id ?? t("nullValue")}
          </span>
        </DetailRow>

        {row.actor_email && (
          <DetailRow label={t("labelActorEmail")}>
            {row.actor_email}
          </DetailRow>
        )}

        <DetailRow label={t("labelActorId")}>
          <span
            className="font-mono text-xs"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {row.actor_id ?? t("nullValue")}
          </span>
        </DetailRow>

        {row.actor_org_id && (
          <DetailRow label={t("labelActorOrgId")}>
            <span
              className="font-mono text-xs"
              style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
            >
              {row.actor_org_id}
            </span>
          </DetailRow>
        )}
      </div>

      {/* Diff section */}
      <div className="mt-5 space-y-4">
        {hasBoth ? (
          <>
            <DiffHighlight
              before={row.before}
              after={row.after}
              noDiffLabel={t("noDiff")}
            />
            <DiffSection
              label={t("labelBefore")}
              data={row.before}
              nullLabel={t("nullValue")}
            />
            <DiffSection
              label={t("labelAfter")}
              data={row.after}
              nullLabel={t("nullValue")}
            />
          </>
        ) : (
          <>
            <DiffSection
              label={t("labelBefore")}
              data={row.before}
              nullLabel={t("nullValue")}
            />
            <DiffSection
              label={t("labelAfter")}
              data={row.after}
              nullLabel={t("nullValue")}
            />
          </>
        )}
      </div>
    </Sheet>
  );
}

/* -------------------------------------------------------------------------- */
/* Table columns type                                                          */
/* -------------------------------------------------------------------------- */

interface Column<T> {
  key: string;
  header: string;
  align?: "left" | "right";
  cell: (row: T) => React.ReactNode;
}

/* -------------------------------------------------------------------------- */
/* Main screen                                                                 */
/* -------------------------------------------------------------------------- */

export function AuditLogScreen() {
  const t = useTranslations("adminConsole.audit");
  const locale = useLocale();
  const { show: showToast } = useToast();

  /* ---- filter state ---- */
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [actorId, setActorId] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");

  /* ---- debounced filter ---- */
  const [debouncedFilters, setDebouncedFilters] = useState<AuditLogParams>({});
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const applyFilters = useCallback(
    (next: AuditLogParams) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        setDebouncedFilters(next);
        setCursor(undefined);
        setAllRows([]);
      }, 250);
    },
    [],
  );

  /* Handler that updates one field and schedules a debounce */
  const handleActionChange = useCallback(
    (v: string) => {
      setAction(v);
      applyFilters({
        action: v || undefined,
        resource_type: resourceType || undefined,
        actor_id: actorId || undefined,
        since: since || undefined,
        until: until || undefined,
      });
    },
    [resourceType, actorId, since, until, applyFilters],
  );

  const handleResourceTypeChange = useCallback(
    (v: string) => {
      setResourceType(v);
      applyFilters({
        action: action || undefined,
        resource_type: v || undefined,
        actor_id: actorId || undefined,
        since: since || undefined,
        until: until || undefined,
      });
    },
    [action, actorId, since, until, applyFilters],
  );

  const handleActorIdChange = useCallback(
    (v: string) => {
      setActorId(v);
      applyFilters({
        action: action || undefined,
        resource_type: resourceType || undefined,
        actor_id: v || undefined,
        since: since || undefined,
        until: until || undefined,
      });
    },
    [action, resourceType, since, until, applyFilters],
  );

  /* Date inputs apply immediately (no debounce — user intent is clear on blur) */
  const handleSinceChange = useCallback(
    (v: string) => {
      setSince(v);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      setDebouncedFilters({
        action: action || undefined,
        resource_type: resourceType || undefined,
        actor_id: actorId || undefined,
        since: v || undefined,
        until: until || undefined,
      });
      setCursor(undefined);
      setAllRows([]);
    },
    [action, resourceType, actorId, until],
  );

  const handleUntilChange = useCallback(
    (v: string) => {
      setUntil(v);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      setDebouncedFilters({
        action: action || undefined,
        resource_type: resourceType || undefined,
        actor_id: actorId || undefined,
        since: since || undefined,
        until: v || undefined,
      });
      setCursor(undefined);
      setAllRows([]);
    },
    [action, resourceType, actorId, since],
  );

  /* ---- cursor / accumulator ---- */
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [allRows, setAllRows] = useState<AuditRow[]>([]);

  /* ---- query ---- */
  const query = useQuery({
    queryKey: ["audit-log", debouncedFilters, cursor] as const,
    queryFn: () => auditLogApi.list({ ...debouncedFilters, cursor, limit: 50 }),
    staleTime: 60_000,
    retry: 1,
  });

  /* Merge new page with accumulator (dedup by id) */
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

  const handleRetry = useCallback(() => {
    setCursor(undefined);
    setAllRows([]);
  }, []);

  /* ---- selected row ---- */
  const [selectedRow, setSelectedRow] = useState<AuditRow | null>(null);

  /* ---- CSV export ---- */
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

  /* ---- table columns ---- */
  const columns: Column<AuditRow>[] = [
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
        <span
          className="font-mono text-xs font-semibold text-[var(--text-primary)]"
          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
        >
          {row.action}
        </span>
      ),
    },
    {
      key: "resource",
      header: t("col.resource"),
      cell: (row) => (
        <div className="flex flex-col gap-0.5">
          <span className="text-xs font-semibold text-[var(--text-primary)]">
            {row.resource_type}
          </span>
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

  /* ---- render ---- */

  if (query.isPending && rowsToShow.length === 0) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <h1 className="mb-1 text-lg font-bold tracking-tight text-[var(--text-primary)]">
          {t("pageTitle")}
        </h1>
        <p className="mb-5 text-sm text-[var(--text-secondary)]">
          {t("pageSubtitle")}
        </p>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (query.isError && rowsToShow.length === 0) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <h1 className="mb-1 text-lg font-bold tracking-tight text-[var(--text-primary)]">
          {t("pageTitle")}
        </h1>
        <p className="mb-5 text-sm text-[var(--text-secondary)]">
          {t("pageSubtitle")}
        </p>
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              type="button"
              onClick={handleRetry}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {t("retry")}
            </button>
          }
        />
      </div>
    );
  }

  return (
    <>
      <div className="marketplace-card rounded-[12px] p-5">
        {/* Header */}
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
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

        {/* Filter bar */}
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label
              htmlFor="audit-filter-action"
              className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
            >
              {t("filter.action")}
            </label>
            <Input
              id="audit-filter-action"
              value={action}
              onChange={(e) => handleActionChange(e.target.value)}
              placeholder={t("filter.actionPlaceholder")}
            />
          </div>
          <div>
            <label
              htmlFor="audit-filter-resource-type"
              className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
            >
              {t("filter.resourceType")}
            </label>
            <Input
              id="audit-filter-resource-type"
              value={resourceType}
              onChange={(e) => handleResourceTypeChange(e.target.value)}
              placeholder={t("filter.resourceTypePlaceholder")}
            />
          </div>
          <div>
            <label
              htmlFor="audit-filter-actor-id"
              className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
            >
              {t("filter.actorId")}
            </label>
            <Input
              id="audit-filter-actor-id"
              value={actorId}
              onChange={(e) => handleActorIdChange(e.target.value)}
              placeholder={t("filter.actorIdPlaceholder")}
            />
          </div>
          <div className="flex gap-2">
            <div className="flex-1">
              <label
                htmlFor="audit-filter-since"
                className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
              >
                {t("filter.since")}
              </label>
              <Input
                id="audit-filter-since"
                type="date"
                value={since}
                onChange={(e) => handleSinceChange(e.target.value)}
              />
            </div>
            <div className="flex-1">
              <label
                htmlFor="audit-filter-until"
                className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
              >
                {t("filter.until")}
              </label>
              <Input
                id="audit-filter-until"
                type="date"
                value={until}
                onChange={(e) => handleUntilChange(e.target.value)}
              />
            </div>
          </div>
        </div>

        {/* Table */}
        <div
          className={cn(
            "overflow-x-auto rounded-xl border border-white/60 bg-white/82 backdrop-blur-md",
          )}
          role="region"
          aria-label={t("pageTitle")}
        >
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">{t("pageTitle")}</caption>
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
              {rowsToShow.length === 0 && !query.isPending ? (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="px-3.5 py-10 text-center"
                  >
                    <EmptyState
                      kind="empty"
                      icon={ClipboardText}
                      title={t("emptyTitle")}
                      description={t("emptyBody")}
                    />
                  </td>
                </tr>
              ) : null}
              {rowsToShow.map((row) => (
                <tr
                  key={row.id}
                  className="cursor-pointer border-b border-white/40 align-middle transition-colors last:border-0 hover:bg-white/60 focus-within:bg-white/60"
                  onClick={() => setSelectedRow(row)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelectedRow(row);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                  aria-label={`${row.action} — ${row.resource_type}`}
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
              {query.isPending && rowsToShow.length > 0 && (
                <tr>
                  <td colSpan={columns.length} className="px-3.5 py-2.5">
                    <Skeleton className="h-4 w-full" />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Load more */}
        {query.data?.next_cursor && (
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

      <AuditDetailSheet row={selectedRow} onClose={() => setSelectedRow(null)} />
    </>
  );
}
