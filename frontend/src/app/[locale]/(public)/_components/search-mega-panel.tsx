"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, CaretRight, MagnifyingGlass } from "@phosphor-icons/react";
import { searchApi } from "@/lib/api/search";
import type { IndustryBranch, IndustryLeaf, IndustryRoot } from "@/lib/api/search";

interface SearchMegaPanelProps {
  onSelectKeyword: (keyword: string) => void;
  onSelectIndustry: (industry: IndustryLeaf) => void;
  visible: boolean;
}

const SKELETON_WIDTHS = ["75%", "60%", "82%", "68%", "72%", "55%", "78%", "63%"];

export function SearchMegaPanel({
  onSelectKeyword,
  onSelectIndustry,
  visible,
}: SearchMegaPanelProps) {
  const locale = useLocale();
  const t = useTranslations("marketplace.megaPanel");

  const [selectedRoot, setSelectedRoot] = useState<IndustryRoot | null>(null);
  const [selectedBranch, setSelectedBranch] = useState<IndustryBranch | null>(null);

  const { data: industriesData, isLoading: industriesLoading } = useQuery({
    queryKey: ["industries", "tree"],
    queryFn: () => searchApi.industryTree(),
    staleTime: 10 * 60_000,
    enabled: visible,
    retry: false,
  });

  // Popular keywords come from the personalized /search/popular endpoint.
  // Session-aware: shows the user's recent searches first, then global trending.
  const { data: popularData, isLoading: popularLoading } = useQuery({
    queryKey: ["search", "popular", locale],
    queryFn: () => searchApi.popular(locale, 8),
    staleTime: 5 * 60_000,
    enabled: visible,
    retry: false,
  });

  const industries = industriesData ?? [];
  const popularKeywords = popularData?.keywords ?? [];

  const getName = (item: IndustryLeaf) =>
    locale === "vi" ? item.name_vi : item.name_en;

  if (!visible) return null;

  return (
    <div
      className="absolute left-0 right-0 top-full z-50 mt-2 overflow-hidden rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-heavy)] shadow-[0_20px_60px_-4px_rgba(11,34,57,0.18),0_4px_16px_-2px_rgba(11,34,57,0.10)] backdrop-blur-xl"
      role="dialog"
      aria-label={t("ariaLabel")}
    >
      <div className="flex min-h-[240px] divide-x divide-[var(--border-subtle)]">

        {/* ── Left: Personalized popular keywords ── */}
        <div className="w-[220px] shrink-0 py-4 sm:w-[250px]">
          <p className="mb-2 px-4 text-[0.68rem] font-bold uppercase tracking-widest text-[var(--text-muted)]">
            {t("trendingSearches")}
          </p>

          {popularLoading ? (
            <div className="space-y-1 px-3 pt-1">
              {SKELETON_WIDTHS.map((w, i) => (
                <div
                  key={i}
                  className="h-8 animate-pulse rounded-lg bg-[var(--bg-subtle)]"
                  style={{ width: w }}
                />
              ))}
            </div>
          ) : popularKeywords.length > 0 ? (
            <div className="py-1">
              {popularKeywords.map((kw) => (
                <button
                  key={kw}
                  type="button"
                  onClick={() => onSelectKeyword(kw)}
                  className="flex w-full items-center gap-2.5 px-4 py-[7px] text-left text-[0.82rem] font-medium text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--brand-navy)] focus-visible:bg-[var(--bg-subtle)]"
                >
                  <ArrowUpRight
                    aria-hidden
                    weight="bold"
                    className="size-3.5 shrink-0 text-[var(--brand-primary)]/50"
                  />
                  <span className="truncate">{kw}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2 px-4 pt-6 text-center">
              <MagnifyingGlass
                aria-hidden
                weight="duotone"
                className="size-7 text-[var(--text-muted)]/50"
              />
              <p className="text-[0.72rem] text-[var(--text-muted)]">
                {t("noTrending")}
              </p>
            </div>
          )}
        </div>

        {/* ── Right: Industry browser ── */}
        <div className="flex min-w-0 flex-1 flex-col py-4">
          <p className="mb-2 px-4 text-[0.68rem] font-bold uppercase tracking-widest text-[var(--text-muted)]">
            {t("browseByIndustry")}
          </p>

          {industriesLoading ? (
            <div className="mx-4 flex-1 animate-pulse rounded-xl bg-[var(--bg-subtle)]" />
          ) : industries.length > 0 ? (
            <div className="mx-4 flex flex-1 divide-x divide-[var(--border-subtle)] overflow-hidden rounded-xl border border-[var(--border-subtle)]">

              {/* Column 1: Roots */}
              <div className="w-1/3 overflow-y-auto py-1">
                {industries.map((root) => (
                  <button
                    key={root.id}
                    type="button"
                    onClick={() => {
                      setSelectedRoot(root);
                      setSelectedBranch(null);
                    }}
                    className={`flex w-full items-center justify-between px-3 py-[7px] text-left text-xs outline-none transition-colors ${
                      selectedRoot?.id === root.id
                        ? "bg-[var(--brand-primary)]/8 font-semibold text-[var(--brand-primary)]"
                        : "font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    <span className="truncate">{getName(root)}</span>
                    {root.children.length > 0 && (
                      <CaretRight aria-hidden weight="bold" className="size-3 shrink-0 opacity-40" />
                    )}
                  </button>
                ))}
              </div>

              {/* Column 2: Branches */}
              <div className="w-1/3 overflow-y-auto py-1">
                {selectedRoot ? (
                  selectedRoot.children.length > 0 ? (
                    selectedRoot.children.map((branch) => (
                      <button
                        key={branch.id}
                        type="button"
                        onClick={() => setSelectedBranch(branch)}
                        className={`flex w-full items-center justify-between px-3 py-[7px] text-left text-xs outline-none transition-colors ${
                          selectedBranch?.id === branch.id
                            ? "bg-[var(--brand-primary)]/8 font-semibold text-[var(--brand-primary)]"
                            : "font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]"
                        }`}
                      >
                        <span className="truncate">{getName(branch)}</span>
                        {branch.children.length > 0 && (
                          <CaretRight aria-hidden weight="bold" className="size-3 shrink-0 opacity-40" />
                        )}
                      </button>
                    ))
                  ) : null
                ) : (
                  <div className="flex h-full items-center justify-center p-4 text-[0.72rem] text-[var(--text-muted)]">
                    {t("selectCategory")}
                  </div>
                )}
              </div>

              {/* Column 3: Leaves */}
              <div className="w-1/3 overflow-y-auto py-1">
                {selectedBranch ? (
                  selectedBranch.children.length > 0 ? (
                    selectedBranch.children.map((leaf) => (
                      <button
                        key={leaf.id}
                        type="button"
                        onClick={() => onSelectIndustry(leaf)}
                        className="flex w-full items-center px-3 py-[7px] text-left text-xs font-medium text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--brand-primary)] focus-visible:bg-[var(--bg-subtle)]"
                      >
                        <span className="truncate">{getName(leaf)}</span>
                      </button>
                    ))
                  ) : null
                ) : (
                  <div className="flex h-full items-center justify-center p-4 text-[0.72rem] text-[var(--text-muted)]">
                    {selectedRoot ? t("selectField") : ""}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="mx-4 flex flex-1 items-center justify-center rounded-xl border border-[var(--border-subtle)] text-xs text-[var(--text-muted)]">
              {t("noIndustries")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
