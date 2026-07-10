# DECK SPEC — 20 slide pitch "VinUni Career Platform"

> **Cách đọc file này:** mỗi slide có 5 phần — **Mục tiêu**, **Nội dung chữ** (đúng để hiển thị, tiếng Việt),
> **Trực quan hóa** (vẽ gì, bố trí ra sao), **Số liệu** (con số nổi bật), **Bố cục & màu**. Tất cả số liệu
> quy mô là **code-verified**. Ô `[ĐIỀN SỐ]` là chỗ bạn tự bổ sung (docs không có), **không được bịa**.
>
> **Design system chung áp cho MỌI slide** (chi tiết ở `03-BRAND-DESIGN-SYSTEM.md`): nền `#F8F7F1`, thẻ
> trắng `#ffffff` bo góc 14px viền 1px `#e5e5e5`; chữ Plus Jakarta Sans, số/metric dùng JetBrains Mono;
> khung monochrome (ink `#171717`), nhấn bằng palette data-viz (indigo `#6366f1`, teal `#14b8a6`, amber
> `#f59e0b`, rose `#f43f5e`, sky `#0ea5e9`, emerald `#10b981`, violet `#8b5cf6`, orange `#f97316`); **tối đa
> 1 panel gradient indigo→violet mỗi slide**. Mỗi slide có **kicker** (11px, uppercase, tracking rộng, xám)
> + **số slide** + **logo nhỏ VinUni** ở footer.

---

## Slide 01 — Bìa (Cover)

- **Mục tiêu:** Ấn tượng đầu, khẳng định tầm vóc "hệ điều hành tuyển dụng của VinUni".
- **Nội dung chữ:**
  - Logo **VinUni** (lớn, trên cùng — đây là slide có logo như bạn yêu cầu).
  - Tên sản phẩm: **VinUni Career Platform**
  - Tagline: *"Hệ điều hành tuyển dụng chính thức của Đại học VinUni — AI-first, dành riêng cho hệ sinh thái VinUni."*
  - Dòng phụ: *"Một nền tảng · Bốn bề mặt vận hành · Toàn bộ vòng đời sự nghiệp"*
  - Chân slide: `[TÊN TEAM]` · `[MÔN/CUỘC THI]` · Tháng 7, 2026
- **Trực quan hóa:** Nền `#F8F7F1` sạch, nhiều khoảng trắng. Một dải "signature" mảnh chạy ngang phía dưới
  tiêu đề gồm 8 chấm tròn nhỏ theo đúng thứ tự palette data-viz (indigo→teal→amber→rose→sky→emerald→violet→
  orange) — ẩn dụ "đa persona, đa module". Góc phải-dưới: 1 khối gradient indigo→violet nhỏ (chấm nhấn duy nhất).
- **Số liệu:** không có (bìa giữ tối giản).
- **Bố cục & màu:** Canh trái, tiêu đề cỡ display 44–56px, tagline xám `#525252`. Không dùng ảnh nền ồn ào.

---

## Slide 02 — Thực trạng & Vấn đề

- **Mục tiêu:** Chỉ ra sự phân mảnh & nông của công cụ hướng nghiệp đại học hiện nay.
- **Nội dung chữ:** Tiêu đề: **"Hướng nghiệp đại học hôm nay: rời rạc và hời hợt"**. 3 cột nỗi đau:
  - 🎓 **Sinh viên:** Không có tín hiệu độ-phù-hợp cá nhân hóa; không có trợ lý AI viết/soi CV; không được
    luyện phỏng vấn; mù mờ về mức độ cạnh tranh & deadline.
  - 🏢 **Nhà tuyển dụng (Đối tác):** ATS doanh nghiệp (Greenhouse/Workday) thì nặng & đắt; job board thì
    ứng viên không được xác thực; **không có pipeline & talent pool gắn với campus**.
  - 🏛️ **Nhà trường:** Không có kiểm duyệt tập trung, không quản trị đối tác, không đo được **career
    outcome** (tỉ lệ có việc, lương, time-to-hire) để phục vụ kiểm định (ABET/AUN-QA).
  - Câu chốt: *"Job board đơn thuần **không** quản được cả vòng đời tuyển dụng."*
- **Trực quan hóa:** 3 thẻ trắng cạnh nhau, mỗi thẻ 1 icon lucide (`graduation-cap`, `building-2`,
  `landmark`), tiêu đề persona + 3 gạch đầu dòng ngắn. Bên dưới: 1 dải "công cụ rời rạc" — các chip xám mờ
  đứt gãy (CV Word · Google Form · Email · Excel · Job board) có dấu `×` để thể hiện sự phân mảnh.
- **Số liệu:** Có thể để 1 dòng insight định tính (không bịa số). Nếu muốn số, dùng `[ĐIỀN SỐ]`.
- **Bố cục & màu:** Khung monochrome; mỗi cột dùng 1 màu icon-chip khác nhau (indigo/teal/amber) để phân biệt,
  không tô nền đậm.

---

## Slide 03 — Thị trường & Vì sao là bây giờ

