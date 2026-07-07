"use client";

import { useEffect, useState } from "react";
import { jobsApi } from "@/lib/api/jobs";
import type { JobFitScoreEntry } from "@/lib/api/jobs";

export function useBatchFitScores(jobIds: string[], enabled: boolean) {
  const [scores, setScores] = useState<Record<string, JobFitScoreEntry>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!enabled || jobIds.length === 0) return;
    let cancelled = false;
    setLoading(true);
    jobsApi
      .batchFitScores(jobIds)
      .then((res) => {
        if (!cancelled) setScores(res.scores ?? {});
      })
      .catch(() => {
        // Silent failure — badge simply does not appear when the endpoint
        // returns 401 (guest/partner) or any other error.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobIds.join(","), enabled]);

  return { scores, loading };
}
