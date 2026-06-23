"use client";

import {
  ArrowRight,
  ChartBar,
  ChatCircleText,
  CheckCircle,
  PaperPlaneTilt,
  SpinnerGap,
  Target,
  WarningCircle,
} from "@phosphor-icons/react";
import { useState } from "react";
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

interface InterviewResponse {
  session_id: string;
  question: string;
  current_phase: InterviewPhase;
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

interface TranscriptItem {
  question: string;
  answer?: string;
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

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      setSession(null);
      setTranscript([]);
      setAnswer("");
      setPending(false);
    }
    onOpenChange(nextOpen);
  }

  async function start() {
    if (!job || !cv) return;
    setPending(true);
    try {
      const response = await apiFetch<InterviewResponse>("/ai/interviews/sessions", {
        method: "POST",
        body: JSON.stringify({
          cv_id: cv.id,
          job_id: job.id,
          interview_config: {
            language: "vi",
            candidate_level: "student",
            target_role: job.title,
          },
        }),
      });
      setSession(response);
      setTranscript(response.question ? [{ question: response.question }] : []);
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
      setTranscript((items) => {
        const next = items.map((item, index) =>
          index === items.length - 1 ? { ...item, answer: content } : item,
        );
        return response.question ? [...next, { question: response.question }] : next;
      });
      setAnswer("");
      setSession(response);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setPending(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={handleOpenChange}
      title="Mô phỏng phỏng vấn"
      description={job ? `Vị trí: ${job.title}` : undefined}
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
          <Button className="w-full" onClick={start} disabled={!cv || pending}>
            {pending ? (
              <SpinnerGap className="size-4 animate-spin" />
            ) : (
              <ArrowRight className="size-4" />
            )}
            Bắt đầu phỏng vấn
          </Button>
        </div>
      ) : (
        <div className="space-y-5">
          <div className="border-b pb-3 text-xs">
            <span className="font-semibold uppercase text-primary">
              {phaseLabel(session.current_phase)}
            </span>
          </div>
          {session.should_end_interview && session.report ? (
            <InterviewReportView report={session.report} />
          ) : (
            <div className="max-h-[48vh] space-y-4 overflow-y-auto pr-1">
              {transcript.map((item, index) => (
                <div key={`${index}-${item.question}`} className="space-y-2">
                  <div className="border-l-2 border-primary pl-3">
                    <p className="text-xs font-semibold text-muted">Người phỏng vấn</p>
                    <p className="mt-1 text-sm leading-6">{item.question}</p>
                  </div>
                  {item.answer ? (
                    <div className="ml-5 bg-slate-50 p-3">
                      <p className="text-xs font-semibold text-muted">Bạn</p>
                      <p className="mt-1 whitespace-pre-wrap text-sm leading-6">{item.answer}</p>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          )}
          {session.should_end_interview ? (
            <div className="border-t pt-4 text-center">
              <p className="font-semibold">Buổi phỏng vấn đã hoàn thành</p>
              <Button className="mt-4" variant="outline" onClick={() => handleOpenChange(false)}>
                Đóng
              </Button>
            </div>
          ) : (
            <form onSubmit={submitAnswer} className="space-y-3 border-t pt-4">
              <textarea
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="Nhập câu trả lời của bạn..."
                className="focus-ring min-h-28 w-full resize-y rounded-lg border p-3 text-sm"
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
          )}
        </div>
      )}
    </Modal>
  );
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

function phaseLabel(phase: InterviewPhase): string {
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
