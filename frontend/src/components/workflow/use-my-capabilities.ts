"use client";

import { useQuery } from "@tanstack/react-query";
import { organizationApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";

export interface MyCapabilities {
  /** Rendered "resource:action" permission strings resolved for the current member. */
  granted: ReadonlySet<string>;
  isSuperadmin: boolean;
  /**
   * False when the current member's role grants could not be confidently
   * resolved (still loading, request failed, or the member row was not found
   * on the first page of the directory). Callers should treat a "missing
   * capabilities" pre-check as advisory-only (not shown, or shown as
   * "unable to verify") when this is false — the real `/activate` call is
   * always the authoritative check.
   */
  resolved: boolean;
  isLoading: boolean;
}

/**
 * Best-effort resolution of the signed-in org member's granted capabilities,
 * for the workflow builder's pre-activation permission pre-check. There is no
 * dedicated "my capabilities" endpoint yet, so this composes the existing
 * roles + members directory reads. Only checks the first directory page —
 * fine for typical partner/university team sizes today; flagged as a
 * follow-up to add a real `GET /organizations/members/me` (or equivalent)
 * contract if org sizes grow past one page.
 */
export function useMyCapabilities(): MyCapabilities {
  const user = useAuthStore((s) => s.user);
  const enabled = Boolean(user) && user!.persona !== "student";

  const rolesQuery = useQuery({
    queryKey: ["org", "roles", "for-capability-check"],
    queryFn: () => organizationApi.listRoles(),
    enabled,
    staleTime: 60_000,
  });
  const membersQuery = useQuery({
    queryKey: ["org", "members", "for-capability-check"],
    queryFn: () => organizationApi.listMembers(),
    enabled,
    staleTime: 60_000,
  });

  const isSuperadmin = user?.isSuperadmin ?? false;
  const isLoading = enabled && (rolesQuery.isLoading || membersQuery.isLoading);

  if (!enabled || isLoading || rolesQuery.isError || membersQuery.isError || !rolesQuery.data || !membersQuery.data) {
    return { granted: new Set(), isSuperadmin, resolved: false, isLoading };
  }

  const me = membersQuery.data.data.find((m) => m.user_id === user!.id);
  if (!me) {
    return { granted: new Set(), isSuperadmin, resolved: false, isLoading: false };
  }

  const roleById = new Map(rolesQuery.data.map((r) => [r.id, r]));
  const granted = new Set<string>();
  for (const roleId of me.role_ids) {
    const role = roleById.get(roleId);
    role?.permissions.forEach((p) => granted.add(p));
  }
  return { granted, isSuperadmin, resolved: true, isLoading: false };
}
