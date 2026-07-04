import { LoginView } from "@/components/auth/login-view";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ returnTo?: string; email?: string }>;
}) {
  const sp = await searchParams;
  const returnTo =
    typeof sp.returnTo === "string" && sp.returnTo.startsWith("/")
      ? sp.returnTo
      : undefined;
  const email = typeof sp.email === "string" ? sp.email : undefined;
  return <LoginView returnTo={returnTo} email={email} />;
}
