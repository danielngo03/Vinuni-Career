import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";
import { Brand } from "@/components/brand/brand";
import { Button } from "@/components/ui/button";
import { isLocale, type Locale } from "@/lib/i18n/config";
import { 
  AnimatedHero, 
  AnimatedMarquee, 
  AnimatedRoles, 
  AnimatedBentoGrid,
  AnimatedMetrics,
  AnimatedTrust,
  AnimatedCTA 
} from "@/components/ui/animated-sections";

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
            <a className="focus-ring rounded hover:text-foreground transition-colors" href="#platform">
              {vi ? "Nền tảng" : "Platform"}
            </a>
            <a className="focus-ring rounded hover:text-foreground transition-colors" href="#roles">
              {vi ? "Giải pháp" : "Solutions"}
            </a>
            <a className="focus-ring rounded hover:text-foreground transition-colors" href="#trust">
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
        <AnimatedHero vi={vi} locale={locale} />
        <AnimatedMarquee vi={vi} />
        <AnimatedRoles vi={vi} />
        <AnimatedBentoGrid vi={vi} />
        <AnimatedMetrics vi={vi} />
        <AnimatedTrust vi={vi} />
        <AnimatedCTA vi={vi} locale={locale} />
      </main>
      
      <footer className="border-t bg-[#030914] text-slate-400">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-12 text-sm sm:px-6 md:flex-row md:items-center">
          <div className="invert">
            <Brand locale={locale} compact />
          </div>
          <p className="md:ml-auto">© 2026 VinUni Career Platform. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
