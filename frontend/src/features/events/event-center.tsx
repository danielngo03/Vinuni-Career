"use client";

import {
  Buildings,
  CalendarDots,
  CheckCircle,
  MapPin,
  Star,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiMessage } from "@/lib/api/client";
import type { CompanyReview, Event, JobPage } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { PanelSkeleton } from "@/components/ui/skeleton";

export function EventCenter() {
  const { locale, dictionary } = useI18n();
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [workingId, setWorkingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setEvents(await apiFetch<Event[]>("/events"));
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setLoading(false);
    }
  }, [dictionary.common.retry]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function register(eventId: string) {
    setWorkingId(eventId);
    try {
      await apiFetch(`/events/${eventId}/register`, { method: "POST" });
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  return (
    <section className="rounded-2xl border bg-white p-4 sm:p-5">
      {loading ? <PanelSkeleton /> : null}
      {!loading && !events.length ? (
        <EmptyState
          icon={CalendarDots}
          title={dictionary.common.empty}
          description={dictionary.operations.student.eventsDescription}
        />
      ) : null}
      {!loading && events.length ? (
        <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
          {events.map((event) => (
            <article
              key={event.id}
              className="overflow-hidden rounded-2xl border bg-white transition-all hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-[0_18px_36px_-30px_rgba(15,92,229,.8)]"
            >
              <div className="bg-[linear-gradient(135deg,#0b3f9d,#0f5ce5_60%,#18a9c4)] p-5 text-white">
                <Badge className="bg-white/15 text-white ring-1 ring-white/25">
                  {event.event_type.replaceAll("_", " ")}
                </Badge>
                <h3 className="mt-8 text-xl font-semibold tracking-[-0.02em]">
                  {event.title}
                </h3>
              </div>
              <div className="p-5">
                <p className="line-clamp-3 text-sm leading-6 text-muted">
                  {event.description}
                </p>
                <div className="mt-4 space-y-2 text-sm">
                  <p className="flex items-center gap-2">
                    <CalendarDots className="size-4 text-primary" />
                    {new Intl.DateTimeFormat(locale, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(event.start_time))}
                  </p>
                  <p className="flex items-center gap-2 text-muted">
                    <MapPin className="size-4" />
                    {event.location_address ||
                      event.meeting_url ||
                      dictionary.common.unknown}
                  </p>
                </div>
                <Button
                  className="mt-5 w-full"
                  onClick={() => register(event.id)}
                  disabled={workingId === event.id}
                >
                  <CheckCircle className="size-4" />
                  {dictionary.common.save}
                </Button>
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function ReviewCenter() {
  const { dictionary } = useI18n();
  const [organizations, setOrganizations] = useState<
    Array<{ id: string; title: string }>
  >([]);
  const [selectedOrg, setSelectedOrg] = useState("");
  const [reviews, setReviews] = useState<CompanyReview[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    apiFetch<JobPage>("/jobs/page?limit=50&offset=0")
      .then((page) => {
        const unique = new Map<string, { id: string; title: string }>();
        page.items.forEach((job) =>
          unique.set(job.org_id, { id: job.org_id, title: job.title }),
        );
        const values = [...unique.values()];
        setOrganizations(values);
        setSelectedOrg(values[0]?.id || "");
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!selectedOrg) return;
    apiFetch<CompanyReview[]>(`/reviews/org/${selectedOrg}`)
      .then(setReviews)
      .catch(() => setReviews([]));
  }, [selectedOrg]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch("/reviews", {
        method: "POST",
        body: JSON.stringify({
          org_id: selectedOrg,
          title: form.get("title"),
          overall_rating: Number(form.get("rating")),
          review_content: form.get("content"),
          is_anonymous: form.get("anonymous") === "on",
        }),
      });
      setReviews(await apiFetch<CompanyReview[]>(`/reviews/org/${selectedOrg}`));
      setOpen(false);
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    }
  }

  return (
    <>
      <section className="rounded-2xl border bg-white">
        <div className="flex flex-col gap-3 border-b p-5 sm:flex-row sm:items-center">
          <select
            value={selectedOrg}
            onChange={(event) => setSelectedOrg(event.target.value)}
            className="focus-ring h-11 rounded-xl border bg-white px-3 text-sm"
          >
            {organizations.map((organization) => (
              <option key={organization.id} value={organization.id}>
                {organization.title}
              </option>
            ))}
          </select>
          <Button className="sm:ml-auto" onClick={() => setOpen(true)}>
            <Star className="size-4" />
            {dictionary.sections.reviews}
          </Button>
        </div>
        <div className="p-4 sm:p-5">
          {!reviews.length ? (
            <EmptyState
              icon={Buildings}
              title={dictionary.common.empty}
              description={dictionary.operations.student.reviewsDescription}
            />
          ) : (
            <div className="grid gap-3 lg:grid-cols-2">
              {reviews.map((review) => (
                <article key={review.id} className="rounded-2xl border p-4">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold">{review.title}</h3>
                    <Badge tone="amber">{review.overall_rating}/5</Badge>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-muted">
                    {review.review_content}
                  </p>
                  <p className="mt-3 text-xs font-semibold text-slate-400">
                    {review.is_anonymous ? "Anonymous" : review.student_id}
                  </p>
                </article>
              ))}
            </div>
          )}
        </div>
      </section>
      <Modal
        open={open}
        onOpenChange={setOpen}
        title={dictionary.sections.reviews}
        description={dictionary.operations.student.reviewsDescription}
      >
        <form onSubmit={submit} className="space-y-4">
          <Input name="title" required placeholder={dictionary.forms.title} />
          <select
            name="rating"
            className="focus-ring h-11 w-full rounded-xl border px-3 text-sm"
            defaultValue="5"
          >
            {[5, 4, 3, 2, 1].map((rating) => (
              <option key={rating} value={rating}>
                {rating}/5
              </option>
            ))}
          </select>
          <textarea
            name="content"
            required
            minLength={10}
            placeholder={dictionary.forms.description}
            className="focus-ring min-h-32 w-full rounded-xl border p-3 text-sm"
          />
          <label className="flex items-center gap-2 text-sm font-medium">
            <input type="checkbox" name="anonymous" className="size-4" />
            {dictionary.forms.anonymous}
          </label>
          <Button type="submit" className="w-full">
            {dictionary.common.save}
          </Button>
        </form>
      </Modal>
    </>
  );
}
