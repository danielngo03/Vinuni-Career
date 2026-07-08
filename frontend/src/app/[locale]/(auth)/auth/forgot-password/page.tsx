import { ForgotPasswordView } from "@/components/auth/forgot-password-view";

export default async function ForgotPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ email?: string }>;
}) {
  const sp = await searchParams;
  return (
    <ForgotPasswordView
      email={typeof sp.email === "string" ? sp.email : undefined}
    />
  );
}
