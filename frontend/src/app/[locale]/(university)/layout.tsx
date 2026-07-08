import { WorkspaceShell } from "@/components/layout/workspace-shell";

export default function UniversityLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <WorkspaceShell persona="university">{children}</WorkspaceShell>;
}
