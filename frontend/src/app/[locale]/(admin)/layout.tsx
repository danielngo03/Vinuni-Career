import { WorkspaceShell } from "@/components/layout/workspace-shell";

/**
 * Platform Admin console shell (`/admin/*`). A distinct superadmin-only
 * workspace split out of University Operations (owner decision 2026-07-08). It
 * reuses the shared `WorkspaceShell`/`Sidebar`/`Topbar` chrome with the `admin`
 * nav config and `/admin` base path, and is gated by `SuperadminGuard` at the
 * shell (inside `WorkspaceShell`) plus per-page guards. Backend `/admin/*` API
 * paths are unchanged.
 */
export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <WorkspaceShell persona="admin">{children}</WorkspaceShell>;
}
