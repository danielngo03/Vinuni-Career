import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

export default function NotFound() {
  const t = useTranslations();
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-4 text-center">
      <p className="text-5xl font-black tracking-tight text-[var(--brand-primary)]">
        404
      </p>
      <h1 className="text-xl font-bold text-[var(--text-primary)]">
        {t("states.errorTitle")}
      </h1>
      <p className="max-w-sm text-sm text-[var(--text-secondary)]">
        {t("states.permissionBody")}
      </p>
      <Link
        href="/"
        className="rounded-lg bg-[var(--brand-primary)] px-4 py-2 text-sm font-semibold text-white outline-none"
      >
        {t("nav.home")}
      </Link>
    </div>
  );
}
