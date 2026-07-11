"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Users, IdCard, Network, Mail, Crown, History, ArrowUpRight, AlertTriangle } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Tabs, TabPanel, EmptyState, type TabItem } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { ApiError, organizationApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { MembersTab } from "./members-tab";
import { RolesTab } from "./roles-tab";
import { DepartmentsTab } from "./departments-tab";
import { InvitationsTab } from "./invitations-tab";
import { OwnershipTab } from "./ownership-tab";
import { AuditLogTab } from "./audit-log-tab";

const TABS_ID = "team";

export function TeamScreen() {
  const t = useTranslations("team");
  const tStates = useTranslations("states");
  const [tab, setTab] = React.useState("members");

  const user = useAuthStore((s) => s.user);

  // Authoritative capability map — gates the tabs + every per-action control.
  // The server remains final; this just reflects it (honest locked states).
  const capsQuery = useQuery({
    queryKey: ["org", "me", "capabilities"],
    queryFn: () => organizationApi.getMyCapabilities(),
    retry: false,
  });
  const orgQuery = useQuery({ queryKey: ["org", "profile"], queryFn: () => organizationApi.get(), retry: false });
  const membersQuery = useQuery({
    queryKey: ["org", "members"],
    queryFn: () => organizationApi.listMembers(),
    retry: false,
  });

  const caps = capsQuery.data;
  const effective = React.useMemo<ReadonlySet<string>>(() => new Set(caps?.grants ?? []), [caps]);
  const holdsWildcard = caps?.is_org_admin ?? false;
  const hasResource = React.useCallback(
    (resource: string) => holdsWildcard || Boolean(caps?.by_resource[resource]?.length),
    [caps, holdsWildcard],
  );

  // Gate on the capability map: 403 → non-org / no access, 401 → auth.
  const capsError = capsQuery.error;
  if (capsError instanceof ApiError && (capsError.isPermissionError || capsError.isAuthError)) {
    const isAuth = capsError.isAuthError;
    return (
      <>
        <PageHeader title={t("title")} subtitle={t("subtitle")} />
        <EmptyState
          kind={isAuth ? "auth" : "permission"}
          title={isAuth ? tStates("authTitle") : tStates("permissionTitle")}
          description={isAuth ? tStates("authBody") : t("permissionBody")}
        />
      </>
    );
  }
  if (orgQuery.isError && orgQuery.error instanceof ApiError && orgQuery.error.isAuthError) {
    return (
      <>
        <PageHeader title={t("title")} subtitle={t("subtitle")} />
        <EmptyState kind="auth" title={tStates("authTitle")} description={tStates("authBody")} />
      </>
    );
  }

  const orgType = orgQuery.data?.org_type ?? "partner";
  const maxSeats = orgQuery.data?.max_team_members ?? 4;
  const activeMembers =
    membersQuery.data?.data.filter((m) => m.status === "active" || m.status === "pending").length ?? 0;
  const seatLimitEnabled = maxSeats !== -1;
  const atSeatLimit = seatLimitEnabled && activeMembers >= maxSeats;

  // Tab visibility from the capability map (server enforces + honest locked states).
  const items: TabItem[] = [
    { value: "members", label: t("tabs.members"), icon: <Users aria-hidden className="size-4" strokeWidth={1.8} /> },
    ...(hasResource("roles")
      ? [{ value: "roles", label: t("tabs.roles"), icon: <IdCard aria-hidden className="size-4" strokeWidth={1.8} /> }]
      : []),
    ...(hasResource("departments")
      ? [{ value: "departments", label: t("tabs.departments"), icon: <Network aria-hidden className="size-4" strokeWidth={1.8} /> }]
      : []),
    ...(hasResource("members")
      ? [{ value: "invitations", label: t("tabs.invitations"), icon: <Mail aria-hidden className="size-4" strokeWidth={1.8} /> }]
      : []),
    ...(holdsWildcard
      ? [{ value: "ownership", label: t("tabs.ownership"), icon: <Crown aria-hidden className="size-4" strokeWidth={1.8} /> }]
      : []),
    ...(hasResource("audit")
      ? [{ value: "auditLog", label: t("tabs.auditLog"), icon: <History aria-hidden className="size-4" strokeWidth={1.8} /> }]
      : []),
  ];

  const activeTab = items.some((i) => i.value === tab) ? tab : "members";

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />

      {/* Seat usage banner — partner orgs with a finite seat limit. */}
      {seatLimitEnabled && orgType === "partner" && (
        <div
          className={`mb-5 flex flex-col gap-3 rounded-xl border px-5 py-4 sm:flex-row sm:items-center ${
            atSeatLimit ? "" : "border-border bg-card"
          }`}
          style={
            atSeatLimit
              ? { borderColor: "var(--content-warning)", background: "var(--content-warning-soft)" }
              : undefined
          }
        >
          <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-center sm:gap-6">
            <div className="flex items-center gap-2">
              {atSeatLimit ? (
                <AlertTriangle className="size-4 shrink-0" strokeWidth={1.9} style={{ color: "var(--content-warning)" }} />
              ) : (
                <Users className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.9} />
              )}
              <span className="text-[0.8125rem] font-semibold text-foreground tabular-nums">
                {t("seats.usage", { used: activeMembers, max: maxSeats })}
              </span>
            </div>
            <div className="h-1.5 w-full max-w-[220px] overflow-hidden rounded-full bg-[var(--bg-muted)]">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(100, (activeMembers / maxSeats) * 100)}%`,
                  background: atSeatLimit ? "var(--content-warning)" : "var(--brand-primary)",
                }}
              />
            </div>
            {atSeatLimit && <p className="type-caption text-muted-foreground">{t("seats.atLimit")}</p>}
          </div>
          {holdsWildcard && (
            <Link
              href="/partner/billing"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border px-3.5 py-2 text-xs font-semibold text-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
            >
              <ArrowUpRight className="size-3.5" strokeWidth={2} />
              {t("seats.upgradeCta")}
            </Link>
          )}
        </div>
      )}

      <Tabs items={items} value={activeTab} onValueChange={setTab} ariaLabel={t("title")} idBase={TABS_ID} className="mb-6" />

      <TabPanel tabsId={TABS_ID} value="members" active={activeTab === "members"}>
        <MembersTab effective={effective} holdsWildcard={holdsWildcard} currentEmail={user?.email ?? ""} />
      </TabPanel>
      {hasResource("roles") && (
        <TabPanel tabsId={TABS_ID} value="roles" active={activeTab === "roles"}>
          <RolesTab effective={effective} holdsWildcard={holdsWildcard} orgType={orgType} />
        </TabPanel>
      )}
      {hasResource("departments") && (
        <TabPanel tabsId={TABS_ID} value="departments" active={activeTab === "departments"}>
          <DepartmentsTab />
        </TabPanel>
      )}
      {hasResource("members") && (
        <TabPanel tabsId={TABS_ID} value="invitations" active={activeTab === "invitations"}>
          <InvitationsTab effective={effective} holdsWildcard={holdsWildcard} />
        </TabPanel>
      )}
      {holdsWildcard && (
        <TabPanel tabsId={TABS_ID} value="ownership" active={activeTab === "ownership"}>
          <OwnershipTab />
        </TabPanel>
      )}
      {hasResource("audit") && (
        <TabPanel tabsId={TABS_ID} value="auditLog" active={activeTab === "auditLog"}>
          <AuditLogTab />
        </TabPanel>
      )}
    </>
  );
}
