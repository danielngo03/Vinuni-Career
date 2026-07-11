"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CalendarBlank,
  LightbulbFilament,
  MapPin,
  VideoCamera,
  Users,
  Clock,
  Star,
  CheckCircle,
  Hourglass,
  WarningCircle,
  MagnifyingGlass,
  SealCheck,
  Sparkle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import {
  Button,
  EmptyState,
  Skeleton,
  StatusBadge,
  SponsoredLabel,
  useToast,
} from "@/components/ui";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { useUiStore } from "@/stores/ui-store";
import { useAuthStore } from "@/stores/auth-store";
import { useEventLabels, REGISTRATION_STATE_TONE } from "@/lib/events/labels";
import {
  EVENT_COVER_FALLBACK,
  formatEventWhen,
  registrationDeadlineIso,
  isRegistrationClosed,
  isRegistrationNotOpen,
  isEventFull,
} from "@/lib/events/format";
import { formatDateTime } from "@/lib/format";
import {
  ApiError,
  eventsApi,
  type MyEventRegistration,
  type PublicEventDetail as EventDetail,
} from "@/lib/api";

const MINE_KEY = ["events", "registrations", "mine"] as const;

export function PublicEventDetail({ eventId }: { eventId: string }) {
  const t = useTranslations("events");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useEventLabels();

  const query = useQuery({
    queryKey: ["events", "detail", eventId],
    queryFn: () => eventsApi.getPublic(eventId),
    retry: false,
  });

  const event = query.data;

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 lg:px-6">
      <Link
        href="/events"
        className="mb-6 inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <ArrowLeft aria-hidden weight="bold" className="size-4" />
        {t("backToBoard")}
      </Link>

      {query.isError ? (
        query.error instanceof ApiError &&
        (query.error.isNotFound || query.error.isValidation) ? (
          <EmptyState
            kind="empty"
            icon={MagnifyingGlass}
            title={t("notFoundTitle")}
            description={t("notFoundBody")}
            action={
              <Link href="/events">
                <Button variant="secondary">{t("backToBoard")}</Button>
              </Link>
            }
          />
        ) : (
          <EmptyState
            kind="error"
            icon={WarningCircle}
            title={tStates("errorTitle")}
            description={tStates("errorBody")}
            action={
              <Button variant="secondary" onClick={() => query.refetch()}>
                {tc("retry")}
              </Button>
            }
          />
        )
      ) : query.isPending ? (
        <div className="space-y-4">
          <Skeleton className="aspect-[21/9] w-full rounded-2xl" />
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="mt-6 h-40 w-full" />
        </div>
      ) : event ? (
        <EventDetailBody event={event} labels={labels} locale={locale} />
      ) : null}
    </div>
  );
}

type EventInsightKey =
  | "insightGoingFast"
  | "insightDeadlineSoon"
  | "insightVerifiedOrganizer"
  | "insightEventFeatured";

interface EventInsight {
  key: EventInsightKey;
  values?: Record<string, string | number>;
}

function deriveEventInsights(event: EventDetail): EventInsight[] {
  const out: EventInsight[] = [];
  const now = Date.now();

  if (
    event.seats_remaining !== null &&
    event.seats_remaining > 0 &&
    event.seats_remaining <= 10
  ) {
    out.push({ key: "insightGoingFast", values: { count: event.seats_remaining } });
  }

  if (event.registration_closes_at) {
    const deadline = new Date(event.registration_closes_at).getTime();
    const hoursLeft = (deadline - now) / (1000 * 60 * 60);
    if (hoursLeft > 0 && hoursLeft < 48) {
      out.push({ key: "insightDeadlineSoon" });
    }
  }

  if (event.company?.is_verified) {
    out.push({ key: "insightVerifiedOrganizer" });
  }

  if (out.length < 3 && event.is_featured) {
    out.push({ key: "insightEventFeatured" });
  }

  return out.slice(0, 3);
}

