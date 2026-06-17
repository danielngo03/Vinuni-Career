import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  BriefcaseBusiness,
  Building2,
  CheckCircle2,
  FileSearch,
  FileText,
  GraduationCap,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Search,
  Sparkles,
  Upload,
  UserRound,
} from "lucide-react";
import { api } from "./api";
import type { Job, MatchResult, ReviewResult, Role, Session, StudentJobMatch, StudentProfile, TeacherRagReport } from "./types";

const ROLE_LABELS: Record<Role, string> = {
  enterprise: "Doanh nghiệp",
  student: "Sinh viên",
  teacher: "Nhà trường",
};

const ROLE_IDS: Record<Role, string> = {
  enterprise: "company_demo",
  student: "mock-student-frontend-001",
  teacher: "teacher_demo",
};

const STRONG_DEFAULT = 0.8;
const PARTIAL_DEFAULT = 0.6;

function App() {
  const [session, setSession] = useState<Session | null>(() => {
    const raw = localStorage.getItem("corhort.session");
    return raw ? (JSON.parse(raw) as Session) : null;
  });
  const [view, setView] = useState<"home" | "workspace">("home");

  function login(next: Session) {
    localStorage.setItem("corhort.session", JSON.stringify(next));
    setSession(next);
    setView("home");
  }

  function logout() {
    localStorage.removeItem("corhort.session");
    setSession(null);
  }

  if (!session) {
    return <LoginScreen onLogin={login} />;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand compact={false} />
        <nav className="nav-stack" aria-label="Điều hướng chính">
          <button className={view === "home" ? "nav-item active" : "nav-item"} onClick={() => setView("home")}>
            <LayoutDashboard size={18} />
            Tổng quan
          </button>
          <button className={view === "workspace" ? "nav-item active" : "nav-item"} onClick={() => setView("workspace")}>
            {session.role === "student" ? <FileSearch size={18} /> : session.role === "enterprise" ? <BriefcaseBusiness size={18} /> : <BookOpenCheck size={18} />}
            Không gian làm việc
          </button>
        </nav>
        <div className="sidebar-footer">
          <div className="profile-chip">
            <span>{ROLE_LABELS[session.role]}</span>
            <strong>{session.userId}</strong>
          </div>
          <button className="quiet-button full" onClick={logout}>
            <LogOut size={16} />
            Đăng xuất
          </button>
        </div>
      </aside>

      <main className="main-stage">
        <header className="topbar">
          <div>
            <p className="eyebrow">Không gian Corhort</p>
            <h1>{view === "home" ? headlineForRole(session.role) : workspaceTitle(session.role)}</h1>
          </div>
          <button className="primary-button" onClick={() => setView(view === "home" ? "workspace" : "home")}>
            {view === "home" ? "Bắt đầu ngay" : "Về tổng quan"}
            <ArrowRight size={16} />
          </button>
        </header>
        {view === "home" ? <Home session={session} onOpenWorkspace={() => setView("workspace")} /> : <Workspace session={session} />}
      </main>
    </div>
  );
}

