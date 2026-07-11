"use client";

import * as React from "react";
import { useTranslations, useLocale } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { Button, useToast } from "@/components/ui";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  DataTable,
  type ColumnDef,
  DetailSheet,
  DetailSheetSection,
  DetailRow,
  EmptyState,
} from "@/components/kit";
import { PageHeader } from "@/components/layout/page-header";
import { auditLogApi, type AuditRow, type AuditLogParams } from "@/lib/api/audit-log";
import { formatDateTime } from "@/lib/format";

const MONO = "font-mono text-[0.7rem]";
const MONO_STYLE: React.CSSProperties = { fontFamily: "'JetBrains Mono', ui-monospace, monospace" };

/* -------------------------------------------------------------------------- */
/* Diff renderers                                                              */
/* -------------------------------------------------------------------------- */

function renderValue(v: unknown): string {
  if (v === null || v === undefined) return "null";
  return typeof v === "object" ? JSON.stringify(v) : String(v);
}

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
        <p className="mb-1 text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="type-small text-muted-foreground">{nullLabel}</p>
      </div>
    );
  }
  return (
    <div>
      <p className="mb-1.5 text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <dl className="space-y-1 rounded-lg border border-border bg-[var(--bg-subtle)] p-3">
        {Object.entries(data).map(([key, value]) => (
          <div key={key} className="flex flex-wrap gap-x-2">
            <dt className={`${MONO} font-semibold text-muted-foreground`} style={MONO_STYLE}>
              {key}:
            </dt>
            <dd className={`${MONO} break-all text-foreground`} style={MONO_STYLE}>
              {renderValue(value)}
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
  const allKeys = new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]);
  const changed = [...allKeys].filter(
    (k) => JSON.stringify((before ?? {})[k] ?? null) !== JSON.stringify((after ?? {})[k] ?? null),
  );
  if (changed.length === 0) return <p className="type-small text-muted-foreground">{noDiffLabel}</p>;
  return (
    <dl className="space-y-1.5 rounded-lg border border-border bg-[var(--bg-subtle)] p-3">
      {changed.map((key) => (
        <div key={key} className="grid grid-cols-[auto_1fr_1fr] gap-x-2">
          <dt className={`${MONO} font-semibold text-muted-foreground`} style={MONO_STYLE}>
            {key}
          </dt>
          <dd
            className={`${MONO} break-all line-through opacity-70`}
            style={{ ...MONO_STYLE, color: "var(--content-danger)" }}
          >
            {renderValue((before ?? {})[key])}
          </dd>
          <dd className={`${MONO} break-all`} style={{ ...MONO_STYLE, color: "var(--content-success)" }}>
            {renderValue((after ?? {})[key])}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/* -------------------------------------------------------------------------- */
/* Detail drawer                                                               */
/* -------------------------------------------------------------------------- */

function AuditDetailSheet({ row, onClose }: { row: AuditRow | null; onClose: () => void }) {
  const t = useTranslations("adminConsole.audit.sheet");
  const locale = useLocale();
  const hasBoth = Boolean(row && row.before !== null && row.after !== null);

  return (
    <DetailSheet
      open={row !== null}
      onClose={onClose}
      title={row?.action ?? t("title")}
      subtitle={row ? row.resource_type : undefined}
      closeLabel={t("closeLabel")}
      width="lg"
    >
      {row && (
        <>
          <DetailSheetSection title={t("title")}>
            <dl className="space-y-0.5">
              <DetailRow label={t("labelId")}>
                <span className={MONO} style={MONO_STYLE}>
                  {row.id}
                </span>
              </DetailRow>
              <DetailRow label={t("labelOccurredAt")}>{formatDateTime(row.occurred_at, locale)}</DetailRow>
              <DetailRow label={t("labelAction")}>
                <span className={MONO} style={MONO_STYLE}>
                  {row.action}
                </span>
              </DetailRow>
              <DetailRow label={t("labelResourceType")}>{row.resource_type}</DetailRow>
              <DetailRow label={t("labelResourceId")}>
                <span className={MONO} style={MONO_STYLE}>
                  {row.resource_id ?? t("nullValue")}
                </span>
              </DetailRow>
              {row.actor_email && <DetailRow label={t("labelActorEmail")}>{row.actor_email}</DetailRow>}
              <DetailRow label={t("labelActorId")}>
                <span className={MONO} style={MONO_STYLE}>
                  {row.actor_id ?? t("nullValue")}
                </span>
              </DetailRow>
              {row.actor_org_id && (
                <DetailRow label={t("labelActorOrgId")}>
                  <span className={MONO} style={MONO_STYLE}>
                    {row.actor_org_id}
                  </span>
                </DetailRow>
              )}
            </dl>
          </DetailSheetSection>

          <DetailSheetSection title={t("labelBefore") + " / " + t("labelAfter")}>
            <div className="space-y-4">
              {hasBoth && <DiffHighlight before={row.before} after={row.after} noDiffLabel={t("noDiff")} />}
              <DiffSection label={t("labelBefore")} data={row.before} nullLabel={t("nullValue")} />
              <DiffSection label={t("labelAfter")} data={row.after} nullLabel={t("nullValue")} />
            </div>
          </DetailSheetSection>
        </>
      )}
    </DetailSheet>
  );
}

/* -------------------------------------------------------------------------- */
/* Filter input                                                                */
/* -------------------------------------------------------------------------- */

function FilterField({
  id,
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-9 w-full rounded-lg border border-border bg-card px-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Screen                                                                      */
/* -------------------------------------------------------------------------- */

export function AuditLogScreen() {
  const t = useTranslations("adminConsole.audit");
  const locale = useLocale();
  const { show: showToast } = useToast();

  const [action, setAction] = React.useState("");
  const [resourceType, setResourceType] = React.useState("");
  const [actorId, setActorId] = React.useState("");
  const [since, setSince] = React.useState("");
  const [until, setUntil] = React.useState("");

  const [debouncedFilters, setDebouncedFilters] = React.useState<AuditLogParams>({});
  const [cursor, setCursor] = React.useState<string | undefined>(undefined);
  const [allRows, setAllRows] = React.useState<AuditRow[]>([]);
  const [selectedRow, setSelectedRow] = React.useState<AuditRow | null>(null);
  const [exporting, setExporting] = React.useState(false);

  const filters = React.useMemo<AuditLogParams>(
    () => ({
      action: action || undefined,
      resource_type: resourceType || undefined,
      actor_id: actorId || undefined,
      since: since || undefined,
      until: until || undefined,
    }),
    [action, resourceType, actorId, since, until],
  );

  // Debounce filter changes; reset the cursor/accumulator on a new filter set.
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedFilters(filters);
      setCursor(undefined);
      setAllRows([]);
    }, 250);
    return () => clearTimeout(timer);
  }, [filters]);

  const query = useQuery({
    queryKey: ["audit-log", debouncedFilters, cursor] as const,
    queryFn: () => auditLogApi.list({ ...debouncedFilters, cursor, limit: 50 }),
    staleTime: 60_000,
    retry: 1,
  });

  const rowsToShow: AuditRow[] = React.useMemo(() => {
    if (!query.data) return allRows;
    if (!cursor) return query.data.items;
    const existing = new Set(allRows.map((r) => r.id));
    return [...allRows, ...query.data.items.filter((r) => !existing.has(r.id))];
  }, [query.data, cursor, allRows]);

  const handleLoadMore = React.useCallback(() => {
    if (query.data?.next_cursor) {
      setAllRows(rowsToShow);
      setCursor(query.data.next_cursor);
    }
  }, [query.data?.next_cursor, rowsToShow]);

  const handleRetry = React.useCallback(() => {
    setCursor(undefined);
    setAllRows([]);
  }, []);

  const handleExport = React.useCallback(async () => {
    setExporting(true);
    try {
      const blob = await auditLogApi.exportCsv(filters);
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
  }, [filters, showToast, t]);

  const columns: ColumnDef<AuditRow, unknown>[] = [
    {
      accessorKey: "occurred_at",
      header: t("col.time"),
      cell: ({ row }) => (
        <span className="whitespace-nowrap type-small text-muted-foreground">
          {formatDateTime(row.original.occurred_at, locale)}
        </span>
      ),
    },
    {
      accessorKey: "actor_email",
      header: t("col.actor"),
      cell: ({ row }) => (
        <span className="text-[0.8125rem] text-foreground">{row.original.actor_email ?? row.original.actor_id ?? "—"}</span>
      ),
    },
    {
      accessorKey: "action",
      header: t("col.action"),
      cell: ({ row }) => (
        <span className={`${MONO} font-semibold text-foreground`} style={MONO_STYLE}>
          {row.original.action}
        </span>
      ),
    },
    {
      accessorKey: "resource_type",
      header: t("col.resource"),
      enableSorting: false,
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="flex flex-col gap-0.5">
            <span className="text-[0.8125rem] font-semibold text-foreground">{r.resource_type}</span>
            {r.resource_id && (
              <span className={`${MONO} text-muted-foreground`} style={MONO_STYLE}>
                {r.resource_id.length > 20 ? `${r.resource_id.slice(0, 8)}…${r.resource_id.slice(-4)}` : r.resource_id}
              </span>
            )}
          </div>
        );
      },
    },
  ];

  const header = (
    <PageHeader
      title={t("pageTitle")}
      subtitle={t("pageSubtitle")}
      actions={
        <Button variant="secondary" size="sm" onClick={() => void handleExport()} loading={exporting}>
          <Download className="size-4" strokeWidth={1.8} />
          {t("exportCsv")}
        </Button>
      }
    />
  );

  if (query.isError && rowsToShow.length === 0) {
    return (
      <>
        {header}
        <EmptyState
          kind="error"
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <Button variant="secondary" onClick={handleRetry}>
              {t("retry")}
            </Button>
          }
        />
      </>
    );
  }

  return (
    <>
      {header}

      <Card>
        <CardHeader>
          <div>
            <CardTitle>{t("pageTitle")}</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Filter grid */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <FilterField
              id="audit-filter-action"
              label={t("filter.action")}
              value={action}
              onChange={setAction}
              placeholder={t("filter.actionPlaceholder")}
            />
            <FilterField
              id="audit-filter-resource-type"
              label={t("filter.resourceType")}
              value={resourceType}
              onChange={setResourceType}
              placeholder={t("filter.resourceTypePlaceholder")}
            />
            <FilterField
              id="audit-filter-actor-id"
              label={t("filter.actorId")}
              value={actorId}
              onChange={setActorId}
              placeholder={t("filter.actorIdPlaceholder")}
            />
            <div className="flex gap-2">
              <div className="flex-1">
                <FilterField id="audit-filter-since" label={t("filter.since")} value={since} onChange={setSince} type="date" />
              </div>
              <div className="flex-1">
                <FilterField id="audit-filter-until" label={t("filter.until")} value={until} onChange={setUntil} type="date" />
              </div>
            </div>
          </div>

          <DataTable
            columns={columns}
            data={rowsToShow}
            getRowId={(r) => String(r.id)}
            loading={query.isPending && rowsToShow.length === 0}
            onRowClick={(r) => setSelectedRow(r)}
            activeRowId={selectedRow ? String(selectedRow.id) : undefined}
            empty={<EmptyState kind="empty" title={t("emptyTitle")} description={t("emptyBody")} />}
          />

          {query.data?.next_cursor && (
            <div className="flex justify-center">
              <Button variant="secondary" onClick={handleLoadMore} loading={query.isFetching}>
                {t("loadMore")}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <AuditDetailSheet row={selectedRow} onClose={() => setSelectedRow(null)} />
    </>
  );
}
