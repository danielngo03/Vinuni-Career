"use client";

import { useTranslations } from "next-intl";
import { Button } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";

export function HeroActions() {
  const t = useTranslations("landing");
  const router = useRouter();

  return (
    <div className="mt-8 flex flex-col gap-3 sm:flex-row">
      <Button
        variant="primaryRed"
        size="xl"
        onClick={() => router.push("/jobs")}
      >
        {t("ctaFindJobs")} →
      </Button>
      <Button
        size="xl"
        className="border-2 border-white bg-transparent text-white hover:bg-white/10"
        onClick={() => router.push("/auth/partner-registration")}
      >
        {t("ctaEmployer")}
      </Button>
    </div>
  );
}
