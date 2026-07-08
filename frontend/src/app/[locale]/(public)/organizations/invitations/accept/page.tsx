import { InvitationAcceptView } from "@/components/organization/invitation-accept-view";

export default async function InvitationAcceptPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const sp = await searchParams;
  return (
    <InvitationAcceptView
      token={typeof sp.token === "string" ? sp.token : undefined}
    />
  );
}
