import { ArrowRight, Robot } from "@phosphor-icons/react/dist/ssr";
import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export function WorkspaceHero({
  eyebrow,
  title,
  description,
  action,
  actionHref,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action: string;
  actionHref?: string;
}) {
  return (
    <section className="hero-scrim relative min-h-[226px] overflow-hidden rounded-2xl text-white">
      <Image
        src="/images/career-day-2026.jpg"
        alt="VinUniversity Career Day"
        fill
        priority
        className="object-cover object-center opacity-55 mix-blend-screen"
      />
      <div className="absolute inset-0 hero-scrim opacity-95" />
      <div className="relative max-w-2xl p-7 sm:p-9">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-100">
          {eyebrow}
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">
          {title}
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-6 text-blue-100 sm:text-base">
          {description}
        </p>
        <Button
          className="mt-6 bg-white text-navy hover:bg-blue-50"
          asChild={Boolean(actionHref)}
        >
          {actionHref ? (
            <Link href={actionHref}>
              <Robot className="size-5" weight="duotone" />
              {action}
              <ArrowRight className="size-4" />
            </Link>
          ) : (
            <>
              <Robot className="size-5" weight="duotone" />
              {action}
              <ArrowRight className="size-4" />
            </>
          )}
        </Button>
      </div>
    </section>
  );
}
