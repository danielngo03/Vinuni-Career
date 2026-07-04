import { Suspense } from "react";
import { CompaniesDirectory } from "@/components/companies/companies-directory";

export default function PublicCompaniesPage() {
  // CompaniesDirectory reads `?q=` / `?industry=` via useSearchParams, which
  // requires a Suspense boundary for static rendering in the App Router.
  return (
    <Suspense>
      <CompaniesDirectory />
    </Suspense>
  );
}
