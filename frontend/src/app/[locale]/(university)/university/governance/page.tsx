import { AccountGovernanceScreen } from "@/components/governance/account-governance-screen";

/**
 * University cross-persona account governance (Phase 5).
 *
 * Grant-gated on `accounts:govern` (acting-university org; superadmin
 * bypasses). This is NOT a superadmin-only screen, so it is not wrapped in
 * `SuperadminGuard` — access is enforced by the backend (403 → clean
 * permission state in the screen) and the sidebar hides the entry for staff
 * without the grant (`requiresPermission`).
 */
export default function UniversityAccountGovernancePage() {
  return <AccountGovernanceScreen />;
}
