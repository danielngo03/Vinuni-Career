"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import {
  ArrowLeft,
  ArrowRight,
  Brain,
  ChatsTeardrop,
  CheckCircle,
  Lightning,
  Lightbulb,
  Sparkle,
  Star,
  Trophy,
  Warning,
  X,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { interviewPrepApi, type InterviewQuestion, type AnswerFeedbackResult } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  jobId: string;
  jobTitle: string;
  companyName?: string;
}

type QuestionType = InterviewQuestion["type"];

type LoadPhase =
  | { name: "idle" }
  | { name: "loading" }
  | { name: "ready"; questions: InterviewQuestion[]; prepTips: string }
  | { name: "failed" };

type AnswerState =
  | { status: "pending" }
  | { status: "submitting" }
  | { status: "done"; feedback: AnswerFeedbackResult }
  | { status: "error" }
  | { status: "skipped" };

const TYPE_ICON: Record<QuestionType, React.ElementType> = {
  behavioral: ChatsTeardrop,
  technical: Brain,
  situational: Lightbulb,
  motivation: Sparkle,
};

const TYPE_COLOR: Record<QuestionType, { badge: string; text: string }> = {
  behavioral: { badge: "bg-[var(--bg-muted)] text-[var(--brand-primary)]", text: "text-[var(--brand-primary)]" },
  technical: { badge: "bg-[var(--gray-100)] text-[var(--gray-700)]", text: "text-[var(--gray-700)]" },
  situational: { badge: "bg-[var(--teal-50)] text-[var(--teal-700)]", text: "text-[var(--teal-700)]" },
  motivation: { badge: "bg-[var(--amber-50)] text-[var(--amber-700)]", text: "text-[var(--amber-700)]" },
};

const SCORE_COLORS = [
  "",
  "text-[var(--red-600)]",
  "text-[var(--amber-700)]",
  "text-[var(--amber-500)]",
  "text-[var(--teal-600)]",
  "text-[var(--brand-primary)]",
];

function ScoreRing({ score }: { score: number }) {
  const pct = (score / 5) * 100;
  const r = 22;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;
  return (
    <svg width="56" height="56" viewBox="0 0 56 56" className="shrink-0" aria-hidden>
      <circle cx="28" cy="28" r={r} fill="none" stroke="currentColor" strokeWidth="4" className="text-white/40" />
      <circle
        cx="28" cy="28" r={r}
        fill="none"
        stroke="currentColor"
        strokeWidth="4"
        strokeDasharray={`${dash} ${circ - dash}`}
        strokeLinecap="round"
        transform="rotate(-90 28 28)"
        className={SCORE_COLORS[score] ?? "text-[var(--brand-primary)]"}
      />
      <text x="28" y="33" textAnchor="middle" fontSize="14" fontWeight="700" fill="currentColor" className={cn("fill-current", SCORE_COLORS[score])}>
        {score}/5
      </text>
    </svg>
  );
}