function LoginScreen({ onLogin }: { onLogin: (session: Session) => void }) {
  const [role, setRole] = useState<Role>("student");
  const [userId, setUserId] = useState(ROLE_IDS.student);

  function chooseRole(next: Role) {
    setRole(next);
    setUserId(ROLE_IDS[next]);
  }

  return (
    <main className="login-page">
      <section className="welcome-panel">
        <Brand compact={false} />
        <div className="welcome-copy">
          <p className="eyebrow">Nền tảng định hướng nghề nghiệp</p>
          <h1>Biến CV thành lộ trình ứng tuyển rõ ràng.</h1>
          <p>
            Corhort giúp sinh viên hiểu điểm mạnh, biết công việc nào phù hợp và thấy ngay điều cần cải thiện trước khi nộp hồ sơ.
          </p>
        </div>
        <div className="promise-row">
          <PromiseCard icon={<FileSearch size={18} />} title="Hiểu năng lực" text="CV được tóm tắt thành kỹ năng và bằng chứng." />
          <PromiseCard icon={<BriefcaseBusiness size={18} />} title="Chọn job đúng" text="Ưu tiên công việc phù hợp thay vì danh sách dài." />
          <PromiseCard icon={<Sparkles size={18} />} title="Biết cần sửa gì" text="Bản nhận xét chỉ ra kỹ năng và từ khóa còn thiếu." />
        </div>
      </section>

      <section className="signin-card">
        <p className="eyebrow">Truy cập demo</p>
        <h2>Bạn muốn trải nghiệm với vai trò nào?</h2>
        <div className="role-grid">
          <RoleButton active={role === "student"} icon={<UserRound size={18} />} label="Sinh viên" onClick={() => chooseRole("student")} />
          <RoleButton active={role === "enterprise"} icon={<Building2 size={18} />} label="Doanh nghiệp" onClick={() => chooseRole("enterprise")} />
          <RoleButton active={role === "teacher"} icon={<GraduationCap size={18} />} label="Nhà trường" onClick={() => chooseRole("teacher")} />
        </div>
        <label className="field-label">
          Mã tài khoản
          <input className="text-input" value={userId} onChange={(event) => setUserId(event.target.value)} />
        </label>
        <button className="primary-button full" onClick={() => onLogin({ role, userId: userId.trim() || ROLE_IDS[role] })}>
          Vào hệ thống
          <ArrowRight size={16} />
        </button>
      </section>
    </main>
  );
}

function Home({ session, onOpenWorkspace }: { session: Session; onOpenWorkspace: () => void }) {
  if (session.role === "student") return <StudentHome session={session} onOpenWorkspace={onOpenWorkspace} />;
  if (session.role === "enterprise") return <EnterpriseHome session={session} onOpenWorkspace={onOpenWorkspace} />;
  return <TeacherHome onOpenWorkspace={onOpenWorkspace} />;
}

function StudentHome({ session, onOpenWorkspace }: { session: Session; onOpenWorkspace: () => void }) {
  const [profiles, setProfiles] = useState<StudentProfile[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.listMyStudents(session), api.listOpenJobs(session)])
      .then(([profileData, jobData]) => {
        setProfiles(profileData);
        setJobs(jobData);
      })
      .catch((err: Error) => setError(err.message));
  }, [session]);

  const hasProfile = profiles.length > 0;

  return (
    <section className="page-grid">
      <ErrorBanner message={error} />
      <HeroCard
        icon={<UserRound size={22} />}
        title={hasProfile ? `Chào ${profiles[0].name}` : "Bắt đầu với CV của bạn"}
        text={hasProfile ? "Bạn đã có hồ sơ kỹ năng. Bước tiếp theo là xem công việc phù hợp và nhận xét CV với JD cụ thể." : "Tải CV hoặc dán nội dung CV để hệ thống tạo hồ sơ kỹ năng đầu tiên."}
        action="Mở cổng sinh viên"
        onAction={onOpenWorkspace}
      />
      <section className="action-grid">
        <ActionCard step="01" title="Tạo hồ sơ kỹ năng" text="AI trích xuất kỹ năng, bằng chứng, học vấn và kinh nghiệm từ CV." done={hasProfile} />
        <ActionCard step="02" title="Xem job nên ưu tiên" text={`${jobs.length || "Các"} công việc đang mở sẽ được xếp theo độ phù hợp.`} done={false} />
        <ActionCard step="03" title="Sửa CV trước khi nộp" text="Bản nhận xét so sánh CV với JD và gợi ý từ khóa, kỹ năng còn thiếu." done={false} />
      </section>
    </section>
  );
}

