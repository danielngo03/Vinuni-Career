import { ResetPasswordView } from "@/components/auth/reset-password-view";

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const sp = await searchParams;
  return (
    <ResetPasswordView
      token={typeof sp.token === "string" ? sp.token : undefined}
    />
  );
}
