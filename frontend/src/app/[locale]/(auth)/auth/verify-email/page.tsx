import { VerifyEmailView } from "@/components/auth/verify-email-view";

export default async function VerifyEmailPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string; email?: string }>;
}) {
  const sp = await searchParams;
  return (
    <VerifyEmailView
      token={typeof sp.token === "string" ? sp.token : undefined}
      email={typeof sp.email === "string" ? sp.email : undefined}
    />
  );
}
