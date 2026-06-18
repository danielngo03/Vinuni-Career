import { Badge } from "@/components/ui/badge";

export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toUpperCase();
  const tone =
    normalized.includes("APPROVED") ||
    normalized.includes("HIRED") ||
    normalized.includes("OFFERED")
      ? "green"
      : normalized.includes("PENDING") ||
          normalized.includes("INTERVIEW") ||
          normalized.includes("REVIEW")
        ? "amber"
        : normalized.includes("REJECT") || normalized.includes("CANCEL")
          ? "red"
          : "blue";
  return (
    <Badge tone={tone}>
      {status.replaceAll("_", " ").toLowerCase()}
    </Badge>
  );
}