function EnterpriseHome({ session, onOpenWorkspace }: { session: Session; onOpenWorkspace: () => void }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [students, setStudents] = useState<StudentProfile[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.listJobs(session), api.listStudentsForEnterprise(session)])
      .then(([jobData, studentData]) => {
        setJobs(jobData);
        setStudents(studentData);
      })
      .catch((err: Error) => setError(err.message));
  }, [session]);

  const openJobs = jobs.filter((job) => job.status === "open");

  return (
    <section className="page-grid">
      <ErrorBanner message={error} />
      <HeroCard
        icon={<Building2 size={22} />}
        title="Tuyển đúng người từ dữ liệu rõ ràng"
        text="Tạo JD có cấu trúc, mở vị trí tuyển dụng và xem danh sách sinh viên phù hợp nhất."
        action="Mở không gian JD"
        onAction={onOpenWorkspace}
      />
      <section className="summary-strip">
        <SummaryItem label="Vị trí đang mở" value={String(openJobs.length)} />
        <SummaryItem label="Hồ sơ có thể xem" value={String(students.length)} />
        <SummaryItem label="Quy trình" value="JD → So khớp → Nhận xét" />
      </section>
      <section className="action-grid">
        <ActionCard step="01" title="Chuẩn hóa JD" text="Dán JD hoặc tải tệp lên để tạo yêu cầu kỹ năng." done={jobs.length > 0} />
        <ActionCard step="02" title="Mở vị trí" text="Chỉ job đang mở mới xuất hiện cho sinh viên." done={openJobs.length > 0} />
        <ActionCard step="03" title="Xem ứng viên phù hợp" text="Kết quả giải thích kỹ năng khớp và khoảng cách cần cân nhắc." done={false} />
      </section>
    </section>
  );
}

function TeacherHome({ onOpenWorkspace }: { onOpenWorkspace: () => void }) {
  return (
    <section className="page-grid">
      <HeroCard
        icon={<GraduationCap size={22} />}
        title="Chuẩn bị dữ liệu học tập cho RAG"
        text="Nhà trường có thể tạo bản chép lời sạch và các đoạn dữ liệu từ video hoặc playlist YouTube."
        action="Mở không gian RAG"
        onAction={onOpenWorkspace}
      />
      <section className="action-grid">
        <ActionCard step="01" title="Nhập nguồn video" text="Dán đường dẫn YouTube video hoặc playlist." done={false} />
        <ActionCard step="02" title="Tạo bản chép lời sạch" text="Hệ thống tải phụ đề, làm sạch và chuẩn hóa thông tin mô tả." done={false} />
        <ActionCard step="03" title="Xuất đoạn dữ liệu cho RAG" text="Dữ liệu được lưu thành JSONL và báo cáo để kiểm tra." done={false} />
      </section>
    </section>
  );
}

function Workspace({ session }: { session: Session }) {
  if (session.role === "student") return <StudentWorkspace session={session} />;
  if (session.role === "enterprise") return <EnterpriseWorkspace session={session} />;
  return <TeacherWorkspace session={session} />;
}

