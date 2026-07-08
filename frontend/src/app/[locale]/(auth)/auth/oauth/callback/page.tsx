import { OauthCallbackView } from "@/components/auth/oauth-callback-view";

export default async function OauthCallbackPage({
  searchParams,
}: {
  searchParams: Promise<{ ticket?: string }>;
}) {
  const sp = await searchParams;
  return (
    <OauthCallbackView
      ticket={typeof sp.ticket === "string" ? sp.ticket : undefined}
    />
  );
}
