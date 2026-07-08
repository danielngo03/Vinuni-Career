import { Suspense } from "react";
import { PublicEventBoard } from "@/components/events/public-event-board";

export default function PublicEventsPage() {
  // PublicEventBoard reads the `?q=` query via useSearchParams, which requires a
  // Suspense boundary for static rendering in the App Router.
  return (
    <Suspense>
      <PublicEventBoard />
    </Suspense>
  );
}
