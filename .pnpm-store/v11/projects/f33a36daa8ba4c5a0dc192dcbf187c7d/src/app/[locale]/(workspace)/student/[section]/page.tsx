import { notFound } from "next/navigation";
import { PortalSection } from "@/features/operations/portal-section";

const sections = new Set([
  "jobs",
  "cv",
  "applications",
  "interviews",
  "events",
  "reviews",
  "ai",
  "settings",
]);

export default async function StudentSectionPage({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  if (!sections.has(section)) notFound();
  return <PortalSection portal="student" section={section} />;
}
