import { api, apiFetch } from "./client";
import { env } from "@/lib/env";
import type { Persona } from "@/stores/auth-store";

/* ----------------------------- Auth wire types ---------------------------- */

/**
 * Backend persona vocabulary (auth/domain/personas.py). Distinct from the
 * route-group `Persona` (student | partner | university) used by the UI; map
 * with `normalizePersona` in the auth store.
 */
export type BackendPersona =
  | "student"
  | "alumni"
  | "partner_member"
  | "university_staff";

export interface AuthIdentity {
  id: string;
  persona: BackendPersona | Persona;
  org_id?: string | null;
  is_primary?: boolean;
  is_active?: boolean;
  org_name?: string | null;
  tier?: string | null;
  display_name?: string | null;
}

export interface AuthUser {
  id: string;
  email: string;
  /** Backend returns `full_name`; older callers used `display_name`. */
  full_name?: string | null;
  display_name?: string | null;
  email_verified?: boolean;
  is_superadmin?: boolean;
  avatar_url?: string | null;
  active_identity?: AuthIdentity | null;
  identities?: AuthIdentity[];
  /**
   * Permission strings from `/auth/me`. Superadmin accounts return `["*"]`.
   * Non-superadmin accounts carry explicit capability grants; defaults to `[]`.
   */
  permissions?: string[];
}

export interface AuthTokens {
  access_token: string;
  token_type?: string;
  expires_in?: number;
}

export interface LoginResult extends Partial<AuthTokens> {
  user?: AuthUser | null;
  /** Set when one email maps to multiple personas and the user must pick one. */
  requires_identity_selection?: boolean;
  identities?: AuthIdentity[];
  /**
   * Set (200, no tokens, no cookie) when the account has TOTP enabled. The UI
   * must prompt for a 6-digit code and exchange `challenge_token` at
   * `/auth/login/totp`. Never persisted; the challenge token is short-lived.
   */
  totp_required?: boolean;
  challenge_token?: string;
}

export interface RegisterResult {
  user?: AuthUser | null;
  /** True when the account must verify its email before logging in. */
  requires_verification?: boolean;
  /** Current backend response for newly-created local accounts. */
  status?: "verification_sent" | string;
  email?: string;
}

/* ------------------------------- Auth calls ------------------------------- */

