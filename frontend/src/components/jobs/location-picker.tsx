"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { MapPin, Plus, X } from "@phosphor-icons/react";
import { locationsApi, type Province, type Ward } from "@/lib/api/locations";
import type { JobLocationItem } from "@/lib/api/jobs";
import { LOCATION_TYPES, type LocationType } from "@/lib/api/jobs";

interface Props {
  value: JobLocationItem[];
  onChange: (locations: JobLocationItem[]) => void;
  disabled?: boolean;
}

const MAX_LOCATIONS = 10;

function blank(): JobLocationItem {
  return {
    type: "onsite",
    province_code: null,
    ward_code: null,
    ward_name: null,
    city: null,
    country: "Vietnam",
  };
}

export function JobLocationPicker({ value, onChange, disabled }: Props) {
  const t = useTranslations("jobs");
  const provincesQuery = useQuery({
    queryKey: ["provinces"],
    queryFn: () => locationsApi.listProvinces(),
    staleTime: 60 * 60 * 1000, // 1h — static reference data
  });
  const provinces: Province[] = provincesQuery.data?.items ?? [];

  function add() {
    if (value.length >= MAX_LOCATIONS) return;
    onChange([...value, blank()]);
  }

  function remove(i: number) {
    onChange(value.filter((_, idx) => idx !== i));
  }

  function patch(i: number, update: Partial<JobLocationItem>) {
    onChange(value.map((loc, idx) => (idx === i ? { ...loc, ...update } : loc)));
  }

  const locations = value.length === 0 ? [blank()] : value;

  return (
    <div className="flex flex-col gap-2">
      {locations.map((loc, i) => (
        <div
          key={i}
          className="flex items-start gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3"
        >
          <MapPin
            aria-hidden
            weight="duotone"
            className="mt-1 size-4 shrink-0 text-[var(--brand-primary)]"
          />
          <div className="flex flex-1 flex-wrap gap-2">
            {/* Work arrangement */}
            <select
              disabled={disabled}
              value={loc.type}
              onChange={(e) => {
                const nextType = e.target.value as LocationType;
                patch(
                  i,
                  nextType === "remote"
                    ? {
                        type: nextType,
                        province_code: null,
                        ward_code: null,
                        ward_name: null,
                        city: null,
                      }
                    : { type: nextType },
                );
              }}
              className="h-9 flex-none rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-2 text-sm text-[var(--text-primary)] outline-none focus:ring-2 focus:ring-[var(--brand-primary)]/30"
            >
              {LOCATION_TYPES.map((lt) => (
                <option key={lt} value={lt}>
                  {t(`locationType.${lt}`)}
                </option>
              ))}
            </select>

            {/* Province / city for onsite + hybrid */}
            {loc.type !== "remote" && (
              <select
                disabled={disabled}
                value={loc.province_code ?? ""}
                onChange={(e) => {
                  const code = e.target.value || null;
                  const prov = provinces.find((p) => p.code === code);
                  patch(i, {
                    province_code: code,
                    ward_code: null,
                    ward_name: null,
                    city: prov?.name ?? null,
                  });
                }}
                className="h-9 min-w-[160px] flex-1 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-2 text-sm text-[var(--text-primary)] outline-none focus:ring-2 focus:ring-[var(--brand-primary)]/30"
              >
                <option value="">{t("locationProvincePlaceholder")}</option>
                {provinces.map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.name}
                  </option>
                ))}
              </select>
            )}

            {loc.type !== "remote" && loc.province_code && (
              <WardSelect
                provinceCode={loc.province_code}
                value={loc.ward_code ?? ""}
                disabled={disabled}
                onChange={(ward) =>
                  patch(i, {
                    ward_code: ward?.code ?? null,
                    ward_name: ward?.full_name ?? ward?.name ?? null,
                  })
                }
              />
            )}
          </div>

          {/* Remove button — always keep at least 1 location */}
          {locations.length > 1 && (
            <button
              type="button"
              disabled={disabled}
              onClick={() => remove(i)}
              aria-label={t("removeLocation")}
              className="mt-1 rounded-lg p-1 text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] hover:text-[var(--brand-red)]"
            >
              <X aria-hidden weight="bold" className="size-4" />
            </button>
          )}
        </div>
      ))}

      {locations.length < MAX_LOCATIONS && (
        <button
          type="button"
          disabled={disabled}
          onClick={add}
          className="flex items-center gap-1.5 self-start rounded-lg px-3 py-1.5 text-sm font-medium text-[var(--brand-primary)] hover:bg-[var(--blue-50)] transition-colors"
        >
          <Plus aria-hidden weight="bold" className="size-3.5" />
          {t("addLocation")}
        </button>
      )}
    </div>
  );
}

function WardSelect({
  provinceCode,
  value,
  disabled,
  onChange,
}: {
  provinceCode: string;
  value: string;
  disabled?: boolean;
  onChange: (ward: Ward | null) => void;
}) {
  const t = useTranslations("jobs");
  const wardsQuery = useQuery({
    queryKey: ["locations", "wards", provinceCode],
    queryFn: () => locationsApi.listWards(provinceCode),
    staleTime: 24 * 60 * 60 * 1000,
    retry: false,
  });
  const wards = wardsQuery.data?.items ?? [];
  return (
    <select
      disabled={disabled || wardsQuery.isPending}
      value={value}
      onChange={(e) => {
        const code = e.target.value;
        onChange(wards.find((w) => w.code === code) ?? null);
      }}
      className="h-9 min-w-[180px] flex-1 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-2 text-sm text-[var(--text-primary)] outline-none focus:ring-2 focus:ring-[var(--brand-primary)]/30 disabled:opacity-60"
    >
      <option value="">{t("locationWardPlaceholder")}</option>
      {wards.map((w) => (
        <option key={w.code} value={w.code}>
          {w.full_name}
        </option>
      ))}
    </select>
  );
}
