import { useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  BarChart3,
  BookOpenCheck,
  BriefcaseBusiness,
  Building2,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  FileSearch,
  FileText,
  Layers3,
  LayoutDashboard,
  LogOut,
  Menu,
  Search,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import { api } from "./api";
import { candidateMatches, jobs, studentJobMatches, students } from "./data";
import type { Job, Match, MatchingWeights, Role, Student } from "./types";

type Section = "overview" | "student-profile" | "cv-manager" | "job-matching" | "company-overview" | "jd-manager" | "candidate-matching";

type Session = {
  account: string;
  displayName: string;
  role: Role;
};

type WeightPreset = "balanced" | "skills_first" | "intern_friendly";
type ActiveWeightPreset = WeightPreset | "custom";

const roleLabels: Record<Role, string> = {
  student: "Học viên",
  company: "Doanh nghiệp",
  admin: "Quản trị",
};

const roleSections: Record<Role, Section[]> = {
  student: ["overview", "student-profile", "cv-manager", "job-matching"],
  company: ["overview", "company-overview", "jd-manager", "candidate-matching"],
  admin: ["overview", "student-profile", "cv-manager", "job-matching", "company-overview", "jd-manager", "candidate-matching"],
};

const sectionMeta: Record<Section, { label: string; icon: ReactNode }> = {
  overview: { label: "Tổng quan", icon: <LayoutDashboard size={18} /> },
  "student-profile": { label: "Hồ sơ học viên", icon: <UserRound size={18} /> },
  "cv-manager": { label: "CV", icon: <FileText size={18} /> },
  "job-matching": { label: "Ghép việc làm", icon: <FileSearch size={18} /> },
  "company-overview": { label: "Tổng quan công ty", icon: <Building2 size={18} /> },
  "jd-manager": { label: "Quản lý JD", icon: <ClipboardList size={18} /> },
  "candidate-matching": { label: "Ghép ứng viên", icon: <BriefcaseBusiness size={18} /> },
};

const flowIntro: Record<Role, { title: string; text: string; start: Section; steps: Section[] }> = {
  student: {
    title: "Luồng học viên",
    text: "Quản lý hồ sơ cá nhân, phân tích CV và xem việc làm phù hợp.",
    start: "student-profile",
    steps: ["student-profile", "cv-manager", "job-matching"],
  },
  company: {
    title: "Luồng doanh nghiệp",
    text: "Theo dõi công ty, quản lý JD và xếp hạng ứng viên.",
    start: "company-overview",
    steps: ["company-overview", "jd-manager", "candidate-matching"],
  },
  admin: {
    title: "Luồng quản trị demo",
    text: "Kiểm thử toàn bộ màn hình học viên và doanh nghiệp trong một phiên.",
    start: "overview",
    steps: ["student-profile", "cv-manager", "job-matching", "company-overview", "jd-manager", "candidate-matching"],
  },
};

const demoAccounts = [
  { account: "student_1", password: "1", displayName: "Nguyen Minh Anh", hint: "Học viên demo" },
  { account: "company_1", password: "1", displayName: "BlueLearn HR", hint: "Doanh nghiệp demo" },
  { account: "admin_1", password: "1", displayName: "Admin Demo", hint: "Quản trị demo" },
];

const weightPresets: Record<WeightPreset, { label: string; weights: MatchingWeights }> = {
  balanced: {
    label: "Cân bằng",
    weights: { skill_weight: 0.65, experience_weight: 0.2, education_weight: 0.15 },
  },
  skills_first: {
    label: "Ưu tiên kỹ năng",
    weights: { skill_weight: 0.85, experience_weight: 0.1, education_weight: 0.05 },
  },
  intern_friendly: {
    label: "Phù hợp thực tập",
    weights: { skill_weight: 0.6, experience_weight: 0.15, education_weight: 0.25 },
  },
};

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [activeSection, setActiveSection] = useState<Section>("overview");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  if (!session) {
    return <LoginScreen onLogin={(nextSession) => {
      setSession(nextSession);
      setActiveSection(flowIntro[nextSession.role].start);
    }} />;
  }

  const role = session.role;
  const visibleSections = roleSections[role];

  function logout() {
    setSession(null);
    setActiveSection("overview");
    setSidebarOpen(false);
  }

  function switchSection(section: Section) {
    setActiveSection(section);
    setSidebarOpen(false);
  }

  return (
    <div className="app-shell">
      <aside className={sidebarOpen ? "sidebar open" : "sidebar"}>
        <div className="sidebar-top">
          <Brand />
          <button className="icon-button mobile-only" aria-label="Đóng menu" onClick={() => setSidebarOpen(false)}>
            <X size={18} />
          </button>
        </div>

        <div className="flow-session">
          <span>Đang ở</span>
          <strong>{flowIntro[role].title}</strong>
          <p>{session.displayName} | {flowIntro[role].text}</p>
        </div>

        <nav className="nav-list" aria-label="Điều hướng">
          {visibleSections.map((section) => (
            <button
              key={section}
              className={activeSection === section ? "nav-item active" : "nav-item"}
              onClick={() => switchSection(section)}
            >
              {sectionMeta[section].icon}
              <span>{sectionMeta[section].label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-card">
          <span>Giao diện sẵn sàng triển khai</span>
          <strong>Giao diện hướng nghiệp</strong>
          <p>Mock data đầy đủ để demo trước khi nối FastAPI.</p>
        </div>

        <button className="ghost-button" onClick={logout}>
          <LogOut size={16} />
          Đăng xuất
        </button>
      </aside>

      <main className="main">
        <header className="topbar">
          <button className="icon-button mobile-only" aria-label="Mở menu" onClick={() => setSidebarOpen(true)}>
            <Menu size={20} />
          </button>
          <div>
            <p className="eyebrow">Cầu Nối Tài Năng</p>
            <h1>{sectionMeta[activeSection].label}</h1>
          </div>
          <div className="topbar-actions">
            <div className="search-box">
              <Search size={17} />
              <span>Tìm học viên, JD, kỹ năng</span>
            </div>
            <button className="primary-button">
              <Sparkles size={16} />
              Tạo demo
            </button>
          </div>
        </header>

        <FlowProgress role={role} activeSection={activeSection} onNavigate={switchSection} />
        <Dashboard session={session} section={activeSection} onNavigate={switchSection} />
      </main>
    </div>
  );
}

function LoginScreen({ onLogin }: { onLogin: (session: Session) => void }) {
  const [account, setAccount] = useState("student_1");
  const [password, setPassword] = useState("1");
  const [error, setError] = useState("");

  function submitLogin() {
    const found = demoAccounts.find((item) => item.account === account.trim() && item.password === password);
    if (!found) {
      setError("Tài khoản demo không đúng. Gợi ý: student_1 / 1, company_1 / 1, admin_1 / 1.");
      return;
    }
    setError("");
    onLogin({ account: found.account, displayName: found.displayName, role: roleFromAccount(found.account) });
  }

  function fillDemo(nextAccount: string) {
    const found = demoAccounts.find((item) => item.account === nextAccount);
    if (!found) return;
    setAccount(found.account);
    setPassword(found.password);
    setError("");
  }

  return (
    <main className="login-page">
      <section className="login-hero">
        <Brand />
        <div>
          <p className="eyebrow">Cổng đăng nhập demo</p>
          <h1>Cầu Nối Tài Năng</h1>
          <p>
            Đăng nhập bằng tài khoản demo, hệ thống sẽ tự nhận vai trò và đưa bạn thẳng vào luồng phù hợp.
          </p>
        </div>
        <div className="login-proof-grid">
          <div>
            <strong>7</strong>
            <span>màn hình flow</span>
          </div>
          <div>
            <strong>3</strong>
            <span>vai trò demo</span>
          </div>
          <div>
            <strong>100%</strong>
            <span>mock UI offline</span>
          </div>
        </div>
      </section>

      <section className="login-card">
        <div className="login-card-heading">
          <p className="eyebrow">Đăng nhập</p>
          <h2>Vào hệ thống</h2>
        </div>
        <label className="field-label">
          Tài khoản
          <input className="text-input" value={account} onChange={(event) => setAccount(event.target.value)} />
        </label>
        <label className="field-label">
          Mật khẩu
          <input className="text-input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter") submitLogin();
          }} />
        </label>
        {error && <div className="login-error">{error}</div>}
        <button className="primary-button full-width" onClick={submitLogin}>
          Đăng nhập
          <ChevronRight size={16} />
        </button>
        <div className="demo-account-list">
          <span>Tài khoản mẫu</span>
          {demoAccounts.map((item) => (
            <button key={item.account} onClick={() => fillDemo(item.account)}>
              <strong>{item.account}</strong>
              <small>{item.hint}</small>
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}

function FlowProgress({ role, activeSection, onNavigate }: { role: Role; activeSection: Section; onNavigate: (section: Section) => void }) {
  return (
    <section className="flow-progress" aria-label="Tiến trình phân luồng">
      <div className="flow-progress-title">
        <Layers3 size={18} />
        <strong>{roleLabels[role]}</strong>
      </div>
      <div className="flow-progress-steps">
        {flowIntro[role].steps.map((step, index) => (
          <button key={step} className={activeSection === step ? "flow-progress-step active" : "flow-progress-step"} onClick={() => onNavigate(step)}>
            <span>{index + 1}</span>
            {sectionMeta[step].label}
          </button>
        ))}
      </div>
    </section>
  );
}

function Dashboard({ session, section, onNavigate }: { session: Session; section: Section; onNavigate: (section: Section) => void }) {
  const role = session.role;

  if (section === "overview") return <Overview role={role} onNavigate={onNavigate} />;
  if (section === "student-profile") return <StudentProfile session={session} />;
  if (section === "cv-manager") return <CvManager />;
  if (section === "job-matching") return <JobMatching />;
  if (section === "company-overview") return <CompanyOverview />;
  if (section === "jd-manager") return <JdManager />;
  return <CandidateMatching />;
}

function Overview({ role, onNavigate }: { role: Role; onNavigate: (section: Section) => void }) {
  const openJobs = jobs.filter((job) => job.status === "open").length;
  const avgMatch = Math.round(studentJobMatches.reduce((sum, item) => sum + item.score, 0) / studentJobMatches.length);
  const showStudentJourney = role === "student" || role === "admin";
  const showCompanyJourney = role === "company" || role === "admin";

  return (
    <div className="page-stack">
      <section className="hero-band">
        <div className="hero-copy">
          <p className="eyebrow">Không gian hướng nghiệp thông minh</p>
          <h2>{role === "company" ? "Tuyển đúng ứng viên từ hồ sơ năng lực có giải thích." : "Biến CV thành lộ trình học tập và ứng tuyển rõ ràng."}</h2>
          <p>
            Giao diện này được chuyển ý tưởng từ phòng thử nghiệm luồng: hồ sơ học viên, quản lý CV, quản lý JD và ghép hai chiều.
          </p>
          <div className="hero-actions">
            <button className="primary-button" onClick={() => onNavigate(role === "company" ? "candidate-matching" : "job-matching")}>
              Mở ghép
              <ChevronRight size={16} />
            </button>
            <button className="secondary-button" onClick={() => onNavigate(role === "company" ? "jd-manager" : "cv-manager")}>
              {role === "company" ? "Quản lý JD" : "Quản lý CV"}
            </button>
          </div>
        </div>
        <div className="learning-visual" aria-hidden="true">
          <div className="visual-card card-a">
            <BookOpenCheck size={22} />
            <strong>Bộ đọc CV</strong>
            <span>Kỹ năng + minh chứng</span>
          </div>
          <div className="visual-card card-b">
            <BarChart3 size={22} />
            <strong>Điểm phù hợp</strong>
            <span>{avgMatch}% trung bình</span>
          </div>
          <div className="visual-card card-c">
            <BriefcaseBusiness size={22} />
            <strong>{openJobs} JD đang mở</strong>
            <span>Ghép theo quy tắc</span>
          </div>
        </div>
      </section>

      <section className="metric-grid">
        <MetricCard label="Học viên demo" value={String(students.length)} detail="Có hồ sơ kỹ năng, học vấn, kinh nghiệm" />
        <MetricCard label="JD đang mở" value={String(openJobs)} detail="Sẵn sàng ghép với ứng viên" />
        <MetricCard label="Điểm phù hợp cao nhất" value="91%" detail="Thực tập sinh Frontend - Nền tảng giáo dục" />
        <MetricCard label="Luồng chính" value="7" detail="Tương ứng các màn hình nghiệp vụ" />
      </section>

      <section className={role === "admin" ? "two-column" : "page-stack"}>
        {showStudentJourney && (
          <Panel title="Lộ trình học viên" subtitle="Từ CV đến quyết định ứng tuyển.">
            <FlowSteps
              items={[
                ["Phân tích CV", "Trích xuất kỹ năng, kinh nghiệm, học vấn."],
                ["Hồ sơ", "Chọn điểm nổi bật hiển thị trong hồ sơ."],
                ["Ghép việc làm", "Xếp hạng công việc và chỉ ra khoảng thiếu."],
              ]}
            />
          </Panel>
        )}
        {showCompanyJourney && (
          <Panel title="Lộ trình doanh nghiệp" subtitle="Từ JD đến shortlist ứng viên.">
            <FlowSteps
              items={[
                ["Overview", "Theo dõi JD mở, đóng, tổng số vị trí."],
                ["Quản lý JD", "Cập nhật trạng thái và kiểm tra nội dung JD."],
                ["Ghép ứng viên", "Xếp hạng ứng viên theo quy tắc ưu tiên kỹ năng."],
              ]}
            />
          </Panel>
        )}
      </section>
    </div>
  );
}

function StudentProfile({ session }: { session: Session }) {
  const canBrowseProfiles = session.role === "admin";
  const ownStudent = students.find((item) => item.id === session.account) ?? students[0];
  const [selectedId, setSelectedId] = useState(ownStudent.id);
  const student = canBrowseProfiles
    ? students.find((item) => item.id === selectedId) ?? ownStudent
    : ownStudent;

  return (
    <div className="page-stack">
      <section className="profile-header">
        <div>
          <p className="eyebrow">Mã học viên: {student.id}</p>
          <h2>{student.name}</h2>
          <p>{student.target}</p>
        </div>
        {canBrowseProfiles && (
          <select className="select-input" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
            {students.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        )}
      </section>

      <section className="three-column">
        <HighlightCard title="Kinh nghiệm nổi bật" value={student.experiences[0].title} detail={`${student.experiences[0].company} | ${student.experiences[0].score}/10`} />
        <HighlightCard title="Học vấn nổi bật" value={student.education[0].degree} detail={`${student.education[0].institution} | ${student.education[0].score}/10`} />
        <HighlightCard title="Kỹ năng nổi bật" value={student.skills[0].name} detail={`${student.skills[0].score}/10 độ tin cậy ${Math.round(student.skills[0].confidence * 100)}%`} />
      </section>

      <section className="two-column wide-left">
        <Panel title="Thông tin cá nhân" subtitle="Phần hiển thị cho học viên sau khi lưu CV chính.">
          <InfoGrid
            rows={[
              ["Email", student.email],
              ["Điện thoại", student.phone],
              ["Địa điểm", student.location],
              ["Trường", student.university],
              ["Ngành học", student.major],
              ["Năm tốt nghiệp", student.graduationYear],
            ]}
          />
          <div className="bio-box">{student.bio}</div>
        </Panel>
        <Panel title="Hồ sơ kỹ năng" subtitle="Điểm dựa trên CV chính và bằng chứng trích xuất.">
          <SkillList skills={student.skills} />
        </Panel>
      </section>

      <Panel title="Chi tiết CV" subtitle="Kinh nghiệm và học vấn được trình bày dạng có thể scan nhanh.">
        <DataTable
          headers={["Loại", "Tiêu đề", "Tổ chức", "Điểm", "Tóm tắt"]}
          rows={[
            ...student.experiences.map((item) => ["Kinh nghiệm", item.title, item.company, `${item.score}/10`, item.summary]),
            ...student.education.map((item) => ["Học vấn", item.degree, item.institution, `${item.score}/10`, item.year]),
          ]}
        />
      </Panel>
    </div>
  );
}

function CvManager() {
  const [cvText, setCvText] = useState("Nguyen Minh Anh\nThực tập sinh Frontend\nDashboard React, tìm kiếm bằng JavaScript, bố cục CSS responsive, phối hợp review sprint.");
  const parsedSkills = useMemo(() => ["React", "JavaScript", "CSS", "Giao tiếp"].filter((skill) => cvText.toLowerCase().includes(skill.toLowerCase())), [cvText]);

  return (
    <div className="two-column wide-left">
      <Panel title="Phân tích CV mới" subtitle="Dán CV, xem bản xem trước có cấu trúc rồi lưu làm CV chính.">
        <label className="field-label">
          Vị trí trong CV
          <input className="text-input" defaultValue="Thực tập sinh Frontend" />
        </label>
        <label className="field-label">
          Nội dung CV
          <textarea className="text-area" value={cvText} onChange={(event) => setCvText(event.target.value)} />
        </label>
        <div className="button-row">
          <button className="primary-button">
            <Sparkles size={16} />
            Phân tích CV
          </button>
          <button className="secondary-button">Lưu làm CV chính</button>
        </div>
      </Panel>

      <Panel title="Bản xem trước CV đã phân tích" subtitle="Mô phỏng bản xem trước trước khi lưu vào hồ sơ học viên.">
        <div className="preview-block">
          <p className="eyebrow">Kỹ năng nhận diện</p>
          <div className="tag-cloud">
            {(parsedSkills.length ? parsedSkills : ["React", "JavaScript", "CSS"]).map((skill) => (
              <span key={skill}>{skill}</span>
            ))}
          </div>
        </div>
        <SavedCvList />
      </Panel>
    </div>
  );
}

function JobMatching() {
  const [minScore, setMinScore] = useState(0);
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const visible = matches.filter((item) => item.score >= minScore);
  async function runMatch() {
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const result = await api.matchStudentJobs(students[0]);
      setMatches(result);
      setNotice(`Đã gọi API và nhận ${result.length} việc làm phù hợp.`);
    } catch (err) {
      setMatches(studentJobMatches);
      setError(`Chưa gọi được API backend (${(err as Error).message}). Đang hiển thị dữ liệu mẫu để kiểm tra giao diện.`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-stack">
      <Panel title="Bộ điều khiển ghép việc" subtitle="Chọn chế độ ghép và lọc kết quả hiển thị.">
        <div className="control-grid">
          <label className="field-label">
            Chế độ ghép
            <select className="select-input" defaultValue="balanced">
              <option value="balanced">Cân bằng</option>
              <option value="strict">Khắt khe</option>
              <option value="intern_friendly">Phù hợp thực tập</option>
            </select>
          </label>
          <label className="field-label">
            Điểm tối thiểu: {minScore}
            <input type="range" min="0" max="100" step="5" value={minScore} onChange={(event) => setMinScore(Number(event.target.value))} />
          </label>
          <button className="primary-button" onClick={runMatch} disabled={loading}>
            <Search size={16} />
            {loading ? "Đang ghép..." : "Ghép tất cả việc làm"}
          </button>
        </div>
      </Panel>

      <RunFeedback notice={notice} error={error} idle={!matches.length && !loading} idleText="Bấm Ghép tất cả việc làm để gọi API ghép việc." />
      <MatchGrid matches={visible} emptyTitle="Không có việc làm nào vượt ngưỡng lọc." />
    </div>
  );
}

function CompanyOverview() {
  const [managedJobs] = useState(jobs);
  const openJobs = managedJobs.filter((job) => job.status === "open");
  const closedJobs = managedJobs.filter((job) => job.status === "closed");

  return (
    <div className="page-stack">
      <section className="metric-grid">
        <MetricCard label="Tổng số JD" value={String(managedJobs.length)} detail="Tất cả vị trí trong bộ dữ liệu mẫu" />
        <MetricCard label="Đang mở" value={String(openJobs.length)} detail="Đang nhận ứng viên" />
        <MetricCard label="Đã đóng" value={String(closedJobs.length)} detail="Đã đóng hoặc tạm ngưng" />
        <MetricCard label="Tỉ lệ đang mở" value={`${Math.round((openJobs.length / managedJobs.length) * 100)}%`} detail="Tỉ lệ vị trí đang mở" />
      </section>
      <Panel title="JD gần đây" subtitle="Tóm tắt các JD gần nhất theo công ty.">
        <DataTable
          headers={["JD", "Công ty", "Trạng thái", "Địa điểm", "Kỹ năng bắt buộc"]}
          rows={managedJobs.map((job) => [job.title, job.companyName, formatStatus(job.status), job.location, job.requiredSkills.join(", ")])}
        />
      </Panel>
    </div>
  );
}

function JdManager() {
  const [managedJobs, setManagedJobs] = useState(jobs);
  const [selectedId, setSelectedId] = useState(jobs[0].id);
  const [jdText, setJdText] = useState("Thực tập sinh Frontend - Nền tảng giáo dục\nKỹ năng bắt buộc: React, JavaScript, CSS, Giao tiếp\nKỹ năng ưu tiên: TypeScript, Figma\nLinh hoạt, HCMC. Thực tập.");
  const [draftJob, setDraftJob] = useState<Job | null>(null);
  const [parseLoading, setParseLoading] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [parseNotice, setParseNotice] = useState("");
  const [parseError, setParseError] = useState("");
  const job = managedJobs.find((item) => item.id === selectedId) ?? managedJobs[0];
  const openCount = managedJobs.filter((item) => item.status === "open").length;
  const closedCount = managedJobs.filter((item) => item.status === "closed").length;

  function toggleSelectedJob() {
    setManagedJobs((currentJobs) =>
      currentJobs.map((item) =>
        item.id === job.id
          ? {
              ...item,
              status: item.status === "open" ? "closed" : "open",
            }
          : item,
      ),
    );
  }

  async function parseNewJd() {
    setParseLoading(true);
    setParseNotice("");
    setParseError("");
    try {
      const parsed = await api.parseJob(jdText, "company_demo");
      setDraftJob(parsed);
      setParseNotice("Đã parse JD bằng API backend.");
    } catch (err) {
      const parsed = parseJobLocally(jdText);
      setDraftJob(parsed);
      setParseError(`Chưa gọi được API parse JD (${(err as Error).message}). Đang dùng parser demo local.`);
    } finally {
      setParseLoading(false);
    }
  }

  async function saveDraftJob() {
    if (!draftJob) return;
    setSaveLoading(true);
    setParseNotice("");
    setParseError("");
    try {
      const saved = await api.saveJob(draftJob);
      setManagedJobs((currentJobs) => upsertJob(currentJobs, saved));
      setSelectedId(saved.id);
      setDraftJob(null);
      setParseNotice("Đã lưu JD bằng API backend và thêm vào danh sách.");
    } catch (err) {
      setManagedJobs((currentJobs) => upsertJob(currentJobs, draftJob));
      setSelectedId(draftJob.id);
      setDraftJob(null);
      setParseError(`Chưa lưu được qua API (${(err as Error).message}). Đã thêm JD vào danh sách local để demo.`);
    } finally {
      setSaveLoading(false);
    }
  }

  return (
    <div className="page-stack">
      <section className="metric-grid compact-metrics">
        <MetricCard label="JD đang mở" value={String(openCount)} detail="Đang hiển thị cho học viên" />
        <MetricCard label="JD đã đóng" value={String(closedCount)} detail="Tạm ẩn khỏi ghép việc" />
        <MetricCard label="Đang chọn" value={job.status === "open" ? "Bật" : "Tắt"} detail={job.title} />
      </section>

      <Panel title="Phân tích JD mới" subtitle="Dán JD thô, hệ thống sẽ trích xuất tiêu đề, kỹ năng bắt buộc và kỹ năng ưu tiên.">
        <label className="field-label">
          Nội dung JD
          <textarea className="text-area jd-text-area" value={jdText} onChange={(event) => setJdText(event.target.value)} />
        </label>
        <div className="button-row">
          <button className="primary-button" onClick={parseNewJd} disabled={parseLoading || !jdText.trim()}>
            <Sparkles size={16} />
            {parseLoading ? "Đang phân tích..." : "Phân tích JD"}
          </button>
          {draftJob && (
            <button className="secondary-button" onClick={saveDraftJob} disabled={saveLoading}>
              <CheckCircle2 size={16} />
              {saveLoading ? "Đang lưu..." : "Lưu JD"}
            </button>
          )}
        </div>
        <RunFeedback notice={parseNotice} error={parseError} idle={!draftJob && !parseLoading && !parseNotice && !parseError} idleText="Phân tích JD mới để xem bản xem trước trước khi lưu." />
        {draftJob && <JdPreview job={draftJob} />}
      </Panel>

      <Panel title="Quản lý JD" subtitle="Chọn JD, xem trạng thái và cập nhật mô phỏng.">
        <label className="field-label">
          Chọn JD
          <select className="select-input" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
            {managedJobs.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title} - {formatStatus(item.status)}
              </option>
            ))}
          </select>
        </label>
        <div className="jd-summary">
          <h3>{job.title}</h3>
          <StatusBadge status={job.status} />
          <p>{job.companyName} | {job.location} | {job.employmentType}</p>
          <div className="jd-toggle-line">
            <div>
              <strong>{job.status === "open" ? "JD đang bật" : "JD đang tắt"}</strong>
              <span>{job.status === "open" ? "Học viên có thể nhìn thấy và được ghép với JD này." : "JD bị ẩn khỏi luồng ghép việc của học viên."}</span>
            </div>
            <button className={job.status === "open" ? "danger-button" : "primary-button"} onClick={toggleSelectedJob}>
              {job.status === "open" ? "Tắt JD" : "Mở JD"}
            </button>
          </div>
        </div>
        <div className="button-row">
          <button className="secondary-button" onClick={toggleSelectedJob}>
            {job.status === "open" ? "Chuyển sang đã đóng" : "Chuyển sang đang mở"}
          </button>
          <button className="danger-button">Xóa JD</button>
        </div>
      </Panel>
    </div>
  );
}

function parseJobLocally(rawText: string): Job {
  const knownSkills = ["React", "JavaScript", "TypeScript", "CSS", "Python", "FastAPI", "SQL", "Power BI", "Giao tiếp", "Figma", "Testing", "Docker"];
  const foundSkills = knownSkills.filter((skill) => rawText.toLowerCase().includes(skill.toLowerCase()));
  const title = rawText.split(/\r?\n/).find((line) => line.trim())?.trim().slice(0, 80) || "JD chưa đặt tên";
  const requiredSkills = foundSkills.slice(0, 5);
  const optionalSkills = foundSkills.slice(5);
  return {
    id: `job_local_${Date.now()}`,
    companyId: "company_demo",
    companyName: "Công ty demo",
    title,
    status: "closed",
    location: rawText.toLowerCase().includes("remote") ? "Từ xa" : "Linh hoạt",
    employmentType: rawText.toLowerCase().includes("full") ? "Toàn thời gian" : "Thực tập",
    requiredSkills: requiredSkills.length ? requiredSkills : ["Giao tiếp", "Tài liệu hóa"],
    optionalSkills,
    salary: "Thỏa thuận",
  };
}

function upsertJob(currentJobs: Job[], nextJob: Job): Job[] {
  const exists = currentJobs.some((item) => item.id === nextJob.id);
  if (exists) return currentJobs.map((item) => (item.id === nextJob.id ? nextJob : item));
  return [nextJob, ...currentJobs];
}

function JdPreview({ job }: { job: Job }) {
  return (
    <div className="jd-preview">
      <div className="jd-preview-head">
        <div>
          <p className="eyebrow">Xem trước JD</p>
          <h3>{job.title}</h3>
          <span>{job.companyName} | {job.location} | {job.employmentType}</span>
        </div>
        <StatusBadge status={job.status} />
      </div>
      <Insight title="Kỹ năng bắt buộc" items={job.requiredSkills} />
      <Insight title="Kỹ năng ưu tiên" items={job.optionalSkills.length ? job.optionalSkills : ["Chưa có kỹ năng ưu tiên"]} />
    </div>
  );
}

function CandidateMatching() {
  const [weights, setWeights] = useState<MatchingWeights>(weightPresets.balanced.weights);
  const [activePreset, setActivePreset] = useState<ActiveWeightPreset>("balanced");
  const [minScore, setMinScore] = useState(0);
  const [selectedJobId, setSelectedJobId] = useState(jobs[0].id);
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const visible = matches.filter((item) => item.score >= minScore);
  const selectedJob = jobs.find((job) => job.id === selectedJobId) ?? jobs[0];
  const activeTotal = Math.round(
    (weights.skill_weight + weights.experience_weight + weights.education_weight) * 100,
  );

  function applyPreset(preset: WeightPreset) {
    setActivePreset(preset);
    setWeights(weightPresets[preset].weights);
  }

  function updateWeight(key: keyof MatchingWeights, value: number) {
    setActivePreset("custom");
    setWeights((current) => ({ ...current, [key]: value / 100 }));
  }

  async function runMatch() {
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const result = await api.matchCandidates(selectedJob, weights);
      setMatches(result);
      setNotice(`Đã gọi API và nhận ${result.length} ứng viên phù hợp.`);
    } catch (err) {
      setMatches(candidateMatches);
      setError(`Chưa gọi được API backend (${(err as Error).message}). Đang hiển thị dữ liệu mẫu để kiểm tra giao diện.`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-stack">
      <Panel title="Ghép ứng viên" subtitle="Xếp hạng ứng viên bằng quy tắc ưu tiên kỹ năng.">
        <div className="control-grid">
          <label className="field-label">
            Chọn JD
            <select className="select-input" value={selectedJobId} onChange={(event) => setSelectedJobId(event.target.value)}>
              {jobs.map((job) => (
                <option key={job.id} value={job.id}>
                  {job.title}
                </option>
              ))}
            </select>
          </label>
          <label className="field-label">
            Điểm tối thiểu: {minScore}
            <input type="range" min="0" max="100" step="5" value={minScore} onChange={(event) => setMinScore(Number(event.target.value))} />
          </label>
          <button className="primary-button" onClick={runMatch} disabled={loading}>
            <Search size={16} />
            {loading ? "Đang xếp hạng..." : "Xếp hạng tất cả ứng viên"}
          </button>
        </div>
        <div className="weight-panel">
          <div className="preset-row" aria-label="Bộ trọng số ghép">
            {(Object.keys(weightPresets) as WeightPreset[]).map((preset) => (
              <button
                key={preset}
                className={activePreset === preset ? "preset-pill active" : "preset-pill"}
                onClick={() => applyPreset(preset)}
              >
                {weightPresets[preset].label}
              </button>
            ))}
          </div>
          <div className="weight-grid">
            <WeightSlider
              label="Kỹ năng"
              value={Math.round(weights.skill_weight * 100)}
              onChange={(value) => updateWeight("skill_weight", value)}
            />
            <WeightSlider
              label="Kinh nghiệm"
              value={Math.round(weights.experience_weight * 100)}
              onChange={(value) => updateWeight("experience_weight", value)}
            />
            <WeightSlider
              label="Học vấn"
              value={Math.round(weights.education_weight * 100)}
              onChange={(value) => updateWeight("education_weight", value)}
            />
          </div>
          <div className="weight-total">
            Tổng trọng số {activeTotal}%. Backend sẽ chuẩn hóa trọng số đang dùng.
          </div>
        </div>
      </Panel>

      <RunFeedback notice={notice} error={error} idle={!matches.length && !loading} idleText="Bấm Xếp hạng tất cả ứng viên để gọi API ghép ứng viên." />
      <MatchGrid matches={visible} emptyTitle="Không có ứng viên nào vượt ngưỡng lọc." />
    </div>
  );
}

function WeightSlider({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className={value === 0 ? "weight-slider disabled" : "weight-slider"}>
      <span>
        {label}
        <strong>{value === 0 ? "Tắt" : `${value}%`}</strong>
      </span>
      <input
        type="range"
        min="0"
        max="100"
        step="5"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function RunFeedback({ notice, error, idle, idleText }: { notice: string; error: string; idle: boolean; idleText: string }) {
  if (error) return <div className="feedback-banner warning">{error}</div>;
  if (notice) return <div className="feedback-banner success">{notice}</div>;
  if (idle) return <div className="feedback-banner neutral">{idleText}</div>;
  return null;
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  );
}

function HighlightCard({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <article className="highlight-card">
      <span>{title}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  );
}

function SkillList({ skills }: { skills: Student["skills"] }) {
  return (
    <div className="skill-list">
      {skills.map((skill) => (
        <div className="skill-row" key={skill.name}>
          <div>
            <strong>{skill.name}</strong>
            <span>{skill.evidence}</span>
          </div>
          <div className="score-chip">{skill.score.toFixed(1)}</div>
        </div>
      ))}
    </div>
  );
}

function MatchGrid({ matches, emptyTitle }: { matches: Match[]; emptyTitle: string }) {
  if (!matches.length) {
    return (
      <div className="empty-state">
        <Sparkles size={22} />
        <strong>{emptyTitle}</strong>
        <p>Hạ bộ lọc hoặc chọn chế độ khác để xem thêm kết quả.</p>
      </div>
    );
  }

  return (
    <section className="match-grid">
      {matches.map((match) => (
        <article className="match-card" key={match.id}>
          <div className="match-card-top">
            <div>
              <p className="eyebrow">{match.subtitle}</p>
              <h3>{match.title}</h3>
            </div>
            <ScoreCircle score={match.score} />
          </div>
          <StatusBadge status={match.decision} />
          <Insight title="Điểm mạnh" items={match.strengths} />
          <Insight title="Khoảng thiếu" items={match.gaps} />
        </article>
      ))}
    </section>
  );
}

function FlowSteps({ items }: { items: Array<[string, string]> }) {
  return (
    <div className="flow-steps">
      {items.map(([title, detail], index) => (
        <div className="flow-step" key={title}>
          <span>{String(index + 1).padStart(2, "0")}</span>
          <div>
            <strong>{title}</strong>
            <p>{detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function InfoGrid({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div className="info-grid">
      {rows.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function SavedCvList() {
  return (
    <div className="saved-list">
      <div className="saved-item">
        <CheckCircle2 size={18} />
        <div>
          <strong>CV thực tập Frontend</strong>
          <span>CV chính | 2 kinh nghiệm | 4 kỹ năng nổi bật</span>
        </div>
      </div>
      <div className="saved-item">
        <FileText size={18} />
        <div>
          <strong>CV phần mềm tổng quát</strong>
          <span>Bản nháp | Sẵn sàng phân tích lại</span>
        </div>
      </div>
    </div>
  );
}

function DataTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row[0]}-${index}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${cell}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Insight({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="insight">
      <strong>{title}</strong>
      <div className="tag-cloud">
        {items.map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>
    </div>
  );
}

function ScoreCircle({ score }: { score: number }) {
  return (
    <div className="score-circle" style={{ "--score": `${score}%` } as CSSProperties}>
      {score}
    </div>
  );
}

function StatusBadge({ status }: { status: Job["status"] | Match["decision"] }) {
  return <span className={`status-badge ${String(status).toLowerCase()}`}>{formatStatus(status)}</span>;
}

function formatStatus(status: Job["status"] | Match["decision"]) {
  if (status === "open") return "Đang mở";
  if (status === "closed") return "Đã đóng";
  if (status === "Shortlist") return "Phù hợp cao";
  if (status === "Review") return "Cần xem thêm";
  if (status === "Gap") return "Còn thiếu";
  return status;
}

function Brand() {
  return (
    <div className="brand">
      <div className="brand-mark">NT</div>
      <div>
        <strong>Cầu Nối Tài Năng</strong>
        <span>Hồ sơ năng lực & ghép việc</span>
      </div>
    </div>
  );
}

function roleFromAccount(account: string): Role {
  if (account.startsWith("company_")) return "company";
  if (account.startsWith("admin_")) return "admin";
  return "student";
}

export default App;
