import {
  Briefcase,
  Buildings,
  FileText,
  Globe,
} from "@phosphor-icons/react/dist/ssr";
import Image from "next/image";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Brand } from "@/components/brand/brand";
import { LoginForm } from "@/features/auth/login-form";
import { getSession } from "@/lib/auth/session";
import { isLocale, type Locale } from "@/lib/i18n/config";

export default async function LoginPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale: rawLocale } = await params;
  const locale: Locale = isLocale(rawLocale) ? rawLocale : "vi";
  const session = await getSession();
  if (session?.active_identity) {
    redirect(`/${locale}/${session.active_identity.portal}`);
  }
  const vi = locale === "vi";
  let oidc = { google: false, microsoft: false };
  try {
    const response = await fetch(
      `${process.env.BACKEND_URL || "http://127.0.0.1:8000/api/v1"}/auth/oidc/providers`,
      { cache: "no-store" },
    );
    if (response.ok) oidc = await response.json();
  } catch {
    // Password authentication remains available when SSO discovery is offline.
  }
  return (
    <main className="grid min-h-screen bg-white lg:grid-cols-[1.05fr_.95fr]">
      <section className="relative hidden overflow-hidden bg-navy text-white lg:block">
        <Image
          src="/images/career-day-2026.jpg"
          alt="VinUniversity Career Day"
          fill
          priority
          className="object-cover opacity-50"
        />
        <div className="absolute inset-0 bg-[linear-gradient(145deg,rgba(4,28,62,.98),rgba(12,72,159,.78),rgba(10,92,172,.38))]" />
        <div className="relative flex h-full flex-col p-10 xl:p-14">
          <Brand
            locale={locale}
            inverse
            variant="wordmark"
            className="w-fit"
          />
          <div className="my-auto max-w-xl">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-200">
              {vi ? "Cổng thông tin nghề nghiệp" : "Career services portal"}
            </p>
            <h1 className="mt-5 text-5xl font-semibold leading-[1.08] tracking-[-0.04em]">
              {vi
                ? "Mở lối sự nghiệp. Kết nối đúng cơ hội."
                : "Build your future. Connect with the right opportunities."}
            </h1>
            <p className="mt-6 max-w-lg text-base leading-7 text-blue-100/90">
              {vi
                ? "Không gian kết nối sinh viên VinUni, doanh nghiệp và nhà trường trong suốt hành trình phát triển nghề nghiệp."
                : "One trusted space connecting VinUni students, employers, and the university throughout every career journey."}
            </p>
            <div className="mt-9 space-y-4 text-blue-100">
              {[
                [
                  Briefcase,
                  vi
                    ? "Khám phá cơ hội phù hợp với năng lực"
                    : "Discover opportunities aligned with your strengths",
                ],
                [
                  FileText,
                  vi
                    ? "Xây dựng hồ sơ và theo dõi hành trình ứng tuyển"
                    : "Build your profile and track every application",
                ],
                [
                  Buildings,
                  vi
                    ? "Kết nối cùng mạng lưới doanh nghiệp đối tác"
                    : "Connect with VinUni's employer network",
                ],
              ].map(([Icon, text]) => (
                <div key={String(text)} className="flex items-center gap-3">
                  <div className="flex size-9 items-center justify-center rounded-lg bg-white/10">
                    <Icon className="size-5" />
                  </div>
                  <span className="text-sm font-medium">{String(text)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
      <section className="relative flex min-h-screen items-center justify-center bg-slate-50/60 px-5 py-10 sm:px-10">
        <div className="absolute right-5 top-5 flex items-center rounded-xl border bg-white p-1 shadow-sm sm:right-8 sm:top-7">
          <Globe className="ml-2 size-4 text-muted" />
          {(["vi", "en"] as const).map((language) => (
            <Link
              key={language}
              href={`/${language}/login`}
              aria-current={locale === language ? "page" : undefined}
              className={`focus-ring ml-1 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                locale === language
                  ? "bg-blue-50 text-primary"
                  : "text-slate-500 hover:text-foreground"
              }`}
            >
              {language === "vi" ? "VI" : "EN"}
            </Link>
          ))}
        </div>
        <div className="w-full max-w-[500px] pt-10">
          <div className="mb-8 lg:hidden">
            <Brand locale={locale} variant="wordmark" />
          </div>
          <div className="rounded-[1.75rem] border border-slate-200/80 bg-white p-6 shadow-[0_24px_70px_-32px_rgba(15,46,96,0.24)] sm:p-8">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary">
              {vi ? "VinUni Career Platform" : "VinUni Career Platform"}
            </p>
            <h2 className="mt-3 text-[2rem] font-semibold leading-tight tracking-[-0.035em]">
              {vi ? "Chào mừng bạn" : "Welcome"}
            </h2>
            <p className="mt-3 text-sm leading-6 text-muted">
              {vi
                ? "Đăng nhập hoặc tạo tài khoản để tiếp tục hành trình nghề nghiệp."
                : "Sign in or create an account to continue your career journey."}
            </p>
            <div className="mt-7">
              <LoginForm locale={locale} oidc={oidc} />
            </div>
          </div>
          <p className="mt-6 text-center text-xs leading-5 text-muted">
            {vi ? "Bằng việc đăng nhập, bạn đồng ý với " : "By signing in, you agree to "}
            <Link href={`/${locale}#legal`} className="font-semibold text-primary">
              {vi ? "điều khoản và chính sách dữ liệu" : "terms and data policy"}
            </Link>
            .
          </p>
        </div>
      </section>
    </main>
  );
}
