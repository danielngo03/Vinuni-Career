"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ShieldCheck,
  ShieldWarning,
  SignIn,
  Key,
  LockKey,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  type Column,
} from "@/components/ui";
import { SectionCard } from "./section-card";
import { ChangePasswordModal } from "./change-password-modal";
import { TotpModal } from "./totp-modal";
import { accountApi, ApiError, type SecurityEvent } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

// Known security event types -> i18n label keys; unknown fall back to server text.
const EVENT_LABEL_KEYS: Record<string, string> = {
  login: "eventLogin",
  new_device: "eventNewDevice",
  password_change: "eventPasswordChange",
};

export function SecurityTab() {
  const t = useTranslations("settings.security");
  const tStates = useTranslations("states");
  const tCommon = useTranslations("common");
  const locale = useLocale();

  const [pwOpen, setPwOpen] = useState(false);
  const [totpOpen, setTotpOpen] = useState(false);

  const query = useQuery({
    queryKey: ["account", "security-events"],
    queryFn: () => accountApi.getSecurityEvents(),
    retry: false,
  });

  function eventLabel(row: SecurityEvent): string {
    if (row.description) return row.description;
    const key = EVENT_LABEL_KEYS[row.type];
    return key ? t(key) : row.type;
  }

  const columns: Column<SecurityEvent>[] = [
    { key: "type", header: t("eventColumn"), cell: (r) => eventLabel(r) },
    {
      key: "occurred_at",
      header: t("occurredAt"),
      cell: (r) => formatDateTime(r.occurred_at, locale),
    },
  ];

  return (
    <>
      <SectionCard
        title={t("actions")}
        icon={LockKey}
        iconGradient="icon-chip-danger"
        className="mb-5"
      >
        <div className="flex flex-wrap gap-3">
          <Button variant="secondary" onClick={() => setPwOpen(true)}>
            <Key aria-hidden weight="duotone" className="size-4" />
            {t("changePassword")}
          </Button>
          <Button variant="secondary" onClick={() => setTotpOpen(true)}>
            <LockKey aria-hidden weight="duotone" className="size-4" />
            {t("enableTotp")}
          </Button>
        </div>
      </SectionCard>

      <SectionCard
        title={t("title")}
        description={t("intro")}
        icon={ShieldCheck}
        iconGradient="icon-chip-info"
      >
        {query.isError ? (
          (() => {
            const isAuth =
              query.error instanceof ApiError && query.error.isAuthError;
            return (
              <EmptyState
                kind={isAuth ? "auth" : "offline"}
                icon={isAuth ? SignIn : ShieldWarning}
                title={isAuth ? tStates("authTitle") : tStates("offlineTitle")}
                description={
                  isAuth ? tStates("authBody") : tStates("offlineBody")
                }
                action={
                  <Button variant="secondary" onClick={() => query.refetch()}>
                    {tCommon("retry")}
                  </Button>
                }
              />
            );
          })()
        ) : (
          <DataTable
            columns={columns}
            rows={query.data?.data ?? []}
            getRowId={(r) => r.id}
            loading={query.isPending}
            caption={t("title")}
            empty={{
              kind: "empty",
              icon: ShieldCheck,
              title: t("empty"),
            }}
          />
        )}
      </SectionCard>

      <ChangePasswordModal open={pwOpen} onClose={() => setPwOpen(false)} />
      <TotpModal
        open={totpOpen}
        onClose={() => setTotpOpen(false)}
        onEnabled={() => query.refetch()}
      />
    </>
  );
}
