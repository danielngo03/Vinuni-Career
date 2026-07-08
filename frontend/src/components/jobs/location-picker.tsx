"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { CaretDown, MapPin, Plus, X } from "@phosphor-icons/react";
import { locationsApi, type Province, type Ward } from "@/lib/api/locations";
import type { JobLocationItem } from "@/lib/api/jobs";
import { LOCATION_TYPES, type LocationType } from "@/lib/api/jobs";
import { cn } from "@/lib/utils";

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
  const locale = useLocale();
  const pickerId = useId();
  const panelId = `${pickerId}-panel`;
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

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

  const locations = useMemo(
    () => (value.length === 0 ? [blank()] : value),
    [value],
  );
  const summary = useMemo(() => {
    const valid = locations.filter((loc) => loc.type === "remote" || loc.city || loc.ward_name);
    if (valid.length === 0) return t("locations");
    const first = valid[0];
    if (!first) return t("locations");
    const firstLabel =
      first.type === "remote"
        ? t("locationType.remote")
        : [t(`locationType.${first.type}`), first.ward_name ?? first.city].filter(Boolean).join(" · ");
    if (valid.length === 1) return firstLabel;
    return `${firstLabel} +${valid.length - 1}`;
  }, [locations, t]);

  useEffect(() => {
    if (!open) return;

    function handlePointerDown(e: PointerEvent) {
      const target = e.target as Node;
      if (!panelRef.current?.contains(target) && !triggerRef.current?.contains(target)) {
        setOpen(false);
      }
    }

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={panelId}
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          "flex h-10 w-full items-center justify-between gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 text-left transition-[border-color,box-shadow] duration-150",
          open
            ? "border-[var(--field-focus-border)] shadow-[0_0_0_4px_var(--field-focus-ring)]"
            : "hover:border-[var(--border-strong)]",
          "disabled:cursor-not-allowed disabled:opacity-60",
        )}
      >
        <span className="flex min-w-0 items-center gap-2">
          <MapPin
            aria-hidden
            weight="duotone"
            className="size-4 shrink-0 text-[var(--brand-primary)]"
          />
          <span className="truncate text-sm font-medium text-[var(--text-primary)]">
            {summary}
          </span>
        </span>
        <CaretDown
          aria-hidden
          weight="bold"
          className={cn(
            "size-4 shrink-0 text-[var(--text-muted)] transition-transform duration-150",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div
          ref={panelRef}
          id={panelId}
          role="dialog"
          aria-label={t("locations")}
          onPointerDown={(e) => e.stopPropagation()}
          className="absolute left-0 top-full z-50 mt-2 w-[min(760px,calc(100vw-2rem))] max-w-[calc(100vw-2rem)] overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_24px_70px_rgba(11,34,57,0.16)]"
        >
          <div className="border-b border-[var(--border-default)] px-4 py-3">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {t("locations")}
            </p>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              {t("locationType.onsite")} / {t("locationType.hybrid")} / {t("locationType.remote")}
            </p>
          </div>

          <div className="space-y-3 p-4">
            {locations.map((loc, i) => (
              <div
                key={i}
                className="grid gap-2 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-secondary)] p-3 md:grid-cols-[140px_minmax(0,1fr)_minmax(0,1fr)_auto] md:items-center"
              >
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
                  className="h-10 w-full rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3 text-sm text-[var(--text-primary)] outline-none focus:ring-2 focus:ring-[var(--brand-primary)]/30"
                >
                  {LOCATION_TYPES.map((lt) => (
                    <option key={lt} value={lt}>
                      {t(`locationType.${lt}`)}
                    </option>
                  ))}
                </select>

                {loc.type !== "remote" ? (
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
                    className="h-10 min-w-[160px] rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3 text-sm text-[var(--text-primary)] outline-none focus:ring-2 focus:ring-[var(--brand-primary)]/30"
                  >
                    <option value="">{t("locationProvincePlaceholder")}</option>
                    {provinces.map((p) => (
                      <option key={p.code} value={p.code}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <div className="flex h-10 items-center rounded-xl border border-dashed border-[var(--border-default)] bg-[var(--surface-card)] px-3 text-sm text-[var(--text-muted)]">
                    {t("locationType.remote")}
                  </div>
                )}

                {loc.type !== "remote" ? (
                  <WardSelect
                    provinceCode={loc.province_code ?? ""}
                    value={loc.ward_code ?? ""}
                    disabled={disabled || !loc.province_code}
                    onChange={(ward) =>
                      patch(i, {
                        ward_code: ward?.code ?? null,
                        ward_name: ward?.full_name ?? ward?.name ?? null,
                      })
                    }
                  />
                ) : (
                  <div className="hidden md:block" />
                )}

                {locations.length > 1 && (
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => remove(i)}
                    aria-label={t("removeLocation")}
                    className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] hover:text-[var(--brand-red)]"
                  >
                    <X aria-hidden weight="bold" className="size-4" />
                  </button>
                )}
              </div>
            ))}

            <div className="flex flex-wrap items-center justify-between gap-2">
              {locations.length < MAX_LOCATIONS && (
                <button
                  type="button"
                  disabled={disabled}
                  onClick={add}
                  className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium text-[var(--brand-primary)] transition-colors hover:bg-[var(--blue-50)]"
                >
                  <Plus aria-hidden weight="bold" className="size-3.5" />
                  {t("addLocation")}
                </button>
              )}

              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-1.5 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]"
              >
                {locale === "vi" ? "Xong" : "Done"}
              </button>
            </div>
          </div>
        </div>
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
    enabled: Boolean(provinceCode),
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
      className="h-10 min-w-[180px] rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-3 text-sm text-[var(--text-primary)] outline-none focus:ring-2 focus:ring-[var(--brand-primary)]/30 disabled:opacity-60"
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