export const authApi = {
  register(body: {
    email: string;
    password: string;
    full_name?: string | null;
  }): Promise<RegisterResult> {
    return api.post<RegisterResult>("/auth/register", body, { skipAuth: true });
  },

  oauthStartUrl(
    provider: "google" | "facebook",
    params: { mode?: "login" | "register"; returnTo?: string } = {},
  ): string {
    const base = env.apiBaseUrl.replace(/\/$/, "");
    const url = new URL(`${base}/auth/oauth/${provider}/start`);
    if (params.mode) url.searchParams.set("mode", params.mode);
    if (params.returnTo) url.searchParams.set("return_to", params.returnTo);
    return url.toString();
  },

  /**
   * Exchanges the one-time ticket from a successful OAuth provider round-trip
   * for a full session (access token + user + httpOnly refresh cookie). Same
   * response shape as `login()`/`loginTotp()`.
   */
  oauthExchange(body: { ticket: string }): Promise<LoginResult> {
    return api.post<LoginResult>("/auth/oauth/exchange", body, {
      skipAuth: true,
    });
  },

  /**
   * Confirms linking an OAuth identity to an existing password account by
   * verifying the account password. Wrong password → uniform 401
   * `AUTH_REQUIRED` (enumeration-safe, same as regular login).
   */
  oauthLinkConfirm(body: {
    ticket: string;
    password: string;
  }): Promise<LoginResult> {
    return api.post<LoginResult>("/auth/oauth/link-confirm", body, {
      skipAuth: true,
    });
  },

  verifyEmail(body: { token: string }): Promise<unknown> {
    return apiFetch("/auth/verify-email", {
      method: "POST",
      json: body,
      skipAuth: true,
    });
  },

  resendVerification(body: { email: string }): Promise<unknown> {
    return apiFetch("/auth/verify-email/resend", {
      method: "POST",
      json: body,
      skipAuth: true,
    });
  },

  verifyEmailOtp(body: {
    email: string;
    otp_code: string;
    purpose?: string;
  }): Promise<{ email: string; email_verified: boolean }> {
    return apiFetch("/auth/verify-email/otp", {
      method: "POST",
      json: body,
      skipAuth: true,
    });
  },

  login(body: { email: string; password: string }): Promise<LoginResult> {
    return api.post<LoginResult>("/auth/login", body, { skipAuth: true });
  },

  /**
   * Second factor for TOTP-protected accounts. Exchanges the short-lived
   * `challenge_token` from a `totp_required` login plus the 6-digit code for a
   * full session (access token + user + httpOnly refresh cookie). Wrong/expired
   * code → 401 invalid-credentials.
   */
  loginTotp(body: {
    challenge_token: string;
    code: string;
  }): Promise<LoginResult> {
    return api.post<LoginResult>("/auth/login/totp", body, { skipAuth: true });
  },

  switchIdentity(identityId: string): Promise<LoginResult> {
    return api.post<LoginResult>("/auth/identity", { identity_id: identityId });
  },

  /** List all identities for the current user (org switching after invite accept). */
  listIdentities(): Promise<AuthIdentity[]> {
    return api.get<AuthIdentity[]>("/auth/identity");
  },

  me(): Promise<AuthUser> {
    return api.get<AuthUser>("/auth/me");
  },

  /** Set a password + verify email for an approved/invited account. */
  activate(body: { token: string; password: string }): Promise<{
    email: string;
    email_verified: boolean;
  }> {
    return api.post("/auth/activate", body, { skipAuth: true });
  },

  logout(): Promise<unknown> {
    return apiFetch("/auth/logout", { method: "POST", json: {} });
  },

  forgotPassword(body: { email: string }): Promise<unknown> {
    return apiFetch("/auth/forgot-password", {
      method: "POST",
      json: body,
      skipAuth: true,
    });
  },

  resetPassword(body: { token: string; password: string }): Promise<unknown> {
    return apiFetch("/auth/reset-password", {
      method: "POST",
      json: body,
      skipAuth: true,
    });
  },

  resetPasswordOtp(body: {
    email: string;
    otp_code: string;
    password: string;
  }): Promise<unknown> {
    return apiFetch("/auth/reset-password/otp", {
      method: "POST",
      json: body,
      skipAuth: true,
    });
  },
};

/* ---------------------------- Account settings ---------------------------- */

export interface NotificationCategoryPref {
  in_app: boolean;
  email: boolean;
  push: boolean;
  /** Mandatory/security categories are returned locked and cannot be disabled. */
  locked?: boolean;
}

export interface AccountPreferences {
  locale: string;
  timezone: string;
  theme?: "light" | "dark" | "system";
  quiet_hours: { enabled: boolean; start: string; end: string };
  categories: Record<string, NotificationCategoryPref>;
}

/** Privacy-safe session: never raw IP, raw UA, or refresh token. */
export interface AccountSession {
  id: string;
  browser_family?: string | null;
  os_family?: string | null;
  device_label?: string | null;
  location?: string | null;
  last_seen_at: string;
  current: boolean;
}

export interface SecurityEvent {
  id: string;
  type: string;
  description?: string | null;
  occurred_at: string;
}

export interface TotpSetup {
  secret: string;
  otpauth_url?: string | null;
}

export const accountApi = {
  getPreferences(): Promise<AccountPreferences> {
    return api.get<AccountPreferences>("/account/preferences");
  },

  updatePreferences(
    body: Partial<AccountPreferences>,
  ): Promise<AccountPreferences> {
    return api.patch<AccountPreferences>("/account/preferences", body);
  },

  getSessions() {
    return api.list<AccountSession>("/account/sessions");
  },

  revokeSession(id: string): Promise<unknown> {
    return apiFetch(`/account/sessions/${id}/revoke`, {
      method: "POST",
      json: {},
    });
  },

  getSecurityEvents() {
    return api.list<SecurityEvent>("/account/security-events");
  },

  changePassword(body: {
    current_password: string;
    new_password: string;
  }): Promise<unknown> {
    return apiFetch("/account/password", { method: "PATCH", json: body });
  },

  totpSetup(): Promise<TotpSetup> {
    return api.post<TotpSetup>("/account/totp/setup", {});
  },

  totpVerify(body: { code: string }): Promise<unknown> {
    return apiFetch("/account/totp/verify", { method: "POST", json: body });
  },

  totpDisable(body: { code: string }): Promise<unknown> {
    return apiFetch("/account/totp/disable", { method: "POST", json: body });
  },
};
