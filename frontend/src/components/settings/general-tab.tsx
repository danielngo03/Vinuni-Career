"use client";

import { useEffect, useState, useTransition } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CloudSlash, CircleNotch, UserGear } from "@phosphor-icons/react";
import { Button, Select, useToast } from "@/components/ui";
import { SectionCard } from "./section-card";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { useTheme } from "@/lib/theme";
import { accountApi, ApiError } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

// Common timezones surfaced first; VN default per LOCAL_DEV_STACK / product.
const TIMEZONES = [
  "Asia/Ho_Chi_Minh",
  "Asia/Singapore",
  "Asia/Bangkok",
  "Asia/Tokyo",
  "Europe/London",
  "America/New_York",
];

export function GeneralTab() {
  const t = useTranslations("settings.general");
  const tSettings = useTranslations("settings");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const [, startTransition] = useTransition();
  const { theme, setTheme } = useTheme();
  const toast = useToast();
  const getMessage = useApiErrorMessage();

  const [timezone, setTimezone] = useState("Asia/Ho_Chi_Minh");

  const query = useQuery({
    queryKey: ["account", "preferences"],
    queryFn: () => accountApi.getPreferences(),
    retry: false,
  });

  useEffect(() => {
    if (query.data?.timezone) setTimezone(query.data.timezone);
  }, [query.data]);

  const save = useMutation({
    mutationFn: () =>
      accountApi.updatePreferences({ locale, timezone, theme }),
    onSuccess: () =>
      toast.show({ tone: "success", title: tSettings("saved") }),
    onError: (e) =>
      toast.show({ tone: "error", title: getMessage(e) }),
  });

  const authError = query.error instanceof ApiError && query.error.isAuthError;

  return (
    <SectionCard
      title={t("title")}
      description={t("intro")}
      icon={UserGear}
      iconGradient="icon-chip-primary"
    >
      {/* Honest connection status. Language + appearance work locally even when
          account sync is unavailable; timezone persists to the account. */}
      {query.isPending ? (
        <div className="mb-4 text-xs">
          <span className="inline-flex items-center gap-1.5 text-[var(--text-muted)]">
            <CircleNotch aria-hidden className="size-3.5 animate-spin" />
            {tCommon("loading")}
          </span>
        </div>
      ) : query.isError ? (
        <div className="mb-4 text-xs">
          <span className="inline-flex items-center gap-1.5 text-[var(--color-warning)]">
            <CloudSlash aria-hidden weight="duotone" className="size-3.5" />
            {authError ? tSettings("permissionRequired") : t("syncUnavailable")}
          </span>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <Select
          label={t("language")}
          help={t("languageHelp")}
          value={locale}
          onChange={(e) => {
            const next = e.target.value;
            startTransition(() => router.replace(pathname, { locale: next }));
          }}
          options={routing.locales.map((loc) => ({
            value: loc,
            label: loc === "vi" ? tCommon("vietnamese") : tCommon("english"),
          }))}
        />

        <Select
          label={t("timezone")}
          help={t("timezoneHelp")}
          value={timezone}
          disabled={query.isPending}
          onChange={(e) => setTimezone(e.target.value)}
          options={TIMEZONES.map((tz) => ({ value: tz, label: tz }))}
        />

        <Select
          label={t("theme")}
          help={t("themeHelp")}
          value={theme}
          onChange={(e) => setTheme(e.target.value as typeof theme)}
          options={[
            { value: "light", label: t("themeLight") },
            { value: "dark", label: t("themeDark") },
            { value: "system", label: t("themeSystem") },
          ]}
        />
      </div>

      <div className="mt-6 flex justify-end">
        <Button
          variant="primary"
          loading={save.isPending}
          disabled={query.isPending}
          onClick={() => save.mutate()}
        >
          {save.isPending ? tCommon("saving") : tCommon("save")}
        </Button>
      </div>
    </SectionCard>
  );
}
