import { cookies } from "next/headers";
import { cache } from "react";
import type { AuthSession, Identity } from "@/lib/api/types";
import { backendFetch } from "@/lib/api/server";
import { IDENTITY_COOKIE } from "./cookies";

export const getSession = cache(async (): Promise<AuthSession | null> => {
  try {
    const [user, identities] = await Promise.all([
      backendFetch<AuthSession["user"]>("/auth/me"),
      backendFetch<Identity[]>("/auth/identities"),
    ]);
    const identityId = (await cookies()).get(IDENTITY_COOKIE)?.value;
    return {
      user,
      identities,
      active_identity:
        identities.find((identity) => identity.id === identityId) ??
        (identities.length === 1 ? identities[0] : null),
    };
  } catch {
    return null;
  }
});

export function workspacePath(locale: string, portal: Identity["portal"]) {
  return `/${locale}/${portal}`;
}
