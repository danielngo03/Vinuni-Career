import { notFound } from "next/navigation";
import { PortalSection } from "@/features/operations/portal-section";
import { getSession } from "@/lib/auth/session";

const sections = new Set([
  "jobs",
  "candidates",
  "interviews",
  "analytics",
  "ai",
  "settings",
]);

export default async function PartnerSectionPage({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  if (!sections.has(section)) notFound();
  const session = await getSession();
  return (
    <PortalSection
      portal="partner"
      section={section}
      orgId={session?.active_identity?.org_id}
    />
  );
}
