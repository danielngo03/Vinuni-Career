"use client";

/**
 * Legacy re-export shim. The guard previously lived here; it has been renamed
 * to `SuperadminGuard` and lives in `superadmin-guard.tsx`. This file keeps
 * backward compatibility for any import that still references `admin-guard`.
 *
 * @deprecated Import `SuperadminGuard` from `./superadmin-guard` directly.
 */
export { SuperadminGuard as AdminGuard } from "./superadmin-guard";