function StudentWorkspace({ session }: { session: Session }) {
  const [profiles, setProfiles] = useState<StudentProfile[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [draftStudent, setDraftStudent] = useState<StudentProfile | null>(null);
  const [cvText, setCvText] = useState("Chi Le\nMajor: Computer Science\nProjects:\nBuilt interactive dashboards with JavaScript and React.\nCompleted a Python API coursework project.");
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [selectedJobId, setSelectedJobId] = useState("");
  const [matches, setMatches] = useState<StudentJobMatch[]>([]);
  const [review, setReview] = useState<ReviewResult | null>(null);
  const [useLlm, setUseLlm] = useState(true);
  const [aiLoading, setAiLoading] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selectedProfile = profiles.find((profile) => profile.student_id === selectedProfileId) || profiles[0];
  const selectedJob = jobs.find((job) => job.job_id === selectedJobId) || jobs[0];
  const topMatch = matches[0];

  async function refresh() {
    const [profileData, jobData] = await Promise.all([api.listMyStudents(session), api.listOpenJobs(session)]);
    setProfiles(profileData);
    setJobs(jobData);
    if (!selectedProfileId && profileData[0]) setSelectedProfileId(profileData[0].student_id);
    if (!selectedJobId && jobData[0]) setSelectedJobId(jobData[0].job_id);
  }

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message));
  }, [session]);

  async function runAction(action: () => Promise<void>, success: string, loadingMessage = "") {
    setError("");
    setNotice("");
    if (loadingMessage) setAiLoading(loadingMessage);
    try {
      await action();
      setNotice(success);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      if (loadingMessage) setAiLoading("");
    }
  }

  return (
    <section className="workspace-flow">
      <ErrorBanner message={error} />
      <Notice message={notice} />
      <AiLoadingBanner message={aiLoading} />
      <section className="flow-main">
        <Panel title="1. Tạo hồ sơ từ CV" subtitle="Bạn chỉ cần đưa CV vào, hệ thống sẽ tóm tắt phần quan trọng.">
          <textarea className="text-area" value={cvText} onChange={(event) => setCvText(event.target.value)} />
          <div className="button-row">
            <button className="primary-button" disabled={Boolean(aiLoading)} onClick={() => runAction(async () => setDraftStudent(await api.parseCvText(session, cvText)), "Đã đọc CV. Hãy kiểm tra hồ sơ trước khi lưu.", "AI đang đọc CV")}>
              {aiLoading === "AI đang đọc CV" ? <LoaderCircle className="spin-icon" size={16} /> : <Sparkles size={16} />}
              {aiLoading === "AI đang đọc CV" ? "Đang đọc CV" : "Đọc CV"}
            </button>
            <label className={aiLoading ? "secondary-button disabled" : "secondary-button"}>
              {aiLoading === "AI đang đọc CV từ tệp" ? <LoaderCircle className="spin-icon" size={16} /> : <Upload size={16} />}
              {aiLoading === "AI đang đọc CV từ tệp" ? "Đang đọc tệp" : "Tải CV lên"}
              <input
                hidden
                type="file"
                accept=".txt,.pdf,.docx"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file && !aiLoading) runAction(async () => {
                    const parsed = await api.parseCvUpload(session, file);
                    if (parsed._raw_text) setCvText(parsed._raw_text);
                    setDraftStudent(parsed);
                  }, "Đã tải lên và đọc CV. Nội dung đã được đưa vào ô CV để kiểm tra.", "AI đang đọc CV từ tệp");
                }}
              />
            </label>
          </div>
          {draftStudent && (
            <ProfilePreview student={draftStudent} onSave={() => runAction(async () => {
              const metadata = {
                ...(draftStudent.metadata || {}),
                owner_user_id: session.userId,
                cv_text_excerpt: cvText.slice(0, 6000),
              };
              const saved = await api.saveStudent(session, { ...draftStudent, student_id: session.userId, metadata });
              setSelectedProfileId(saved.student_id);
              setDraftStudent(null);
              await refresh();
            }, "Đã lưu hồ sơ kỹ năng.")} />
          )}
        </Panel>

        <Panel title="2. Chọn công việc phù hợp" subtitle="Danh sách được giữ gọn để bạn tập trung vào lựa chọn tiếp theo.">
          {jobs.length ? (
            <div className="soft-list">
              {jobs.map((job) => (
                <button key={job.job_id} className={selectedJob?.job_id === job.job_id ? "soft-card selected" : "soft-card"} onClick={() => setSelectedJobId(job.job_id)}>
                  <div>
                    <strong>{job.title}</strong>
                    <span>{job.location} · {job.employment_type}</span>
                  </div>
                  <ArrowRight size={16} />
                </button>
              ))}
            </div>
          ) : (
            <EmptyState title="Chưa có công việc đang mở" text="Khi doanh nghiệp mở JD, công việc sẽ xuất hiện tại đây." />
          )}
        </Panel>
      </section>

      <aside className="flow-side">
        <Panel title="Hồ sơ đang dùng" subtitle="Chọn hồ sơ để so khớp và nhận xét.">
          {profiles.length ? (
            <select className="text-input" value={selectedProfile?.student_id || ""} onChange={(event) => setSelectedProfileId(event.target.value)}>
              {profiles.map((profile) => (
                <option key={profile.student_id} value={profile.student_id}>{profile.name}</option>
              ))}
            </select>
          ) : (
            <EmptyState title="Chưa có hồ sơ" text="Hãy đọc CV và lưu hồ sơ trước." />
          )}
        </Panel>

        <Panel title="3. Xem mức độ phù hợp" subtitle="Kết quả được diễn giải bằng ngôn ngữ dễ hiểu.">
          <div className="button-column">
            <button
              className="primary-button full"
              disabled={!selectedProfile}
              onClick={() => selectedProfile && runAction(async () => setMatches(await api.matchStudentJobs(session, selectedProfile.student_id, STRONG_DEFAULT, PARTIAL_DEFAULT)), "Đã xếp hạng công việc phù hợp.")}
            >
              Tìm job phù hợp
              <Search size={16} />
            </button>
            <label className="toggle-line">
              <input type="checkbox" checked={useLlm} onChange={(event) => setUseLlm(event.target.checked)} />
              Dùng AI nhận xét khi có cấu hình
            </label>
            <button
              className="secondary-button full"
              disabled={!selectedProfile || !selectedJob || Boolean(aiLoading)}
              onClick={() => selectedProfile && selectedJob && runAction(async () => setReview(await api.reviewStudentJob(session, selectedProfile.student_id, selectedJob.job_id, STRONG_DEFAULT, PARTIAL_DEFAULT, useLlm)), "Đã nhận xét CV với JD.", useLlm ? "AI đang nhận xét CV" : "")}
            >
              {aiLoading === "AI đang nhận xét CV" ? "Đang nhận xét CV" : "Nhận xét CV với JD đã chọn"}
              {aiLoading === "AI đang nhận xét CV" ? <LoaderCircle className="spin-icon" size={16} /> : <FileSearch size={16} />}
            </button>
          </div>
          {topMatch && <MatchHighlight match={topMatch} />}
          {review && <ReviewCard review={review} />}
        </Panel>
      </aside>
    </section>
  );
}

