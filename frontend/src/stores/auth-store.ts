"use client";

import { create } from "zustand";
import {
  authApi,
  clearSession,
  hasSessionHint,
  refreshSession,
  setSession,
  type AuthUser,
  type LoginResult,
} from "@/lib/api";
import { onboardingApi, type OnboardingStep } from "@/lib/api/onboarding";

export type Persona = "student" | "partner" | "university";

/**
 * Map a backend persona (student | alumni | partner_member | university_staff)
 * to the route-group persona used by the UI shells/navigation. Students and
 * alumni share the student workspace; org members land in their org workspace.
 */
export function normalizePersona(persona: string | null | undefined): Persona {
  switch (persona) {
    case "partner_member":
    case "partner":
      return "partner";
    case "university_staff":
    case "university":
      return "university";
    default:
      return "student";
  }
}

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  persona: Persona;
  /** Active organization id, when the identity is org-scoped. */
  orgId?: string | null;
  /** Platform-wide superadmin bypass (RBAC). */
  isSuperadmin?: boolean;
  /** Display tier label, e.g. "VinUni Student", "Alumni" (DESIGN.md §2.5). */
  tier?: string;
  avatarUrl?: string | null;
  /**
   * Permission strings from `/auth/me`. Superadmin accounts return `["*"]`.
   * Non-superadmin accounts carry explicit capability grants; defaults to `[]`.
   * Used by the sidebar to gate `requiresPermission` items.
   */
  permissions: string[];
}

function toSessionUser(u: AuthUser): SessionUser {
  const identity = u.active_identity ?? u.identities?.[0] ?? null;
  return {
    id: u.id,
    name: u.full_name || u.display_name || identity?.display_name || u.email,
    email: u.email,
    persona: normalizePersona(identity?.persona),
    orgId: identity?.org_id ?? null,
    isSuperadmin: u.is_superadmin ?? false,
    tier: identity?.tier ?? undefined,
    avatarUrl: u.avatar_url ?? null,
    permissions: u.permissions ?? [],
  };
}

interface AuthState {
  user: SessionUser | null;
  status: "unknown" | "authenticated" | "guest";
  /** Whether the user has completed onboarding. null = not yet checked. */
  onboardingComplete: boolean | null;
  /** Current onboarding step, for routing the wizard resume. */
  onboardingStep: OnboardingStep | null;

  /** Silent session restore on app load via refresh + /auth/me. */
  hydrate: () => Promise<void>;
  /**
   * Email/password sign-in. Returns the raw result so the form can branch to
   * the identity chooser or the TOTP second-factor step.
   */
  signIn: (email: string, password: string) => Promise<LoginResult>;
  /** Complete a TOTP-protected login by exchanging the challenge + 6-digit code. */
  completeTotp: (challengeToken: string, code: string) => Promise<LoginResult>;
  /**
   * Applies a session-bearing `LoginResult` obtained outside the normal
   * email/password form (e.g. OAuth ticket exchange, OAuth link-confirm).
   * Mirrors the post-login handling `signIn` does: persist the access token,
   * hydrate the user, and refresh onboarding state. Does not itself decide
   * navigation — callers branch on `requires_identity_selection` the same way
   * `LoginForm` does.
   */
  applyLoginResult: (result: LoginResult) => Promise<void>;
  /** Choose an active identity when one email maps to several personas. */
  selectIdentity: (identityId: string) => Promise<void>;
  /** Re-fetch the current user (after identity switch / profile change). */
  refreshMe: () => Promise<void>;
  /** Sign out everywhere on this device and clear local session. */
  signOut: () => Promise<void>;

  setUser: (user: SessionUser | null) => void;
  setGuest: () => void;
  /** Re-check onboarding status from the API and update store. */
  checkOnboarding: () => Promise<void>;
}

async function fetchOnboardingStatus() {
  try {
    const data = await onboardingApi.getStatus();
    return { complete: data.is_complete, step: data.current_step as OnboardingStep };
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  status: "unknown",
  onboardingComplete: null,
  onboardingStep: null,

  hydrate: async () => {
    if (!hasSessionHint()) {
      set({ user: null, status: "guest" });
      return;
    }
    const ok = await refreshSession();
    if (!ok) {
      set({ user: null, status: "guest" });
      return;
    }
    try {
      const me = await authApi.me();
      set({ user: toSessionUser(me), status: "authenticated" });
      // Check onboarding in background — do not block hydration
      fetchOnboardingStatus().then(ob => {
        if (ob) set({ onboardingComplete: ob.complete, onboardingStep: ob.step });
      });
    } catch {
      clearSession();
      set({ user: null, status: "guest" });
    }
  },

  signIn: async (email, password) => {
    const result = await authApi.login({ email, password });
    // TOTP-protected accounts return no tokens/cookie here — the form must
    // collect a 6-digit code and call completeTotp. Do not start a session.
    if (result.totp_required) {
      return result;
    }
    if (result.access_token) {
      setSession({ access_token: result.access_token });
    }
    if (!result.requires_identity_selection) {
      if (result.user) {
        set({ user: toSessionUser(result.user), status: "authenticated" });
      } else if (result.access_token) {
        await get().refreshMe();
      }
      // After sign-in, check onboarding so redirect guard can act
      await get().checkOnboarding();
    }
    return result;
  },

  applyLoginResult: async (result) => {
    if (result.access_token) {
      setSession({ access_token: result.access_token });
    }
    if (!result.requires_identity_selection) {
      if (result.user) {
        set({ user: toSessionUser(result.user), status: "authenticated" });
      } else if (result.access_token) {
        await get().refreshMe();
      }
      await get().checkOnboarding();
    }
  },

  completeTotp: async (challengeToken, code) => {
    const result = await authApi.loginTotp({
      challenge_token: challengeToken,
      code,
    });
    if (result.access_token) {
      setSession({ access_token: result.access_token });
    }
    if (!result.requires_identity_selection) {
      if (result.user) {
        set({ user: toSessionUser(result.user), status: "authenticated" });
      } else if (result.access_token) {
        await get().refreshMe();
      }
      await get().checkOnboarding();
    }
    return result;
  },

  selectIdentity: async (identityId) => {
    const result = await authApi.switchIdentity(identityId);
    if (result.access_token) {
      setSession({ access_token: result.access_token });
    }
    if (result.user) {
      set({ user: toSessionUser(result.user), status: "authenticated" });
    } else {
      await get().refreshMe();
    }
    await get().checkOnboarding();
  },

  refreshMe: async () => {
    const me = await authApi.me();
    set({ user: toSessionUser(me), status: "authenticated" });
  },

  signOut: async () => {
    try {
      await authApi.logout();
    } catch {
      // Best-effort: clear locally even if the server call fails.
    } finally {
      clearSession();
      set({ user: null, status: "guest", onboardingComplete: null, onboardingStep: null });
    }
  },

  setUser: (user) =>
    set({
      user,
      status: user ? "authenticated" : "guest",
      onboardingComplete: user ? get().onboardingComplete : null,
      onboardingStep: user ? get().onboardingStep : null,
    }),
  setGuest: () => set({ user: null, status: "guest", onboardingComplete: null, onboardingStep: null }),

  checkOnboarding: async () => {
    const ob = await fetchOnboardingStatus();
    if (ob) set({ onboardingComplete: ob.complete, onboardingStep: ob.step });
  },
}));
