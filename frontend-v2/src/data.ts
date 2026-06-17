import type { Job, Match, Student } from "./types";

export const students: Student[] = [
  {
    id: "student_1",
    name: "Nguyen Minh Anh",
    target: "Thực tập sinh Frontend",
    email: "minhanh@edu.vn",
    phone: "0901 234 567",
    location: "TP. Hồ Chí Minh",
    university: "Trường Đại học Khoa học Tự nhiên",
    major: "Khoa học máy tính",
    graduationYear: "2027",
    bio: "Muốn phát triển sản phẩm học tập số, mạnh về React, tư duy giao diện và làm việc nhóm.",
    skills: [
      { name: "React", score: 8.6, confidence: 0.9, evidence: "Dashboard đồ án dùng React và TypeScript" },
      { name: "JavaScript", score: 8.2, confidence: 0.88, evidence: "Xây dựng tính năng lọc, tìm kiếm và biểu đồ" },
      { name: "Giao tiếp", score: 7.4, confidence: 0.82, evidence: "Thuyết trình sprint review hằng tuần" },
      { name: "Python", score: 6.8, confidence: 0.72, evidence: "API coursework với FastAPI" },
    ],
    experiences: [
      {
        title: "Trưởng nhóm dự án Frontend",
        company: "Phòng lab Capstone",
        duration: "2025 - 2026",
        score: 8.5,
        summary: "Thiết kế giao diện quản lý lớp học, phân rã component và review UI với nhóm 4 người.",
      },
      {
        title: "Trợ giảng",
        company: "Lớp nền tảng Web",
        duration: "2025",
        score: 7.6,
        summary: "Hỗ trợ sinh viên mới debug HTML, CSS và JavaScript căn bản.",
      },
    ],
    education: [
      { degree: "Cử nhân Khoa học máy tính", institution: "Trường Đại học Khoa học Tự nhiên", year: "2027", score: 8.1 },
    ],
  },
  {
    id: "student_2",
    name: "Tran Quoc Bao",
    target: "Thực tập sinh phân tích dữ liệu",
    email: "quocbao@edu.vn",
    phone: "0909 888 777",
    location: "Đà Nẵng",
    university: "Đại học Đà Nẵng",
    major: "Hệ thống thông tin",
    graduationYear: "2026",
    bio: "Tập trung phân tích dữ liệu giáo dục, trực quan hóa insight và xây pipeline dữ liệu nhỏ.",
    skills: [
      { name: "SQL", score: 8.8, confidence: 0.91, evidence: "Thiết kế kho dữ liệu cho đồ án học vụ" },
      { name: "Python", score: 8.1, confidence: 0.87, evidence: "Notebook phân tích retention sinh viên" },
      { name: "Power BI", score: 7.7, confidence: 0.81, evidence: "Dashboard enrollment theo ngành học" },
      { name: "Statistics", score: 7.2, confidence: 0.76, evidence: "Mô hình dự đoán rủi ro bỏ học" },
    ],
    experiences: [
      {
        title: "Tình nguyện viên dữ liệu",
        company: "Tổ chức giáo dục phi lợi nhuận",
        duration: "2025",
        score: 8,
        summary: "Làm sạch dữ liệu khảo sát và tạo báo cáo tiến độ học tập cho 300 học viên.",
      },
    ],
    education: [
      { degree: "Cử nhân Hệ thống thông tin", institution: "Đại học Đà Nẵng", year: "2026", score: 8.3 },
    ],
  },
];

export const jobs: Job[] = [
  {
    id: "job_fe_01",
    companyId: "company_1",
    companyName: "BlueLearn",
    title: "Thực tập sinh Frontend - Nền tảng giáo dục",
    status: "open",
    location: "Linh hoạt, TP.HCM",
    employmentType: "Thực tập",
    requiredSkills: ["React", "JavaScript", "CSS", "Giao tiếp"],
    optionalSkills: ["TypeScript", "Figma"],
    salary: "4 - 6M VND",
  },
  {
    id: "job_da_02",
    companyId: "company_2",
    companyName: "EduMetric",
    title: "Thực tập sinh phân tích dữ liệu",
    status: "open",
    location: "Từ xa",
    employmentType: "Thực tập",
    requiredSkills: ["SQL", "Python", "Statistics"],
    optionalSkills: ["Power BI", "Data Storytelling"],
    salary: "5 - 7M VND",
  },
  {
    id: "job_be_03",
    companyId: "company_1",
    companyName: "BlueLearn",
    title: "Lập trình viên Backend mới tốt nghiệp",
    status: "closed",
    location: "Hà Nội",
    employmentType: "Toàn thời gian",
    requiredSkills: ["Python", "FastAPI", "SQL"],
    optionalSkills: ["Docker", "Testing"],
    salary: "10 - 14M VND",
  },
];

export const studentJobMatches: Match[] = [
  {
    id: "job_fe_01",
    title: "Thực tập sinh Frontend - Nền tảng giáo dục",
    subtitle: "BlueLearn",
    score: 91,
    decision: "Shortlist",
    strengths: ["React mạnh", "Có kinh nghiệm dashboard", "Giao tiếp tốt"],
    gaps: ["Bổ sung TypeScript", "Thêm link sản phẩm đã triển khai"],
  },
  {
    id: "job_be_03",
    title: "Lập trình viên Backend mới tốt nghiệp",
    subtitle: "BlueLearn",
    score: 68,
    decision: "Review",
    strengths: ["Có nền Python", "Hiểu API căn bản"],
    gaps: ["Thiếu FastAPI production", "Chưa có testing evidence"],
  },
  {
    id: "job_da_02",
    title: "Thực tập sinh phân tích dữ liệu",
    subtitle: "EduMetric",
    score: 54,
    decision: "Gap",
    strengths: ["Có tư duy số liệu căn bản"],
    gaps: ["Thiếu SQL", "Thiếu dashboard BI"],
  },
];

export const candidateMatches: Match[] = [
  {
    id: "student_1",
    title: "Nguyen Minh Anh",
    subtitle: "Thực tập sinh Frontend",
    score: 91,
    decision: "Shortlist",
    strengths: ["React", "JavaScript", "Giao tiếp"],
    gaps: ["TypeScript cần rõ hơn"],
  },
  {
    id: "student_2",
    title: "Tran Quoc Bao",
    subtitle: "Thực tập sinh phân tích dữ liệu",
    score: 64,
    decision: "Review",
    strengths: ["Python", "Tư duy dữ liệu"],
    gaps: ["Thiếu React", "Không đúng hướng frontend"],
  },
];
