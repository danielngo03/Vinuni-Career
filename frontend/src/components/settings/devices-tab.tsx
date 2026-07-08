"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery } from "@tanstack/react-query";
import { DeviceMobile, ShieldWarning, SignIn } from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  Modal,
  StatusBadge,
  useToast,
  type Column,
} from "@/components/ui";
import { SectionCard } from "./section-card";
import { useRouter } from "@/i18n/navigation";
import { accountApi, ApiError, type AccountSession } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { formatDateTime } from "@/lib/format";

export function DevicesTab() {
  const t = useTranslations("settings.devices");
  const tStates = useTranslations("states");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const router = useRouter();
  const signOut = useAuthStore((s) => s.signOut);
  const getMessage = useApiErrorMessage();

  const [target, setTarget] = useState<AccountSession | null>(null);

  const query = useQuery({
    queryKey: ["account", "sessions"],
    queryFn: () => accountApi.getSessions(),
    retry: false,
  });

  const revoke = useMutation({
    mutationFn: (session: AccountSession) =>
      accountApi.revokeSession(session.id),
    onSuccess: async (_data, session) => {
      setTarget(null);
      // Revoking the current device logs you out here too (EDGE_CASES §Auth).
      if (session.current) {
        await signOut();
        router.replace("/auth/login");
        return;
      }
      toast.show({ tone: "success", title: t("revokedToast") });
      await query.refetch();
    },
    onError: (e) => {
      setTarget(null);
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  function deviceLabel(row: AccountSession): string {
    if (row.device_label) return row.device_label;
    const parts = [row.browser_family, row.os_family].filter(Boolean);
    return parts.length ? parts.join(" · ") : t("unknownDevice");
  }

  if (query.isError) {
    const isAuth = query.error instanceof ApiError && query.error.isAuthError;
    return (
      <SectionCard
      title={t("title")}
      description={t("intro")}
      icon={DeviceMobile}
      iconGradient="icon-chip-success"
    >
        <div className="rounded-2xl border border-dashed border-white/50 bg-white/72 px-6 py-12 text-center backdrop-blur-sm">
          <span
            className={
              "mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl shadow-sm " +
              (isAuth
                ? "icon-chip-primary"
                : "icon-chip-neutral")
            }
          >
            {isAuth ? (
              <SignIn aria-hidden weight="duotone" className="size-6 text-white" />
            ) : (
              <ShieldWarning aria-hidden weight="duotone" className="size-6 text-white" />
            )}
          </span>
          <h3 className="text-base font-semibold text-[var(--text-primary)]">
            {isAuth ? tStates("authTitle") : tStates("offlineTitle")}
          </h3>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {isAuth ? tStates("authBody") : tStates("offlineBody")}
          </p>
          <div className="mt-5">
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tCommon("retry")}
            </Button>
          </div>
        </div>
      </SectionCard>
    );
  }

  const rows = query.data?.data ?? [];

  const columns: Column<AccountSession>[] = [
    {
      key: "device",
      header: t("deviceColumn"),
      cell: (row) => (
        <div className="flex items-center gap-2">
          <DeviceMobile
            aria-hidden
            weight="duotone"
            className="size-5 text-[var(--text-muted)]"
          />
          <span className="font-medium">{deviceLabel(row)}</span>
          {row.current && (
            <StatusBadge tone="active">{t("thisDevice")}</StatusBadge>
          )}
        </div>
      ),
    },
    {
      key: "location",
      header: t("location"),
      cell: (row) => row.location ?? "—",
    },
    {
      key: "last_seen_at",
      header: t("lastSeen"),
      cell: (row) => formatDateTime(row.last_seen_at, locale),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (row) => (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setTarget(row)}
          disabled={revoke.isPending}
        >
          {t("logout")}
        </Button>
      ),
    },
  ];

  return (
    <SectionCard
      title={t("title")}
      description={t("intro")}
      icon={DeviceMobile}
      iconGradient="icon-chip-success"
    >
      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(r) => r.id}
        loading={query.isPending}
        caption={t("title")}
        empty={{
          kind: "empty",
          icon: DeviceMobile,
          title: t("empty"),
        }}
      />
      <p className="mt-4 text-xs text-[var(--text-muted)]">{t("privacyNote")}</p>

      <Modal
        open={target !== null}
        onClose={() => setTarget(null)}
        title={t("revokeTitle")}
        description={
          target?.current ? t("revokeCurrentBody") : t("revokeBody")
        }
        size="sm"
        closeLabel={tCommon("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setTarget(null)}>
              {tCommon("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={revoke.isPending}
              onClick={() => target && revoke.mutate(target)}
            >
              {t("revokeConfirm")}
            </Button>
          </>
        }
      >
        {target && (
          <p className="text-sm text-[var(--text-secondary)]">
            {deviceLabel(target)}
            {target.location ? ` · ${target.location}` : ""}
          </p>
        )}
      </Modal>
    </SectionCard>
  );
}
