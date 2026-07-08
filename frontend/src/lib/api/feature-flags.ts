import { api } from "./client";

/* -------------------------------------------------------------------------- */
/* Types — snake_case matching backend exactly                                 */
/* -------------------------------------------------------------------------- */

/**
 * One feature flag row from `GET /admin/feature-flags`.
 * The list endpoint returns `{data: [...]}` which `api.get` unwraps to the
 * bare array directly (typed as FeatureFlag[]).
 */
export interface FeatureFlag {
  id: string;
  key: string;
  description: string;
  enabled: boolean;
  rollout_percentage: number;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

/** Body for `POST /admin/feature-flags`. */
export interface FeatureFlagCreateBody {
  key: string;
  description: string;
  enabled: boolean;
  rollout_percentage: number;
}

/** Partial body for `PATCH /admin/feature-flags/{flag_id}`. */
export interface FeatureFlagUpdateBody {
  enabled?: boolean;
  description?: string;
  rollout_percentage?: number;
}

/**
 * One resource+actions row from `GET /admin/permission-catalog`.
 * Both arrays are sorted by the backend.
 */
export interface PermissionCatalogEntry {
  resource: string;
  actions: string[];
}

/** Response shape for `GET /admin/permission-catalog` (NOT a `{data:...}` envelope). */
export interface PermissionCatalogResponse {
  catalog: PermissionCatalogEntry[];
}

/* -------------------------------------------------------------------------- */
/* API object                                                                  */
/* -------------------------------------------------------------------------- */

export const featureFlagsApi = {
  /**
   * List all feature flags.
   * `GET /admin/feature-flags`
   * Returns a bare array after `api.get` unwraps the outer `{data: [...]}`.
   */
  list(): Promise<FeatureFlag[]> {
    return api.get<FeatureFlag[]>("/admin/feature-flags");
  },

  /**
   * Create a new feature flag.
   * `POST /admin/feature-flags`
   * 409 = duplicate key (user-safe ApiError message).
   */
  create(body: FeatureFlagCreateBody): Promise<FeatureFlag> {
    return api.post<FeatureFlag>("/admin/feature-flags", body);
  },

  /**
   * Partially update an existing feature flag.
   * `PATCH /admin/feature-flags/{flag_id}`
   * 404 if the flag does not exist.
   */
  update(flagId: string, body: FeatureFlagUpdateBody): Promise<FeatureFlag> {
    return api.patch<FeatureFlag>(`/admin/feature-flags/${flagId}`, body);
  },

  /**
   * Read-only permission catalog — lists every resource+action pair known to
   * the system (for admin reference).
   * `GET /admin/permission-catalog`
   * Returns `{ catalog: [...] }` — NOT a `{data:...}` envelope, so we call
   * `api.get` which unwraps the outer `{data: ...}` layer; the inner object
   * has the `catalog` key directly.
   */
  permissionCatalog(): Promise<PermissionCatalogResponse> {
    return api.get<PermissionCatalogResponse>("/admin/permission-catalog");
  },
};
