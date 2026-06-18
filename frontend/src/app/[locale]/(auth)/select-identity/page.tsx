import { redirect } from "next/navigation";
import { Brand } from "@/components/brand/brand";
import { IdentitySelector } from "@/features/auth/identity-selector";
import { getSession } from "@/lib/auth/session";
import { isLocale, type Locale } from "@/lib/i18n/config";

export default async function SelectIdentityPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale: rawLocale } = await params;
  const locale: Locale = isLocale(rawLocale) ? rawLocale : "vi";
  const session = await getSession();
  if (!session) redirect(`/${locale}/login`);
  if (session.active_identity) {
    redirect(`/${locale}/${session.active_identity.portal}`);
  }
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12">
      <section className="w-full max-w-lg rounded-2xl border bg-white p-6 shadow-sm sm:p-8">
        <Brand locale={locale} />
        <h1 className="mt-10 text-3xl font-semibold tracking-[-0.03em]">
          {locale === "vi" ? "Chọn không gian làm việc" : "Choose a workspace"}
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted">
          {locale === "vi"
            ? "Tài khoản của bạn có nhiều vai trò. Bạn có thể đổi lại workspace bất kỳ lúc nào."
            : "Your account has multiple roles. You can switch workspaces at any time."}
        </p>
        <div className="mt-7">
          <IdentitySelector locale={locale} identities={session.identities} />
        </div>
      </section>
    </main>
  );
}
