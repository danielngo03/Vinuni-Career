import {
  Brain,
  Briefcase,
  CalendarCheck,
  ChartLineUp,
  Database,
  LockKey,
  Wallet,
  Waveform,
} from "@phosphor-icons/react/dist/ssr";
import type { MetricItem } from "@/lib/api/types";

const icons = {
  brain: Brain,
  lock: LockKey,
  activity: Waveform,
  database: Database,
  wallet: Wallet,
  briefcase: Briefcase,
  calendar: CalendarCheck,
  chart: ChartLineUp,
};

export function MetricStrip({ metrics }: { metrics: MetricItem[] }) {
  return (
    <section className="grid divide-y rounded-xl border bg-white sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-4">
      {metrics.map((metric) => {
        const Icon = icons[metric.icon as keyof typeof icons] || Waveform;
        return (
          <article key={metric.label} className="flex min-w-0 items-center gap-4 px-5 py-4">
            <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-blue-50 text-primary">
              <Icon className="size-6" weight="duotone" />
            </div>
            <div className="min-w-0">
              <p className="text-2xl font-semibold tracking-[-0.03em]">{metric.value}</p>
              <p className="truncate text-sm font-medium">{metric.label}</p>
              <p className="mt-0.5 truncate text-xs text-muted">{metric.delta}</p>
            </div>
          </article>
        );
      })}
    </section>
  );
}
