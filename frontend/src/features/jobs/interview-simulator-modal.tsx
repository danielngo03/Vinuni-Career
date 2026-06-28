"use client";

import {
  ArrowRight,
  ChartBar,
  ChatCircleText,
  CheckCircle,
  ClockCounterClockwise,
  PaperPlaneTilt,
  SpinnerGap,
  Target,
  WarningCircle,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { apiFetch, apiMessage } from "@/lib/api/client";
import type { CV, Job } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";

type InterviewPhase =
  | "career"
  | "cv_verification"
  | "problem_solving"
  | "behavioral"
  | "candidate_questions"
  | "completed";
type InterviewMode = "tech_lead" | "technical_check";

interface InterviewResponse {
  session_id: string;
  question: string;
  current_phase: InterviewPhase;
  should_end_interview: boolean;
  report: InterviewReport | null;
  attempt_id?: string | null;
  feedback?: AnswerFeedback | null;
  awaiting_acceptance?: boolean;
}

interface AnswerFeedback {
  summary: string;
  tags: string[];
  strengths: string[];
  improvements: string[];
}

interface InterviewReportDimension {
  key: string;
  label: string;
  score: number;
  weight: number;
  summary: string;
  evidence: string[];
}

interface InterviewReport {
  overall_score: number;
  overall_summary: string;
  dimensions: InterviewReportDimension[];
  strengths: string[];
  improvements: string[];
  insufficient_evidence: string[];
  action_plan: string[];
  confidence: "low" | "medium" | "high";
}

interface InterviewSessionSummary {
  session_id: string;
  job_id: string;
  cv_id: string;
  interview_mode: InterviewMode;
  status: string;
  current_phase: InterviewPhase;
  question_count: number;
  job_title: string;
  created_at: string;
  updated_at: string;
  has_report: boolean;
}

interface InterviewSessionDetail extends InterviewSessionSummary {
  report: InterviewReport | null;
  turns: Array<{
    sequence: number;
    phase: InterviewPhase;
    topic_key: string;
    question: string;
    answer: string | null;
    feedback: AnswerFeedback | null;
    attempts: Array<{
      attempt_id: string;
      answer: string;
      feedback: AnswerFeedback;
    }>;
  }>;
}

interface TranscriptItem {
  question: string;
  answer?: string;
  feedback?: AnswerFeedback;
}

export function InterviewSimulatorModal({
  open,
  onOpenChange,
  job,
  cv,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  job: Job | null;
  cv: CV | null;
}) {
  const { dictionary } = useI18n();
  const [session, setSession] = useState<InterviewResponse | null>(null);
  const [transcript, setTranscript] = useState<TranscriptItem[]>([]);
  const [answer, setAnswer] = useState("");
  const [pending, setPending] = useState(false);
  const [selectedMode, setSelectedMode] = useState<InterviewMode>("tech_lead");
  const [history, setHistory] = useState<InterviewSessionSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const [attemptedAnswer, setAttemptedAnswer] = useState("");
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const answerRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!session || session.should_end_interview) return;
    const frame = window.requestAnimationFrame(() => {
      transcriptEndRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "end",
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [attemptId, session, transcript]);

  useEffect(() => {
    if (!open || !job) return;
    let ignore = false;
    async function loadHistory() {
      setHistoryLoading(true);
      try {
        const items = await apiFetch<InterviewSessionSummary[]>(
          `/ai/interviews/sessions?job_id=${job?.id}`,
        );
        if (!ignore) setHistory(items);
      } catch (error) {
        if (!ignore) toast.error(apiMessage(error, dictionary.common.retry));
      } finally {
        if (!ignore) setHistoryLoading(false);
      }
    }
    void loadHistory();
    return () => {
      ignore = true;
    };
  }, [dictionary.common.retry, job, open]);

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      setSession(null);
      setTranscript([]);
      setAnswer("");
      setPending(false);
      setSelectedMode("tech_lead");
      setHistory([]);
      setHistoryLoading(false);
      setAttemptId(null);
      setAttemptedAnswer("");
    }
    onOpenChange(nextOpen);
  }

  async function start(mode: InterviewMode) {
    if (!job || !cv) return;
    setSelectedMode(mode);
    setAttemptId(null);
    setAttemptedAnswer("");
    setPending(true);
    try {
      const response = await apiFetch<InterviewResponse>("/ai/interviews/sessions", {
        method: "POST",
        body: JSON.stringify({
          cv_id: cv.id,
          job_id: job.id,
          interview_config: {
            interview_mode: mode,
            language: "vi",
            candidate_level: "student",
            target_role: job.title,
          },
        }),
      });
      setSession(response);
      setTranscript(response.question ? [{ question: response.question }] : []);
      setHistory([]);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setPending(false);
    }
  }

  async function openSavedSession(sessionId: string) {
    setPending(true);
    try {
      const detail = await apiFetch<InterviewSessionDetail>(
        `/ai/interviews/sessions/${sessionId}`,
      );
      setSelectedMode(detail.interview_mode);
      setSession({
        session_id: detail.session_id,
        question: "",
        current_phase: detail.current_phase,
        should_end_interview: detail.status === "COMPLETED",
        report: detail.report,
      });
      setTranscript(
        detail.turns.map((turn) => ({
          question: turn.question,
          answer: turn.answer || undefined,
          feedback: turn.feedback || undefined,
        })),
      );
      const latestAttempt = detail.turns.at(-1)?.attempts.at(-1);
      if (detail.status !== "COMPLETED" && latestAttempt) {
        setAttemptId(latestAttempt.attempt_id);
        setAttemptedAnswer(latestAttempt.answer);
        setTranscript((items) =>
          items.map((item, index) =>
            index === items.length - 1
              ? { ...item, feedback: latestAttempt.feedback }
              : item,
          ),
        );
      } else {
        setAttemptId(null);
        setAttemptedAnswer("");
      }
      setAnswer("");
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setPending(false);
    }
  }

  async function submitAnswer(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = answer.trim();
    if (!session || !content) return;
    setPending(true);
    try {
      const response = await apiFetch<InterviewResponse>(
        `/ai/interviews/sessions/${session.session_id}/answers`,
        {
          method: "POST",
          body: JSON.stringify({ answer: content }),
        },
      );
      setTranscript((items) =>
        items.map((item, index) =>
          index === items.length - 1 && response.feedback
            ? { ...item, answer: content, feedback: response.feedback }
            : item,
        ),
      );
      setAttemptId(response.attempt_id || null);
      setAttemptedAnswer(content);
      setAnswer("");
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setPending(false);
    }
  }

  async function acceptAnswer() {
    if (!session || !attemptId) return;
    setPending(true);
    try {
      const response = await apiFetch<InterviewResponse>(
        `/ai/interviews/sessions/${session.session_id}/answers/accept`,
        {
          method: "POST",
          body: JSON.stringify({ attempt_id: attemptId }),
        },
      );
      setTranscript((items) => {
        const accepted = items.map((item, index) =>
          index === items.length - 1 ? { ...item, answer: attemptedAnswer } : item,
        );
        return response.question ? [...accepted, { question: response.question }] : accepted;
      });
      setAttemptId(null);
      setAttemptedAnswer("");
      setSession(response);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setPending(false);
    }
  }

  function retryAnswer() {
    setAnswer(attemptedAnswer);
    setAttemptId(null);
    setTranscript((items) =>
      items.map((item, index) =>
        index === items.length - 1
          ? { ...item, answer: undefined, feedback: undefined }
        : item,
      ),
    );
    window.requestAnimationFrame(() => answerRef.current?.focus());
  }

  const latestFeedback = transcript.at(-1)?.feedback;

  return (
    <Modal
      open={open}
      onOpenChange={handleOpenChange}
      title="Mô phỏng phỏng vấn"
      description={job ? `Vị trí: ${job.title}` : undefined}
      contentClassName="max-w-6xl"
    >
      {!session ? (
        <div className="space-y-5">
          <div className="border-y py-4">
            <div className="flex items-start gap-3">
              <ChatCircleText className="mt-0.5 size-5 shrink-0 text-primary" />
              <div>
                <p className="text-sm font-semibold">Phỏng vấn dựa trên CV và yêu cầu công việc</p>
                <p className="mt-1 text-sm leading-6 text-muted">
                  Hệ thống sẽ hỏi từng câu và điều chỉnh nội dung dựa trên câu trả lời của bạn.
                </p>
              </div>
            </div>
          </div>
          {!cv ? (
            <p className="text-sm text-danger">
              Bạn cần tải lên CV trước khi bắt đầu phỏng vấn.
            </p>
          ) : (
            <p className="text-sm text-muted">
              CV sử dụng: <span className="font-semibold text-foreground">{cv.title}</span>
            </p>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <InterviewModeButton
              title="Phỏng vấn với Tech Lead AI"
              description="Mô phỏng phỏng vấn thích ứng theo CV/JD, có hỏi sâu về dự án và cách xử lý vấn đề."
              active={selectedMode === "tech_lead"}
              pending={pending}
              disabled={!cv}
              onClick={() => start("tech_lead")}
            />
            <InterviewModeButton
              title="Kiểm tra kỹ thuật"
              description="Thuần câu hỏi code, query, debug và kiến thức kỹ thuật dựa trên skill trong CV/JD."
              active={selectedMode === "technical_check"}
              pending={pending}
              disabled={!cv}
              onClick={() => start("technical_check")}
            />
          </div>
          <InterviewHistoryList
            items={history}
            loading={historyLoading}
            pending={pending}
            onOpen={openSavedSession}
          />
        </div>
      ) : (
        <div className="space-y-4">
          <div className="border-b pb-3 text-xs">
            <span className="font-semibold uppercase text-primary">
              {phaseLabel(session.current_phase, selectedMode)}
            </span>
          </div>
          {session.should_end_interview && session.report ? (
            <InterviewReportView report={session.report} />
          ) : (
            <div className="grid h-[68vh] min-h-0 grid-cols-[minmax(0,2fr)_minmax(20rem,1fr)] gap-5">
              <section className="flex min-h-0 flex-col rounded-2xl border bg-white">
                <div className="border-b px-5 py-3">
                  <p className="text-sm font-semibold">Nội dung phỏng vấn</p>
                  <p className="mt-0.5 text-xs text-muted">
                    Câu {transcript.length} · {phaseLabel(session.current_phase, selectedMode)}
                  </p>
                </div>
                <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
                  {transcript.map((item, index) => (
                    <div key={`${index}-${item.question}`} className="space-y-2">
                      <div className="border-l-2 border-primary pl-3">
                        <p className="text-xs font-semibold text-muted">Người phỏng vấn</p>
                        <p className="mt-1 whitespace-pre-wrap text-sm leading-6">{item.question}</p>
                      </div>
                      {item.answer ? (
                        <div className="ml-5 rounded-xl bg-slate-50 p-3">
                          <p className="text-xs font-semibold text-muted">Bạn</p>
                          <p className="mt-1 whitespace-pre-wrap text-sm leading-6">{item.answer}</p>
                        </div>
                      ) : null}
                      {item.feedback && index < transcript.length - 1 ? (
                        <div className="ml-5 flex flex-wrap gap-1.5">
                          {item.feedback.tags.map((tag) => (
                            <span
                              key={tag}
                              className={feedbackTagClass(tag, "subtle")}
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
                  <div ref={transcriptEndRef} aria-hidden="true" />
                </div>
                {!attemptId ? (
                  <form onSubmit={submitAnswer} className="space-y-3 border-t bg-white p-4">
                    <textarea
                      ref={answerRef}
                      value={answer}
                      onChange={(event) => setAnswer(event.target.value)}
                      placeholder="Nhập câu trả lời của bạn..."
                      className="focus-ring min-h-24 w-full resize-none rounded-lg border p-3 text-sm"
                      maxLength={10000}
                      disabled={pending}
                      autoFocus
                    />
                    <Button type="submit" className="w-full" disabled={pending || !answer.trim()}>
                      {pending ? (
                        <SpinnerGap className="size-4 animate-spin" />
                      ) : (
                        <PaperPlaneTilt className="size-4" />
                      )}
                      Gửi câu trả lời
                    </Button>
                  </form>
                ) : null}
              </section>

              <aside className="flex min-h-0 flex-col rounded-2xl border bg-slate-50/70">
                <div className="border-b px-5 py-3">
                  <p className="text-sm font-semibold">Coaching</p>
                  <p className="mt-0.5 text-xs text-muted">Nhận xét cho câu trả lời hiện tại</p>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto p-4">
                  {latestFeedback ? (
                    <AnswerFeedbackCard feedback={latestFeedback} />
                  ) : (
                    <div className="rounded-xl border border-dashed bg-white p-4">
                      <p className="text-sm font-semibold">Hãy trả lời theo trải nghiệm của bạn</p>
                      <p className="mt-2 text-sm leading-6 text-muted">
                        Sau khi gửi, hệ thống sẽ chỉ ra điểm tốt, phần chưa sâu và cho phép bạn thử lại.
                      </p>
                    </div>
                  )}
                </div>
                {attemptId ? (
                  <div className="space-y-3 border-t bg-white p-4">
                    <Button type="button" className="w-full" disabled={pending} onClick={acceptAnswer}>
                      {pending ? (
                        <SpinnerGap className="size-4 animate-spin" />
                      ) : (
                        <ArrowRight className="size-4" />
                      )}
                      Dùng câu trả lời này và tiếp tục
                    </Button>
                    <Button
                      type="button"
                      className="w-full"
                      variant="outline"
                      disabled={pending}
                      onClick={retryAnswer}
                    >
                      Thử trả lời lại
                    </Button>
                  </div>
                ) : null}
              </aside>
            </div>
          )}
          {session.should_end_interview ? (
            <div className="border-t pt-4 text-center">
              <p className="font-semibold">Buổi phỏng vấn đã hoàn thành</p>
              <Button className="mt-4" variant="outline" onClick={() => handleOpenChange(false)}>
                Đóng
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </Modal>
  );
}

function AnswerFeedbackCard({ feedback }: { feedback: AnswerFeedback }) {
  return (
    <div className="rounded-xl border border-primary/20 bg-primary/5 p-3">
      <p className="text-xs font-semibold uppercase text-primary">Nhận xét câu trả lời</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {feedback.tags.map((tag) => (
          <span key={tag} className={feedbackTagClass(tag, "solid")}>
            {tag}
          </span>
        ))}
      </div>
      <p className="mt-3 text-sm leading-6 text-muted">{feedback.summary}</p>
      {feedback.strengths.length ? (
        <p className="mt-2 text-xs leading-5 text-emerald-700">
          Điểm tốt: {feedback.strengths.join(" · ")}
        </p>
      ) : null}
      {feedback.improvements.length ? (
        <p className="mt-1 text-xs leading-5 text-amber-700">
          Có thể bổ sung: {feedback.improvements.join(" · ")}
        </p>
      ) : null}
    </div>
  );
}

function InterviewHistoryList({
  items,
  loading,
  pending,
  onOpen,
}: {
  items: InterviewSessionSummary[];
  loading: boolean;
  pending: boolean;
  onOpen: (sessionId: string) => void;
}) {
  if (loading) {
    return (
      <div className="rounded-2xl border p-4 text-sm text-muted">
        Đang tải buổi phỏng vấn đã lưu...
      </div>
    );
  }
  if (!items.length) return null;
  return (
    <section className="space-y-3 rounded-2xl border p-4">
      <div className="flex items-center gap-2">
        <ClockCounterClockwise className="size-5 text-primary" />
        <h3 className="font-semibold">Buổi đã lưu</h3>
      </div>
      <div className="space-y-2">
        {items.map((item) => (
          <button
            key={item.session_id}
            type="button"
            disabled={pending}
            onClick={() => onOpen(item.session_id)}
            className="focus-ring w-full rounded-xl border p-3 text-left transition hover:border-primary hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-semibold">{modeLabel(item.interview_mode)}</p>
              <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-muted">
                {item.status === "COMPLETED" ? "Đã hoàn thành" : "Đang làm"}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted">
              {new Date(item.created_at).toLocaleString()} · {item.question_count} câu
              {item.has_report ? " · có đánh giá" : ""}
            </p>
          </button>
        ))}
      </div>
    </section>
  );
}

function InterviewModeButton({
  title,
  description,
  active,
  pending,
  disabled,
  onClick,
}: {
  title: string;
  description: string;
  active: boolean;
  pending: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || pending}
      className="focus-ring rounded-2xl border p-4 text-left transition hover:border-primary hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-60"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{title}</p>
          <p className="mt-2 text-sm leading-6 text-muted">{description}</p>
        </div>
        {pending && active ? (
          <SpinnerGap className="size-5 shrink-0 animate-spin text-primary" />
        ) : (
          <ArrowRight className="size-5 shrink-0 text-primary" />
        )}
      </div>
    </button>
  );
}

function modeLabel(mode: InterviewMode): string {
  return mode === "technical_check" ? "Kiểm tra kỹ thuật" : "Phỏng vấn với Tech Lead AI";
}

function InterviewReportView({ report }: { report: InterviewReport }) {
  return (
    <div className="max-h-[58vh] space-y-5 overflow-y-auto pr-1">
      <div className="bg-primary/5 p-4">
        <div className="flex items-center gap-3">
          <div className="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary text-lg font-bold text-white">
            {report.overall_score}
          </div>
          <div>
            <p className="font-semibold">Đánh giá tổng thể</p>
            <p className="mt-1 text-sm leading-6 text-muted">{report.overall_summary}</p>
          </div>
        </div>
        <p className="mt-3 text-xs text-muted">
          Độ tin cậy: {confidenceLabel(report.confidence)}
        </p>
      </div>

      <section>
        <div className="mb-3 flex items-center gap-2">
          <ChartBar className="size-5 text-primary" />
          <h3 className="font-semibold">Các khía cạnh đánh giá</h3>
        </div>
        <div className="space-y-4">
          {report.dimensions.map((dimension) => (
            <div key={dimension.key} className="border p-3">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="font-semibold">{dimension.label}</span>
                <span className="font-bold text-primary">{dimension.score}/100</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${dimension.score}%` }}
                />
              </div>
              <p className="mt-2 text-sm leading-6 text-muted">{dimension.summary}</p>
              {dimension.evidence.length ? (
                <ul className="mt-2 space-y-1 text-xs leading-5 text-muted">
                  {dimension.evidence.map((item) => (
                    <li key={item}>• {item}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))}
        </div>
      </section>

      <ReportList
        icon={<CheckCircle className="size-5 text-emerald-600" />}
        title="Điểm mạnh"
        items={report.strengths}
      />
      <ReportList
        icon={<WarningCircle className="size-5 text-amber-600" />}
        title="Điểm cần cải thiện"
        items={report.improvements}
      />
      <ReportList
        icon={<Target className="size-5 text-primary" />}
        title="Kế hoạch cải thiện"
        items={report.action_plan}
      />
      <ReportList
        icon={<WarningCircle className="size-5 text-muted" />}
        title="Nội dung chưa đủ bằng chứng"
        items={report.insufficient_evidence}
      />
    </div>
  );
}

function ReportList({
  icon,
  title,
  items,
}: {
  icon: React.ReactNode;
  title: string;
  items: string[];
}) {
  if (!items.length) return null;
  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        {icon}
        <h3 className="font-semibold">{title}</h3>
      </div>
      <ul className="space-y-2 text-sm leading-6 text-muted">
        {items.map((item) => (
          <li key={item} className="border-l-2 border-slate-200 pl-3">
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

function confidenceLabel(confidence: InterviewReport["confidence"]): string {
  return {
    low: "Thấp",
    medium: "Trung bình",
    high: "Cao",
  }[confidence];
}

function feedbackTagClass(tag: string, variant: "solid" | "subtle"): string {
  const negative = isNegativeFeedbackTag(tag);
  if (variant === "solid") {
    return negative
      ? "rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700 ring-1 ring-red-200"
      : "rounded-full bg-white px-2.5 py-1 text-xs font-medium text-primary ring-1 ring-primary/15";
  }
  return negative
    ? "rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700 ring-1 ring-red-200"
    : "rounded-full bg-primary/5 px-2.5 py-1 text-xs font-medium text-primary";
}

function isNegativeFeedbackTag(tag: string): boolean {
  const normalized = tag.trim().toLowerCase();
  return [
    "chưa",
    "thiếu",
    "cần",
    "không",
    "sai",
    "yếu",
    "mơ hồ",
    "chung chung",
  ].some((marker) => normalized.includes(marker));
}

function phaseLabel(phase: InterviewPhase, mode: InterviewMode): string {
  if (mode === "technical_check" && phase !== "completed") {
    return "Kiểm tra kỹ thuật";
  }
  const labels: Record<InterviewPhase, string> = {
    career: "Định hướng sự nghiệp",
    cv_verification: "Xác thực CV",
    problem_solving: "Xử lý vấn đề",
    behavioral: "Tình huống hành vi",
    candidate_questions: "Câu hỏi của ứng viên",
    completed: "Hoàn thành",
  };
  return labels[phase];
}
