import { OauthLinkConflictView } from "@/components/auth/oauth-link-conflict-view";

export default async function OauthLinkConflictPage({
  searchParams,
}: {
  searchParams: Promise<{ ticket?: string; email?: string }>;
}) {
  const sp = await searchParams;
  return (
    <OauthLinkConflictView
      ticket={typeof sp.ticket === "string" ? sp.ticket : undefined}
      email={typeof sp.email === "string" ? sp.email : undefined}
    />
  );
}
