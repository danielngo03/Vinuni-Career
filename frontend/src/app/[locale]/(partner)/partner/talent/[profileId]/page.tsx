import { TalentProfileScreen } from "@/components/talent-pool/talent-profile-screen";

export default async function TalentProfilePage({
  params,
}: {
  params: Promise<{ profileId: string }>;
}) {
  const { profileId } = await params;
  return <TalentProfileScreen profileId={profileId} />;
}
