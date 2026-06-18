import { notFound } from "next/navigation";
import { PortalSection } from "@/features/operations/portal-section";

const sections = new Set([
  "registrations",
  "moderation",
  "partners",
  "workflows",
  "analytics",
  "ai",
  "settings",
]);

export default async function UniversitySectionPage({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  if (!sections.has(section)) notFound();
  return <PortalSection portal="university" section={section} />;
}
