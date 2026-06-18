export function RingScore({
  value,
  label,
  description,
}: {
  value: number;
  label: string;
  description?: string;
}) {
  const safe = Math.max(0, Math.min(100, value));
  return (
    <div className="flex items-center gap-4">
      <div
        className="grid size-24 shrink-0 place-items-center rounded-full"
        style={{
          background: `conic-gradient(var(--cyan) ${safe * 3.6}deg, #e7edf5 0deg)`,
        }}
      >
        <div className="grid size-[76px] place-items-center rounded-full bg-white">
          <span className="text-xl font-semibold">{safe}%</span>
        </div>
      </div>
      <div>
        <p className="text-sm font-semibold">{label}</p>
        {description ? (
          <p className="mt-1 text-xs leading-5 text-muted">{description}</p>
        ) : null}
      </div>
    </div>
  );
}
