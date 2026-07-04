"use client";

export function RevenueCard({
  label,
  value,
  loading,
  icon,
  iconBg = "icon-chip-primary",
}: {
  label: string;
  value: string;
  loading: boolean;
  icon: React.ReactNode;
  iconBg?: string;
}) {
  return (
    <div className="rounded-2xl border border-[var(--border-default)] bg-white px-5 py-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5 hover:shadow-[0_6px_24px_rgba(11,34,57,0.10)]">
      <div
        className={`mb-3 flex size-11 items-center justify-center rounded-xl shadow-sm ${iconBg}`}
      >
        {icon}
      </div>
      <p className="text-3xl font-black tracking-tight text-[var(--text-primary)]">
        {loading ? "…" : value}
      </p>
      <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">{label}</p>
    </div>
  );
}
