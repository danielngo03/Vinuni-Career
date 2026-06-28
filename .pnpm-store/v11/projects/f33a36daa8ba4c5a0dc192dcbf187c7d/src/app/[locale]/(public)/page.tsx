import {
  ArrowRight,
  Brain,
  Briefcase,
  Buildings,
  CheckCircle,
  ShieldCheck,
  Student,
} from "@phosphor-icons/react/dist/ssr";
import Image from "next/image";
import Link from "next/link";
import { Brand } from "@/components/brand/brand";
import { Button } from "@/components/ui/button";
import { isLocale, type Locale } from "@/lib/i18n/config";

export default async function LandingPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale: rawLocale } = await params;
  const locale: Locale = isLocale(rawLocale) ? rawLocale : "vi";
  const vi = locale === "vi";
  return (
    <div className="min-h-screen bg-white">
      <header className="sticky top-0 z-30 border-b bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-[72px] max-w-7xl items-center gap-8 px-4 sm:px-6">
          <Brand locale={locale} />
          <nav className="hidden items-center gap-7 text-sm font-medium text-slate-600 lg:flex">
            <a className="focus-ring rounded hover:text-foreground" href="#platform">
              {vi ? "Nền tảng" : "Platform"}
            </a>
            <a className="focus-ring rounded hover:text-foreground" href="#roles">
              {vi ? "Giải pháp" : "Solutions"}
            </a>
            <a className="focus-ring rounded hover:text-foreground" href="#trust">
              {vi ? "An toàn AI" : "Responsible AI"}
            </a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <Button variant="ghost" asChild>
              <Link href={`/${locale === "vi" ? "en" : "vi"}`}>
                {locale.toUpperCase()}
              </Link>
            </Button>
            <Button asChild>
              <Link href={`/${locale}/login`}>
                {vi ? "Đăng nhập" : "Sign in"}
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>
        </div>
      </header>

      <main>
        <section className="relative overflow-hidden bg-[#071f43] text-white">
          <Image
            src="/images/career-day-2026.jpg"
            alt="VinUniversity Career Day"
            fill
            priority
            className="object-cover object-center opacity-45"
          />
          <div className="absolute inset-0 bg-[linear-gradient(90deg,#071f43_0%,rgba(7,31,67,.94)_42%,rgba(7,31,67,.25)_78%)]" />
          <div className="relative mx-auto grid min-h-[650px] max-w-7xl items-center px-4 py-20 sm:px-6 lg:grid-cols-[1.05fr_.95fr]">
            <div className="max-w-2xl">
              <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-xs font-semibold text-cyan-100">
                <Brain className="size-4" weight="fill" />
                {vi
                  ? "Career intelligence có trách nhiệm"
                  : "Responsible career intelligence"}
              </div>
              <h1 className="text-4xl font-semibold leading-[1.08] tracking-[-0.04em] sm:text-6xl">
                {vi
                  ? "Biến dữ liệu thành cơ hội nghề nghiệp thực tế."
                  : "Turn data into real career opportunities."}
              </h1>
              <p className="mt-6 max-w-xl text-lg leading-8 text-blue-100">
                {vi
                  ? "Một nền tảng thống nhất cho sinh viên, doanh nghiệp và nhà trường—từ CV ẩn danh đến tuyển dụng và kiểm duyệt bằng AI."
                  : "One platform for students, employers and universities—from privacy-first CVs to AI-assisted recruitment and moderation."}
              </p>
              <div className="mt-9 flex flex-col gap-3 sm:flex-row">
                <Button size="lg" asChild className="bg-white text-navy hover:bg-blue-50">
                  <Link href={`/${locale}/login`}>
                    {vi ? "Bắt đầu ngay" : "Get started"}
                    <ArrowRight className="size-4" />
                  </Link>
                </Button>
                <Button
                  size="lg"
                  variant="outline"
                  asChild
                  className="border-white/30 bg-white/5 text-white hover:bg-white/10"
                >
                  <a href="#platform">{vi ? "Khám phá nền tảng" : "Explore platform"}</a>
                </Button>
              </div>
              <div className="mt-10 flex flex-wrap gap-x-7 gap-y-3 text-sm text-blue-100">
                {[
                  vi ? "Bảo vệ PII" : "PII protection",
                  vi ? "Phân quyền theo tổ chức" : "Organization RBAC",
                  vi ? "AI có kiểm soát" : "Governed AI",
                ].map((item) => (
                  <span key={item} className="flex items-center gap-2">
                    <CheckCircle className="size-4 text-cyan-300" weight="fill" />
                    {item}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="platform" className="mx-auto max-w-7xl px-4 py-20 sm:px-6">
          <div className="max-w-2xl">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-primary">
              {vi ? "Một hệ sinh thái" : "One ecosystem"}
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">
              {vi
                ? "Mỗi vai trò có một workspace riêng, cùng dùng một nguồn dữ liệu."
                : "A focused workspace for every role, powered by one source of truth."}
            </h2>
          </div>
          <div id="roles" className="mt-10 grid gap-5 md:grid-cols-3">
            {[
              {
                icon: Student,
                title: vi ? "Sinh viên" : "Students",
                text: vi
                  ? "Xây CV, tìm cơ hội phù hợp, theo dõi ứng tuyển và chuẩn bị phỏng vấn."
                  : "Build CVs, discover matching roles and prepare for interviews.",
              },
              {
                icon: Briefcase,
                title: vi ? "Doanh nghiệp" : "Employers",
                text: vi
                  ? "Đăng tuyển, quản lý pipeline ứng viên và tuyển dụng công bằng hơn."
                  : "Publish roles, manage candidate pipelines and hire more fairly.",
              },
              {
                icon: Buildings,
                title: vi ? "Nhà trường" : "University",
                text: vi
                  ? "Kiểm duyệt, đo lường hiệu quả và quản trị hệ sinh thái nghề nghiệp."
                  : "Moderate, measure and govern the career ecosystem.",
              },
            ].map(({ icon: Icon, title, text }) => (
              <article
                key={title}
                className="rounded-2xl border bg-white p-6 transition-colors hover:border-blue-200"
              >
                <div className="flex size-11 items-center justify-center rounded-xl bg-blue-50 text-primary">
                  <Icon className="size-6" weight="duotone" />
                </div>
                <h3 className="mt-6 text-xl font-semibold">{title}</h3>
                <p className="mt-3 text-sm leading-7 text-muted">{text}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="trust" className="bg-slate-50">
          <div className="mx-auto grid max-w-7xl gap-10 px-4 py-20 sm:px-6 lg:grid-cols-2 lg:items-center">
            <div>
              <ShieldCheck className="size-10 text-primary" weight="duotone" />
              <h2 className="mt-5 text-3xl font-semibold tracking-[-0.03em]">
                {vi
                  ? "AI hỗ trợ quyết định—không thay thế trách nhiệm."
                  : "AI supports decisions—it does not replace accountability."}
              </h2>
              <p className="mt-4 max-w-xl leading-7 text-muted">
                {vi
                  ? "Dữ liệu nhạy cảm được che trước khi xử lý; mọi gợi ý có bằng chứng, quota và audit trail theo tổ chức."
                  : "Sensitive data is masked before processing; recommendations include evidence, quotas and organization-level audit trails."}
              </p>
            </div>
            <Image
              src="/images/career-intelligence.png"
              alt="Career intelligence workflow"
              width={1600}
              height={900}
              className="w-full rounded-2xl border bg-white object-cover shadow-sm"
            />
          </div>
        </section>
      </main>
      <footer className="border-t bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-8 text-sm text-muted sm:px-6 md:flex-row md:items-center">
          <Brand locale={locale} compact />
          <p className="md:ml-auto">© 2026 VinUni Career Platform</p>
        </div>
      </footer>
    </div>
  );
}
