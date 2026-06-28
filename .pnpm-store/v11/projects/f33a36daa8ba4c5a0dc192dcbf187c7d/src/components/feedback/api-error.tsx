import { WarningCircle } from "@phosphor-icons/react/dist/ssr";

export function ApiError({
  title = "Không thể tải dữ liệu",
  description,
}: {
  title?: string;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-red-900">
      <div className="flex items-start gap-3">
        <WarningCircle className="mt-0.5 size-5 shrink-0" weight="fill" />
        <div>
          <h2 className="font-semibold">{title}</h2>
          <p className="mt-1 text-sm leading-6 text-red-800">{description}</p>
        </div>
      </div>
    </div>
  );
}