function EnterpriseWorkspace({ session }: { session: Session }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [students, setStudents] = useState<StudentProfile[]>([]);
  const [draftJob, setDraftJob] = useState<Job | null>(null);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [matches, setMatches] = useState<MatchResult[]>([]);
  const [rawText, setRawText] = useState("Frontend Intern. Required skills: JavaScript 8, React 7, Communication 6. Nice to have: Documentation.");
  const [aiLoading, setAiLoading] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selectedJob = jobs.find((job) => job.job_id === selectedJobId) || jobs[0];

  async function refresh() {
    const [jobData, studentData] = await Promise.all([api.listJobs(session), api.listStudentsForEnterprise(session)]);
    setJobs(jobData);
    setStudents(studentData);
    if (!selectedJobId && jobData[0]) setSelectedJobId(jobData[0].job_id);
  }

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message));
  }, [session]);

  async function runAction(action: () => Promise<void>, success: string, loadingMessage = "") {
    setError("");
    setNotice("");
    if (loadingMessage) setAiLoading(loadingMessage);
    try {
      await action();
      setNotice(success);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      if (loadingMessage) setAiLoading("");
    }
  }

  return (
    <section className="workspace-flow">
      <ErrorBanner message={error} />
      <Notice message={notice} />
      <AiLoadingBanner message={aiLoading} />
      <section className="flow-main">
        <Panel title="1. Chuẩn hóa JD" subtitle="Dán JD hoặc tải tệp lên. Hệ thống sẽ biến JD thành yêu cầu kỹ năng.">
          <textarea className="text-area" value={rawText} onChange={(event) => setRawText(event.target.value)} />
          <div className="button-row">
            <button className="primary-button" disabled={Boolean(aiLoading)} onClick={() => runAction(async () => setDraftJob(await api.parseJob(session, { raw_text: rawText, company_id: session.userId })), "Đã đọc JD. Hãy kiểm tra trước khi lưu.", "AI đang đọc JD")}>
              {aiLoading === "AI đang đọc JD" ? <LoaderCircle className="spin-icon" size={16} /> : <Sparkles size={16} />}
              {aiLoading === "AI đang đọc JD" ? "Đang đọc JD" : "Đọc JD"}
            </button>
            <label className={aiLoading ? "secondary-button disabled" : "secondary-button"}>
              {aiLoading === "AI đang đọc JD từ tệp" ? <LoaderCircle className="spin-icon" size={16} /> : <Upload size={16} />}
              {aiLoading === "AI đang đọc JD từ tệp" ? "Đang đọc tệp" : "Tải JD lên"}
              <input
                hidden
                type="file"
                accept=".txt,.pdf,.docx"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file && !aiLoading) runAction(async () => setDraftJob(await api.parseJobUpload(session, file)), "Đã tải lên và đọc JD.", "AI đang đọc JD từ tệp");
                }}
              />
            </label>
          </div>
          {draftJob && (
            <JobPreview job={draftJob} onSave={() => runAction(async () => {
              await api.saveJob(session, draftJob);
              setDraftJob(null);
              await refresh();
            }, "Đã lưu JD.")} />
          )}
        </Panel>

        <Panel title="2. Quản lý vị trí" subtitle="Mở vị trí để sinh viên có thể xem và được so khớp.">
          {jobs.length ? (
            <div className="soft-list">
              {jobs.map((job) => (
                <button key={job.job_id} className={selectedJob?.job_id === job.job_id ? "soft-card selected" : "soft-card"} onClick={() => setSelectedJobId(job.job_id)}>
                  <div>
                    <strong>{job.title}</strong>
                    <span>{job.status === "open" ? "Đang mở" : job.status === "closed" ? "Đã đóng" : "Bản nháp"} · {job.location}</span>
                  </div>
                  <ArrowRight size={16} />
                </button>
              ))}
            </div>
          ) : (
            <EmptyState title="Chưa có JD" text="Hãy tạo JD đầu tiên để bắt đầu so khớp." />
          )}
          {selectedJob && (
            <div className="button-row roomy">
              <button className="secondary-button" onClick={() => runAction(async () => {
                await api.openJob(session, selectedJob.job_id);
                await refresh();
              }, "Đã mở vị trí.")}>Mở vị trí</button>
              <button className="quiet-button" onClick={() => runAction(async () => {
                await api.closeJob(session, selectedJob.job_id);
                await refresh();
              }, "Đã đóng vị trí.")}>Đóng</button>
            </div>
          )}
        </Panel>
      </section>

      <aside className="flow-side">
        <Panel title="Ứng viên phù hợp" subtitle={`${students.length} hồ sơ có thể được xem trong bản demo.`}>
          <button
            className="primary-button full"
            disabled={!selectedJob || selectedJob.status !== "open"}
            onClick={() => selectedJob && runAction(async () => setMatches(await api.matchJob(session, selectedJob.job_id, STRONG_DEFAULT, PARTIAL_DEFAULT)), "Đã tìm ứng viên phù hợp.")}
          >
            Tìm ứng viên
            <Search size={16} />
          </button>
          <CandidateList matches={matches} />
        </Panel>
      </aside>
    </section>
  );
}

