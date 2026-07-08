import { api, apiFetch } from "./client";
import type { ApiListEnvelope } from "./types";

/* -------------------------------------------------------------------------- */
/* Types — snake_case matching backend exactly                                 */
/* -------------------------------------------------------------------------- */

/** One row from `GET /admin/users` (offset-paginated list). */
export interface PlatformUserRow {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  email_verified: boolean;
  persona: string;
  org_id: string | null;
  created_at: string | null;
}

/** Offset-pagination envelope returned by `GET /admin/users`. */
export interface PlatformUsersPage {
  items: PlatformUserRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** Query params for `GET /admin/users`. */
export interface PlatformUsersParams {
  persona?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

/** Identity attached to a user (from the 360 view). */
export interface PlatformUserIdentity {
  identity_id: string;
  persona: string;
  org_id: string | null;
  is_primary: boolean;
}

/** Full 360 view from `GET /admin/users/{id}`. */
export interface PlatformUser360 {
  core: {
    id: string;
    email: string;
    is_active: boolean;
    is_superadmin: boolean;
    email_verified: boolean;
    created_at: string | null;
    last_login_at: string | null;
  };
  identities: PlatformUserIdentity[];
  active_session_count: number;
  recent_ai_usage_count: number;
}

/** Suspend/unsuspend response. */
export interface PlatformUserActiveResult {
  id: string;
  is_active: boolean;
}

/** Grant/revoke superadmin response. */
export interface PlatformUserSuperadminResult {
  id: string;
  is_superadmin: boolean;
}

/** One session row from `GET /admin/sessions`. */
export interface AdminSession {
  session_id: string;
  user_id: string;
  user_email: string | null;
  device_hint: string | null;
  city_level_location: string | null;
  last_seen_at: string;
  created_at: string;
  expires_at: string;
}

/** Params for `GET /admin/sessions`. */
export interface AdminSessionsParams {
  user_id?: string;
  cursor?: string;
  limit?: number;
}

/** Unwrapped page result from `platformUsersApi.listSessions`. */
export interface AdminSessionsPage {
  items: AdminSession[];
  next_cursor: string | null;
}

/* -------------------------------------------------------------------------- */
/* API object                                                                  */
/* -------------------------------------------------------------------------- */

export const platformUsersApi = {
  /**
   * Offset-paginated user list.
   * `GET /admin/users?persona=&q=&page=&page_size=`
   *
   * NOTE: this endpoint returns a plain object (not the cursor-paginated
   * `{data:[...], page:{...}}` envelope), so we call `api.get` which unwraps
   * the outer `{data: ...}` wrapper to get the inner `PlatformUsersPage`.
   */
  list(params: PlatformUsersParams = {}): Promise<PlatformUsersPage> {
    const { persona, q, page, page_size } = params;
    return api.get<PlatformUsersPage>("/admin/users", {
      query: { persona, q, page, page_size },
    });
  },

  /**
   * Full 360 view for one user.
   * `GET /admin/users/{id}`
   */
  get360(id: string): Promise<PlatformUser360> {
    return api.get<PlatformUser360>(`/admin/users/${id}`);
  },

  /**
   * Suspend a user account.
   * `POST /admin/users/{id}/suspend`
   */
  suspend(id: string): Promise<PlatformUserActiveResult> {
    return api.post<PlatformUserActiveResult>(`/admin/users/${id}/suspend`, {});
  },

  /**
   * Unsuspend a user account.
   * `POST /admin/users/{id}/unsuspend`
   */
  unsuspend(id: string): Promise<PlatformUserActiveResult> {
    return api.post<PlatformUserActiveResult>(
      `/admin/users/${id}/unsuspend`,
      {},
    );
  },

  /**
   * Grant superadmin to a user.
   * `POST /admin/users/{id}/grant-superadmin`
   */
  grantSuperadmin(id: string): Promise<PlatformUserSuperadminResult> {
    return api.post<PlatformUserSuperadminResult>(
      `/admin/users/${id}/grant-superadmin`,
      {},
    );
  },

  /**
   * Revoke superadmin from a user.
   * `POST /admin/users/{id}/revoke-superadmin`
   * May return 409 when revoking the last active superadmin — the ApiError
   * message is user-safe and should be surfaced inline.
   */
  revokeSuperadmin(id: string): Promise<PlatformUserSuperadminResult> {
    return api.post<PlatformUserSuperadminResult>(
      `/admin/users/${id}/revoke-superadmin`,
      {},
    );
  },

  /**
   * Cursor-paginated admin session list.
   * `GET /admin/sessions?user_id=&cursor=&limit=`
   * Uses `api.list` to unwrap the `paginated()` envelope:
   *   `{ data: AdminSession[], page: { next_cursor, limit } }`.
   */
  async listSessions(
    params: AdminSessionsParams = {},
  ): Promise<AdminSessionsPage> {
    const { user_id, cursor, limit } = params;
    const envelope: ApiListEnvelope<AdminSession> =
      await api.list<AdminSession>("/admin/sessions", {
        query: { user_id, cursor, limit },
      });
    return {
      items: envelope.data,
      next_cursor: envelope.page.next_cursor,
    };
  },

  /**
   * Revoke a specific session.
   * `POST /admin/sessions/{session_id}/revoke`
   */
  revokeSession(sessionId: string): Promise<unknown> {
    return apiFetch(`/admin/sessions/${sessionId}/revoke`, {
      method: "POST",
      json: {},
    });
  },
};
