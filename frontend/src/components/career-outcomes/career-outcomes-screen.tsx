"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Buildings,
  GraduationCap,
  LightbulbFilament,
  SealCheck,
  ShieldWarning,
  SignIn,
  Sparkle,
  Trophy,
} from "@phosphor-icons/react";
import {
  DataTable,
  EmptyState,
  StatusBadge,
  type Column,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { formatMonthYear } from "@/lib/format";
import {
  ApiError,
  careerOutcomesApi,
  type CareerOutcomeRecord,
} from "@/lib/api";

type CareerInsightKey =
  | "insightManyOutcomes"
  | "insightDiverseEmployers"
  | "insightHighTrust"
  | "insightNoOutcomes";

function deriveCareerInsights(
  totalOutcomes: number,
  topEmployers: number,
  highTrustCount: number,
): CareerInsightKey[] {
  const out: CareerInsightKey[] = [];
  if (totalOutcomes === 0) { out.push("insightNoOutcomes"); return out; }
  if (totalOutcomes >= 10) out.push("insightManyOutcomes");
  if (topEmployers >= 5) out.push("insightDiverseEmployers");
  if (highTrustCount > 0) out.push("insightHighTrust");
  return out.slice(0, 3);
}

export function CareerOutcomesScreen() {
  const t = useTranslations("careerOutcomes");
  const tStates = useTranslations("states");
  const locale = useLocale();

  const query = useQuery({
    queryKey: ["university", "career-outcomes", "kpi", locale],
    queryFn: () => careerOutcomesApi.getKpi(locale),
    retry: false,
  });

  /* ---- Permission / auth states ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader title={t("title")} description={t("subtitle")} />
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={
              err.isPermissionError
                ? tStates("permissionTitle")
                : tStates("authTitle")
            }
            description={
              err.isPermissionError ? t("permissionBody") : tStates("authBody")
            }
          />
        </>
      );
    }
  }

  const data = query.data;
  const loading = query.isPending;

  const columns: Column<CareerOutcomeRecord>[] = [
    {
      key: "position",
      header: t("colPosition"),
      cell: (r) => (
        <span className="font-semibold text-[var(--text-primary)]">
          {r.position_title ?? t("untitledPosition")}
        </span>
      ),
    },
    {
      key: "employer",
      header: t("colEmployer"),
      cell: (r) => (
        <span className="text-[var(--text-secondary)]">{r.employer_name}</span>
      ),
    },
    {
      key: "outcome",
      header: t("colOutcome"),
      cell: (r) => <StatusBadge tone="accepted">{r.outcome}</StatusBadge>,
    },
    {
      key: "trust",
      header: t("colTrust"),
      cell: (r) => (
        <span className="inline-flex items-center gap-1 text-xs text-[var(--text-muted)]">
          <SealCheck size={14} weight="duotone" aria-hidden />
          {r.trust_label}
        </span>
      ),
    },
    {
      key: "start",
      header: t("colStart"),
      cell: (r) =>
        r.start_date ? (
          <span className="text-[var(--text-secondary)]">
            {formatMonthYear(r.start_date, locale)}
          </span>
        ) : (
          <span className="text-[var(--text-muted)]">—</span>
        ),
    },
  ];

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />

      {/* Provenance note: this surface holds no student PII and no salary. */}
      <p className="mb-5 rounded-xl border border-white/50 bg-white/72 px-4 py-3 text-sm text-[var(--text-secondary)] backdrop-blur-sm">
        {t("privacyNote")}
      </p>

      {/* KPI strip */}
      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard
          label={t("kpiTotal")}
          value={data ? String(data.total_outcomes) : "—"}
          loading={loading}
          icon={<GraduationCap aria-hidden weight="duotone" className="size-5 text-white" />}
          iconBg="icon-chip-primary"
        />
        <StatCard
          label={t("kpiEmployers")}
          value={data ? String(data.top_employers.length) : "—"}
          loading={loading}
          icon={<Buildings aria-hidden weight="duotone" className="size-5 text-white" />}
          iconBg="icon-chip-success"
        />
        <StatCard
          label={t("kpiEstimated")}
          value={
            data
              ? String(
                  data.by_trust_level.find((b) => b.trust_level === 4)?.count ??
                    0,
                )
              : "—"
          }
          loading={loading}
          icon={<Trophy aria-hidden weight="duotone" className="size-5 text-white" />}
          iconBg="icon-chip-warning"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_minmax(0,360px)]">
        {/* Recent outcomes table */}
        <section>
          <h2 className="mb-2.5 text-sm font-semibold text-[var(--text-primary)]">
            {t("recentTitle")}
          </h2>
          <DataTable
            columns={columns}
            rows={data?.recent ?? []}
            getRowId={(r) => r.id}
            loading={loading}
            caption={t("recentTitle")}
            empty={{
              kind: "empty",
              icon: GraduationCap,
              title: t("empty"),
              description: t("emptyBody"),
            }}
          />
        </section>

        {/* Top employers + trust-level mix */}
        <aside className="space-y-5">
          <section className="rounded-2xl border border-white/60 bg-white/82 backdrop-blur-md p-4">
            <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-[var(--text-primary)]">
              <Buildings size={16} weight="duotone" aria-hidden />
              {t("topEmployersTitle")}
            </h2>
            {data && data.top_employers.length > 0 ? (
              <ul className="space-y-2">
                {data.top_employers.map((e) => (
                  <li
                    key={e.employer_name}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="truncate text-[var(--text-secondary)]">
                      {e.employer_name}
                    </span>
                    <span className="shrink-0 font-semibold text-[var(--text-primary)]">
                      {e.count}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-[var(--text-muted)]">{t("empty")}</p>
            )}
          </section>

          <section className="rounded-2xl border border-white/60 bg-white/82 backdrop-blur-md p-4">
            <h2 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">
              {t("trustMixTitle")}
            </h2>
            {data && data.by_trust_level.length > 0 ? (
              <ul className="space-y-2">
                {data.by_trust_level.map((b) => (
                  <li
                    key={b.trust_level}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="truncate text-[var(--text-secondary)]">
                      {b.label}
                    </span>
                    <span className="shrink-0 font-semibold text-[var(--text-primary)]">
                      {b.count}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-[var(--text-muted)]">{t("empty")}</p>
            )}
          </section>

          {/* ── AI Career Outcomes Insights ── */}
          {data && (() => {
            const highTrustCount = data.by_trust_level.find((b) => b.trust_level === 4)?.count ?? 0;
            const insights = deriveCareerInsights(data.total_outcomes, data.top_employers.length, highTrustCount);
            if (!insights.length) return null;
            return (
              <section
                aria-label={t("aiInsightsTitle")}
                className="rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-4 backdrop-blur-xl"
              >
                <div className="mb-3 flex items-center gap-2">
                  <span className="flex size-6 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                    <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
                  </span>
                  <p className="text-sm font-semibold text-[var(--text-primary)]">{t("aiInsightsTitle")}</p>
                </div>
                <ul className="space-y-1.5">
                  {insights.map((key) => (
                    <li key={key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                      <LightbulbFilament aria-hidden className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                      {t(key)}
                    </li>
                  ))}
                </ul>
              </section>
            );
          })()}
        </aside>
      </div>
    </>
  );
}

function StatCard({
  label,
  value,
  loading,
  icon,
  iconBg = "icon-chip-primary",
}: {
  label: string;
  value: string;
  loading: boolean;
  icon: React.ReactNode;
  iconBg?: string;
}) {
  return (
    <div className="rounded-2xl border border-white/60 bg-white/85 px-5 py-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)] backdrop-blur-xl transition-all hover:-translate-y-0.5 hover:shadow-[0_6px_24px_rgba(11,34,57,0.10)]">
      <div
        className={`mb-3 flex size-11 items-center justify-center rounded-xl shadow-sm ${iconBg}`}
      >
        {icon}
      </div>
      <p className="text-3xl font-black tracking-tight text-[var(--text-primary)]">
        {loading ? "…" : value}
      </p>
      <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">{label}</p>
    </div>
  );
}