export function InterviewSimulatorScreen({ jobId, jobTitle, companyName }: Props) {
  const t = useTranslations("jobs.interviewSim");
  const [load, setLoad] = useState<LoadPhase>({ name: "idle" });
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [states, setStates] = useState<Record<number, AnswerState>>({});
  const [hintOpen, setHintOpen] = useState(false);
  const [showSummary, setShowSummary] = useState(false);

  const startSession = useCallback(async () => {
    setLoad({ name: "loading" });
    try {
      const result = await interviewPrepApi.generatePrep(jobId, { num_questions: 6 });
      setLoad({ name: "ready", questions: result.questions, prepTips: result.prep_tips });
      setCurrentIdx(0);
      setAnswers({});
      setStates({});
      setHintOpen(false);
      setShowSummary(false);
    } catch {
      setLoad({ name: "failed" });
    }
  }, [jobId]);

  const submitAnswer = useCallback(async (q: InterviewQuestion, answer: string) => {
    const idx = q.number;
    setStates((prev) => ({ ...prev, [idx]: { status: "submitting" } }));
    try {
      const feedback = await interviewPrepApi.getAnswerFeedback(jobId, {
        question: q.question,
        question_type: q.type,
        rubric: q.rubric,
        answer,
      });
      setStates((prev) => ({ ...prev, [idx]: { status: "done", feedback } }));
    } catch {
      setStates((prev) => ({ ...prev, [idx]: { status: "error" } }));
    }
  }, [jobId]);

  const skipQuestion = useCallback((q: InterviewQuestion) => {
    setStates((prev) => ({ ...prev, [q.number]: { status: "skipped" } }));
  }, []);

  if (load.name === "idle" || load.name === "failed") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center px-4 text-center">
        <div className="mb-6 flex size-16 items-center justify-center rounded-2xl icon-chip-info shadow-[var(--shadow-lg)]">
          <Sparkle weight="duotone" className="size-8 text-white" aria-hidden />
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">{t("pageTitle")}</h1>
        <p className="mt-2 max-w-md text-sm text-[var(--text-secondary)]">{t("pageSubtitle")}</p>
        {load.name === "failed" && (
          <p className="mt-3 text-sm text-[var(--brand-red)]">{t("loadError")}</p>
        )}
        <button
          type="button"
          onClick={startSession}
          className="mt-6 inline-flex items-center gap-2 rounded-xl bg-[var(--ai-accent)] px-6 py-3 text-sm font-bold text-white shadow-[0_2px_12px_rgba(11,34,57,0.18)] transition hover:opacity-90 active:scale-[0.98]"
        >
          <Sparkle weight="bold" className="size-4" aria-hidden />
          {load.name === "failed" ? t("retryLoad") : t("pageTitle")}
        </button>
        <Link
          href={`/jobs/${jobId}`}
          className="mt-4 text-sm text-[var(--text-muted)] underline hover:text-[var(--text-secondary)]"
        >
          {t("backToJob")}
        </Link>
      </div>
    );
  }

  if (load.name === "loading") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3">
        <span className="size-8 animate-spin rounded-full border-4 border-[var(--ai-accent)]/30 border-t-[var(--ai-accent)]" aria-hidden />
        <p className="text-sm text-[var(--text-muted)]">{t("loadingQuestions")}</p>
      </div>
    );
  }

  const { questions, prepTips } = load;

  if (showSummary) {
    return (
      <SummaryScreen
        questions={questions}
        states={states}
        prepTips={prepTips}
        onRestart={startSession}
        jobId={jobId}
        t={t}
      />
    );
  }

  const q = questions[currentIdx];
  if (!q) return null;

  const qState = states[q.number] ?? { status: "pending" };
  const qAnswer = answers[q.number] ?? "";
  const TypeIcon = TYPE_ICON[q.type] ?? ChatsTeardrop;
  const typeColor = TYPE_COLOR[q.type] ?? TYPE_COLOR.behavioral;
  const isLast = currentIdx === questions.length - 1;

  function goNext() {
    if (isLast) {
      setShowSummary(true);
    } else {
      setCurrentIdx((i) => i + 1);
      setHintOpen(false);
    }
  }
  function goPrev() {
    if (currentIdx > 0) {
      setCurrentIdx((i) => i - 1);
      setHintOpen(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 lg:py-12">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            href={`/jobs/${jobId}`}
            className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
          >
            <ArrowLeft weight="bold" className="size-3.5" aria-hidden />
            {t("backToJob")}
          </Link>
          <p className="text-xs text-[var(--text-muted)]">{jobTitle}{companyName ? ` · ${companyName}` : ""}</p>
        </div>
        <div className="shrink-0 text-right">
          <span className="text-sm font-bold text-[var(--text-primary)]">
            {t("progress", { current: currentIdx + 1, total: questions.length })}
          </span>
          {/* Progress bar */}
          <div className="mt-1.5 h-1.5 w-32 overflow-hidden rounded-full bg-[var(--bg-muted)]">
            <div
              className="h-full rounded-full bg-[var(--ai-accent)] transition-all duration-300"
              style={{ width: `${((currentIdx + 1) / questions.length) * 100}%` }}
            />
          </div>
        </div>
      </div>

      {/* Question card */}
      <div className="overflow-hidden rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] shadow-[0_4px_24px_rgba(11,34,57,0.08)] backdrop-blur-md">
        {/* Question header */}
        <div className="flex items-center gap-2.5 border-b border-[var(--glass-border)] px-5 py-3.5">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-bold",
              typeColor.badge,
            )}
          >
            <TypeIcon weight="duotone" className="size-3.5" aria-hidden />
            {t(q.type)}
          </span>
          <span className="text-xs font-semibold text-[var(--text-muted)]">
            {t("questionLabel", { number: q.number })}
          </span>
        </div>

        {/* Question text */}
        <div className="px-5 py-5">
          <p className="text-lg font-semibold leading-relaxed text-[var(--text-primary)]">
            {q.question}
          </p>

          {/* Hint toggle */}
          <button
            type="button"
            onClick={() => setHintOpen((o) => !o)}
            className={cn(
              "mt-3 flex items-center gap-1.5 text-xs font-semibold transition-colors",
              typeColor.text,
            )}
          >
            <Lightbulb weight="duotone" className="size-3.5" aria-hidden />
            {hintOpen ? t("hintHide") : t("hintToggle")}
          </button>
          {hintOpen && (
            <p className="mt-2 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface-light)] px-3.5 py-2.5 text-sm leading-relaxed text-[var(--text-secondary)]">
              <span className="font-semibold text-[var(--text-primary)]">{t("hintPrefix")} </span>
              {q.hint}
            </p>
          )}
        </div>

        {/* Answer textarea — hidden when feedback is shown */}
        {qState.status !== "done" && qState.status !== "skipped" && (
          <div className="border-t border-[var(--glass-border)] px-5 pb-5 pt-4">
            <label className="mb-2 block text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider">
              {t("answerLabel")}
            </label>
            <textarea
              rows={5}
              value={qAnswer}
              onChange={(e) => setAnswers((prev) => ({ ...prev, [q.number]: e.target.value }))}
              placeholder={t("answerPlaceholder")}
              disabled={qState.status === "submitting"}
              className="w-full resize-none rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface)] px-4 py-3 text-sm leading-relaxed text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--ai-accent)]/60 focus:bg-[var(--glass-surface-heavy)] focus:outline-none focus:ring-2 focus:ring-[var(--ai-accent)]/25 disabled:opacity-60"
            />

            {qState.status === "error" && (
              <p className="mt-1.5 text-xs text-[var(--brand-red)]">{t("feedbackError")}</p>
            )}

            <div className="mt-3 flex items-center gap-2.5">
              <button
                type="button"
                disabled={!qAnswer.trim() || qState.status === "submitting"}
                onClick={() => submitAnswer(q, qAnswer)}
                className="inline-flex items-center gap-2 rounded-xl bg-[var(--ai-accent)] px-4 py-2.5 text-sm font-bold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {qState.status === "submitting" ? (
                  <>
                    <span className="size-4 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden />
                    {t("submitting")}
                  </>
                ) : (
                  <>
                    <Sparkle weight="bold" className="size-4" aria-hidden />
                    {t("submitAnswer")}
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={() => skipQuestion(q)}
                disabled={qState.status === "submitting"}
                className="text-sm font-semibold text-[var(--text-muted)] hover:text-[var(--text-secondary)] disabled:opacity-40"
              >
                {t("skipQuestion")}
              </button>
            </div>
          </div>
        )}

        {/* Feedback panel */}
        {qState.status === "done" && (
          <FeedbackPanel feedback={qState.feedback} t={t} />
        )}

        {qState.status === "skipped" && (
          <div className="border-t border-[var(--glass-border)] px-5 py-4">
            <p className="flex items-center gap-1.5 text-sm text-[var(--text-muted)]">
              <X weight="bold" className="size-4" aria-hidden />
              {t("skippedLabel")}
            </p>
          </div>
        )}

        {/* Navigation */}
        {(qState.status === "done" || qState.status === "skipped") && (
          <div className="flex items-center justify-between border-t border-[var(--glass-border)] px-5 py-3.5">
            <button
              type="button"
              onClick={goPrev}
              disabled={currentIdx === 0}
              className="flex items-center gap-1.5 text-sm font-semibold text-[var(--text-muted)] hover:text-[var(--text-secondary)] disabled:opacity-30"
            >
              <ArrowLeft weight="bold" className="size-4" aria-hidden />
              {t("prevQuestion")}
            </button>
            <button
              type="button"
              onClick={goNext}
              className="flex items-center gap-2 rounded-xl bg-[var(--brand-primary)] px-4 py-2 text-sm font-bold text-white transition hover:opacity-90"
            >
              {isLast ? (
                <>
                  <Trophy weight="duotone" className="size-4" aria-hidden />
                  {t("endSession")}
                </>
              ) : (
                <>
                  {t("nextQuestion")}
                  <ArrowRight weight="bold" className="size-4" aria-hidden />
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Session progress dots */}
      <div className="mt-5 flex justify-center gap-2">
        {questions.map((question, i) => {
          const s = states[question.number];
          const isDone = s?.status === "done";
          const isSkipped = s?.status === "skipped";
          const isCurrent = i === currentIdx;
          return (
            <button
              key={question.number}
              type="button"
              onClick={() => { setCurrentIdx(i); setHintOpen(false); }}
              className={cn(
                "size-2.5 rounded-full transition-all",
                isDone ? "bg-[var(--brand-primary)]" :
                isSkipped ? "bg-[var(--text-muted)]" :
                isCurrent ? "w-5 bg-[var(--ai-accent)]" :
                "bg-[var(--glass-surface-light)] hover:bg-[var(--glass-surface)]",
              )}
              aria-label={`Question ${question.number}`}
            />
          );
        })}
      </div>

      {/* Disclaimer */}
      <p className="mt-4 text-center text-[11px] text-[var(--text-muted)]">
        {t("disclaimer")}
      </p>
    </div>
  );
}

function FeedbackPanel({
  feedback,
  t,
}: {
  feedback: AnswerFeedbackResult;
  t: ReturnType<typeof useTranslations<"jobs.interviewSim">>;
}) {
  return (
    <div className="border-t border-[var(--ai-accent)]/20 bg-[var(--ai-accent-soft)] px-5 py-4">
      {/* Feedback header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-info shadow-sm">
            <Sparkle weight="duotone" className="size-3 text-white" aria-hidden />
          </span>
          <span className="text-xs font-bold text-[var(--text-primary)]">{t("feedbackTitle")}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <ScoreRing score={feedback.score} />
        </div>
      </div>

      {feedback.is_fallback && (
        <div className="mb-3 flex items-center gap-1.5 rounded-lg bg-[var(--amber-50)] px-3 py-2 text-xs text-[var(--amber-700)]">
          <Warning weight="bold" className="size-3.5 shrink-0" aria-hidden />
          {t("fallbackNote")}
        </div>
      )}

      <div className="space-y-3">
        {feedback.praise && (
          <FeedbackRow
            icon={CheckCircle}
            iconClass="text-[var(--teal-600)]"
            label={t("praiseLabel")}
            text={feedback.praise}
            bgClass="bg-[var(--teal-50)]/80"
          />
        )}
        {feedback.improve && (
          <FeedbackRow
            icon={Lightning}
            iconClass="text-[var(--amber-600)]"
            label={t("improveLabel")}
            text={feedback.improve}
            bgClass="bg-[var(--amber-50)]/80"
          />
        )}
        {feedback.hint && (
          <FeedbackRow
            icon={Lightbulb}
            iconClass="text-[var(--brand-primary)]"
            label={t("hintLabel")}
            text={feedback.hint}
            bgClass="bg-[var(--bg-muted)]/80"
          />
        )}
      </div>
    </div>
  );
}

function FeedbackRow({
  icon: Icon,
  iconClass,
  label,
  text,
  bgClass,
}: {
  icon: React.ElementType;
  iconClass: string;
  label: string;
  text: string;
  bgClass: string;
}) {
  return (
    <div className={cn("rounded-xl px-3.5 py-3", bgClass)}>
      <div className="mb-1 flex items-center gap-1.5">
        <Icon weight="duotone" className={cn("size-3.5 shrink-0", iconClass)} aria-hidden />
        <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">{label}</span>
      </div>
      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{text}</p>
    </div>
  );
}

function SummaryScreen({
  questions,
  states,
  prepTips,
  onRestart,
  jobId,
  t,
}: {
  questions: InterviewQuestion[];
  states: Record<number, AnswerState>;
  prepTips: string;
  onRestart: () => void;
  jobId: string;
  t: ReturnType<typeof useTranslations<"jobs.interviewSim">>;
}) {
  const scored = questions
    .map((q) => {
      const s = states[q.number];
      if (s?.status === "done") return { q, score: s.feedback.score };
      return null;
    })
    .filter(Boolean) as { q: InterviewQuestion; score: number }[];

  const avgScore = scored.length
    ? Math.round((scored.reduce((acc, r) => acc + r.score, 0) / scored.length) * 10) / 10
    : 0;
  const strongest = scored.length ? scored.reduce((a, b) => (a.score >= b.score ? a : b)) : null;
  const weakest = scored.length ? scored.reduce((a, b) => (a.score <= b.score ? a : b)) : null;

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      {/* Trophy header */}
      <div className="mb-8 text-center">
        <div className="mb-4 flex justify-center">
          <div className="flex size-16 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--amber-400)]/30 to-[var(--ai-accent)]/30 shadow-[var(--shadow-md)]">
            <Trophy weight="duotone" className="size-8 text-[var(--amber-600)]" aria-hidden />
          </div>
        </div>
        <h2 className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">
          {t("summaryTitle")}
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {t("summarySubtitle", { total: questions.length })}
        </p>
      </div>

      {/* Score card */}
      {scored.length > 0 && (
        <div className="mb-6 rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-md shadow-[0_2px_12px_rgba(11,34,57,0.06)]">
          <div className="flex items-center justify-around gap-4">
            <div className="text-center">
              <div className="flex justify-center">
                <ScoreRing score={Math.round(avgScore)} />
              </div>
              <p className="mt-1 text-xs font-semibold text-[var(--text-secondary)]">{t("summaryAvgScore")}</p>
            </div>
            {strongest && (
              <div className="min-w-0 flex-1 text-center">
                <div className="flex items-center justify-center gap-1 text-xs font-bold text-[var(--teal-600)]">
                  <Star weight="fill" className="size-3.5" aria-hidden />
                  {t("summaryStrong")}
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-[var(--text-primary)]">
                  {strongest.q.question}
                </p>
              </div>
            )}
            {weakest && weakest.q.number !== strongest?.q.number && (
              <div className="min-w-0 flex-1 text-center">
                <div className="flex items-center justify-center gap-1 text-xs font-bold text-[var(--amber-600)]">
                  <Lightning weight="fill" className="size-3.5" aria-hidden />
                  {t("summaryWeak")}
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-[var(--text-primary)]">
                  {weakest.q.question}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Per-question breakdown */}
      <div className="space-y-3">
        {questions.map((q) => {
          const s = states[q.number];
          const TypeIcon = TYPE_ICON[q.type] ?? ChatsTeardrop;
          const typeColor = TYPE_COLOR[q.type] ?? TYPE_COLOR.behavioral;
          return (
            <div
              key={q.number}
              className="overflow-hidden rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface-light)] backdrop-blur-sm"
            >
              <div className="flex items-start gap-3 px-4 py-3">
                <span className={cn("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md text-[10px] font-bold", typeColor.badge)}>
                  <TypeIcon weight="duotone" className="size-3.5" aria-hidden />
                </span>
                <p className="flex-1 text-sm font-medium text-[var(--text-primary)]">{q.question}</p>
                {s?.status === "done" && (
                  <span className={cn("shrink-0 text-sm font-bold tabular-nums", SCORE_COLORS[s.feedback.score])}>
                    {s.feedback.score}/5
                  </span>
                )}
                {s?.status === "skipped" && (
                  <span className="shrink-0 text-xs text-[var(--text-muted)]">{t("skippedLabel")}</span>
                )}
              </div>
              {s?.status === "done" && s.feedback.improve && (
                <div className="border-t border-[var(--glass-border)] bg-[var(--glass-surface-light)] px-4 py-2.5">
                  <p className="flex items-start gap-1.5 text-xs text-[var(--text-secondary)]">
                    <Lightning weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--amber-600)]" aria-hidden />
                    {s.feedback.improve}
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Prep tips */}
      {prepTips && (
        <div className="mt-5 rounded-xl border border-[var(--ai-accent)]/30 bg-[var(--ai-accent-soft)] px-4 py-3.5">
          <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
            {t("prepTipsLabel")}
          </p>
          <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{prepTips}</p>
        </div>
      )}

      {/* Actions */}
      <div className="mt-6 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
        <button
          type="button"
          onClick={onRestart}
          className="inline-flex items-center gap-2 rounded-xl bg-[var(--ai-accent)] px-6 py-3 text-sm font-bold text-white shadow-[0_2px_12px_rgba(11,34,57,0.14)] transition hover:opacity-90"
        >
          <Sparkle weight="bold" className="size-4" aria-hidden />
          {t("practiceAgain")}
        </button>
        <Link
          href={`/jobs/${jobId}`}
          className="text-sm font-semibold text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
        >
          {t("backToJob")}
        </Link>
      </div>

      <p className="mt-6 text-center text-[11px] text-[var(--text-muted)]">{t("disclaimer")}</p>
    </div>
  );
}
