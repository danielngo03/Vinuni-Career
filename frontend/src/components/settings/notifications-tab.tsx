"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery } from "@tanstack/react-query";
import { BellRinging, ShieldWarning, SignIn } from "@phosphor-icons/react";
import {
  Button,
  EmptyState,
  Skeleton,
  StatusBadge,
  Switch,
  useToast,
} from "@/components/ui";
import { SectionCard } from "./section-card";
import {
  accountApi,
  ApiError,
  type AccountPreferences,
  type NotificationCategoryPref,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

type Channel = keyof Pick<
  NotificationCategoryPref,
  "in_app" | "email" | "push"
>;

// Known category id -> i18n label key. Unknown ids fall back to the raw id.
const CATEGORY_LABEL_KEYS: Record<string, string> = {
  security_alert: "categorySecurity",
  legal_compliance: "categoryLegal",
  application_lifecycle: "categoryLifecycle",
  billing_receipt: "categoryBilling",
  application_status: "categoryApplications",
  interview: "categoryInterview",
  offer: "categoryOffer",
  job_digest: "categoryJobDigest",
  job_alert: "categoryJobAlerts",
  event: "categoryEvents",
  cv: "categoryCv",
  message: "categoryMessages",
  // legacy keys (pre-rename)
  "security.alert": "categorySecurity",
  "application.status_changed": "categoryApplications",
  "job.digest": "categoryJobDigest",
  "event.reminder": "categoryEvents",
};

export function NotificationsTab() {
  const t = useTranslations("settings.notifications");
  const tSettings = useTranslations("settings");
  const tStates = useTranslations("states");
  const tCommon = useTranslations("common");
  const toast = useToast();
  const getMessage = useApiErrorMessage();

  const query = useQuery({
    queryKey: ["account", "preferences"],
    queryFn: () => accountApi.getPreferences(),
    retry: false,
  });

  const [prefs, setPrefs] = useState<AccountPreferences | null>(null);
  useEffect(() => {
    if (query.data) setPrefs(query.data);
  }, [query.data]);

  const save = useMutation({
    mutationFn: (next: AccountPreferences) =>
      accountApi.updatePreferences(next),
    onSuccess: (data) => {
      setPrefs(data);
      toast.show({ tone: "success", title: tSettings("saved") });
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  function setChannel(catId: string, channel: Channel, value: boolean) {
    setPrefs((p) =>
      p
        ? {
            ...p,
            categories: {
              ...p.categories,
              [catId]: { ...p.categories[catId]!, [channel]: value },
            },
          }
        : p,
    );
  }

  function setQuietHours(patch: Partial<AccountPreferences["quiet_hours"]>) {
    setPrefs((p) =>
      p ? { ...p, quiet_hours: { ...p.quiet_hours, ...patch } } : p,
    );
  }

  function labelFor(id: string): string {
    const key = CATEGORY_LABEL_KEYS[id];
    return key ? t(key) : id;
  }

  // Loading.
  if (query.isPending) {
    return (
      <SectionCard
        title={t("title")}
        description={t("intro")}
        icon={BellRinging}
        iconGradient="icon-chip-warning"
      >
        <div className="space-y-3">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      </SectionCard>
    );
  }

  // Error / permission.
  if (query.isError || !prefs) {
    const isAuth = query.error instanceof ApiError && query.error.isAuthError;
    return (
      <SectionCard
        title={t("title")}
        description={t("intro")}
        icon={BellRinging}
        iconGradient="icon-chip-warning"
      >
        <EmptyState
          kind={isAuth ? "auth" : "offline"}
          icon={isAuth ? SignIn : ShieldWarning}
          title={isAuth ? tStates("authTitle") : tStates("offlineTitle")}
          description={isAuth ? tStates("authBody") : tStates("offlineBody")}
          action={
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tCommon("retry")}
            </Button>
          }
        />
      </SectionCard>
    );
  }

  const categoryIds = Object.keys(prefs.categories);

  return (
    <SectionCard
      title={t("title")}
      description={t("intro")}
      icon={BellRinging}
      iconGradient="icon-chip-warning"
    >
      {categoryIds.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={BellRinging}
          title={tStates("emptyTitle")}
          description={tStates("emptyBody")}
        />
      ) : (
        <div className="space-y-6">
          {/* Per-category channels */}
          <div className="divide-y divide-white/40">
            {categoryIds.map((id) => {
              const pref = prefs.categories[id]!;
              const locked = Boolean(pref.locked);
              return (
                <div
                  key={id}
                  className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-[var(--text-primary)]">
                      {labelFor(id)}
                    </span>
                    {locked && (
                      <StatusBadge tone="info">{t("mandatory")}</StatusBadge>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-4">
                    <Switch
                      id={`${id}-inapp`}
                      label={t("channelInApp")}
                      checked={pref.in_app}
                      disabled={locked}
                      onCheckedChange={(v) => setChannel(id, "in_app", v)}
                    />
                    <Switch
                      id={`${id}-email`}
                      label={t("channelEmail")}
                      checked={pref.email}
                      disabled={locked}
                      onCheckedChange={(v) => setChannel(id, "email", v)}
                    />
                    <Switch
                      id={`${id}-push`}
                      label={t("channelPush")}
                      checked={pref.push}
                      disabled={locked}
                      onCheckedChange={(v) => setChannel(id, "push", v)}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Quiet hours */}
          <div className="rounded-xl border border-white/60 bg-white/72 p-4 backdrop-blur-sm">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {t("quietHours")}
                </p>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  {t("quietHoursHelp")}
                </p>
              </div>
              <Switch
                id="quiet-hours"
                label={t("quietHours")}
                hideLabel
                checked={prefs.quiet_hours.enabled}
                onCheckedChange={(v) => setQuietHours({ enabled: v })}
              />
            </div>
            {prefs.quiet_hours.enabled && (
              <div className="mt-4 flex flex-wrap items-end gap-4">
                <label className="flex flex-col gap-1.5 text-sm font-semibold text-[var(--text-primary)]">
                  {t("quietStart")}
                  <input
                    type="time"
                    value={prefs.quiet_hours.start}
                    onChange={(e) => setQuietHours({ start: e.target.value })}
                    className="rounded-xl border border-white/60 bg-white/80 backdrop-blur-sm px-3 py-2 text-sm font-medium text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-white/95 focus:ring-2 focus:ring-[var(--brand-primary)]/30"
                  />
                </label>
                <label className="flex flex-col gap-1.5 text-sm font-semibold text-[var(--text-primary)]">
                  {t("quietEnd")}
                  <input
                    type="time"
                    value={prefs.quiet_hours.end}
                    onChange={(e) => setQuietHours({ end: e.target.value })}
                    className="rounded-xl border border-white/60 bg-white/80 backdrop-blur-sm px-3 py-2 text-sm font-medium text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-white/95 focus:ring-2 focus:ring-[var(--brand-primary)]/30"
                  />
                </label>
              </div>
            )}
          </div>

          <p className="text-xs text-[var(--text-secondary)]">
            {t("mandatoryHint")}
          </p>
          <p className="text-xs text-[var(--text-muted)]">
            {t("pushPermissionNote")}
          </p>

          <div className="flex justify-end">
            <Button
              variant="primary"
              loading={save.isPending}
              onClick={() => save.mutate(prefs)}
            >
              {save.isPending ? tCommon("saving") : tCommon("save")}
            </Button>
          </div>
        </div>
      )}
    </SectionCard>
  );
}
