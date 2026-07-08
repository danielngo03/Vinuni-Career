"use client";

import { useQuery } from "@tanstack/react-query";
import { organizationApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import type { OrgIdentity } from "./thread-panel";

/**
 * The caller's own organization identity (name/slug/logo) for the "Replying as"
 * affordance in org threads. Only fetched for partner/university personas;
 * students act as themselves and get `null`. Cached long — org identity is stable.
 */
export function useMyOrgIdentity(): OrgIdentity | null {
  const persona = useAuthStore((s) => s.user?.persona);
  const isOrgPersona = persona === "partner" || persona === "university";

  const { data } = useQuery({
    queryKey: ["messaging", "my-org"],
    queryFn: () => organizationApi.get(),
    enabled: isOrgPersona,
    staleTime: 5 * 60_000,
    retry: false,
  });

  if (!isOrgPersona || !data) return null;
  return {
    name: data.display_name,
    slug: data.slug,
    logoUrl: data.logo_url ?? null,
  };
}