function EventDetailBody({
  event,
  labels,
  locale,
}: {
  event: EventDetail;
  labels: ReturnType<typeof useEventLabels>;
  locale: string;
}) {
  const t = useTranslations("events");

  const online = event.format === "online";
  const hybrid = event.format === "hybrid";
  const cover = event.cover_image_url ?? EVENT_COVER_FALLBACK;
  const eventInsights = deriveEventInsights(event);

  return (
    <>
      {/* Hero cover with non-removable disclosure labels. */}
      <div className="relative aspect-[21/9] w-full overflow-hidden rounded-2xl bg-[var(--bg-muted)]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={cover}
          alt=""
          aria-hidden
          className="size-full object-cover"
        />
        <div className="absolute left-3 top-3 flex flex-wrap items-center gap-1.5">
          {event.is_sponsored && <SponsoredLabel label={t("sponsored")} />}
          {event.is_featured && (
            <StatusBadge tone="featured">
              <Star aria-hidden weight="fill" className="size-3" />
              {t("featured")}
            </StatusBadge>
          )}
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        {/* Main content */}
        <article className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center rounded-full bg-[var(--blue-50)] px-3 py-0.5 text-xs font-semibold text-[var(--brand-primary)]">
              {labels.eventType(event.event_type, event.event_type_label)}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full border border-[var(--glass-border)] bg-[var(--glass-surface-light)] px-3 py-0.5 text-xs font-medium text-[var(--text-secondary)] backdrop-blur-sm">
              {online ? (
                <VideoCamera aria-hidden weight="duotone" className="size-3.5" />
              ) : (
                <MapPin aria-hidden weight="duotone" className="size-3.5" />
              )}
              {labels.format(event.format, event.format_label)}
            </span>
          </div>

          <h1 className="mt-3 text-2xl font-bold tracking-tight text-[var(--text-primary)] sm:text-3xl">
            {event.title}
          </h1>

          {event.company && (
            <p className="mt-2 flex items-center gap-2 text-sm font-medium text-[var(--text-secondary)]">
              <CompanyAvatar
                name={event.company.display_name}
                logoUrl={event.company.logo_url}
                size="sm"
              />
              <span className="truncate">{event.company.display_name}</span>
              {event.company.is_verified && (
                <SealCheck
                  aria-label={t("verified")}
                  weight="fill"
                  className="size-4 shrink-0 text-[var(--brand-teal)]"
                />
              )}
            </p>
          )}

          <dl className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Meta icon={CalendarBlank} label={t("when")}>
              {formatEventWhen(event.starts_at, event.ends_at, locale)}
            </Meta>
            <Meta icon={online ? VideoCamera : MapPin} label={t("where")}>
              {online ? (
                <span>
                  {t("online")}
                  <span className="mt-0.5 block text-xs font-normal text-[var(--text-muted)]">
                    {t("onlineHint")}
                  </span>
                </span>
              ) : (
                <span>
                  {event.venue?.name ??
                    labels.format(event.format, event.format_label)}
                  {event.venue?.address && (
                    <span className="mt-0.5 block text-xs font-normal text-[var(--text-muted)]">
                      {event.venue.address}
                    </span>
                  )}
                  {hybrid && (
                    <span className="mt-0.5 block text-xs font-normal text-[var(--text-muted)]">
                      {t("onlineHint")}
                    </span>
                  )}
                </span>
              )}
            </Meta>
            {event.capacity !== null && (
              <Meta icon={Users} label={t("capacity")}>
                {isEventFull(event)
                  ? t("full")
                  : t("spotsLeftOfCapacity", {
                      remaining: event.seats_remaining ?? 0,
                      capacity: event.capacity,
                    })}
              </Meta>
            )}
          </dl>

          <section className="mt-7">
            <h2 className="mb-2 text-lg font-bold tracking-tight text-[var(--text-primary)]">
              {t("about")}
            </h2>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--text-secondary)]">
              {event.description}
            </p>
          </section>

          {event.tags.length > 0 && (
            <ul className="mt-5 flex flex-wrap gap-1.5">
              {event.tags.map((tag) => (
                <li
                  key={tag}
                  className="rounded-full border border-[var(--glass-border)] bg-[var(--glass-surface-light)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)] backdrop-blur-sm"
                >
                  {tag}
                </li>
              ))}
            </ul>
          )}

          {eventInsights.length > 0 && (
            <section
              className="mt-6 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-secondary)] p-5"
              aria-label={t("aiEventInsightsTitle")}
            >
              <h2 className="mb-3 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-xl icon-chip-neutral shadow-sm">
                  <Sparkle aria-hidden weight="duotone" className="size-4" />
                </span>
                {t("aiEventInsightsTitle")}
              </h2>
              <ul className="space-y-2">
                {eventInsights.map((insight) => (
                  <li
                    key={insight.key}
                    className="flex items-start gap-2.5 text-sm text-[var(--text-secondary)]"
                  >
                    <LightbulbFilament
                      aria-hidden
                      weight="duotone"
                      className="mt-0.5 size-4 shrink-0 text-[var(--text-muted)]"
                    />
                    {insight.values
                      ? t(insight.key, insight.values as Record<string, string>)
                      : t(insight.key)}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </article>

        {/* Registration sidebar */}
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <RegisterPanel event={event} />
        </aside>
      </div>
    </>
  );
}

/** Live countdown to the registration deadline. Announced politely. */
function DeadlineCountdown({ iso }: { iso: string }) {
  const t = useTranslations("events");
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(id);
  }, []);

  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) return null;
  const diff = target - now;
  if (diff <= 0) return null;

  const totalMin = Math.floor(diff / 60000);
  const days = Math.floor(totalMin / (60 * 24));
  const hours = Math.floor((totalMin % (60 * 24)) / 60);
  const minutes = totalMin % 60;
  const parts: string[] = [];
  if (days > 0) parts.push(t("unit.day", { count: days }));
  if (days > 0 || hours > 0) parts.push(t("unit.hour", { count: hours }));
  if (days === 0) parts.push(t("unit.minute", { count: minutes }));

  return (
    <p
      aria-live="polite"
      className="mb-3 flex items-center gap-1.5 rounded-xl bg-[var(--amber-100)] px-3 py-2 text-xs font-medium text-[var(--amber-700)]"
    >
      <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-warning shadow-sm">
        <Hourglass aria-hidden weight="duotone" className="size-3 text-white" />
      </span>
      {t("registrationCloses")}: {parts.join(" ")}
    </p>
  );
}

