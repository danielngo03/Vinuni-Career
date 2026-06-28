"use client";

import {
  CalendarDots,
  ChartBar,
  ChatCircleText,
  CheckCircle,
  ClockCounterClockwise,
  Eye,
  PaperPlaneTilt,
  SpinnerGap,
  Trash,
  WarningCircle,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { apiFetch, apiMessage } from "@/lib/api/client";
import { useI18n } from "@/lib/i18n/provider";

type InterviewMode = "tech_lead" | "technical_check";
type DetailTab = "transcript" | "report";

interface InterviewResponse {
  session_id: string;
  question: string;
  current_phase: string;
  should_end_interview: boolean;
  report: InterviewReport | null;
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
  current_phase: string;
  question_count: number;
  job_title: string;
  created_at: string;
  updated_at: string | null;
  has_report: boolean;
}

interface InterviewSessionDetail extends InterviewSessionSummary {
  report: InterviewReport | null;
  turns: Array<{
    sequence: number;
    phase: string;
    topic_key: string;
    question: string;
    answer: string | null;
  }>;
}

export function AIInterviewHistory() {
  const { locale, dictionary } = useI18n();
  const [sessions, setSessions] = useState<InterviewSessionSummary[]>([]);
  const [selected, setSelected] = useState<InterviewSessionDetail | null>(null);
  const [activeTab, setActiveTab] = useState<DetailTab>("transcript");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [submittingAnswer, setSubmittingAnswer] = useState(false);

  const dateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(locale, {
        dateStyle: "medium",
        timeStyle: "short",
      }),
    [locale],
  );

  const loadSessions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch<InterviewSessionSummary[]>("/ai/interviews/sessions");
      setSessions(data);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setLoading(false);
    }
  }, [dictionary.common.retry]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadSessions(), 0);
    return () => window.clearTimeout(timer);
  }, [loadSessions]);

  async function openSession(sessionId: string) {
    setDetailLoading(true);
    setActiveTab("transcript");
    try {
      const detail = await apiFetch<InterviewSessionDetail>(
        `/ai/interviews/sessions/${sessionId}`,
      );
      setSelected(detail);
      setAnswer("");
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setDetailLoading(false);
    }
  }

  async function submitAnswer(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = answer.trim();
    if (!selected || !content || selected.status === "COMPLETED") return;

    setSubmittingAnswer(true);
    try {
      const response = await apiFetch<InterviewResponse>(
        `/ai/interviews/sessions/${selected.session_id}/answers`,
        {
          method: "POST",
          body: JSON.stringify({ answer: content }),
        },
      );

      const nextTurns = selected.turns.map((turn, index) =>
        index === selected.turns.length - 1 && !turn.answer
          ? { ...turn, answer: content }
          : turn,
      );
      if (response.question) {
        nextTurns.push({
          sequence: nextTurns.length + 1,
          phase: response.current_phase,
          topic_key: "",
          question: response.question,
          answer: null,
        });
      }

      const nextSelected: InterviewSessionDetail = {
        ...selected,
        current_phase: response.current_phase,
        status: response.should_end_interview ? "COMPLETED" : selected.status,
        has_report: Boolean(response.report) || selected.has_report,
        question_count: nextTurns.length,
        report: response.report || selected.report,
        turns: nextTurns,
        updated_at: new Date().toISOString(),
      };

      setSelected(nextSelected);
      setSessions((items) =>
        items.map((item) =>
          item.session_id === selected.session_id
            ? {
                ...item,
                current_phase: nextSelected.current_phase,
                status: nextSelected.status,
                has_report: nextSelected.has_report,
                question_count: nextSelected.question_count,
                updated_at: nextSelected.updated_at,
              }
            : item,
        ),
      );
      setAnswer("");
      if (response.should_end_interview) setActiveTab("report");
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setSubmittingAnswer(false);
    }
  }

  async function deleteSession(sessionId: string) {
    if (!window.confirm("Xóa buổi phỏng vấn này? Hành động này không thể hoàn tác.")) {
      return;
    }
    setDeletingId(sessionId);
    try {
      await apiFetch<void>(`/ai/interviews/sessions/${sessionId}`, {
        method: "DELETE",
      });
      setSessions((items) => items.filter((item) => item.session_id !== sessionId));
      if (selected?.session_id === sessionId) setSelected(null);
      toast.success(dictionary.common.deleted || "Đã xóa");
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setDeletingId(null);
    }
  }

  if (loading) {
    return (
      <section className="rounded-2xl border bg-white p-5">
        <PanelSkeleton />
      </section>
    );
  }

  if (!sessions.length) {
    return (
      <section className="rounded-2xl border bg-white p-5">
        <EmptyState
          icon={ChatCircleText}
          title="Chưa có buổi phỏng vấn thử"
          description="Các buổi Phỏng vấn với Tech Lead AI và Kiểm tra kỹ thuật sau khi bắt đầu sẽ được lưu lại tại đây."
        />
      </section>
    );
  }

  return (
    <>
      <section className="rounded-2xl border bg-white">
        <div className="border-b p-5">
          <div className="flex items-center gap-3">
            <ClockCounterClockwise className="size-6 text-primary" weight="duotone" />
            <div>
              <h2 className="font-semibold">Buổi phỏng vấn đã lưu</h2>
              <p className="mt-1 text-sm text-muted">
                Hover qua từng buổi để xem hiệu ứng, click để mở popup nội dung và đánh giá.
              </p>
            </div>
          </div>
        </div>
        <div className="grid gap-5 p-5 xl:grid-cols-2">
          {sessions.map((session) => (
            <article
              key={session.session_id}
              className="group relative min-h-40 overflow-hidden rounded-2xl border bg-white p-5 transition-all duration-200 hover:-translate-y-1 hover:scale-[1.01] hover:border-primary hover:bg-primary/5 hover:shadow-xl hover:shadow-primary/10"
            >
              <div className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-primary opacity-0 transition-opacity group-hover:opacity-100" />
              <div className="flex items-start justify-between gap-3">
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() => openSession(session.session_id)}
                  disabled={detailLoading}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold">{session.job_title || "Không rõ vị trí"}</h3>
                    <Badge tone={session.interview_mode === "technical_check" ? "cyan" : "blue"}>
                      {modeLabel(session.interview_mode)}
                    </Badge>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-muted">
                    {dateFormatter.format(new Date(session.created_at))} ·{" "}
                    {session.question_count} câu ·{" "}
                    {session.status === "COMPLETED" ? "Đã hoàn thành" : "Đang làm"}
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    {session.has_report ? "Có đánh giá sau phỏng vấn" : "Chưa có đánh giá"}
                  </p>
                  <span className="mt-4 inline-flex translate-y-1 items-center gap-2 rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-primary opacity-0 shadow-sm ring-1 ring-primary/10 transition-all group-hover:translate-y-0 group-hover:opacity-100">
                    <Eye className="size-4" />
                    Xem lại buổi phỏng vấn
                  </span>
                </button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="shrink-0 text-danger opacity-70 hover:bg-red-50 hover:opacity-100"
                  title="Xóa buổi phỏng vấn"
                  disabled={deletingId === session.session_id}
                  onClick={() => deleteSession(session.session_id)}
                >
                  {deletingId === session.session_id ? (
                    <SpinnerGap className="size-4 animate-spin" />
                  ) : (
                    <Trash className="size-4" />
                  )}
                </Button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <Modal
        open={Boolean(selected) || detailLoading}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title={selected?.job_title || "Buổi phỏng vấn đã lưu"}
        description={
          selected
            ? `${modeLabel(selected.interview_mode)} · ${dateFormatter.format(
                new Date(selected.created_at),
              )}`
            : "Đang tải nội dung buổi phỏng vấn..."
        }
        contentClassName="max-w-5xl"
      >
        {detailLoading ? <PanelSkeleton /> : null}
        {!detailLoading && selected ? (
          <InterviewDetail
            detail={selected}
            activeTab={activeTab}
            answer={answer}
            submittingAnswer={submittingAnswer}
            onTabChange={setActiveTab}
            onAnswerChange={setAnswer}
            onSubmitAnswer={submitAnswer}
          />
        ) : null}
      </Modal>
    </>
  );
}

function InterviewDetail({
  detail,
  activeTab,
  answer,
  submittingAnswer,
  onTabChange,
  onAnswerChange,
  onSubmitAnswer,
}: {
  detail: InterviewSessionDetail;
  activeTab: DetailTab;
  answer: string;
  submittingAnswer: boolean;
  onTabChange: (tab: DetailTab) => void;
  onAnswerChange: (value: string) => void;
  onSubmitAnswer: (event: React.FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={detail.interview_mode === "technical_check" ? "cyan" : "blue"}>
          {modeLabel(detail.interview_mode)}
        </Badge>
        <Badge tone={detail.status === "COMPLETED" ? "green" : "amber"}>
          {detail.status === "COMPLETED" ? "Đã hoàn thành" : "Đang làm"}
        </Badge>
        <Badge tone={detail.has_report ? "green" : "gray"}>
          {detail.has_report ? "Có đánh giá" : "Chưa có đánh giá"}
        </Badge>
      </div>

      <div className="grid grid-cols-2 rounded-xl bg-slate-100 p-1">
        <TabButton
          active={activeTab === "transcript"}
          icon={<ChatCircleText className="size-4" />}
          label="Nội dung cuộc phỏng vấn"
          onClick={() => onTabChange("transcript")}
        />
        <TabButton
          active={activeTab === "report"}
          icon={<ChartBar className="size-4" />}
          label="Đánh giá"
          onClick={() => onTabChange("report")}
        />
      </div>

      <div className="max-h-[58vh] overflow-y-auto pr-1">
        {activeTab === "transcript" ? <TranscriptPage detail={detail} /> : null}
        {activeTab === "report" ? <ReportPage report={detail.report} /> : null}
      </div>

      {detail.status !== "COMPLETED" && activeTab === "transcript" ? (
        <ResumeAnswerForm
          answer={answer}
          pending={submittingAnswer}
          onAnswerChange={onAnswerChange}
          onSubmit={onSubmitAnswer}
        />
      ) : null}
    </div>
  );
}

function TabButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`focus-ring flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition ${
        active ? "bg-white text-primary shadow-sm" : "text-muted hover:bg-white/70"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

function TranscriptPage({ detail }: { detail: InterviewSessionDetail }) {
  if (!detail.turns.length) {
    return (
      <EmptyState
        icon={CalendarDots}
        title="Chưa có nội dung"
        description="Buổi phỏng vấn này chưa ghi nhận câu hỏi nào."
      />
    );
  }
  return (
    <section className="space-y-4">
      {detail.turns.map((turn) => (
        <article key={turn.sequence} className="rounded-2xl border p-4">
          <p className="text-xs font-semibold uppercase text-primary">Câu {turn.sequence}</p>
          <div className="mt-3 border-l-2 border-primary pl-3">
            <p className="text-xs font-semibold text-muted">Người phỏng vấn</p>
            <p className="mt-1 whitespace-pre-wrap text-sm leading-6">{turn.question}</p>
          </div>
          <div className="mt-3 rounded-xl bg-slate-50 p-3">
            <p className="text-xs font-semibold text-muted">Bạn</p>
            <p className="mt-1 whitespace-pre-wrap text-sm leading-6">
              {turn.answer || "Chưa trả lời"}
            </p>
          </div>
        </article>
      ))}
    </section>
  );
}

function ResumeAnswerForm({
  answer,
  pending,
  onAnswerChange,
  onSubmit,
}: {
  answer: string;
  pending: boolean;
  onAnswerChange: (value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <form onSubmit={onSubmit} className="space-y-3 border-t pt-4">
      <div>
        <label className="text-sm font-semibold" htmlFor="saved-interview-answer">
          Trả lời câu hiện tại
        </label>
        <textarea
          id="saved-interview-answer"
          value={answer}
          onChange={(event) => onAnswerChange(event.target.value)}
          placeholder="Nhập câu trả lời của bạn để tiếp tục buổi phỏng vấn..."
          className="focus-ring mt-2 min-h-28 w-full resize-y rounded-lg border p-3 text-sm"
          maxLength={10000}
          disabled={pending}
        />
      </div>
      <Button type="submit" className="w-full" disabled={pending || !answer.trim()}>
        {pending ? (
          <SpinnerGap className="size-4 animate-spin" />
        ) : (
          <PaperPlaneTilt className="size-4" />
        )}
        Gửi câu trả lời
      </Button>
    </form>
  );
}

function ReportPage({ report }: { report: InterviewReport | null }) {
  if (!report) {
    return (
      <EmptyState
        icon={ChartBar}
        title="Chưa có đánh giá"
        description="Buổi phỏng vấn cần hoàn thành trước khi hệ thống tạo đánh giá."
      />
    );
  }
  return (
    <section className="space-y-5">
      <div className="rounded-2xl bg-primary/5 p-4">
        <div className="flex items-start gap-3">
          <div className="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary text-lg font-bold text-white">
            {report.overall_score}
          </div>
          <div>
            <h3 className="font-semibold">Đánh giá sau phỏng vấn</h3>
            <p className="mt-1 text-sm leading-6 text-muted">{report.overall_summary}</p>
          </div>
        </div>
      </div>

      <div>
        <div className="mb-3 flex items-center gap-2">
          <ChartBar className="size-5 text-primary" />
          <h4 className="font-semibold">Các khía cạnh đánh giá</h4>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {report.dimensions.map((dimension) => (
            <div key={dimension.key} className="rounded-xl border bg-white p-3">
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
              <p className="mt-2 text-xs leading-5 text-muted">{dimension.summary}</p>
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
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <ReportList
          icon={<CheckCircle className="size-5 text-emerald-600" />}
          title="Điểm mạnh"
          items={report.strengths}
        />
        <ReportList
          icon={<WarningCircle className="size-5 text-amber-600" />}
          title="Cần cải thiện"
          items={report.improvements}
        />
        <ReportList
          icon={<CheckCircle className="size-5 text-primary" />}
          title="Kế hoạch cải thiện"
          items={report.action_plan}
        />
        <ReportList
          icon={<WarningCircle className="size-5 text-muted" />}
          title="Chưa đủ bằng chứng"
          items={report.insufficient_evidence}
        />
      </div>
    </section>
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
    <div className="rounded-xl border bg-white p-3">
      <div className="mb-2 flex items-center gap-2">
        {icon}
        <h4 className="font-semibold">{title}</h4>
      </div>
      <ul className="space-y-1 text-xs leading-5 text-muted">
        {items.map((item) => (
          <li key={item}>• {item}</li>
        ))}
      </ul>
    </div>
  );
}

function modeLabel(mode: InterviewMode): string {
  return mode === "technical_check" ? "Kiểm tra kỹ thuật" : "Phỏng vấn với Tech Lead AI";
}
