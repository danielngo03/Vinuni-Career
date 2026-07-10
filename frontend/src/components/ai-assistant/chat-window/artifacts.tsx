"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  AlertTriangle,
  Briefcase,
  Check,
  ChevronDown,
  Download,
  Loader2,
  RefreshCw,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { cn } from "@/lib/utils";
import { env } from "@/lib/env";
import type { ChatMessage } from "@/lib/api";
import { getAccessToken } from "@/lib/api/session";
import { Card, StatusChip } from "@/components/kit";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

/* ------------------------------ Artifact types ----------------------------- */

/** A chart spec the backend emits for the FE to render with Recharts. */
export type ChartSpec = {
  type?: string;
  title?: string;
  x_key?: string;
  series?: { key: string; name?: string }[];
  data?: Record<string, number | string>[];
};

/** A funnel/flow diagram spec the backend emits for the FE to draw (no lib). */
export type DiagramSpec = {
  type?: string;
  title?: string;
  note?: string;
  stages?: { label: string; count: number; pct: number }[];
};

export type DownloadArtifactData = {
  kind: "download";
  download_path?: string;
  filename?: string;
  row_count?: number;
  format?: string;
};

export type ChartArtifactData = { kind: "chart"; chart?: ChartSpec };

export type DiagramArtifactData = { kind: "diagram"; diagram?: DiagramSpec };

export type ImageArtifactData = {
  kind: "image";
  download_path?: string;
  filename?: string;
  alt?: string;
  width?: number;
  height?: number;
};

export type JobDraftWarning = { code: string; message: string };

export type JobDraftFields = {
  title?: string | null;
  description?: string | null;
  requirements?: string | null;
  benefits?: string | null;
  employment_type?: string | null;
  location_type?: string | null;
  location_city?: string | null;
  required_skills?: string[] | null;
  preferred_skills?: string[] | null;
  experience_min_years?: number | null;
  experience_max_years?: number | null;
  seniority_level?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: string | null;
};

export type JobDraftArtifactData = {
  kind: "job_draft";
  draft?: JobDraftFields;
  missing_required?: string[];
  warnings?: JobDraftWarning[];
  ready?: boolean;
};

/** The full render-artifact union attached to assistant messages. */
export type MessageArtifact =
  | DownloadArtifactData
  | ChartArtifactData
  | DiagramArtifactData
  | ImageArtifactData
  | JobDraftArtifactData;

/** Read (tolerantly) the artifacts array from a message's tool_result. */
export function readArtifacts(message: ChatMessage): MessageArtifact[] {
  const raw = (message.tool_result as { artifacts?: unknown } | null)?.artifacts;
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (a): a is MessageArtifact =>
      !!a && typeof a === "object" && typeof (a as { kind?: unknown }).kind === "string",
  );
}

/** Render backend-attached artifacts (download / chart / diagram / image / job draft). */
export function MessageArtifacts({
  message,
  expanded,
}: {
  message: ChatMessage;
  expanded: boolean;
}) {
  const artifacts = readArtifacts(message);
  if (artifacts.length === 0) return null;
  return (
    <div className="mt-2 flex w-full min-w-0 flex-col gap-2">
      {artifacts.map((a, i) => {
        switch (a.kind) {
          case "download":
            return a.download_path ? <DownloadArtifact key={i} artifact={a} /> : null;
          case "chart":
            return a.chart ? <ChartArtifact key={i} artifact={a} expanded={expanded} /> : null;
          case "diagram":
            return a.diagram ? <FunnelDiagram key={i} artifact={a} /> : null;
          case "image":
            return a.download_path ? <ImageArtifact key={i} artifact={a} /> : null;
          case "job_draft":
            return a.draft ? <JobDraftCard key={i} artifact={a} /> : null;
          default:
            return null;
        }
      })}
    </div>
  );
}

/* --------------------------------- Shared --------------------------------- */

