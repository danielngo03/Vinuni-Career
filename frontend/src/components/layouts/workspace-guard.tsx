import { redirect } from "next/navigation";
import type { Portal } from "@/lib/api/types";
import type { Locale } from "@/lib/i18n/config";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { getSession } from "@/lib/auth/session";
import { WorkspaceShell } from "./workspace-shell";

export async function WorkspaceGuard({
  locale,
  portal,
  children,
}: {
  locale: Locale;
  portal: Portal;
  children: React.ReactNode;
}) {
  const session = await getSession();
  if (!session) redirect(`/${locale}/login`);
  if (!session.active_identity) redirect(`/${locale}/select-identity`);
  if (session.active_identity.portal !== portal) {
    redirect(`/${locale}/${session.active_identity.portal}`);
  }
  return (
    <WorkspaceShell
      locale={locale}
      portal={portal}
      session={session}
      dictionary={getDictionary(locale)}
    >
      {children}
    </WorkspaceShell>
  );
}
