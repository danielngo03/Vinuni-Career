import { getTranslations } from "next-intl/server";
import Image from "next/image";
import {
  Briefcase,
  CalendarCheck,
  ReadCvLogo,
} from "@phosphor-icons/react/dist/ssr";
import { PlatformStatus } from "./_components/platform-status";
import { MarketplaceHero } from "./_components/marketplace-hero";
import { MarketplaceOverview } from "./_components/marketplace-overview";
import { QuickSnapshotCard } from "./_components/quick-snapshot-card";
import { PartnerBannerSlider } from "./_components/partner-banner-slider";
import { CuratedSpotlight } from "./_components/curated-spotlight";

const FEATURES = [
  {
    icon: Briefcase,
    chip: "icon-chip-primary",
    key: "feature1Title" as const,
    bodyKey: "feature1Body" as const,
  },
  {
    icon: ReadCvLogo,
    chip: "icon-chip-success",
    key: "feature2Title" as const,
    bodyKey: "feature2Body" as const,
  },
  {
    icon: CalendarCheck,
    chip: "icon-chip-info",
    key: "feature3Title" as const,
    bodyKey: "feature3Body" as const,
  },
] as const;

export default async function HomePage() {
  const [t, tm] = await Promise.all([
    getTranslations("landing"),
    getTranslations("marketplace"),
  ]);

  return (
    <>
      {/* ── Public marketplace gateway: follows docs/DESIGN_EXAMPLE.png structurally. ── */}
      <section className="relative border-b border-[var(--border-default)] bg-[var(--brand-navy)] pb-14">
        <div className="mx-auto grid min-h-[350px] max-w-[1400px] grid-cols-1 lg:grid-cols-[64%_36%]">
          <div className="relative flex items-center overflow-hidden px-6 py-10 lg:px-6">
            <div
              aria-hidden
              className="absolute inset-0 opacity-[0.18]"
              style={{
                backgroundImage:
                  "linear-gradient(135deg, rgba(255,255,255,0.16) 1px, transparent 1px)",
                backgroundSize: "28px 28px",
              }}
            />
            <div className="relative w-full">
              <div className="max-w-[620px]">
                <h1 className="text-[2.15rem] font-extrabold leading-[1.14] tracking-tight text-white sm:text-[2.7rem] lg:text-[3rem]">
                  {tm.rich("heroHeadline", {
                    highlight: (chunks) => (
                      <span className="text-white">{chunks}</span>
                    ),
                  })}
                </h1>
                <p className="mt-5 max-w-[560px] text-[0.98rem] font-medium leading-7 text-[var(--blue-100)]/82">
                  {tm("heroSubtitle")}
                </p>
              </div>
            </div>
          </div>
          <div className="relative min-h-[260px] overflow-hidden">
            <Image
              src="/images/vinuni-campus.png"
              alt="VinUniversity campus"
              fill
              priority
              sizes="(max-width: 1024px) 100vw, 36vw"
              className="object-cover"
            />
          </div>
        </div>

        <div className="absolute inset-x-0 bottom-0 z-10 translate-y-[55%] px-4 lg:px-6">
          <div className="mx-auto max-w-[1400px] rounded-[14px] border border-[var(--border-default)] bg-[var(--surface-card)] p-3 shadow-[0_18px_44px_rgba(11,34,57,0.16)]">
            <MarketplaceHero variant="search" />
          </div>
        </div>
      </section>

      {/* Live marketplace data starts immediately below the gateway. */}
      <div className="pt-16">
        <MarketplaceOverview />
      </div>

      {/* Partner and university-curated visual placements. */}
      <section className="career-container grid grid-cols-1 gap-4 py-4 lg:grid-cols-[1fr_320px]">
        <PartnerBannerSlider />
        <QuickSnapshotCard />
      </section>

      {/* ── Curated spotlight — university-selected editorial (not paid) ── */}
      <CuratedSpotlight />

      {/* ── Feature highlights + platform status ── */}
      <section className="border-t border-[var(--border-default)] bg-[var(--surface-card)]">
        <div className="career-container py-10 lg:py-12">
          <h2 className="text-lg font-bold tracking-tight text-[var(--brand-navy)]">
            {t("featuresTitle")}
          </h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {t("featuresSubtitle")}
          </p>
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {FEATURES.map(({ icon: Icon, chip, key, bodyKey }) => (
              <div
                key={key}
                className="marketplace-card flex items-start gap-3.5 rounded-[14px] p-4"
              >
                <span className={`flex size-9 shrink-0 items-center justify-center rounded-xl ${chip}`}>
                  <Icon aria-hidden weight="duotone" className="size-5" />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-bold text-[var(--brand-navy)]">{t(key)}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-secondary)]">
                    {t(bodyKey)}
                  </p>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-8">
            <PlatformStatus />
          </div>
        </div>
      </section>
    </>
  );
}