- **Mục tiêu:** Định vị thị trường mục tiêu + tính thời điểm (AI).
- **Nội dung chữ:** Tiêu đề: **"Xây riêng cho hệ sinh thái VinUni — không phải SaaS bán đại trà"**.
  - **Thị trường mục tiêu:** hệ sinh thái VinUni khép kín — Sinh viên, Cựu sinh viên (Alumni), Đối tác tuyển
    dụng, và Nhà trường. *(Docs nêu rõ: "xây dựng dành riêng cho hệ sinh thái VinUni, không phải sản phẩm bán
    cho trường khác.")*
  - **Vì sao campus-native thắng:** danh tính đã xác thực + dữ liệu vòng đời khép kín (học → CV → ứng tuyển →
    tuyển → outcome → phản hồi vào chương trình học).
  - **Vì sao là bây giờ:** làn sóng LLM khiến bóc tách CV, matching, trợ lý & luyện phỏng vấn *thực sự hữu
    ích* với chi phí thấp — điều 2–3 năm trước chưa khả thi.
  - **Quy mô thị trường (TAM/SAM):** `[ĐIỀN SỐ — docs không nêu]` (số SV/năm, số đối tác, v.v.).
- **Trực quan hóa:** Sơ đồ **vòng tròn đồng tâm** (bull's-eye): lõi = "VinUni", vòng 2 = 4 nhóm người dùng,
  vòng ngoài = "vòng lặp dữ liệu khép kín" với 4 mũi tên xoay (Học → Ứng tuyển → Tuyển dụng → Outcome). Bên
  phải: 3 chip "động lực thời điểm" (AI chi phí thấp · Nhu cầu kiểm định · Kỳ vọng SV số hóa).
- **Số liệu:** 4 ô KPI placeholder cho thị trường: SV/khóa `[ĐIỀN SỐ]`, Đối tác mục tiêu `[ĐIỀN SỐ]`, v.v.
- **Bố cục & màu:** Vòng tròn dùng gradient nhẹ theo palette; giữ 1 gradient hero nếu chưa dùng ở đâu khác.

---

## Slide 04 — Giải pháp: 1 hệ điều hành, 4 bề mặt *(SLIDE HERO)*

- **Mục tiêu:** Câu trả lời trung tâm — nói "cái này LÀ gì" trong 5 giây.
- **Nội dung chữ:** Tiêu đề: **"Một nền tảng AI-first, bốn bề mặt vận hành"**. 4 khối:
  1. **Public Marketplace** — khám phá việc/sự kiện/công ty công khai, salary explorer cho khách.
  2. **Student Command Center** — CV-first: tạo/soi CV, fit score, ứng tuyển, trợ lý AI, luyện phỏng vấn.
  3. **Partner Recruiting OS** — đăng JD, pipeline ATS đa vòng, talent pool, quảng cáo, analytics.
  4. **University Operations Center** — kiểm duyệt, quản trị đối tác, workflow automation, career outcomes.
  - Câu chốt: *"AI trợ giúp thật ở mọi bước — không phải demo trang trí."*
- **Trực quan hóa:** **Đây là slide hero** → dùng **1 panel gradient indigo→violet** làm nền cho dải tiêu đề
  hoặc cho 1 thẻ trung tâm "AI-first core", 4 bề mặt là 4 thẻ trắng vệ tinh xung quanh (bố cục 2×2 hoặc hình
  chữ thập). Mỗi bề mặt có icon lucide (`compass`, `layout-dashboard`, `briefcase`, `landmark`) + 3 từ khóa.
- **Số liệu:** 4 chip nhỏ: "1 nền tảng", "4 persona-surface", "AI ở mọi bước", "vi/en".
- **Bố cục & màu:** Đây là điểm nhấn thị giác mạnh nhất của deck — cho phép gradient hero lớn hơn slide khác.

---

## Slide 05 — Sản phẩm thực tế (Product Showcase)

- **Mục tiêu:** Cho hội đồng "thấy" sản phẩm thật, không chỉ nghe.
- **Nội dung chữ:** Tiêu đề: **"Sản phẩm đang chạy — v10 'Monochrome Shell + Data-viz Content'"**. Nhãn 4
  ảnh: *Student Dashboard · CV Studio (canvas A4) · Partner Pipeline (Kanban) · University Analytics*.
- **Trực quan hóa:** Gallery **4 mock-screen** vẽ theo đúng design system (nếu có screenshot thật → chèn từ
  `assets/`; nếu không → Claude Design **vẽ lại mock UI** dạng browser frame):
  - Mock 1: sidebar monochrome + hàng KPI tile + 1 line chart + 1 gradient hero tile.
  - Mock 2: khung canvas A4 giữa, thanh block bên trái, style inspector bên phải.
  - Mock 3: Kanban 4–5 cột (Applied → Screening → Interview → Offer) với thẻ ứng viên + vòng fit-score.
  - Mock 4: lưới biểu đồ (funnel placement + bar salary) — nhớ giữ nhãn `Được tài trợ` nếu có ô quảng cáo.
- **Số liệu:** Chú thích nhỏ: "120 màn hình · light + dark theme · colorblind-safe palette".
- **Bố cục & màu:** 4 khung trình duyệt bo góc, đổ bóng cực nhẹ; đây là nơi khoe palette data-viz nhiều màu.

---

## Slide 06 — Phân tích đối thủ

- **Mục tiêu:** Chứng minh khác biệt phòng thủ được (defensible).
- **Nội dung chữ:** Tiêu đề: **"Chúng tôi đứng ở đâu"**. Bảng định vị (theo PRD §1.2):
  - **vs LinkedIn** (mạng lưới toàn cầu) → *AI cá nhân hóa + talent đã xác thực + pipeline ATS*.
  - **vs TopCV / VietnamWorks** (job board VN quen thuộc) → *pipeline đa vòng + luyện phỏng vấn + mạng alumni*.
  - **vs Handshake** (campus Mỹ) → *AI matching sâu hơn + hệ quảng cáo + quản lý sự kiện*.
  - **vs Greenhouse / Workday** (ATS doanh nghiệp) → *nhẹ hơn, campus-native, AI-first*.
- **Trực quan hóa:** Chọn 1 trong 2:
  - (a) **Bảng so sánh** 5 cột (Đối thủ · Thế mạnh của họ · Khoảng trống · Lợi thế VinUni) — dòng VinUni tô
    nền `-soft` indigo để nổi.
  - (b) **Ma trận 2×2**: trục X = "Generic ↔ Campus-native", trục Y = "Job board ↔ Full lifecycle+AI". Đặt
    logo/tên các đối thủ; **VinUni ở góc phải-trên** (campus-native × full lifecycle+AI) với chấm indigo lớn.
  - → Khuyến nghị (b) trực quan hơn cho hội đồng.
- **Số liệu:** không cần số; nhấn vị trí.
- **Bố cục & màu:** Đối thủ dùng chấm xám trung tính, **chỉ VinUni** dùng màu indigo — nguyên tắc "màu = ý nghĩa".

---

## Slide 07 — Người dùng & Phân quyền (Personas + RBAC)

- **Mục tiêu:** Cho thấy chiều sâu mô hình người dùng & phân quyền linh hoạt (điểm mạnh kỹ thuật-sản phẩm).
- **Nội dung chữ:** Tiêu đề: **"Nhiều persona, một mô hình phân quyền cấu hình được"**.
  - **Persona:** Sinh viên VinUni · Alumni · External Student · General User · Guest · Partner Admin · Nhân sự
    Partner (vai trò tự đặt tên) · University Super Admin · Nhân sự Trường (vai trò tự đặt tên) · Platform
    Superadmin · Mentor.
  - **Multi-identity:** một tài khoản giữ nhiều danh tính (vd SV + nhân viên đối tác), đổi ở header.
  - **RBAC:** năng lực (analytics, xem CV/định danh, billing, pipeline, hành động AI, export…) là **capability
    cấp phát được** theo **user / role / department** ở **service layer** — *không hardcode theo tên vai trò*.
- **Trực quan hóa:** Cột trái = **bản đồ persona** gom theo 4 nhóm (Public/Student · Partner · University ·
  Platform) dạng các chip. Cột phải = **sơ đồ RBAC 3 tầng**: `Organization → Roles/Departments → Permissions`
  với ví dụ "Partner Admin cấp quyền 'xem định danh ứng viên' cho 'Technical Interviewer'". Thêm badge
  **multi-identity** (icon `repeat`/`users`).
- **Số liệu:** "11 loại persona · vai trò tự đặt tên · phân quyền theo department".
- **Bố cục & màu:** Mỗi nhóm persona 1 màu chip; sơ đồ RBAC monochrome + 1 nhánh highlight màu.

---

## Slide 08 — Hành trình Sinh viên (Flow 1)

- **Mục tiêu:** Trình bày luồng end-to-end đắt giá nhất: từ khách → ứng tuyển có dữ liệu.
- **Nội dung chữ:** Tiêu đề: **"Từ khách vãng lai đến ứng tuyển thông minh"**. 7 bước (đánh số để vẽ flow):
  1. **Khách** duyệt `/jobs`, mở job detail (chưa thấy fit cá nhân hóa).
  2. Bấm *Ứng tuyển/Lưu* → modal login **giữ nguyên ý định** → đăng ký (**chỉ email + mật khẩu**).
  3. **Onboarding**: chọn vai trò → seeker-type → xác minh sinh viên / hồ sơ.
  4. **CV**: upload CV cũ (*upload-and-name*, backend tự bóc tách) **hoặc** chọn template → mở editor canvas.
  5. Quay lại job detail (đã đăng nhập) → thấy **CV nên dùng · điểm fit 0–100 · bằng chứng khớp · lỗ hổng ·
     tín hiệu cạnh tranh**.
  6. Nộp → hệ thống tạo **CV snapshot bất biến**.
  7. `/student/applications` theo dõi trạng thái, timeline, tin nhắn, phỏng vấn.
- **Trực quan hóa:** **Flow ngang 7 node** (mỗi node là 1 pill bo tròn có icon lucide), mũi tên nối. Node 5 phóng
  to thành 1 thẻ "job-intelligence" mini (vòng fit-score + 2 chip gap). Dải "Guest → Auth → Student" đổi màu
  nền nhạt để thể hiện chuyển ngữ cảnh.
- **Số liệu:** Badge "CV snapshot bất biến khi nộp" · "Guest không thấy fit/cạnh tranh".
- **Bố cục & màu:** Node trung tính; node có AI (4,5) viền sky/indigo (info/AI). Tránh quá nhiều màu.

---

## Slide 09 — CV Studio

- **Mục tiêu:** Khoe tính năng chữ ký: trình soạn CV canvas kiểu Canva + AI sửa có kiểm soát.
- **Nội dung chữ:** Tiêu đề: **"CV Studio — soạn CV trực quan như Canva, an toàn nhờ AI có xác nhận"**.
  - **Template CV = editor canvas:** canvas A4 thật (cảnh báo tràn trang), **template marketplace** (trường
    duyệt), sửa chữ inline, kéo-thả khối, thay/crop ảnh, style inspector, **autosave (~5s)**, lịch sử phiên
    bản/khôi phục, xuất PDF cùng renderer với preview.
  - **Uploaded CV = upload-and-name, READ-ONLY:** upload → xác nhận file → đặt tên → xong; **không** bắt sửa
    tay field; xem đúng bản gốc, **không mở editor**.
  - **Sửa bằng ngôn ngữ tự nhiên = AI write action:** tạo **diff/patch có cấu trúc** trên canvas → SV **xác
    nhận** mới áp dụng → sinh **phiên bản mới + audit**. AI **không** tự bịa học vấn/GPA/giải thưởng/ngày tháng.
- **Trực quan hóa:** Ảnh mock editor: giữa là **trang A4**, trái là **palette block** (Experience/Education/
  Skills…), phải là **AI diff panel** đang hiện 1 thay đổi với nút *Chấp nhận / Sửa / Từ chối* (xanh emerald /
  xám / đỏ). Góc dưới: timeline phiên bản v1·v2·v3.
- **Số liệu:** "Autosave ~5s · versioning + audit · export = cùng renderer với PDF".
- **Bố cục & màu:** Diff panel là ngôi sao — dùng emerald (accept) / rose (reject) làm điểm màu.

---

## Slide 10 — CV Ingestion Cascade *(câu chuyện kỹ thuật chữ ký)*

- **Mục tiêu:** Chứng minh chiều sâu kỹ thuật + tư duy chi phí: pipeline bóc tách CV phân tầng.
- **Nội dung chữ:** Tiêu đề: **"Bóc tách CV phân tầng theo chi phí — local-first, gọi AI khi cần"**. Các tầng
  (chạy tầng rẻ trước, tầng sau chỉ khi tầng trước chưa đủ):
  1. **Cổng an ninh/định dạng** — kiểm MIME/magic-byte/dung lượng, checksum trùng, quét virus, phát hiện
     mã hóa/hỏng. **File rác/blank/không-phải-CV bị chặn ở đây — không model nào bị gọi lên rác.**
  2. **Native text (miễn phí)** — PyMuPDF4LLM/pdfplumber (PDF), python-docx (DOCX), TXT.
  3. **Layout-aware** — khi text lộn xộn/nhiều cột (docling tùy chọn).
  4. **Local OCR** — Tesseract `vie+eng`, chỉ khi trang thiếu text đọc được.
  5. **Vision-LLM rẻ (Gemini-class)** — cho ảnh & PDF scan nhiều cột; **được gửi ảnh tài liệu đã hạ độ phân
     giải** (chủ dự án duyệt), OCR + cấu trúc hóa trong 1 lần; PDF vẫn kèm native text để email/sđt/ngày chính
     xác. Phải trả `is_cv=false` với tài liệu không phải CV.
  6. **Text-LLM cấu trúc hóa (tùy chọn)** — chỉ nhận text/markdown, không nhận nhị phân.
  - **Đầu ra có cấu trúc:** mỗi công việc/bằng cấp = 1 entry (role · organization · timeframe · highlights,
    **không ký tự bullet trong data**); kỹ năng & ngôn ngữ có **level 0–100**. Là **nguồn chuẩn** cho CV–JD matching.
  - **Trạng thái lỗi rõ ràng, an toàn:** `BLANK_DOCUMENT`, `NOT_A_CV`, `LOW_QUALITY_SCAN`,
    `PASSWORD_PROTECTED_FILE`, `CORRUPT_FILE` — mỗi lỗi kèm hành động kế tiếp. **Không bao giờ bịa CV từ rác.**
- **Trực quan hóa:** **Sơ đồ pipeline dọc 6 tầng** hình bậc thang, mỗi tầng 1 thanh ngang có: tên tầng · nhãn
  chi phí (`Free`/`Rẻ`/`Rẻ+`) · mũi tên "chỉ chạy nếu tầng trên chưa đủ". Nhánh rẽ đỏ "reject" ở tầng 1. Bên
  phải: thẻ "Structured Output" minh họa 1 entry (role/org/timeframe/skills-bar).
- **Số liệu:** Chip nhãn chi phí tăng dần; badge "skills 0–100" · "feeds CV–JD matching".
- **Bố cục & màu:** Dùng gradient chi phí: tầng rẻ = emerald-soft, tầng đắt dần = amber→rose-soft. Nhánh reject
  = VinUni red `#c83538`.

---

## Slide 11 — CV–JD Matching & Competition Intelligence

- **Mục tiêu:** Cho thấy AI ra quyết định **tất định, giải thích được, tôn trọng riêng tư**.
- **Nội dung chữ:** Tiêu đề: **"Điểm khớp tất định, cạnh tranh minh bạch — không phải điểm ma thuật"**.
  - **Công thức fit (tất định, cùng input → cùng số nguyên):**
    `score = round(0.50·skills + 0.25·experience + 0.10·logistics + 0.15·quality)` → **0–100**.
  - **4 dải fit:** 85–100 mạnh · 70–84 tốt · 50–69 khả thi · <50 yếu.
  - **Evidence gaps:** `matched_skills` + `gaps` + cảnh báo CV cũ (>60 ngày).
  - **Lưu có version-stamp:** cache nhanh chỉ dùng khi `content_version == cv.version`; **sửa CV là re-score**.
  - **Learning cache:** phần *giải thích AI* (chỉ cho CV được đề xuất) cache theo `(cv_version, job_version)`;
    điểm tất định **miễn phí**, chỉ phần chữ AI mới tốn credit.
  - **Competition Intelligence:** tín hiệu sản phẩm dựa trên **input thật** (seats/hiring target, số lượng &
    vận tốc ứng tuyển, phân bố chất lượng ứng viên dạng bucket, **fit percentile của SV**, độ tươi deadline,
    source mix) — **không** lộ ứng viên khác/PII/điểm nội bộ/confidence; dữ liệu yếu thì **tắt mềm**, không bịa.
- **Trực quan hóa:** Trái = **thẻ score**: vòng tròn tiến độ 0–100 (donut) + 4 thanh band (skills 50% /
  experience 25% / logistics 10% / quality 15%) đúng trọng số + 2 chip "matched" (emerald) & "gap" (amber).
  Phải = **thẻ competition**: thanh percentile "Bạn nằm ở top X%", chip mức cạnh tranh (Thấp/Vừa/Cao), + dòng
  privacy "Không hiển thị ứng viên khác". Guest overlay mờ + khóa 🔒.
- **Số liệu:** "0–100 · 4 band · re-score khi CV đổi · điểm tất định miễn phí".
- **Bố cục & màu:** Donut theo màu band; competition dùng sky/indigo (info). Nhấn dòng privacy.

---

## Slide 12 — AI Career Assistant & Interview Simulator

- **Mục tiêu:** Khoe lớp AI-agent thật sự hữu ích, có kiểm soát.
- **Nội dung chữ:** Tiêu đề: **"Trợ lý AI biết làm việc — và luyện phỏng vấn bám JD/CV"**.
  - **AI Career Assistant (ReAct agent):** chat streaming, **25+ tool** đọc/ghi (tìm việc, soi CV, nộp hộ…),
    **mọi hành động ghi đều dừng lại chờ xác nhận** (confirm-before-write) qua thẻ xác nhận có audit.
  - **Interview Simulator:** mock interview **bám JD + CV**, phản hồi theo từng câu trả lời, theo dõi tiến bộ,
    **không chấm điểm tuyển/loại**.
  - **Bên đối tác:** JD writer + bias checker · **bulk screening brief** (đa-agent, tối đa 25 subtask/lần) ·
    scorecard assistant · semantic candidate search.
- **Trực quan hóa:** Trái = mock **chat trợ lý**: bong bóng người dùng "Tìm 3 job BE phù hợp CV của tôi rồi
  nộp job đầu" → agent trả lời + **thẻ xác nhận "Xác nhận nộp đơn?"** (nút emerald/xám). Phải = mock **màn
  phỏng vấn**: câu hỏi + ô ghi âm + panel "Phản hồi từng câu" (điểm mạnh/điểm cần cải thiện), thanh tiến bộ.
- **Số liệu:** "25+ tool · streaming · confirm-before-write · JD+CV grounded".
- **Bố cục & màu:** Viền info sky/indigo cho khối AI; thẻ xác nhận là điểm nhấn (nhắc thông điệp "AI an toàn").

---

## Slide 13 — Partner Recruiting OS (Flow 2) + Talent Pool

- **Mục tiêu:** Trình bày ATS campus-native đầy đủ + tìm kiếm thụ động.
- **Nội dung chữ:** Tiêu đề: **"Recruiting OS: từ JD đến offer, cộng talent pool chủ động"**. Flow 6 bước:
  1. `/partner/jobs/new` — tạo **hoặc upload JD** (bóc tách auto-fill).
  2. Publish → **cổng kiểm duyệt của trường**.
  3. Ứng viên nộp → danh sách applications.
  4. **Pipeline Kanban** theo stage cấu hình; kéo-thả có xác nhận; rollback cần chọn stage đích + lý do.
  5. **Screen**: chỉ field được phép, preview CV, scorecard, ghi chú; **định danh talent-pool bị ẩn tới khi
     reveal được chấp nhận**; kèm **fit score**.
  6. Lên lịch phỏng vấn → scorecard → chuyển sang **offer**.
  - **Talent Pool & Passive Search:** semantic search (pgvector) trên hồ sơ, **contact-request theo consent**,
    quota chống spam, thẻ ứng viên **ẩn danh** cho tới khi được đồng ý.
- **Trực quan hóa:** Trên = **flow ngang 6 node** (JD → Publish → Apply → Pipeline → Screen → Offer). Dưới =
  mock **Kanban 5 cột** (Applied · Screening · Interview · Offer · Hired) với thẻ ứng viên (tên **ẩn** "Ứng
  viên #A7" + vòng fit-score + chip stage). Một thẻ bên phải minh họa "reveal identity → cần quyền + audit".
- **Số liệu:** "pipeline đa vòng cấu hình được · identity masked + RBAC · pgvector talent search".
- **Bố cục & màu:** Kanban là nơi khoe palette (mỗi cột 1 màu header nhạt). Nhấn khóa 🔒 ở thẻ ẩn danh.

---

## Slide 14 — University Operations Center (Flow 3)

- **Mục tiêu:** Cho thấy lớp quản trị/governance mà job board không có.
- **Nội dung chữ:** Tiêu đề: **"Trung tâm vận hành của Nhà trường"**. Flow 4 bước:
  1. **Kiểm duyệt** (`/moderation` + jobs/events): hàng đợi có loại, người gửi, **SLA**, cờ rủi ro, người phụ
     trách; **checklist chính sách là chính, gợi ý AI chỉ tư vấn**.
  2. **Duyệt đối tác/công ty** (`/partners`): điểm nghi ngờ gian lận (AI, chỉ-admin, tư vấn) → gán gói + mức
     tin cậy → duyệt (báo) hoặc từ chối kèm lý do.
  3. **Workflow automation** (`/workflow`): DAG trực quan, dry-run, phiên bản active bất biến, kích hoạt gated
     theo RBAC, **node hệ trọng cần xác nhận người**.
  4. **Analytics & Career Outcomes**: tỉ lệ placement/lương/time-to-employment (**ngưỡng riêng tư tối thiểu
     5**), export async gated RBAC, báo cáo kiểm định.
- **Trực quan hóa:** **Flow 4 node dọc/ngang** với icon (`shield-check`, `building-2`, `workflow`,
  `bar-chart-3`). Node 4 phóng to thành mini-dashboard (funnel placement + KPI lương). Badge "min-5 privacy
  floor" cạnh analytics.
- **Số liệu:** "SLA-aware · immutable active version · min-5 privacy · export cho kiểm định (ABET/AUN-QA)".
- **Bố cục & màu:** Governance = tông trung tính + emerald cho "approved", VinUni red cho "reject/risk".

---

## Slide 15 — Visual Workflow Builder

- **Mục tiêu:** Khoe automation cấu hình được (không phải pipeline hardcode).
- **Nội dung chữ:** Tiêu đề: **"Tự động hóa quy trình bằng DAG trực quan, có kiểm soát"**.
  - Trình dựng **DAG bằng React Flow** (`@xyflow/react`): palette node / canvas / inspector / test console.
  - Vòng đời **DRAFT → TEST → ACTIVE**; **dry-run**; **phiên bản active bất biến**; kích hoạt **gated theo
    RBAC**; **node ghi/AI hệ trọng bắt buộc human-confirm**.
  - Dùng selector cho user/department/stage/template/prompt/action — **không phơi ID thô** làm mô hình cấu hình.
- **Trực quan hóa:** Mock **canvas DAG**: các node (Trigger → Điều kiện → Gửi thông báo → **AI action (badge
  cần xác nhận)** → Cập nhật pipeline) nối bằng cạnh cong. Thanh trên hiện badge trạng thái `DRAFT/TEST/ACTIVE`
  + nút *Dry-run*. Panel phải = inspector của node đang chọn.
- **Số liệu:** "DRAFT→TEST→ACTIVE · dry-run · immutable · human-confirm node".
- **Bố cục & màu:** Node AI/ghi dùng viền amber (cảnh báo cần xác nhận); trạng thái ACTIVE = emerald.

---

## Slide 16 — AI Governance, Safety & Trust

- **Mục tiêu:** Điểm cộng lớn với hội đồng: AI có trách nhiệm, đo đếm & che giấu đúng.
- **Nội dung chữ:** Tiêu đề: **"AI có kế toán, có rào chắn, có che giấu đúng chỗ"**.
  - **Metering 3 sổ tách biệt:** `ai_usage_log` (đồng hồ PII-safe) · telemetry superadmin · **sổ credit/energy
    tính phí** (credit SV · credit gói đối tác · ngân sách trường/khoa) với **`UsageContext`** + **idempotency
    key** → retry không tính phí 2 lần.
  - **Quy tắc trừ credit:** chỉ trừ khi có **output hữu ích thật**; scoring tất định / OCR local / lỗi / cache
    hit / provider fail **không** trừ credit.
  - **Human confirm** cho mọi write action (thẻ xác nhận có chữ ký + audit).
  - **Che giấu định danh provider/model:** chỉ **Platform Superadmin** thấy registry thật; API **không bao giờ
    trả key/base_url**. End user không thấy token/latency/prompt/confidence.
  - **Guardrail:** input guard (chống prompt-injection, strip PII, rate limit 30/60/100 req-giờ), RAG citation
    verification, circuit breaker + fallback chain, **offline-eval CI gate** (vi phạm ranh giới riêng tư =
    chặn cứng).
  - **Tách sponsored:** organic / recommended / **sponsored (`Được tài trợ`/`Quảng cáo`)** / university-curated
    luôn phân biệt; nhãn công bố **không gỡ được**.
- **Trực quan hóa:** Lưới **6 thẻ trust** (icon lucide): Metering & Ledger · Idempotency · Human-confirm ·
  Provider masking · Guardrails · Sponsored separation. Có thể thêm 1 dải "UsageContext" nhỏ thể hiện các field
  (principal · org · feature_key · billing_scope).
- **Số liệu:** "3 ledger · idempotency · 20 bộ eval AI · rate-limit 30/60/100".
- **Bố cục & màu:** Đây là slide "niềm tin" → tông trung tính, chấm màu theo vai trò (info/success/warning).

---

## Slide 17 — Mô hình kinh doanh & Monetization

- **Mục tiêu:** Tính khả thi thương mại.
- **Nội dung chữ:** Tiêu đề: **"Bốn dòng doanh thu, một sổ AI credit minh bạch"** (PRD §1.3):
  1. **Gói đối tác (Partner packages)** — quota đăng tin, spotlight, featured.
  2. **Quảng cáo đối tác** — banner, sponsored jobs, email ads, tài trợ sự kiện (**luôn có nhãn công bố**).
  3. **Gói sinh viên (subscriptions)** — External/General user mua AI + tính năng premium.
  4. **Gói sự kiện** — slot tài trợ / vé.
  - **Cơ chế:** sổ AI credit/usage bền vững; SV/đối tác **nâng cấp hoặc mua thêm**; **trường dùng ngân sách
    admin, không upsell**. Billing có proration (không thiệt khi nâng cấp), grace period, reset quota.
  - **V1 thanh toán = chuyển khoản/manual**; VNPay/MoMo/ZaloPay là phase sau.
  - **Giá gói:** `[ĐIỀN SỐ — docs để admin cấu hình, không cố định]`.
- **Trực quan hóa:** 4 thẻ doanh thu (icon `package`, `megaphone`, `graduation-cap`, `calendar`) → hội tụ vào
  1 thẻ trung tâm **"AI Credit / Usage Ledger"**. Bên dưới: dải phân tầng exhaustion "SV/Đối tác → mua/nâng
  cấp" vs "Trường → yêu cầu admin". Có 1 chip **`Được tài trợ`** minh họa (không được gỡ).
- **Số liệu:** 4 chip nguồn doanh thu; ô giá `[ĐIỀN SỐ]`.
- **Bố cục & màu:** Amber cho các yếu tố sponsored (đúng semantics); phần credit dùng indigo.

---

## Slide 18 — Kiến trúc tổng quan (Architecture)

- **Mục tiêu:** Thuyết phục hội đồng kỹ thuật: kiến trúc sạch, có kỷ luật.
- **Nội dung chữ:** Tiêu đề: **"Kiến trúc DDD theo module — biên rõ ràng, sự kiện & audit ở mọi ghi"**.
  - **Luồng request:** `Client (Next.js)` → `API (router + Pydantic)` → `Application (service, RBAC ở đây,
    transaction)` → `Domain (models thuần + repo interface)` → `Infrastructure (SQLAlchemy repo, adapter)` → `PostgreSQL`.
  - **Nguyên tắc bất di:** không import chéo module (giao tiếp qua service/event), không business-logic trong
    router, không ORM trong domain, **không JOIN đa-domain trực tiếp cho dashboard**.
  - **Read model / projection:** `proj_student_dashboard`, `proj_partner_pipeline`, `proj_university_kpi`.
  - **Event-driven:** **outbox pattern** (`outbox_events` + `analytics_events`) do scheduler rút; **audit ở
    mọi ghi** (`audit_logs`). Pipeline là state machine có version (ADR-0004→0007).
  - **AI Gateway** provider-agnostic: task → chọn model → load-balance → adapter → fallback chain; UsageContext
    + observability (Langfuse) + output guard.
- **Trực quan hóa:** **Sơ đồ layered dọc** 5 tầng (mỗi tầng 1 băng ngang, nhãn trách nhiệm), mũi tên xuống là
  request / lên là response. Bên phải tách 1 nhánh **AI Gateway** (task→model→fallback). Dưới cùng: 3 thành
  phần ngang **Read Models · Outbox/Events · Audit Log** như "xương sống dữ liệu". Băng "RBAC" gắn ở tầng
  Application để nhấn "RBAC ở service layer".
- **Số liệu:** "34 module · biên DDD cứng · outbox + audit + read-model".
- **Bố cục & màu:** Monochrome là chính; mỗi tầng 1 sắc xám khác; **AI Gateway** tô indigo-soft để nổi.

---

## Slide 19 — Công nghệ & Quy mô (Tech Stack + Scale)

- **Mục tiêu:** "Đây là hệ thống lớn thật" — bằng số đếm được, không nói suông.
- **Nội dung chữ:** Tiêu đề: **"Stack hiện đại · quy mô đã dựng thật"**.
  - **Backend:** Python 3.12 · **FastAPI** · SQLAlchemy 2 async + asyncpg · Pydantic v2 · **PostgreSQL 16 +
    pgvector** (RAG) · Alembic · **Celery + Redis** · JWT + Argon2 + TOTP 2FA · OIDC/SAML SSO · AI gateway
    (OpenRouter default, OpenAI-compatible/Gemini/Anthropic) · **Langfuse** · OCR (PyMuPDF4LLM, pdfplumber,
    Tesseract vie+eng) · pytest · ruff/mypy · **uv**.
  - **Frontend:** **Next.js 15 (App Router)** · React 19 · TypeScript 5.7 strict · **Tailwind v4 + shadcn/ui**
    · lucide-react · TanStack Query + Zustand · Recharts · **next-intl (vi/en)** · `@xyflow/react` (workflow)
    · `@dnd-kit` (CV Studio/kanban) · Vitest + Playwright.
- **Trực quan hóa:** Trên = 2 hàng chip công nghệ (Backend / Frontend), mỗi chip 1 tên (không cần logo ngoài;
  nếu có logo thì embed data-URI). Dưới = **hàng KPI tiles** khoe số liệu (số dùng JetBrains Mono cỡ lớn).
- **Số liệu (CODE-VERIFIED — đếm bằng lệnh, ghi kèm để bảo vệ trước hội đồng):**
  - **34** backend modules — `ls backend/app/modules/ | grep -v __ | wc -l`
  - **98** Alembic migrations — `ls backend/alembic/versions/*.py | grep -v __ | wc -l`
  - **766** file Python backend — `find backend/app -name '*.py' | wc -l`
  - **~477** route decorator (195 trên `@router` chính) · **41** `APIRouter`
  - **2.022** hàm test backend / **201** file test — `grep -rE '^\s*(async )?def test_' backend/tests | wc -l`
  - **120** màn hình frontend (`page.tsx`) · **655** file TS/TSX
  - **54 vi + 54 en** file i18n (parity) · **20** bộ dataset đánh giá AI
  - → chọn ~6 con số mạnh nhất làm KPI tiles: **34 module · 98 migration · 2.022 test · 120 màn hình · vi/en
    · 20 bộ eval AI**.
- **Bố cục & màu:** KPI tiles là ngôi sao — mỗi tile 1 icon-chip màu palette, số to tabular. Có thể dùng 1 tile
  gradient hero cho con số ấn tượng nhất (vd "2.022 test").

> **Ghi chú trung thực (đừng đưa lên slide, để bạn biết):** đây là **quy mô đã dựng**, không đồng nghĩa "toàn
> bộ test xanh". Trình bày là "quy mô hệ thống", đừng khẳng định "100% pass" trước hội đồng nếu bị hỏi sâu.

---

## Slide 20 — Roadmap, Traction & Kết luận

- **Mục tiêu:** Chốt bằng lộ trình khả thi + tầm nhìn + logo.
- **Nội dung chữ:** Tiêu đề: **"Lộ trình rõ ràng — và một tầm nhìn khép kín"**.
  - **6 phase (~36 tuần, đội nhỏ 2–3 kỹ sư + 1 AI engineer):**
    - P0 Foundation (t1–3) · P1 Core Loops (t4–8) · P2 Advanced Hiring/ATS (t9–14) · P3 AI Intelligence
      (t15–20) · P4 Events + Monetization (t21–27) *(+P4b realtime/messaging/workflow)* · P5 University
      Intelligence (t28–36: mentorship, alumni, career outcomes, tích hợp SIS).
  - **Đã dựng (theo scale slide 19):** 4 bề mặt persona, CV Studio, pipeline ATS, AI assistant, workflow,
    analytics — 120 màn hình, 34 module.
  - **Tầm nhìn:** *"Vòng lặp dữ liệu khép kín Học → Ứng tuyển → Tuyển dụng → Outcome → phản hồi vào chương
    trình học."*
  - **Kết:** Logo VinUni + 1 câu CTA + `[TÊN TEAM]` + liên hệ.
- **Trực quan hóa:** **Timeline ngang 6 mốc** (P0→P5) với thanh tiến độ tô phần "đã dựng". Dưới: 3 chip tầm
  nhìn (Closed-loop data · AI-first · Campus-native). Góc: logo VinUni + gradient hero khép lại (đối xứng với
  slide 1).
- **Số liệu:** "6 phase · ~36 tuần · 4 bề mặt đã dựng".
- **Bố cục & màu:** Timeline theo palette tăng dần; phần "đã dựng" tô indigo→violet gradient (điểm nhấn cuối).

---

## 🔧 Danh sách placeholder cần bạn điền (trước khi pitch)

| Ký hiệu | Ở slide | Nội dung cần điền |
|---|---|---|
| `[TÊN TEAM]` | 1, 20 | Tên nhóm / thành viên |
| `[MÔN/CUỘC THI]` | 1 | Bối cảnh trình bày |
| `[ĐIỀN SỐ]` (thị trường) | 3 | TAM/SAM, số SV/khóa, số đối tác mục tiêu — docs **không** có |
| `[ĐIỀN SỐ]` (giá) | 17 | Giá gói đối tác/SV — docs để admin cấu hình |
| Logo + screenshot | 1, 5, 20 | Bỏ vào `assets/` (xem `assets/README.md`) |

**Nguyên tắc vàng:** phần *quy mô/kỹ thuật* dùng số code-verified (mạnh & an toàn); phần *thị trường/tài chính*
để placeholder — **thà trống còn hơn bịa số** trước hội đồng.
