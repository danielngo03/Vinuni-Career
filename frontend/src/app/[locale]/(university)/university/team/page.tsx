import { SuperadminGuard } from "@/components/layout/superadmin-guard";
import { TeamScreen } from "@/components/organization/team-screen";

/**
 * University Team & Access (`/university/team`).
 *
 * The RBAC control plane for the VinUniversity org: departments, staff members,
 * roles/permissions, and invitations. Superadmin-only for this phase (the same
 * gating as the other superadmin surfaces in the university shell); a superadmin
 * may not be a member of the org, so `TeamScreen source="managed"` resolves the
 * org via `GET /organizations/current` and threads its id as `?org_id=` on every
 * sub-query/mutation. `SuperadminGuard` redirects non-superadmin staff to
 * `/university/dashboard`; backend RBAC remains the final authority.
 */
export default function UniversityTeamPage() {
  return (
    <SuperadminGuard>
      <TeamScreen source="managed" />
    </SuperadminGuard>
  );
}
