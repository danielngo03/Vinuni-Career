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
} from "@phosphor-icons/react";
import Link from "next/link";
import { Tabs, TabPanel, EmptyState, Skeleton, type TabItem } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { ApiError, organizationApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { MembersTab } from "./members-tab";
import { RolesTab } from "./roles-tab";
import { DepartmentsTab } from "./departments-tab";
import { InvitationsTab } from "./invitations-tab";
import { OwnershipTab } from "./ownership-tab";
import { AuditLogTab } from "./audit-log-tab";
import { OrgScopeProvider, orgScopedKey } from "./org-scope";

const TABS_ID = "team";

/**
 * Shared org team/RBAC screen, reused by two personas via `source`:
 *
 * - `"self"` (default — `/partner/team`): loads the caller's own org via
 *   `GET /organizations` and threads no `?org_id=`. Byte-for-byte unchanged.
 * - `"managed"` (`/university/team`): loads the org the caller manages via
 *   `GET /organizations/current` (for a superadmin: the single university org),
 *   then threads its id as `?org_id=` into every sub-query/mutation so a pure
 *   superadmin and a university-admin member both operate on the right org.
 */
export function TeamScreen({ source = "self" }: { source?: "self" | "managed" }) {
  const t = useTranslations("team");
  const tStates = useTranslations("states");
  const [tab, setTab] = useState("members");

  const user = useAuthStore((s) => s.user);
  const isSuperadmin = user?.isSuperadmin ?? false;
  const isManaged = source === "managed";

  // Discover the org this screen operates on. Managed = "the org I manage"
  // (superadmin -> single university org); self = the caller's own org.
  const orgQuery = useQuery({
    queryKey: isManaged ? ["org", "managed-profile"] : ["org", "profile"],
    queryFn: () => (isManaged ? organizationApi.getCurrent() : organizationApi.get()),
    retry: false,
  });

  // The org id threaded as `?org_id=` everywhere (null on the partner/self path).
  // Sub-queries wait until it resolves so a superadmin never hits an endpoint
  // without the org context it needs.
  const scopedOrgId = isManaged ? (orgQuery.data?.id ?? null) : null;
  const scopeReady = !isManaged || scopedOrgId !== null;

  // Shared queries (deduped by key with the tabs; org-scoped for the managed path).
  const rolesQuery = useQuery({
    queryKey: orgScopedKey(["org", "roles"], scopedOrgId),
    queryFn: () => organizationApi.listRoles(scopedOrgId),
    enabled: scopeReady,
    retry: false,
  });
  const membersQuery = useQuery({
    queryKey: orgScopedKey(["org", "members"], scopedOrgId),
    queryFn: () => organizationApi.listMembers(null, scopedOrgId),
    enabled: scopeReady,
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

  // University superadmins manage the whole org's RBAC; partner admins manage
  // their own org's team. The page label reflects the context.
  const title = isManaged ? t("universityTitle") : t("title");
  const subtitle = isManaged ? t("universitySubtitle") : t("subtitle");

  // Gate on the org query: 403 → permission, 401 → auth.
  if (orgQuery.isError && orgQuery.error instanceof ApiError) {
    const err = orgQuery.error;
    if (err.isPermissionError) {
      return (
        <>
          <PageHeader title={title} description={subtitle} />
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
          <PageHeader title={title} description={subtitle} />
          <EmptyState
            kind="auth"
            icon={SignIn}
            title={tStates("authTitle")}
            description={tStates("authBody")}
          />
        </>
      );
    }
    // Managed path resolves its org id from this query before any sub-query can
    // run, so a generic failure must surface here (rather than leaving the tabs
    // in a perpetual skeleton). The self/partner path falls through unchanged.
    if (isManaged) {
      return (
        <>
          <PageHeader title={title} description={subtitle} />
          <EmptyState
            kind="error"
            icon={Warning}
            title={tStates("errorTitle")}
            description={tStates("errorBody")}
          />
        </>
      );
    }
  }

  // Managed path: hold the tabs until the org id resolves so no sub-query fires
  // without the `?org_id=` context a superadmin needs.
  if (isManaged && !scopeReady && !orgQuery.isError) {
    return (
      <>
        <PageHeader title={title} description={subtitle} />
        <Skeleton className="mb-4 h-10 w-full max-w-md" />
        <Skeleton className="h-64 w-full" />
      </>
    );
  }

  const orgType = orgQuery.data?.org_type ?? (isManaged ? "university" : "partner");
  const maxSeats = orgQuery.data?.max_team_members ?? 4;
  const activeMembers = membersQuery.data?.data.filter(
    (m) => m.status === "active" || m.status === "pending"
  ).length ?? 0;
  const seatLimitEnabled = maxSeats !== -1;
  const atSeatLimit = seatLimitEnabled && activeMembers >= maxSeats;

  // Ownership transfer is a per-org designated-owner action (partner path). For
  // the university control plane the institution owns the org and superadmins
  // hold wildcard control, so the ownership tab is omitted there.
  const showOwnership = orgType !== "university";

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
    {
      value: "invitations",
      label: t("tabs.invitations"),
      icon: <EnvelopeSimple aria-hidden weight="duotone" className="size-4" />,
    },
    ...(showOwnership
      ? [
          {
            value: "ownership",
            label: t("tabs.ownership"),
            icon: <Crown aria-hidden weight="duotone" className="size-4" />,
          } satisfies TabItem,
        ]
      : []),
    {
      value: "auditLog",
      label: t("tabs.auditLog"),
      icon: <ClockCounterClockwise aria-hidden weight="duotone" className="size-4" />,
    },
  ];

  return (
    <OrgScopeProvider orgId={scopedOrgId}>
      <PageHeader title={title} description={subtitle} />

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
      <TabPanel tabsId={TABS_ID} value="invitations" active={tab === "invitations"}>
        <InvitationsTab
          effective={effective}
          holdsWildcard={holdsWildcard}
        />
      </TabPanel>
      {showOwnership && (
        <TabPanel tabsId={TABS_ID} value="ownership" active={tab === "ownership"}>
          <OwnershipTab />
        </TabPanel>
      )}
      <TabPanel tabsId={TABS_ID} value="auditLog" active={tab === "auditLog"}>
        <AuditLogTab />
      </TabPanel>
    </OrgScopeProvider>
  );
}
