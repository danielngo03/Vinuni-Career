"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  UsersThree,
  IdentificationBadge,
  TreeStructure,
  EnvelopeSimple,
  ShieldWarning,
  SignIn,
  ArrowSquareOut,
  Warning,
  Crown,
  ClockCounterClockwise,
  Lightning,
} from "@phosphor-icons/react";
import Link from "next/link";
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
import { AiEnergyTab } from "./ai-energy-tab";

const TABS_ID = "team";

export function TeamScreen() {
  const t = useTranslations("team");
  const tStates = useTranslations("states");
  const [tab, setTab] = useState("members");

  const user = useAuthStore((s) => s.user);
  const isSuperadmin = user?.isSuperadmin ?? false;

  // Shared queries (deduped by key with the tabs).
  const orgQuery = useQuery({
    queryKey: ["org", "profile"],
    queryFn: () => organizationApi.get(),
    retry: false,
  });
  const rolesQuery = useQuery({
    queryKey: ["org", "roles"],
    queryFn: () => organizationApi.listRoles(),
    retry: false,
  });
  const membersQuery = useQuery({
    queryKey: ["org", "members"],
    queryFn: () => organizationApi.listMembers(),
    retry: false,
  });

  // Effective permissions of the current actor = union of their roles'
  // permissions. Drives the escalation ceiling in the role editor.
  const { effective, holdsWildcard } = useMemo(() => {
    const set = new Set<string>();
    const myEmail = user?.email?.toLowerCase();
    const members = membersQuery.data?.data ?? [];
    const roles = rolesQuery.data ?? [];
    const mine = members.find((m) => m.user_email.toLowerCase() === myEmail);
    const myRoleIds = new Set(mine?.role_ids ?? []);
    for (const r of roles) {
      if (myRoleIds.has(r.id)) for (const p of r.permissions) set.add(p);
    }
    if (isSuperadmin) set.add("*:*");
    return { effective: set as ReadonlySet<string>, holdsWildcard: set.has("*:*") };
  }, [membersQuery.data, rolesQuery.data, user?.email, isSuperadmin]);

  // Gate on the org query: 403 → permission, 401 → auth.
  if (orgQuery.isError && orgQuery.error instanceof ApiError) {
    const err = orgQuery.error;
    if (err.isPermissionError) {
      return (
        <>
          <PageHeader title={t("title")} description={t("subtitle")} />
          <EmptyState
            kind="permission"
            icon={ShieldWarning}
            title={tStates("permissionTitle")}
            description={t("permissionBody")}
          />
        </>
      );
    }
    if (err.isAuthError) {
      return (
        <>
          <PageHeader title={t("title")} description={t("subtitle")} />
          <EmptyState
            kind="auth"
            icon={SignIn}
            title={tStates("authTitle")}
            description={tStates("authBody")}
          />
        </>
      );
    }
  }

  const orgType = orgQuery.data?.org_type ?? "partner";
  // AI energy is a shared partner-org pool governed by billing managers. Gate the
  // tab on the org-management capability (backend re-checks); universities meter
  // AI differently, so it's a partner-org surface.
  const canManageBilling = holdsWildcard || effective.has("billing:manage");
  const showEnergyTab = orgType === "partner" && canManageBilling;
  const maxSeats = orgQuery.data?.max_team_members ?? 4;
  const activeMembers = membersQuery.data?.data.filter(
    (m) => m.status === "active" || m.status === "pending"
  ).length ?? 0;
  const seatLimitEnabled = maxSeats !== -1;
  const atSeatLimit = seatLimitEnabled && activeMembers >= maxSeats;

  const items: TabItem[] = [
    {
      value: "members",
      label: t("tabs.members"),
      icon: <UsersThree aria-hidden weight="duotone" className="size-4" />,
    },
    {
      value: "roles",
      label: t("tabs.roles"),
      icon: <IdentificationBadge aria-hidden weight="duotone" className="size-4" />,
    },
    {
      value: "departments",
      label: t("tabs.departments"),
      icon: <TreeStructure aria-hidden weight="duotone" className="size-4" />,
    },
    ...(showEnergyTab
      ? [
          {
            value: "aiEnergy",
            label: t("tabs.aiEnergy"),
            icon: <Lightning aria-hidden weight="duotone" className="size-4" />,
          },
        ]
      : []),
    {
      value: "invitations",
      label: t("tabs.invitations"),
      icon: <EnvelopeSimple aria-hidden weight="duotone" className="size-4" />,
    },
    {
      value: "ownership",
      label: t("tabs.ownership"),
      icon: <Crown aria-hidden weight="duotone" className="size-4" />,
    },
    {
      value: "auditLog",
      label: t("tabs.auditLog"),
      icon: <ClockCounterClockwise aria-hidden weight="duotone" className="size-4" />,
    },
  ];

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />

      {/* Seat usage banner — shown for partner orgs with a seat limit */}
      {seatLimitEnabled && orgQuery.data?.org_type === "partner" && (
        <div
          className={`mb-5 flex items-center gap-4 rounded-2xl border px-5 py-3.5 backdrop-blur-md ${
            atSeatLimit
              ? "border-[var(--amber-600)]/40 bg-[var(--amber-100)]/50"
              : "border-white/60 bg-white/80"
          }`}
        >
          <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-center sm:gap-6">
            <div className="flex items-center gap-2">
              {atSeatLimit ? (
                <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-warning shadow-sm">
                  <Warning aria-hidden weight="duotone" className="size-3.5 text-white" />
                </span>
              ) : (
                <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-primary shadow-sm">
                  <UsersThree aria-hidden weight="duotone" className="size-3.5 text-white" />
                </span>
              )}
              <span className={`text-sm font-semibold ${atSeatLimit ? "text-[var(--amber-800)]" : "text-[var(--text-primary)]"}`}>
                {t("seats.usage", { used: activeMembers, max: maxSeats })}
              </span>
            </div>
            <div className="flex-1">
              <div className="h-1.5 w-full max-w-[200px] overflow-hidden rounded-full bg-black/10">
                <div
                  className={`h-full rounded-full transition-all ${atSeatLimit ? "bg-[var(--amber-600)]" : "bg-[var(--brand-primary)]"}`}
                  style={{ width: `${Math.min(100, (activeMembers / maxSeats) * 100)}%` }}
                />
              </div>
            </div>
            {atSeatLimit && (
              <p className="text-xs text-[var(--amber-700)]">
                {t("seats.atLimit")}
              </p>
            )}
          </div>
          <Link
            href="/partner/billing"
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold outline-none transition-colors ${
              atSeatLimit
                ? "bg-[var(--amber-600)] text-white hover:bg-[var(--amber-700)]"
                : "border border-[var(--brand-primary)] text-[var(--brand-primary)] hover:bg-[var(--blue-50)]"
            } focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30`}
          >
            <ArrowSquareOut aria-hidden weight="bold" className="size-3.5" />
            {t("seats.upgradeCta")}
          </Link>
        </div>
      )}

      <Tabs
        items={items}
        value={tab}
        onValueChange={setTab}
        ariaLabel={t("title")}
        idBase={TABS_ID}
        className="mb-6"
      />
      <TabPanel tabsId={TABS_ID} value="members" active={tab === "members"}>
        <MembersTab
          effective={effective}
          holdsWildcard={holdsWildcard}
          currentEmail={user?.email ?? ""}
        />
      </TabPanel>
      <TabPanel tabsId={TABS_ID} value="roles" active={tab === "roles"}>
        <RolesTab
          effective={effective}
          holdsWildcard={holdsWildcard}
          orgType={orgType}
        />
      </TabPanel>
      <TabPanel tabsId={TABS_ID} value="departments" active={tab === "departments"}>
        <DepartmentsTab />
      </TabPanel>
      {showEnergyTab && (
        <TabPanel tabsId={TABS_ID} value="aiEnergy" active={tab === "aiEnergy"}>
          <AiEnergyTab />
        </TabPanel>
      )}
      <TabPanel tabsId={TABS_ID} value="invitations" active={tab === "invitations"}>
        <InvitationsTab
          effective={effective}
          holdsWildcard={holdsWildcard}
        />
      </TabPanel>
      <TabPanel tabsId={TABS_ID} value="ownership" active={tab === "ownership"}>
        <OwnershipTab />
      </TabPanel>
      <TabPanel tabsId={TABS_ID} value="auditLog" active={tab === "auditLog"}>
        <AuditLogTab />
      </TabPanel>
    </>
  );
}