function RegisterPanel({ event }: { event: EventDetail }) {
  const t = useTranslations("events");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const queryClient = useQueryClient();
  const toast = useToast();
  const openLoginModal = useUiStore((s) => s.openLoginModal);
  const status = useAuthStore((s) => s.status);
  const persona = useAuthStore((s) => s.user?.persona);
  const isHydratingAuth = status === "unknown";
  const isGuest = status === "guest";
  const canRegister = status === "authenticated" && persona === "student";

  const mineQuery = useQuery({
    queryKey: MINE_KEY,
    queryFn: () => eventsApi.myRegistrations(),
    enabled: canRegister,
    retry: false,
  });

  const myReg: MyEventRegistration | null =
    mineQuery.data?.find(
      (r) => r.event.id === event.id && r.status !== "cancelled",
    ) ?? null;

  function handleError(err: unknown) {
    if (err instanceof ApiError && err.isAuthError) {
      openLoginModal({
        label: t("registerIntent"),
        returnTo: `/events/${event.id}`,
      });
      return;
    }
    const reason =
      err instanceof ApiError
        ? (err.details?.reason as string | undefined)
        : undefined;
    const reasonMap: Record<string, string> = {
      registration_closed: t("error.registrationClosed"),
      registration_not_open: t("error.registrationNotOpen"),
      event_not_open: t("error.eventNotOpen"),
      not_registered: t("error.notRegistered"),
    };
    toast.show({
      tone: "error",
      title: tStates("errorTitle"),
      description: (reason && reasonMap[reason]) || tStates("errorBody"),
    });
  }

  const registerMut = useMutation({
    mutationFn: () => eventsApi.register(event.id),
    onSuccess: (reg) => {
      queryClient.invalidateQueries({ queryKey: MINE_KEY });
      queryClient.invalidateQueries({
        queryKey: ["events", "detail", event.id],
      });
      if (reg.status === "waitlisted") {
        toast.show({
          tone: "info",
          title: t("toast.waitlistedTitle"),
          description: t("toast.waitlistedBody", {
            position: reg.waitlist_position ?? 0,
          }),
        });
      } else {
        toast.show({
          tone: "success",
          title: t("toast.registeredTitle"),
          description: t("toast.registeredBody"),
        });
      }
    },
    onError: handleError,
  });

  const cancelMut = useMutation({
    mutationFn: () => eventsApi.cancelRegistration(event.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MINE_KEY });
      queryClient.invalidateQueries({
        queryKey: ["events", "detail", event.id],
      });
      toast.show({
        tone: "success",
        title: t("toast.cancelledTitle"),
        description: t("toast.cancelledBody"),
      });
    },
    onError: handleError,
  });

  const closed = isRegistrationClosed(event);
  const notOpen = isRegistrationNotOpen(event);
  const full = isEventFull(event);
  const deadlineIso = registrationDeadlineIso(event);
  const busy = registerMut.isPending || cancelMut.isPending;

  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] backdrop-blur-md p-5">
      {deadlineIso && !closed && !myReg && (
        <DeadlineCountdown iso={deadlineIso} />
      )}

      {/* Authenticated: my registration state. */}
      {isHydratingAuth ? (
        <>
          <Button variant="primary" fullWidth disabled>
            {tc("loading")}
          </Button>
          <Skeleton className="mt-3 h-4 w-2/3 rounded-full" />
        </>
      ) : canRegister && mineQuery.isPending ? (
        <Skeleton className="h-10 w-full rounded-xl" />
      ) : myReg ? (
        <MyRegistrationState
          reg={myReg}
          onCancel={() => cancelMut.mutate()}
          cancelling={cancelMut.isPending}
        />
      ) : (
        <>
          {isGuest ? (
            <>
              <Button
                variant="primary"
                fullWidth
                onClick={() =>
                  openLoginModal({
                    label: t("registerIntent"),
                    returnTo: `/events/${event.id}`,
                  })
                }
              >
                {t("signInToRegister")}
              </Button>
              <p className="mt-3 text-xs text-[var(--text-muted)]">
                {t("guestRegisterHint")}
              </p>
            </>
          ) : !canRegister ? (
            <>
              <Button variant="primary" fullWidth disabled>
                {t("studentsOnlyRegister")}
              </Button>
              <p className="mt-3 text-xs text-[var(--text-muted)]">
                {t("studentsOnlyRegisterHint")}
              </p>
            </>
          ) : notOpen ? (
            <>
              <Button variant="primary" fullWidth disabled>
                {t("register")}
              </Button>
              <p className="mt-3 text-xs text-[var(--text-muted)]">
                {event.registration_opens_at
                  ? t("registrationOpensAt", {
                      date: formatDateTime(
                        event.registration_opens_at,
                        locale,
                      ),
                    })
                  : t("registrationNotOpenNotice")}
              </p>
            </>
          ) : closed ? (
            <>
              <Button variant="primary" fullWidth disabled>
                {t("register")}
              </Button>
              <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-[var(--brand-red)]">
                <Clock aria-hidden weight="duotone" className="size-3.5" />
                {t("registrationClosedNotice")}
              </p>
            </>
          ) : (
            <>
              {full && (
                <p className="mb-3 flex items-center gap-1.5 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface-light)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)] backdrop-blur-sm">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-neutral shadow-sm">
                    <Users aria-hidden weight="duotone" className="size-3 text-white" />
                  </span>
                  {t("fullNotice")}
                </p>
              )}
              <Button
                variant="primary"
                fullWidth
                loading={busy}
                onClick={() => registerMut.mutate()}
              >
                {full ? t("registerWaitlist") : t("register")}
              </Button>
              <p className="mt-3 text-xs text-[var(--text-muted)]">
                {t("registerHint")}
              </p>
            </>
          )}
        </>
      )}
    </div>
  );
}