/** Authenticated fetch of a chat export/artifact binary. */
async function fetchArtifactBlob(path: string): Promise<Blob> {
  const base = env.apiBaseUrl.replace(/\/$/, "");
  const token = getAccessToken();
  const res = await fetch(`${base}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
  });
  if (!res.ok) throw new Error(`artifact fetch failed: ${res.status}`);
  return res.blob();
}

function triggerBlobDownload(url: string, filename: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/* -------------------------------- Download -------------------------------- */

function DownloadArtifact({ artifact }: { artifact: DownloadArtifactData }) {
  const t = useTranslations("aiAssistant");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const onDownload = async () => {
    if (!artifact.download_path) return;
    setBusy(true);
    setFailed(false);
    try {
      const blob = await fetchArtifactBlob(artifact.download_path);
      const url = URL.createObjectURL(blob);
      triggerBlobDownload(url, artifact.filename || "export.xlsx");
      URL.revokeObjectURL(url);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <button
      type="button"
      onClick={onDownload}
      disabled={busy}
      className="inline-flex w-fit items-center gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-left outline-none transition-colors hover:border-[var(--field-focus-border)] hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)] disabled:cursor-not-allowed disabled:opacity-60"
    >
      {busy ? (
        <Loader2 className="size-4 shrink-0 animate-spin text-[var(--content-ai)]" />
      ) : (
        <Download
          aria-hidden
          strokeWidth={1.9}
          className="size-4 shrink-0 text-[var(--content-ai)]"
        />
      )}
      <span className="flex flex-col items-start leading-tight">
        <span className="type-small font-semibold text-[var(--text-primary)]">
          {failed ? t("download.failedRetry") : (artifact.filename ?? t("download.fallbackName"))}
        </span>
        {typeof artifact.row_count === "number" && !failed && (
          <span className="type-caption font-normal tabular-nums text-[var(--text-muted)]">
            {artifact.format === "xlsx" ? t("download.fileExcel") : t("download.fileGeneric")} ·{" "}
            {t("download.rowCount", { count: artifact.row_count })}
          </span>
        )}
      </span>
    </button>
  );
}

/* ---------------------------------- Image ---------------------------------- */

/** Auth-fetched inline image with skeleton, retry, full-view dialog, download. */
function ImageArtifact({ artifact }: { artifact: ImageArtifactData }) {
  const t = useTranslations("aiAssistant");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [url, setUrl] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const [open, setOpen] = useState(false);
  const path = artifact.download_path;

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    setState("loading");
    setUrl(null);
    fetchArtifactBlob(path)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
        setState("ready");
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path, nonce]);

  if (!path) return null;
  const alt = artifact.alt?.trim() || artifact.filename || t("image.altFallback");

  if (state === "loading") {
    return (
      <div
        role="status"
        aria-label={t("image.loading")}
        className="w-full max-w-md animate-skeleton rounded-xl bg-[var(--bg-muted)]"
        style={{
          aspectRatio:
            artifact.width && artifact.height
              ? `${artifact.width} / ${artifact.height}`
              : "4 / 3",
          maxHeight: "24rem",
        }}
      />
    );
  }

  if (state === "error") {
    return (
      <button
        type="button"
        onClick={() => setNonce((n) => n + 1)}
        className="inline-flex w-fit items-center gap-2 rounded-lg border border-[var(--content-danger)]/30 bg-[var(--content-danger-soft)] px-3 py-2 text-left outline-none transition-colors hover:border-[var(--content-danger)]/50 focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
      >
        <RefreshCw aria-hidden strokeWidth={1.9} className="size-4 shrink-0 text-[var(--content-danger)]" />
        <span className="type-small font-semibold text-[var(--content-danger)]">
          {t("image.failed")} — {t("image.retry")}
        </span>
      </button>
    );
  }

  if (!url) return null;
  return (
    <figure className="w-full min-w-0">
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={t("image.view")}
        title={t("image.view")}
        className="block w-fit max-w-full overflow-hidden rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] outline-none transition-colors hover:border-[var(--field-focus-border)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={url}
          alt={alt}
          width={artifact.width}
          height={artifact.height}
          className="max-h-96 w-auto max-w-full object-contain"
        />
      </button>
      <figcaption className="mt-1.5 flex items-center gap-2">
        <button
          type="button"
          onClick={() => triggerBlobDownload(url, artifact.filename || "image.png")}
          className="type-caption inline-flex items-center gap-1.5 rounded-lg px-2 py-1 font-medium text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
        >
          <Download aria-hidden strokeWidth={1.9} className="size-3.5 shrink-0" />
          {t("image.download")}
        </button>
      </figcaption>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-[min(94vw,64rem)] gap-2 p-3 sm:max-w-[min(92vw,64rem)]">
          <DialogTitle className="sr-only">{alt}</DialogTitle>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={url} alt={alt} className="max-h-[80vh] w-full rounded-lg object-contain" />
        </DialogContent>
      </Dialog>
    </figure>
  );
}

/* ---------------------------------- Charts --------------------------------- */

// Content data-viz palette (locked categorical order, DESIGN.md §1.1.2).
const CHART_COLORS = [
  "var(--viz-indigo)",
  "var(--viz-teal)",
  "var(--viz-amber)",
  "var(--viz-rose)",
  "var(--viz-sky)",
  "var(--viz-emerald)",
  "var(--viz-violet)",
  "var(--viz-orange)",
];

const TOOLTIP_STYLE: React.CSSProperties = {
  fontSize: 13,
  borderRadius: 8,
  background: "var(--surface-card)",
  border: "1px solid var(--border-default)",
  color: "var(--text-primary)",
};

/** Render a backend-emitted analytics chart (bar/line/area/donut) with Recharts. */
function ChartArtifact({
  artifact,
  expanded,
}: {
  artifact: ChartArtifactData;
  expanded: boolean;
}) {
  const chart = artifact.chart;
  if (!chart || !Array.isArray(chart.data) || chart.data.length === 0) return null;
  const xKey = chart.x_key ?? "label";
  const series = chart.series && chart.series.length > 0 ? chart.series : [{ key: "value" }];
  const many = chart.data.length > 4;

  // Shared presentational props (inlined per chart — Recharts inspects direct
  // children by type, so we avoid fragment composition entirely).
  const gridProps = {
    strokeDasharray: "3 3",
    stroke: "var(--border-subtle)",
    vertical: false,
  } as const;
  const yAxisProps = {
    tick: { fontSize: 11, fill: "var(--text-muted)" },
    allowDecimals: false,
    width: 34,
  } as const;
  const tooltipProps = {
    contentStyle: TOOLTIP_STYLE,
    labelStyle: { color: "var(--text-secondary)" },
    cursor: { fill: "var(--bg-muted)", fillOpacity: 0.6 },
  } as const;
  const legendWrapperStyle = { fontSize: 13, color: "var(--text-secondary)" } as const;
  const margin = { top: 4, right: 8, bottom: 4, left: -10 };

  let body: React.ReactElement;
  if (chart.type === "line") {
    body = (
      <LineChart data={chart.data} margin={margin}>
        <CartesianGrid {...gridProps} />
        <YAxis {...yAxisProps} />
        <Tooltip {...tooltipProps} />
        {series.length > 1 && <Legend wrapperStyle={legendWrapperStyle} />}
        <XAxis
          dataKey={xKey}
          tick={{ fontSize: 11, fill: "var(--text-muted)" }}
          interval="preserveStartEnd"
        />
        {series.map((sr, i) => (
          <Line
            key={sr.key}
            type="monotone"
            dataKey={sr.key}
            name={sr.name ?? sr.key}
            stroke={CHART_COLORS[i % CHART_COLORS.length]}
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        ))}
      </LineChart>
    );
  } else if (chart.type === "area") {
    body = (
      <AreaChart data={chart.data} margin={margin}>
        <CartesianGrid {...gridProps} />
        <YAxis {...yAxisProps} />
        <Tooltip {...tooltipProps} />
        {series.length > 1 && <Legend wrapperStyle={legendWrapperStyle} />}
        <XAxis
          dataKey={xKey}
          tick={{ fontSize: 11, fill: "var(--text-muted)" }}
          interval="preserveStartEnd"
        />
        {series.map((sr, i) => (
          <Area
            key={sr.key}
            type="monotone"
            dataKey={sr.key}
            name={sr.name ?? sr.key}
            stroke={CHART_COLORS[i % CHART_COLORS.length]}
            fill={CHART_COLORS[i % CHART_COLORS.length]}
            fillOpacity={0.15}
            strokeWidth={2}
          />
        ))}
      </AreaChart>
    );
  } else if (chart.type === "donut" || chart.type === "pie") {
    body = (
      <PieChart>
        <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: "var(--text-secondary)" }} />
        <Legend wrapperStyle={legendWrapperStyle} />
        <Pie
          data={chart.data}
          dataKey={series[0]!.key}
          nameKey={xKey}
          innerRadius="55%"
          outerRadius="82%"
          paddingAngle={2}
          stroke="var(--surface-card)"
        >
          {chart.data.map((_, i) => (
            <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
          ))}
        </Pie>
      </PieChart>
    );
  } else {
    // Bar is the default and the graceful fallback for unknown chart types.
    body = (
      <BarChart data={chart.data} margin={margin}>
        <CartesianGrid {...gridProps} />
        <YAxis {...yAxisProps} />
        <Tooltip {...tooltipProps} />
        {series.length > 1 && <Legend wrapperStyle={legendWrapperStyle} />}
        <XAxis
          dataKey={xKey}
          tick={{ fontSize: 11, fill: "var(--text-muted)" }}
          interval={0}
          angle={many ? -20 : 0}
          textAnchor={many ? "end" : "middle"}
          height={many ? 52 : 24}
        />
        {series.map((sr, i) => (
          <Bar
            key={sr.key}
            dataKey={sr.key}
            name={sr.name ?? sr.key}
            fill={CHART_COLORS[i % CHART_COLORS.length]}
            radius={[3, 3, 0, 0]}
            maxBarSize={44}
          />
        ))}
      </BarChart>
    );
  }

  return (
    <figure className="mt-1 w-full rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3">
      {chart.title && (
        <figcaption className="type-small mb-2 font-semibold text-[var(--text-secondary)]">
          {chart.title}
        </figcaption>
      )}
      <div className={cn("w-full", expanded ? "h-[360px]" : "h-[280px]")}>
        <ResponsiveContainer width="100%" height="100%">
          {body}
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

/* ---------------------------------- Funnel --------------------------------- */

/** Render a backend-emitted hiring-funnel diagram (vertical flow, no library). */
function FunnelDiagram({ artifact }: { artifact: DiagramArtifactData }) {
  const t = useTranslations("aiAssistant");
  const diagram = artifact.diagram;
  if (!diagram || !Array.isArray(diagram.stages) || diagram.stages.length === 0) return null;
  return (
    <figure className="mt-1 w-full rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3">
      {diagram.title && (
        <figcaption className="type-small mb-2.5 font-semibold text-[var(--text-secondary)]">
          {diagram.title}
        </figcaption>
      )}
      <div className="flex flex-col gap-2">
        {diagram.stages.map((st, i) => {
          const prev = i > 0 ? diagram.stages![i - 1]! : null;
          const drop =
            prev && prev.count > 0
              ? Math.max(0, Math.round((1 - st.count / prev.count) * 100))
              : null;
          return (
            <div key={i} className="flex items-center gap-2.5">
              <span
                title={st.label}
                className="type-small w-28 shrink-0 truncate font-normal text-[var(--text-secondary)] sm:w-36"
              >
                {st.label}
              </span>
              <div className="relative h-7 min-w-0 flex-1 overflow-hidden rounded-md bg-[var(--bg-muted)]">
                <div
                  className="flex h-full items-center rounded-md bg-[var(--viz-indigo)] px-2 transition-all"
                  style={{ width: `${Math.min(100, Math.max(st.pct, 6))}%` }}
                >
                  <span className="type-caption font-semibold tabular-nums text-white">
                    {st.count}
                  </span>
                </div>
              </div>
              <span className="type-small w-11 shrink-0 text-right font-normal tabular-nums text-[var(--text-muted)]">
                {st.pct}%
              </span>
              <span className="w-14 shrink-0 text-right">
                {drop !== null && (
                  <span
                    title={t("funnelDropOff")}
                    className={cn(
                      "type-caption inline-flex rounded-full px-1.5 py-0.5 font-medium tabular-nums",
                      drop > 0
                        ? "bg-[var(--content-warning-soft)] text-[var(--content-warning)]"
                        : "bg-[var(--bg-muted)] text-[var(--text-muted)]",
                    )}
                  >
                    −{drop}%
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>
      {diagram.note && (
        <p className="type-caption mt-2.5 font-normal text-[var(--text-muted)]">{diagram.note}</p>
      )}
    </figure>
  );
}

/* --------------------------------- Job draft -------------------------------- */

const JOB_DRAFT_FIELDS = [
  "title",
  "description",
  "requirements",
  "benefits",
  "employment_type",
  "location_type",
  "location_city",
  "required_skills",
  "preferred_skills",
  "experience_min_years",
  "experience_max_years",
  "seniority_level",
  "salary_min",
  "salary_max",
  "salary_currency",
] as const;

const LONG_SECTIONS = ["description", "requirements", "benefits"] as const;

function isFilled(v: unknown): boolean {
  if (v === null || v === undefined) return false;
  if (typeof v === "string") return v.trim() !== "";
  if (Array.isArray(v)) return v.length > 0;
  return true;
}

function prettify(key: string): string {
  const s = key.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Informational JD draft card — publishing still goes through the confirm card. */
function JobDraftCard({ artifact }: { artifact: JobDraftArtifactData }) {
  const t = useTranslations("aiAssistant");
  const locale = useLocale();
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({});

  const draft = artifact.draft ?? {};
  const missing = artifact.missing_required ?? [];
  const warnings = artifact.warnings ?? [];
  const ready = artifact.ready === true;

  const fieldLabel = (key: string) =>
    t.has(`jobDraft.fields.${key}`) ? t(`jobDraft.fields.${key}`) : prettify(key);

  const numberFmt = new Intl.NumberFormat(locale === "vi" ? "vi-VN" : "en-US");
  const facts: string[] = [];
  if (isFilled(draft.employment_type)) facts.push(prettify(draft.employment_type!));
  const location = [
    isFilled(draft.location_type) ? prettify(draft.location_type!) : null,
    isFilled(draft.location_city) ? draft.location_city!.trim() : null,
  ].filter(Boolean);
  if (location.length > 0) facts.push(location.join(" · "));
  if (isFilled(draft.seniority_level)) facts.push(prettify(draft.seniority_level!));
  const expMin = draft.experience_min_years;
  const expMax = draft.experience_max_years;
  if (expMin != null && expMax != null) {
    facts.push(t("jobDraft.expRange", { min: expMin, max: expMax }));
  } else if (expMin != null) {
    facts.push(t("jobDraft.expMin", { min: expMin }));
  } else if (expMax != null) {
    facts.push(t("jobDraft.expMax", { max: expMax }));
  }
  const currency = draft.salary_currency?.trim() || "VND";
  if (draft.salary_min != null && draft.salary_max != null) {
    facts.push(
      `${numberFmt.format(draft.salary_min)}–${numberFmt.format(draft.salary_max)} ${currency}`,
    );
  } else if (draft.salary_min != null) {
    facts.push(`≥ ${numberFmt.format(draft.salary_min)} ${currency}`);
  } else if (draft.salary_max != null) {
    facts.push(`≤ ${numberFmt.format(draft.salary_max)} ${currency}`);
  }

  const knownKeys = new Set<string>(JOB_DRAFT_FIELDS);
  const checklist: { key: string; ok: boolean }[] = [];
  for (const key of JOB_DRAFT_FIELDS) {
    const isMissing = missing.includes(key);
    const filled = isFilled(draft[key]);
    if (filled || isMissing) checklist.push({ key, ok: filled && !isMissing });
  }
  for (const key of missing) {
    if (!knownKeys.has(key)) checklist.push({ key, ok: false });
  }

  const sections = LONG_SECTIONS.filter((key) => isFilled(draft[key])).map((key) => ({
    key,
    value: (draft[key] as string).trim(),
  }));

  return (
    <Card className="mt-1 w-full min-w-0">
      <div className="flex items-start justify-between gap-3 border-b border-[var(--border-subtle)] px-4 py-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span
            aria-hidden
            className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--viz-indigo-soft)]"
          >
            <Briefcase strokeWidth={1.9} className="size-4 text-[var(--viz-indigo)]" />
          </span>
          <div className="min-w-0">
            <p className="type-small truncate font-semibold text-[var(--text-primary)]">
              {draft.title?.trim() || t("jobDraft.untitled")}
            </p>
            <p className="type-caption font-normal text-[var(--text-muted)]">
              {t("jobDraft.subtitle")}
            </p>
          </div>
        </div>
        <StatusChip tone={ready ? "success" : "warning"} dot size="sm" className="mt-0.5">
          {ready ? t("jobDraft.ready") : t("jobDraft.missingCount", { count: missing.length })}
        </StatusChip>
      </div>

      <div className="space-y-3 px-4 py-3">
        {facts.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {facts.map((fact, i) => (
              <StatusChip key={i} tone="neutral" size="sm">
                {fact}
              </StatusChip>
            ))}
          </div>
        )}

        {(isFilled(draft.required_skills) || isFilled(draft.preferred_skills)) && (
          <div className="space-y-1.5">
            {isFilled(draft.required_skills) && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="type-caption font-medium text-[var(--text-muted)]">
                  {fieldLabel("required_skills")}:
                </span>
                {draft.required_skills!.map((skill, i) => (
                  <StatusChip key={i} tone="indigo" size="sm">
                    {skill}
                  </StatusChip>
                ))}
              </div>
            )}
            {isFilled(draft.preferred_skills) && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="type-caption font-medium text-[var(--text-muted)]">
                  {fieldLabel("preferred_skills")}:
                </span>
                {draft.preferred_skills!.map((skill, i) => (
                  <StatusChip key={i} tone="teal" size="sm">
                    {skill}
                  </StatusChip>
                ))}
              </div>
            )}
          </div>
        )}

        {sections.length > 0 && (
          <div className="space-y-1.5">
            {sections.map(({ key, value }) => {
              const open = openSections[key] === true;
              return (
                <div key={key} className="rounded-lg border border-[var(--border-subtle)]">
                  <button
                    type="button"
                    onClick={() => setOpenSections((prev) => ({ ...prev, [key]: !open }))}
                    aria-expanded={open}
                    className="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
                  >
                    <span className="type-small font-semibold text-[var(--text-primary)]">
                      {fieldLabel(key)}
                    </span>
                    <ChevronDown
                      aria-hidden
                      strokeWidth={1.9}
                      className={cn(
                        "size-4 shrink-0 text-[var(--text-muted)] transition-transform",
                        open && "rotate-180",
                      )}
                    />
                  </button>
                  {open && (
                    <div className="border-t border-[var(--border-subtle)] px-3 py-2">
                      <p className="type-small whitespace-pre-wrap font-normal leading-relaxed text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                        {value}
                      </p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {checklist.length > 0 && (
          <div>
            <p className="type-caption font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
              {t("jobDraft.checklist")}
            </p>
            <div className="mt-1.5 grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
              {checklist.map(({ key, ok }) => (
                <div key={key} className="flex items-center gap-1.5">
                  {ok ? (
                    <Check
                      aria-hidden
                      strokeWidth={2}
                      className="size-3.5 shrink-0 text-[var(--content-success)]"
                    />
                  ) : (
                    <AlertTriangle
                      aria-hidden
                      strokeWidth={1.9}
                      className="size-3.5 shrink-0 text-[var(--content-warning)]"
                    />
                  )}
                  <span
                    className={cn(
                      "type-small min-w-0 truncate",
                      ok
                        ? "font-normal text-[var(--text-secondary)]"
                        : "font-medium text-[var(--content-warning)]",
                    )}
                  >
                    {fieldLabel(key)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {warnings.length > 0 && (
          <div className="rounded-lg border border-[var(--content-warning)]/25 bg-[var(--content-warning-soft)] px-3 py-2">
            <p className="type-caption font-semibold text-[var(--content-warning)]">
              {t("jobDraft.warnings")}
            </p>
            <ul className="mt-1 space-y-1">
              {warnings.map((w, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <AlertTriangle
                    aria-hidden
                    strokeWidth={1.9}
                    className="mt-0.5 size-3.5 shrink-0 text-[var(--content-warning)]"
                  />
                  <span className="type-small min-w-0 flex-1 font-normal text-[var(--text-primary)] [overflow-wrap:anywhere]">
                    {w.message}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}
