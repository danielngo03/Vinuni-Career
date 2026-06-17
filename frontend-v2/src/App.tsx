import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  BookOpenCheck,
  BriefcaseBusiness,
  Building2,
  CheckCircle2,
  Filter,
  GraduationCap,
  LayoutDashboard,
  Search,
  Sparkles,
  Trash2,
  UserRound,
} from "lucide-react";
import { api } from "./api";
import type { CompatMatch, FlowMode, Job, Student, StudentJobMatch, View } from "./types";

const MODE_LABEL: Record<FlowMode, string> = {
  balanced: "Cân bằng",
  strict: "Khắt khe",
  intern_friendly: "Thân thiện intern",
};

function App() {
  const [view, setView] = useState<View>("overview");
  const [students, setStudents] = useState<Student[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function refresh() {
    setError("");
    setLoading(true);
    try {
      const [studentData, jobData] = await Promise.all([api.listStudents(), api.listJobs()]);
      setStudents(studentData);
      setJobs(jobData);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <nav className="nav-stack" aria-label="Điều hướng chính">
          <NavButton active={view === "overview"} icon={<LayoutDashboard size={18} />} label="Tổng quan" onClick={() => setView("overview")} />
          <NavButton active={view === "student"} icon={<UserRound size={18} />} label="Sinh viên" onClick={() => setView("student")} />
          <NavButton active={view === "company"} icon={<Building2 size={18} />} label="Doanh nghiệp" onClick={() => setView("company")} />
        </nav>
        <div className="sidebar-note">
          <BookOpenCheck size={18} />
          <span>Prototype từ Streamlit Flow Lab, dùng dữ liệu demo trong backend.</span>
        </div>
      </aside>

      <main className="main-stage">
        <header className="topbar">
          <div>
            <p className="eyebrow">Corhort Edu Match</p>
            <h1>{titleForView(view)}</h1>
          </div>
          <button className="secondary-button" onClick={refresh}>
            <Sparkles size={16} />
            Làm mới dữ liệu
          </button>
        </header>

        {error && <Banner tone="error" text={error} />}
        {loading && <Banner tone="info" text="Đang tải dữ liệu demo..." />}

        {view === "overview" && <Overview students={students} jobs={jobs} onOpen={setView} />}
        {view === "student" && <StudentFlow students={students} jobs={jobs} />}
        {view === "company" && <CompanyFlow students={students} jobs={jobs} onChanged={refresh} />}
      </main>
    </div>
  );
}

function Overview({ students, jobs, onOpen }: { students: Student[]; jobs: Job[]; onOpen: (view: View) => void }) {
  const openJobs = jobs.filter((job) => job.status === "open");
  const skillCount = new Set(students.flatMap((student) => Object.keys(student.skills || {}))).size;

  return (
    <section className="overview-grid">
      <section className="hero-band">
        <div className="hero-copy">
          <p className="eyebrow">Nền tảng giáo dục hướng nghiệp</p>
          <h2>Biến hồ sơ năng lực thành lộ trình ứng tuyển rõ ràng.</h2>
          <p>
            Sinh viên thấy công việc phù hợp và khoảng cách kỹ năng. Doanh nghiệp xem ứng viên theo điểm match, điểm mạnh và rủi ro cần kiểm tra.
          </p>
          <div className="button-row">
            <button className="primary-button" onClick={() => onOpen("student")}>
              Mở flow sinh viên
              <ArrowRight size={16} />
            </button>
            <button className="quiet-button" onClick={() => onOpen("company")}>
              Mở flow doanh nghiệp
              <BriefcaseBusiness size={16} />
            </button>
          </div>
        </div>
        <div className="learning-visual" aria-hidden="true">
          <div className="visual-board">
            <span />
            <span />
            <span />
          </div>
          <div className="visual-card primary">CV</div>
          <div className="visual-card accent">JD</div>
          <div className="visual-score">92%</div>
        </div>
      </section>

      <div className="metric-strip">
        <Metric label="Sinh viên" value={students.length} />
        <Metric label="Job đang mở" value={openJobs.length} />
        <Metric label="Kỹ năng đã ghi nhận" value={skillCount} />
      </div>

      <section className="action-grid">
        <ActionCard icon={<UserRound size={18} />} title="Student flow" text="Tìm job phù hợp, lọc theo điểm, trạng thái và xem kỹ năng còn thiếu." onClick={() => onOpen("student")} />
        <ActionCard icon={<Building2 size={18} />} title="Company flow" text="Quản lý trạng thái JD và xếp hạng ứng viên theo rulebase matching." onClick={() => onOpen("company")} />
        <ActionCard icon={<GraduationCap size={18} />} title="Education theme" text="Tông sáng, nội dung tiếng Việt, tập trung vào học tập và phát triển năng lực." onClick={() => onOpen("student")} />
      </section>
    </section>
  );
}

function StudentFlow({ students, jobs }: { students: Student[]; jobs: Job[] }) {
  const [studentId, setStudentId] = useState(students[0]?.student_id || "");
  const [mode, setMode] = useState<FlowMode>("balanced");
  const [query, setQuery] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [status, setStatus] = useState("all");
  const [matches, setMatches] = useState<StudentJobMatch[]>([]);
  const [error, setError] = useState("");
  const selectedStudent = students.find((student) => student.student_id === studentId) || students[0];

  useEffect(() => {
    if (!studentId && students[0]) setStudentId(students[0].student_id);
  }, [studentId, students]);

  const visibleMatches = useMemo(() => {
    return matches.filter(({ job, match }) => {
      const score = percent(match.match_score);
      const haystack = `${job.job_id} ${job.title} ${job.company_id}`.toLowerCase();
      return score >= minScore && (status === "all" || job.status === status) && (!query || haystack.includes(query.toLowerCase()));
    });
  }, [matches, minScore, query, status]);

  async function runMatch() {
    if (!selectedStudent) return;
    setError("");
    try {
      setMatches(await api.matchStudentJobs(selectedStudent.student_id, mode));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <section className="flow-layout">
      <div className="main-column">
        <Panel title="Hồ sơ sinh viên" subtitle="Dữ liệu lấy từ demo JSON trong Streamlit flow.">
          {selectedStudent ? <StudentProfile student={selectedStudent} /> : <EmptyState text="Chưa có hồ sơ sinh viên." />}
        </Panel>

        <Panel title="Job matching" subtitle="Chọn chế độ match rồi chạy xếp hạng tất cả JD cho sinh viên.">
          <div className="control-grid">
            <label>
              Sinh viên
              <select value={selectedStudent?.student_id || ""} onChange={(event) => setStudentId(event.target.value)}>
                {students.map((student) => (
                  <option key={student.student_id} value={student.student_id}>
                    {student.name || student.student_id}
                  </option>
                ))}
              </select>
            </label>
            <ModePicker value={mode} onChange={setMode} />
            <button className="primary-button align-end" onClick={runMatch} disabled={!selectedStudent}>
              Match all jobs
              <Search size={16} />
            </button>
          </div>
        </Panel>

        <Panel title="Kết quả phù hợp" subtitle={`Đang hiển thị ${visibleMatches.length} trong ${matches.length} kết quả.`}>
          <ResultFilters query={query} setQuery={setQuery} minScore={minScore} setMinScore={setMinScore} status={status} setStatus={setStatus} jobs={jobs} />
          {error && <Banner tone="error" text={error} />}
          <div className="result-list">
            {visibleMatches.map(({ job, match }) => (
              <JobMatchCard key={job.job_id} job={job} match={match} />
            ))}
            {!visibleMatches.length && <EmptyState text="Chưa có kết quả phù hợp với bộ lọc hiện tại." />}
          </div>
        </Panel>
      </div>

      <aside className="side-column">
        <Panel title="Tín hiệu học tập" subtitle="Góc nhìn nhanh để tư vấn kỹ năng tiếp theo.">
          <InsightStats students={students} jobs={jobs} matches={matches.map((item) => item.match)} />
        </Panel>
      </aside>
    </section>
  );
}

function CompanyFlow({ students, jobs, onChanged }: { students: Student[]; jobs: Job[]; onChanged: () => void }) {
  const [jobId, setJobId] = useState(jobs[0]?.job_id || "");
  const [mode, setMode] = useState<FlowMode>("balanced");
  const [query, setQuery] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [matches, setMatches] = useState<CompatMatch[]>([]);
  const [error, setError] = useState("");
  const selectedJob = jobs.find((job) => job.job_id === jobId) || jobs[0];

  useEffect(() => {
    if (!jobId && jobs[0]) setJobId(jobs[0].job_id);
  }, [jobId, jobs]);

  const visibleMatches = useMemo(() => {
    return matches.filter((match) => {
      const score = percent(match.match_score);
      const haystack = `${match.student_id} ${match.student_name || ""}`.toLowerCase();
      return score >= minScore && (!query || haystack.includes(query.toLowerCase()));
    });
  }, [matches, minScore, query]);

  async function runMatch() {
    if (!selectedJob) return;
    setError("");
    try {
      setMatches(await api.matchJobCandidates(selectedJob.job_id, mode));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function setStatus(status: "open" | "closed") {
    if (!selectedJob) return;
    setError("");
    try {
      await api.updateJobStatus(selectedJob.job_id, status);
      await onChanged();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function deleteJob() {
    if (!selectedJob) return;
    setError("");
    try {
      await api.deleteJob(selectedJob.job_id);
      setMatches([]);
      await onChanged();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <section className="flow-layout">
      <div className="main-column">
        <Panel title="Quản lý JD" subtitle="Tương đương phần Manage JD by ID trong Streamlit.">
          <div className="control-grid">
            <label>
              JD
              <select value={selectedJob?.job_id || ""} onChange={(event) => setJobId(event.target.value)}>
                {jobs.map((job) => (
                  <option key={job.job_id} value={job.job_id}>
                    {job.title} - {job.job_id}
                  </option>
                ))}
              </select>
            </label>
            <ModePicker value={mode} onChange={setMode} />
            <button className="primary-button align-end" onClick={runMatch} disabled={!selectedJob}>
              Rank all candidates
              <Search size={16} />
            </button>
          </div>
          {selectedJob && <JobDetail job={selectedJob} />}
          <div className="button-row">
            <button className="secondary-button" onClick={() => setStatus("open")} disabled={!selectedJob}>
              <CheckCircle2 size={16} />
              Set open
            </button>
            <button className="quiet-button" onClick={() => setStatus("closed")} disabled={!selectedJob}>
              Set closed
            </button>
            <button className="danger-button" onClick={deleteJob} disabled={!selectedJob}>
              <Trash2 size={16} />
              Delete JD
            </button>
          </div>
          {error && <Banner tone="error" text={error} />}
        </Panel>

        <Panel title="Ứng viên phù hợp" subtitle={`Đang hiển thị ${visibleMatches.length} trong ${matches.length} ứng viên.`}>
          <div className="filter-row">
            <label>
              <Filter size={15} />
              Tìm sinh viên
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tên hoặc mã sinh viên" />
            </label>
            <label>
              Điểm tối thiểu
              <input type="range" min="0" max="100" step="5" value={minScore} onChange={(event) => setMinScore(Number(event.target.value))} />
              <span>{minScore}%</span>
            </label>
          </div>
          <div className="result-list">
            {visibleMatches.map((match) => (
              <CandidateCard key={match.student_id} match={match} />
            ))}
            {!visibleMatches.length && <EmptyState text="Chưa có kết quả. Hãy chọn JD và chạy xếp hạng ứng viên." />}
          </div>
        </Panel>
      </div>

      <aside className="side-column">
        <Panel title="Nguồn ứng viên" subtitle={`${students.length} hồ sơ sinh viên trong demo data.`}>
          <div className="student-mini-list">
            {students.slice(0, 6).map((student) => (
              <span key={student.student_id}>{student.name || student.student_id}</span>
            ))}
          </div>
        </Panel>
      </aside>
    </section>
  );
}

function StudentProfile({ student }: { student: Student }) {
  const skills = Object.entries(student.skills || {});
  return (
    <div className="profile-block">
      <div>
        <p className="eyebrow">{student.student_id}</p>
        <h2>{student.name || "Sinh viên demo"}</h2>
      </div>
      <div className="skill-cloud">
        {skills.map(([name, detail]) => (
          <span key={name}>
            {name} · {Math.round(detail.score || 0)}/10
          </span>
        ))}
      </div>
    </div>
  );
}

function JobDetail({ job }: { job: Job }) {
  return (
    <div className="job-detail">
      <div>
        <p className="eyebrow">{job.job_id}</p>
        <h3>{job.title}</h3>
        <span>{job.company_id} · {job.location || "Remote"} · {job.status || "draft"}</span>
      </div>
      <div className="skill-cloud compact">
        {Object.entries(job.skills || {}).slice(0, 8).map(([name, detail]) => (
          <span key={name}>{name} · {Math.round(detail.required_level || 0)}/10</span>
        ))}
      </div>
    </div>
  );
}

function ResultFilters({
  query,
  setQuery,
  minScore,
  setMinScore,
  status,
  setStatus,
  jobs,
}: {
  query: string;
  setQuery: (value: string) => void;
  minScore: number;
  setMinScore: (value: number) => void;
  status: string;
  setStatus: (value: string) => void;
  jobs: Job[];
}) {
  const statuses = Array.from(new Set(jobs.map((job) => job.status || "-")));
  return (
    <div className="filter-row">
      <label>
        <Filter size={15} />
        Tìm JD
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tên job, mã job, công ty" />
      </label>
      <label>
        Trạng thái
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="all">Tất cả</option>
          {statuses.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
      </label>
      <label>
        Điểm tối thiểu
        <input type="range" min="0" max="100" step="5" value={minScore} onChange={(event) => setMinScore(Number(event.target.value))} />
        <span>{minScore}%</span>
      </label>
    </div>
  );
}

function JobMatchCard({ job, match }: { job: Job; match: CompatMatch }) {
  return (
    <article className="match-card">
      <div className="match-card-top">
        <div>
          <p className="eyebrow">{job.job_id} · {job.status || "-"}</p>
          <h3>{job.title}</h3>
          <span>{job.company_id} · {job.location || "Remote"}</span>
        </div>
        <Score value={match.match_score} />
      </div>
      <MatchText match={match} />
    </article>
  );
}

function CandidateCard({ match }: { match: CompatMatch }) {
  return (
    <article className="match-card">
      <div className="match-card-top">
        <div>
          <p className="eyebrow">{match.student_id}</p>
          <h3>{match.student_name || match.student_id}</h3>
          <span>{labelForStatus(match.match_status)}</span>
        </div>
        <Score value={match.match_score} />
      </div>
      <MatchText match={match} />
    </article>
  );
}

function MatchText({ match }: { match: CompatMatch }) {
  const gaps = Object.keys(match.missing_or_weak_skills || {});
  return (
    <div className="match-text">
      <p>{match.explanation}</p>
      <div className="two-column-list">
        <div>
          <strong>Điểm mạnh</strong>
          <span>{match.matched_skills?.join(", ") || "-"}</span>
        </div>
        <div>
          <strong>Khoảng cách</strong>
          <span>{gaps.join(", ") || "-"}</span>
        </div>
      </div>
    </div>
  );
}

function InsightStats({ students, jobs, matches }: { students: Student[]; jobs: Job[]; matches: CompatMatch[] }) {
  const best = matches[0];
  return (
    <div className="insight-stack">
      <Metric label="Hồ sơ" value={students.length} />
      <Metric label="JD" value={jobs.length} />
      <Metric label="Best match" value={best ? `${percent(best.match_score)}%` : "-"} />
      <p className="muted">Gợi ý tư vấn: ưu tiên những kỹ năng xuất hiện trong cả JD đang mở và phần gap của sinh viên.</p>
    </div>
  );
}

function ModePicker({ value, onChange }: { value: FlowMode; onChange: (value: FlowMode) => void }) {
  return (
    <label>
      Matching mode
      <div className="segmented">
        {(Object.keys(MODE_LABEL) as FlowMode[]).map((mode) => (
          <button key={mode} className={value === mode ? "active" : ""} type="button" onClick={() => onChange(mode)}>
            {MODE_LABEL[mode]}
          </button>
        ))}
      </div>
    </label>
  );
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      {children}
    </section>
  );
}

function NavButton({ active, icon, label, onClick }: { active: boolean; icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button className={active ? "nav-item active" : "nav-item"} onClick={onClick}>
      {icon}
      {label}
    </button>
  );
}

function Brand() {
  return (
    <div className="brand">
      <div className="brand-mark">C2</div>
      <div>
        <strong>Corhort</strong>
        <span>Education matching lab</span>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ActionCard({ icon, title, text, onClick }: { icon: React.ReactNode; title: string; text: string; onClick: () => void }) {
  return (
    <button className="action-card" onClick={onClick}>
      <span>{icon}</span>
      <strong>{title}</strong>
      <p>{text}</p>
    </button>
  );
}

function Score({ value }: { value: number }) {
  const score = percent(value);
  return <div className="score-ring" style={{ "--score": `${score}%` } as React.CSSProperties}>{score}%</div>;
}

function Banner({ tone, text }: { tone: "error" | "info"; text: string }) {
  return <div className={tone === "error" ? "banner error" : "banner info"}>{text}</div>;
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="empty-state">
      <Sparkles size={18} />
      <span>{text}</span>
    </div>
  );
}

function percent(value: number) {
  return Math.round(value <= 1 ? value * 100 : value);
}

function labelForStatus(status: CompatMatch["match_status"]) {
  if (status === "strong_match") return "Strong match";
  if (status === "partial_match") return "Partial match";
  return "Needs review";
}

function titleForView(view: View) {
  if (view === "student") return "Flow sinh viên";
  if (view === "company") return "Flow doanh nghiệp";
  return "Dashboard giáo dục";
}

export default App;