function MyRegistrationState({
  reg,
  onCancel,
  cancelling,
}: {
  reg: MyEventRegistration;
  onCancel: () => void;
  cancelling: boolean;
}) {
  const t = useTranslations("events");
  const labels = useEventLabels();
  const canCancel = reg.status === "confirmed" || reg.status === "waitlisted";

  return (
    <div>
      <div className="flex items-start gap-3 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface-light)] p-3.5 backdrop-blur-sm">
        <span
          aria-hidden
          className={
            reg.status === "waitlisted"
              ? "flex size-8 shrink-0 items-center justify-center rounded-lg icon-chip-warning shadow-sm"
              : "flex size-8 shrink-0 items-center justify-center rounded-lg icon-chip-success shadow-sm"
          }
        >
          {reg.status === "waitlisted" ? (
            <Hourglass weight="duotone" className="size-4.5 text-white" />
          ) : (
            <CheckCircle weight="duotone" className="size-4.5 text-white" />
          )}
        </span>
        <div className="min-w-0">
          <p className="text-sm font-bold text-[var(--text-primary)]">
            {reg.status === "waitlisted"
              ? t("waitlistedTitle")
              : reg.status === "attended"
                ? t("attendedTitle")
                : t("youreRegistered")}
          </p>
          {reg.status === "waitlisted" && reg.waitlist_position != null && (
            <p className="mt-0.5 text-sm font-semibold text-[var(--amber-700)]">
              {t("waitlistedPosition", { position: reg.waitlist_position })}
            </p>
          )}
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {reg.status === "waitlisted"
              ? t("waitlistedHint")
              : reg.status === "attended"
                ? t("attendedHint")
                : t("youreRegisteredHint")}
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between">
        <StatusBadge tone={REGISTRATION_STATE_TONE[reg.status]}>
          {labels.registrationState(reg.status, reg.status_label)}
        </StatusBadge>
        {canCancel && (
          <Button variant="ghost" loading={cancelling} onClick={onCancel}>
            {reg.status === "waitlisted"
              ? t("leaveWaitlist")
              : t("cancelRegistration")}
          </Button>
        )}
      </div>
    </div>
  );
}

function Meta({
  icon: Icon,
  label,
  children,
}: {
  icon: React.ElementType;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface-light)] px-3.5 py-2.5 backdrop-blur-sm">
      <Icon
        aria-hidden
        weight="duotone"
        className="mt-0.5 size-4 shrink-0 text-[var(--text-muted)]"
      />
      <div className="min-w-0">
        <dt className="text-xs font-medium text-[var(--text-muted)]">{label}</dt>
        <dd className="text-sm font-semibold text-[var(--text-primary)]">
          {children}
        </dd>
      </div>
    </div>
  );
}
