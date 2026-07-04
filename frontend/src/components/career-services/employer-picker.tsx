"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Buildings } from "@phosphor-icons/react";
import { Input } from "@/components/ui";
import { companiesApi } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Employer (partner org) search picker backed by the public directory
 * (`companiesApi.list`, no auth required) — safe for any counselor role
 * regardless of which `career_services_*` capabilities they hold.
 */
export function EmployerPicker({
  value,
  onChange,
  required,
}: {
  value: { id: string; label: string } | null;
  onChange: (next: { id: string; label: string } | null) => void;
  required?: boolean;
}) {
  const t = useTranslations("careerServices.employerNotes");
  const [query, setQuery] = useState(value?.label ?? "");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const search = useQuery({
    queryKey: ["career-services", "employer-search", query],
    queryFn: () => companiesApi.list({ q: query || undefined, limit: 8 }),
    enabled: open && query.trim().length > 0,
  });

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const results = search.data?.data ?? [];

  return (
    <div ref={containerRef} className="relative w-full">
      <Input
        label={t("employerLabel")}
        required={required}
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          if (value) onChange(null);
        }}
        placeholder={t("employerSearchPlaceholder")}
        help={value ? undefined : t("employerSearchHelp")}
      />
      {open && query.trim().length > 0 && (
        <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-xl border border-white/70 bg-white/98 shadow-lg backdrop-blur-xl">
          {search.isFetching ? (
            <p className="px-3.5 py-2.5 text-sm text-[var(--text-muted)]">
              {t("employerSearching")}
            </p>
          ) : results.length === 0 ? (
            <p className="px-3.5 py-2.5 text-sm text-[var(--text-muted)]">
              {t("employerNoResults")}
            </p>
          ) : (
            <ul role="listbox" aria-label={t("employerLabel")}>
              {results.map((company) => (
                <li key={company.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={value?.id === company.id}
                    onClick={() => {
                      onChange({ id: company.id, label: company.display_name });
                      setQuery(company.display_name);
                      setOpen(false);
                    }}
                    className={cn(
                      "flex w-full items-center gap-2 px-3.5 py-2.5 text-left text-sm hover:bg-[var(--bg-subtle)]",
                      value?.id === company.id && "bg-[var(--bg-subtle)]",
                    )}
                  >
                    <Buildings
                      aria-hidden
                      weight="duotone"
                      className="size-4 shrink-0 text-[var(--text-muted)]"
                    />
                    <span className="truncate font-medium text-[var(--text-primary)]">
                      {company.display_name}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
