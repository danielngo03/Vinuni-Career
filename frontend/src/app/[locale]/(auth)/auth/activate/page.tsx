import { ActivateView } from "@/components/auth/activate-view";

export default async function ActivatePage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const sp = await searchParams;
  return (
    <ActivateView token={typeof sp.token === "string" ? sp.token : undefined} />
  );
}
