import { RegisterView } from "@/components/auth/register-view";

export default async function RegisterPage({
  searchParams,
}: {
  searchParams: Promise<{ returnTo?: string; email?: string }>;
}) {
  const sp = await searchParams;
  // Only accept internal, path-relative returnTo values (open-redirect guard),
  // mirroring the login page so a guest CTA can deep-link back after auth.
  const returnTo =
    typeof sp.returnTo === "string" && sp.returnTo.startsWith("/")
      ? sp.returnTo
      : undefined;
  const email = typeof sp.email === "string" ? sp.email : undefined;
  return <RegisterView returnTo={returnTo} email={email} />;
}