function TeacherWorkspace({ session }: { session: Session }) {
  const [sourceUrl, setSourceUrl] = useState("https://www.youtube.com/watch?v=0Va2dOLqUfM");
  const [courseTitle, setCourseTitle] = useState("Bài giảng mẫu");
  const [category, setCategory] = useState("Khoa học");
  const [sourceType, setSourceType] = useState("");
  const [report, setReport] = useState<TeacherRagReport | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function detectSource() {
    setError("");
    setNotice("");
    try {
      const result = await api.detectTeacherSource(session, sourceUrl);
      setSourceType(result.source_type);
      setNotice(result.source_type === "playlist" ? "Đã nhận diện playlist." : "Đã nhận diện video.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function runPipeline() {
    setError("");
    setNotice("");
    setRunning(true);
    try {
      const result = await api.runTeacherRag(session, {
        source_url: sourceUrl,
        course_title: courseTitle,
        category,
        languages: ["vi", "en"],
        chunk_size_words: 420,
        overlap_words: 100,
        sleep_seconds: 0,
      });
      setReport(result);
      setNotice("Đã tạo dữ liệu RAG.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="workspace-flow single">
      <Panel title="Tạo dữ liệu học tập" subtitle="Nhập video hoặc playlist để xuất bản chép lời sạch và các đoạn dữ liệu cho RAG.">
        <div className="form-grid">
          <label className="field-label">
            Đường dẫn YouTube
            <input className="text-input" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} />
          </label>
          <label className="field-label">
            Tên khóa học
            <input className="text-input" value={courseTitle} onChange={(event) => setCourseTitle(event.target.value)} />
          </label>
          <label className="field-label">
            Danh mục
            <input className="text-input" value={category} onChange={(event) => setCategory(event.target.value)} />
          </label>
        </div>
        <div className="button-row roomy">
          <button className="secondary-button" onClick={detectSource}>Kiểm tra nguồn</button>
          <button className="primary-button" disabled={running} onClick={runPipeline}>
            {running ? "Đang xử lý" : "Tạo dữ liệu"}
            <ArrowRight size={16} />
          </button>
        </div>
        <ErrorBanner message={error} />
        <Notice message={notice} />
        {sourceType && <InfoPill label="Loại nguồn" value={sourceType === "playlist" ? "Playlist" : "Video"} />}
        {report && (
          <div className="report-card">
            <strong>{report.course_title}</strong>
            <span>Đã tạo {report.chunks_created} đoạn dữ liệu. Báo cáo lưu tại: {report.report_output}</span>
          </div>
        )}
      </Panel>
    </section>
  );
}

function ProfilePreview({ student, onSave }: { student: StudentProfile; onSave: () => void }) {
  const skills = Object.entries(student.skills || {}).slice(0, 6);
  return (
    <div className="preview-card">
      <div className="preview-header">
        <div>
          <p className="eyebrow">Hồ sơ đọc được</p>
          <h3>{student.name}</h3>
        </div>
        <button className="primary-button" onClick={onSave}>
          Lưu hồ sơ
          <CheckCircle2 size={16} />
        </button>
      </div>
      <div className="skill-cloud">
        {skills.map(([name, skill]) => (
          <span key={name}>
            {name} · {Math.round(skill.score)}/10
            {skill.self_rating && <em>{formatSelfRating(skill.self_rating)}</em>}
          </span>
        ))}
      </div>
    </div>
  );
}

function JobPreview({ job, onSave }: { job: Job; onSave: () => void }) {
  const skills = Object.entries(job.skills || {}).slice(0, 6);
  return (
    <div className="preview-card">
      <div className="preview-header">
        <div>
          <p className="eyebrow">JD đọc được</p>
          <h3>{job.title}</h3>
        </div>
        <button className="primary-button" onClick={onSave}>
          Lưu JD
          <CheckCircle2 size={16} />
        </button>
      </div>
      <div className="skill-cloud">
        {skills.map(([name, skill]) => (
          <span key={name}>{name} · yêu cầu {Math.round(skill.required_level)}/10</span>
        ))}
      </div>
    </div>
  );
}

function MatchHighlight({ match }: { match: StudentJobMatch }) {
  return (
    <div className="match-highlight">
      <span>Phù hợp nhất hiện tại</span>
      <strong>{match.job.title}</strong>
      <ScoreRing score={match.match.match_score} />
      <p>{match.match.explanation}</p>
    </div>
  );
}

function ReviewCard({ review }: { review: ReviewResult }) {
  return (
    <div className="review-card">
      <div className="preview-header">
        <div>
          <p className="eyebrow">Nhận xét CV</p>
          <h3>{review.job_title}</h3>
        </div>
        <ScoreRing score={review.match.match_score} />
      </div>
      <p>{review.overall_assessment}</p>
      <InsightBlock title="Nên bổ sung vào CV" items={review.missing_keywords.length ? review.missing_keywords : review.cv_improvements} />
      <InsightBlock title="Việc nên làm tiếp" items={review.priority_actions} />
    </div>
  );
}

function CandidateList({ matches }: { matches: MatchResult[] }) {
  if (!matches.length) return <EmptyState title="Chưa chạy so khớp" text="Mở một vị trí và bấm Tìm ứng viên để xem gợi ý." />;
  return (
    <div className="candidate-list">
      {matches.slice(0, 5).map((match) => (
        <div className="candidate-card" key={match.student_id}>
          <div>
            <strong>{match.student_name}</strong>
            <span>{match.matched_skills.slice(0, 4).join(", ") || "Chưa có kỹ năng khớp rõ"}</span>
          </div>
          <ScoreRing score={match.match_score} />
        </div>
      ))}
    </div>
  );
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
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

function HeroCard({ icon, title, text, action, onAction }: { icon: ReactNode; title: string; text: string; action: string; onAction: () => void }) {
  return (
    <section className="hero-card">
      <div className="hero-icon">{icon}</div>
      <div>
        <p className="eyebrow">Gợi ý hôm nay</p>
        <h2>{title}</h2>
        <p>{text}</p>
      </div>
      <button className="primary-button" onClick={onAction}>
        {action}
        <ArrowRight size={16} />
      </button>
    </section>
  );
}

function ActionCard({ step, title, text, done }: { step: string; title: string; text: string; done: boolean }) {
  return (
    <article className={done ? "action-card done" : "action-card"}>
      <span>{done ? <BadgeCheck size={17} /> : step}</span>
      <strong>{title}</strong>
      <p>{text}</p>
    </article>
  );
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty-state">
      <Sparkles size={20} />
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  );
}

function InsightBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="insight-block">
      <strong>{title}</strong>
      <ul>
        {items.slice(0, 4).map((item, index) => (
          <li key={`${item}-${index}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  return <div className="score-ring" aria-label={`Điểm phù hợp ${pct}%`}>{pct}%</div>;
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="info-pill">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PromiseCard({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return (
    <div className="promise-card">
      {icon}
      <strong>{title}</strong>
      <span>{text}</span>
    </div>
  );
}

function RoleButton({ active, icon, label, onClick }: { active: boolean; icon: ReactNode; label: string; onClick: () => void }) {
  return (
    <button className={active ? "role-button active" : "role-button"} onClick={onClick}>
      {icon}
      {label}
    </button>
  );
}

function Brand({ compact }: { compact: boolean }) {
  return (
    <div className={compact ? "brand compact" : "brand"}>
      <div className="brand-mark">C</div>
      <div>
        <strong>Corhort</strong>
        <span>Kết nối năng lực với cơ hội</span>
      </div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return message ? <div className="error-banner">{message}</div> : null;
}

function Notice({ message }: { message: string }) {
  return message ? <div className="notice-banner">{message}</div> : null;
}

function formatSelfRating(rating: { value: number; scale: number; normalized_score: number; source: string }) {
  if (rating.source === "percent") return `tự đánh giá ${Math.round(rating.value)}%`;
  if (rating.source === "level") return `tự đánh giá ${Math.round(rating.normalized_score)}/10`;
  return `tự đánh giá ${Number(rating.value).toFixed(Number.isInteger(rating.value) ? 0 : 1)}/${Math.round(rating.scale)}`;
}

function AiLoadingBanner({ message }: { message: string }) {
  if (!message) return null;
  return (
    <div className="ai-loading-banner" role="status" aria-live="polite">
      <div className="ai-loading-mark">
        <span>C</span>
        <LoaderCircle className="spin-icon" size={18} />
      </div>
      <div>
        <strong>{message}</strong>
        <span>Vui lòng chờ trong giây lát.</span>
      </div>
    </div>
  );
}

function headlineForRole(role: Role) {
  if (role === "student") return "Lộ trình ứng tuyển của bạn";
  if (role === "enterprise") return "Không gian tuyển dụng thông minh";
  return "Không gian dữ liệu học tập";
}

function workspaceTitle(role: Role) {
  if (role === "student") return "Cổng sinh viên";
  if (role === "enterprise") return "Không gian JD";
  return "Không gian RAG";
}

export default App;
