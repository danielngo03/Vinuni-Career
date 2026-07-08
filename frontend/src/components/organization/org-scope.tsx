"use client";

import { createContext, useContext } from "react";

/**
 * Org scope for the shared team/RBAC screen.
 *
 * The team screen (`team-screen.tsx`) and its tabs are reused by two personas:
 *
 * - **Partner** (`/partner/team`, `source="self"`): every org call resolves the
 *   caller's own org from `principal.org_id`. `orgId` is `null`, so no `?org_id=`
 *   is threaded and the request is byte-for-byte identical to before.
 * - **University / superadmin** (`/university/team`, `source="managed"`): the
 *   screen first loads `GET /organizations/current` to discover the org id it
 *   manages, then provides it here. Every sub-query/mutation threads it as
 *   `?org_id=` — a param the backend honours ONLY for superadmins — so a pure
 *   superadmin (whose `principal.org_id` is `null`) and a university-admin member
 *   both operate on the correct org.
 *
 * The resolved `orgId` is also folded into react-query keys via {@link orgScopedKey}
 * so a partner session and a cross-org superadmin session never share a cache
 * bucket for the same resource.
 */
export interface OrgScope {
  /** Managed org id to thread as `?org_id=`, or `null` for the caller's own org. */
  orgId: string | null;
}

const OrgScopeContext = createContext<OrgScope>({ orgId: null });

export function OrgScopeProvider({
  orgId,
  children,
}: {
  orgId: string | null;
  children: React.ReactNode;
}) {
  return (
    <OrgScopeContext.Provider value={{ orgId }}>{children}</OrgScopeContext.Provider>
  );
}

export function useOrgScope(): OrgScope {
  return useContext(OrgScopeContext);
}

/**
 * Build an org-scoped react-query key: appends the managed `orgId` when present
 * so partner and cross-org superadmin caches never collide; returns the base key
 * unchanged when `null` (partner path) so existing prefix-based invalidation
 * (e.g. `["org", "members"]`) keeps matching.
 */
export function orgScopedKey(
  base: ReadonlyArray<string | undefined>,
  orgId: string | null,
): Array<string | undefined> {
  return orgId ? [...base, orgId] : [...base];
}
