# DECK SPEC — 21 slide pitch "VinUni Career Platform"

> **Cách đọc file này:** mỗi slide có 5 phần — **Mục tiêu**, **Nội dung chữ** (đúng để hiển thị, tiếng Việt),
> **Trực quan hóa** (vẽ gì, bố trí ra sao), **Số liệu** (con số nổi bật), **Bố cục & màu**. Số liệu quy mô là
> **code-verified**; số thị trường là **số thật 2024 có nguồn**; giá & KPI là **đề xuất/mục tiêu** (ghi rõ).
>
> **Storyline (đã tối ưu cho hội đồng — front-load business/quy mô/thách thức, đóng bằng business):**
> Vấn đề → Cơ hội & tầm nhìn nền tảng → Giải pháp → Sản phẩm thật → **Quy mô (bằng chứng đã dựng)** →
> **Mô hình kinh doanh** → Đối thủ → Người dùng → (7 slide chiều sâu sản phẩm/AI) → Kiến trúc & công nghệ →
> **Traction & Mục tiêu 12 tháng** → **Roadmap + Đường mở rộng + Ask**.
>
> **Motif xuyên suốt — "Ưu tiên VinUni, sẵn sàng thành nền tảng"** (*beachhead → mở rộng*): thắng sâu ở
> VinUni trước (dữ liệu đã xác thực, vòng lặp khép kín), và **kiến trúc đã sẵn sàng** (multi-tenant RBAC,
> multi-identity, đã phục vụ cả external/general user) để mở thành nền tảng độc lập cho mọi người. Trình bày
> là **tầm nhìn + tính sẵn-sàng-kỹ-thuật**, KHÔNG phải cam kết V1 → an toàn khi bị vặn.
>
> **Design system chung áp cho MỌI slide** (chi tiết ở `03-BRAND-DESIGN-SYSTEM.md`): nền `#F8F7F1`, thẻ
> trắng `#ffffff` bo góc 14px viền 1px `#e5e5e5`; chữ Plus Jakarta Sans, số/metric dùng JetBrains Mono;
> khung monochrome (ink `#171717`), nhấn bằng palette data-viz (indigo `#6366f1`, teal `#14b8a6`, amber
> `#f59e0b`, rose `#f43f5e`, sky `#0ea5e9`, emerald `#10b981`, violet `#8b5cf6`, orange `#f97316`); **tối đa
> 1 panel gradient indigo→violet mỗi slide**. Mỗi slide có **kicker** + **số slide** + **logo nhỏ VinUni** ở footer.

---

## Slide 01 — Bìa (Cover)

- **Mục tiêu:** Ấn tượng đầu, khẳng định tầm vóc "hệ điều hành tuyển dụng của VinUni".
- **Nội dung chữ:**
  - Logo **VinUni** (lớn, trên cùng — đây là slide có logo như bạn yêu cầu).
  - Tên sản phẩm: **VinUni Career Platform**
  - Tagline: *"Hệ điều hành tuyển dụng chính thức của Đại học VinUni — AI-first, sẵn sàng thành nền tảng."*
  - Dòng phụ: *"Một nền tảng · Bốn bề mặt vận hành · Toàn bộ vòng đời sự nghiệp"*
  - Chân slide: **C2-Team-037** · `[MÔN/CUỘC THI]` · Tháng 7, 2026
- **Trực quan hóa:** Nền `#F8F7F1` sạch, nhiều khoảng trắng. Một dải "signature" mảnh chạy ngang phía dưới
  tiêu đề gồm 8 chấm tròn nhỏ theo đúng thứ tự palette data-viz (indigo→teal→amber→rose→sky→emerald→violet→
  orange) — ẩn dụ "đa persona, đa module". Góc phải-dưới: 1 khối gradient indigo→violet nhỏ (chấm nhấn duy nhất).
- **Số liệu:** không có (bìa giữ tối giản).
- **Bố cục & màu:** Canh trái, tiêu đề cỡ display 44–56px, tagline xám `#525252`. Không dùng ảnh nền ồn ào.

---

## Slide 02 — Thực trạng & Thách thức

- **Mục tiêu:** Chỉ ra sự phân mảnh & nông của công cụ hướng nghiệp đại học — và vì sao chưa ai giải được.
- **Nội dung chữ:** Tiêu đề: **"Hướng nghiệp đại học hôm nay: rời rạc và hời hợt"**. 3 cột nỗi đau:
  - 🎓 **Sinh viên:** Không có tín hiệu độ-phù-hợp cá nhân hóa; không có trợ lý AI viết/soi CV; không được
    luyện phỏng vấn; mù mờ về mức độ cạnh tranh & deadline.
  - 🏢 **Nhà tuyển dụng (Đối tác):** ATS doanh nghiệp (Greenhouse/Workday) thì nặng & đắt; job board thì
    ứng viên không được xác thực; **không có pipeline & talent pool gắn với campus**.
  - 🏛️ **Nhà trường:** Không có kiểm duyệt tập trung, không quản trị đối tác, không đo được **career
    outcome** (tỉ lệ có việc, lương, time-to-hire) để phục vụ kiểm định (ABET/AUN-QA).
  - **Vì sao chưa ai giải được (thách thức):** ATS doanh nghiệp *quá nặng*, job board *quá nông*, tự xây
    in-house *quá khó* (AI + pipeline + governance + realtime). *"Job board đơn thuần **không** quản được cả
    vòng đời tuyển dụng."*
- **Trực quan hóa:** 3 thẻ trắng persona (icon lucide `graduation-cap`, `building-2`, `landmark`) + 3 gạch đầu
  dòng. Bên dưới: dải "3 thách thức" — 3 chip (*Quá nặng · Quá nông · Quá khó tự xây*) với icon rào cản; và
  dải "công cụ rời rạc" (CV Word · Google Form · Email · Excel · Job board) có dấu `×` thể hiện phân mảnh.
- **Số liệu (số thật để nhấn quy mô nỗi đau):** mỗi năm VN có **~314.000** cử nhân ra trường tìm việc và
  **~2,36 triệu** SV đang học — nhưng công cụ hướng nghiệp vẫn rời rạc. *(Nguồn: Bộ GD&ĐT / Tổng cục Thống kê VN 2024.)*
- **Bố cục & màu:** Khung monochrome; mỗi cột 1 màu icon-chip (indigo/teal/amber); dải thách thức tông đỏ-cam nhạt.

---

## Slide 03 — Cơ hội thị trường & Tầm nhìn nền tảng

- **Mục tiêu:** Định vị thị trường + gieo **motif beachhead → mở rộng** (điểm business cốt lõi).
- **Nội dung chữ:** Tiêu đề: **"Bắt đầu từ VinUni — kiến trúc sẵn sàng thành nền tảng cho mọi người"**.
  - **Beachhead (điểm tựa):** thắng sâu ở hệ sinh thái VinUni trước — Sinh viên, **Cựu sinh viên (Alumni)**,
    Đối tác tuyển dụng, Nhà trường. Lợi thế: **danh tính đã xác thực + vòng lặp dữ liệu khép kín** (Học → CV
    → Ứng tuyển → Tuyển → Outcome → phản hồi vào chương trình học).
  - **Đã vượt khỏi "chỉ VinUni":** hệ thống *đã* phục vụ **External Student** (SV trường khác) và **General
    User** (người đi làm) với quyền hạn chế + có thể mua nâng cấp — tức **người ngoài VinUni dùng được ngay**.
  - **Sẵn sàng thành nền tảng độc lập:** **multi-identity** + mô hình **Organization → Roles → Permissions**
    (multi-tenant RBAC) + biên module rõ ràng ⇒ *cùng một codebase* có thể mở thành nền tảng đa-tổ chức phục
    vụ nhiều trường / mọi người, **không phải viết lại**.
  - **Vì sao là bây giờ:** làn sóng LLM khiến bóc tách CV, matching, trợ lý & luyện phỏng vấn *thực sự hữu
    ích* với chi phí thấp — điều 2–3 năm trước chưa khả thi.
  - **Quy mô thị trường (số thật 2024, có nguồn):**
    - **SOM / Beachhead (VinUni):** ~**3.500** SV ở công suất tối đa + **~145** cử nhân/năm khóa đầu (2024,
      14 ngành) + đối tác tuyển dụng campus. *(VinUni thành lập 2020, hợp tác Cornell & UPenn.)*
    - **SAM (khối trường tư/quốc tế VN):** **67** trường đại học tư trong tổng **243** trường.
    - **TAM (toàn Việt Nam):** **~2,36 triệu** sinh viên đại học · **~314.000** cử nhân tốt nghiệp/năm ·
      **>940.000** doanh nghiệp đang hoạt động. Thị trường **HR-tech VN** được dự báo tiến tới **~US$1 tỷ**.
- **Trực quan hóa:** **Sơ đồ 3 vòng mở rộng đồng tâm** (ẩn dụ beachhead): lõi = *VinUni (~3.500 SV, bây giờ)*
  → vòng 2 = *Alumni + SV ngoài + người đi làm (đã hỗ trợ)* → vòng 3 = *Nền tảng độc lập / đa-trường: 67
  trường tư · 2,36M SV · 940k DN (sẵn sàng)*. Mỗi vòng gắn số ở trên. Bên phải: thẻ "Vòng lặp dữ liệu khép
  kín" (4 mũi tên xoay) + 3 chip "động lực thời điểm".
- **Số liệu:** 3 vòng gắn số (3.500 → 67 trường → 2,36M SV / 940k DN); chip "HR-tech VN → ~US$1 tỷ".
- **Nguồn (ghi chân slide, cỡ nhỏ):** Tổng cục Thống kê / Bộ GD&ĐT VN 2024 (2,36M SV; 314k cử nhân; 243
  trường); NSO/VietnamNet 2024 (>940k DN); VinUni.edu.vn (khóa đầu 145 cử nhân, 2024).
- **Bố cục & màu:** 3 vòng dùng indigo→violet nhạt dần (đây có thể là panel gradient hero của slide). Vòng
  "sẵn sàng" vẽ nét đứt để thể hiện *tầm nhìn*, không phải cam kết.
- **⚠️ Ghi chú trung thực (đừng in lên slide):** docs khung V1 = tập trung VinUni. Trình bày vòng 3 là **tầm
  nhìn + tính sẵn-sàng-kỹ-thuật**, không nói "đang bán cho trường khác". Nếu bị hỏi: *"V1 tối ưu cho VinUni;
  kiến trúc multi-tenant khiến việc mở rộng là một lựa chọn có sẵn, không phải dự án làm lại."*

---

## Slide 04 — Giải pháp: 1 hệ điều hành, 4 bề mặt *(SLIDE HERO)*

- **Mục tiêu:** Câu trả lời trung tâm — nói "cái này LÀ gì" trong 5 giây.
- **Nội dung chữ:** Tiêu đề: **"Một nền tảng AI-first, bốn bề mặt vận hành"**. 4 khối:
  1. **Public Marketplace** — khám phá việc/sự kiện/công ty công khai, salary explorer cho khách.
  2. **Student Command Center** — CV-first: tạo/soi CV, fit score, ứng tuyển, trợ lý AI, luyện phỏng vấn.
  3. **Partner Recruiting OS** — đăng JD, pipeline ATS đa vòng, talent pool, quảng cáo, analytics.
  4. **University Operations Center** — kiểm duyệt, quản trị đối tác, workflow automation, career outcomes.
  - Câu chốt: *"AI trợ giúp thật ở mọi bước — không phải demo trang trí."*
- **Trực quan hóa:** **Đây là slide hero** → dùng **1 panel gradient indigo→violet** cho thẻ trung tâm
  "AI-first core", 4 bề mặt là 4 thẻ trắng vệ tinh quanh (bố cục chữ thập / 2×2). Mỗi bề mặt có icon lucide
  (`compass`, `layout-dashboard`, `briefcase`, `landmark`) + 3 từ khóa.
- **Số liệu:** 4 chip nhỏ: "1 nền tảng", "4 persona-surface", "AI ở mọi bước", "vi/en".
- **Bố cục & màu:** Điểm nhấn thị giác mạnh nhất của deck — cho phép gradient hero lớn hơn slide khác.

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

## Slide 06 — Quy mô & Mức độ hoàn thiện *(BẰNG CHỨNG "ĐÃ DỰNG THẬT")*

- **Mục tiêu:** De-risk cho hội đồng — *"đây là hệ thống thật, không phải mockup/slideware"*. Đặt sớm để tạo
  niềm tin trước khi vào chi tiết.
- **Nội dung chữ:** Tiêu đề: **"Không phải ý tưởng trên giấy — hệ thống đã dựng thật"**.
  - 4 bề mặt persona đã hoạt động · light + dark · song ngữ vi/en · pipeline AI end-to-end.
  - Câu chốt: *"Mọi con số dưới đây đếm trực tiếp từ mã nguồn — kiểm chứng được."*
- **Trực quan hóa:** **Hàng KPI tiles** lớn (số dùng JetBrains Mono cỡ lớn, mỗi tile 1 icon-chip màu palette).
  Có thể dùng 1 tile gradient hero cho con số ấn tượng nhất ("2.022 test"). Dưới: dải "trạng thái hoàn thiện"
  gồm chip *Backend · Frontend · AI pipeline · i18n · Tests*.
- **Số liệu (CODE-VERIFIED — chọn ~6 mạnh nhất làm KPI):**
  - **34** backend modules · **98** Alembic migrations · **766** file Python
  - **2.022** test backend / **201** file test · **~477** route (41 `APIRouter`)
  - **120** màn hình frontend · **655** file TS/TSX
  - **54 vi + 54 en** i18n (parity) · **20** bộ dataset đánh giá AI
  - → KPI tiles gợi ý: **34 module · 98 migration · 2.022 test · 120 màn hình · vi/en · 20 bộ eval AI**.
- **Bố cục & màu:** KPI tiles là ngôi sao; số to tabular, delta/label ngắn gọn.
- **⚠️ Ghi chú trung thực (đừng in lên slide):** đây là **quy mô đã dựng**, không đồng nghĩa "toàn bộ test
  xanh". Trình bày là "quy mô hệ thống"; nếu bị hỏi sâu, nói thẳng là đang ổn định các quality gate.

---

## Slide 07 — Mô hình kinh doanh & Doanh thu

- **Mục tiêu:** Tính khả thi thương mại + kinh tế khi mở rộng nền tảng (business chiều sâu).
- **Nội dung chữ:** Tiêu đề: **"Bốn dòng doanh thu hôm nay — kinh tế nền tảng ngày mai"** (PRD §1.3):
  - **4 dòng doanh thu (ai trả tiền):**
    1. **Gói đối tác (Partner packages)** — *đối tác trả*: quota đăng tin, spotlight, featured.
    2. **Quảng cáo đối tác** — *đối tác trả*: banner, sponsored jobs, email ads, tài trợ sự kiện (**luôn có
       nhãn `Được tài trợ`/`Quảng cáo`, không gỡ**).
    3. **Gói sinh viên (subscriptions)** — *External/General user trả*: mua AI credit + tính năng premium.
    4. **Gói sự kiện** — *đối tác/nhà tài trợ trả*: slot tài trợ / vé.
  - **Cơ chế kiếm tiền từ AI:** sổ **AI credit/usage** bền vững; SV/đối tác **nâng cấp hoặc mua thêm credit**;
    **nhà trường dùng ngân sách admin, KHÔNG bị upsell** (đúng đạo đức với người dùng nội bộ).
  - **Kinh tế khi mở rộng nền tảng (beachhead → mở rộng):** cùng bộ máy monetization áp cho tổ chức mới ⇒
    thêm **doanh thu theo tổ chức** (license/SaaS theo chỗ ngồi hoặc theo tính năng) khi mở ra ngoài VinUni —
    biên phí cận biên thấp vì hạ tầng AI dùng chung, metering đã sẵn.
  - **Bảng giá đề xuất (rẻ & hợp lý cho thị trường VN — admin cấu hình được):**
    - 🎓 **Sinh viên** *(SV VinUni: MIỄN PHÍ, trường tài trợ)* — với SV ngoài/người đi làm:
      **Free 0₫** (duyệt việc, ứng tuyển, 1 CV, AI credit cơ bản) · **Pro 49.000₫/tháng** *(hoặc
      199.000₫/học kỳ)*: AI credit rộng, full template CV, mock interview, fit score chi tiết, không quảng cáo.
    - 🏢 **Đối tác tuyển dụng:** **Starter 0₫** (2 tin/tháng) · **Growth 2.000.000₫/tháng** (10 tin, spotlight,
      pipeline ATS, analytics cơ bản) · **Pro 5.000.000₫/tháng** (tin không giới hạn, featured employer, talent
      pool, AI screening, full analytics) · **Enterprise: thương lượng**.
    - 📣 **Quảng cáo:** sponsored job từ **500.000₫/tin/tuần**; banner & email theo chiến dịch.
    - 🎪 **Sự kiện:** gói tài trợ career fair từ **10.000.000₫**.
    - 🌐 **Mở rộng (license tổ chức ngoài VinUni):** từ **~150 triệu₫/năm** theo quy mô *(illustrative)*.
  - **V1 thanh toán = chuyển khoản/manual**; VNPay/MoMo/ZaloPay là phase sau.
- **Trực quan hóa:** Trái = 4 thẻ doanh thu (icon `package`, `megaphone`, `graduation-cap`, `calendar`), mỗi
  thẻ ghi rõ **"ai trả" + mức giá neo** (vd Đối tác Growth 2tr₫/th, SV Pro 49k₫/th), hội tụ vào 1 thẻ trung
  tâm **"AI Credit / Usage Ledger"**. Phải = dải "kinh tế mở rộng": mũi tên *VinUni (4 dòng doanh thu) → Tổ
  chức mới (+ license/SaaS ~150tr₫/năm)*. Chip **`Được tài trợ`** minh họa (không gỡ). Chú thích phân tầng
  exhaustion: SV/Đối tác → mua/nâng cấp · Trường → yêu cầu admin.
- **Số liệu:** neo giá SV Pro **49k₫/th** · Đối tác Growth **2tr₫/th** / Pro **5tr₫/th** · license **~150tr₫/năm**.
- **Bố cục & màu:** Amber cho yếu tố sponsored (đúng semantics); credit/ledger dùng indigo; mũi tên mở rộng violet.

---

## Slide 08 — Phân tích đối thủ & Định vị

- **Mục tiêu:** Chứng minh khác biệt phòng thủ được (defensible) **và** có đường mở rộng.
- **Nội dung chữ:** Tiêu đề: **"Chúng tôi đứng ở đâu — và vì sao lợi thế còn nới rộng"**. Định vị (PRD §1.2):
  - **vs LinkedIn** (mạng lưới toàn cầu) → *AI cá nhân hóa + talent đã xác thực + pipeline ATS*.
  - **vs TopCV / VietnamWorks** (job board VN) → *pipeline đa vòng + luyện phỏng vấn + mạng alumni*.
  - **vs Handshake** (campus Mỹ) → *AI matching sâu hơn + hệ quảng cáo + quản lý sự kiện*.
  - **vs Greenhouse / Workday** (ATS doanh nghiệp) → *nhẹ hơn, campus-native, AI-first*.
  - **Moat kép:** *campus-native + AI-first* vừa là **hào phòng thủ** (dữ liệu xác thực + vòng lặp khép kín
    khó sao chép) vừa là **bệ phóng** (kiến trúc multi-tenant → mở thành nền tảng).
- **Trực quan hóa:** **Ma trận 2×2**: trục X = "Generic ↔ Campus-native", trục Y = "Job board ↔ Full
  lifecycle + AI". Đặt tên đối thủ (chấm xám trung tính); **VinUni ở góc phải-trên** (chấm indigo lớn) + mũi
  tên nhỏ chỉ ra ngoài ghi *"sẵn sàng mở rộng"*. (Tùy chọn: bảng 5 cột Đối thủ · Thế mạnh · Khoảng trống ·
  Lợi thế VinUni bên dưới.)
- **Số liệu:** không cần số; nhấn vị trí.
- **Bố cục & màu:** Đối thủ chấm xám, **chỉ VinUni** màu indigo (nguyên tắc "màu = ý nghĩa"); mũi tên mở rộng violet.

---

## Slide 09 — Người dùng & Phân quyền (Personas + RBAC)

- **Mục tiêu:** Chiều sâu mô hình người dùng + **nền tảng cho tính multi-tenant** (chống lưng cho slide 3/8).
- **Nội dung chữ:** Tiêu đề: **"Nhiều persona, một mô hình phân quyền cấu hình được (multi-tenant-ready)"**.
  - **Persona:** Sinh viên VinUni · Alumni · **External Student** · **General User** · Guest · Partner Admin ·
    Nhân sự Partner (vai trò tự đặt tên) · University Super Admin · Nhân sự Trường (tự đặt tên) · Platform
    Superadmin · Mentor. *(External/General = bằng chứng "người ngoài VinUni đã dùng được".)*
  - **Multi-identity:** một tài khoản giữ nhiều danh tính (vd SV + nhân viên đối tác), đổi ở header.
  - **RBAC:** năng lực (analytics, xem CV/định danh, billing, pipeline, hành động AI, export…) là **capability
    cấp phát được** theo **user / role / department** ở **service layer** — *không hardcode theo tên vai trò*.
  - **→ Vì sao đây là "platform-ready":** `Organization → Roles → Permissions` chính là mô hình **đa-tổ chức**;
    thêm một tổ chức mới = thêm một Organization, không đụng code.
- **Trực quan hóa:** Cột trái = **bản đồ persona** gom 4 nhóm (Public/Student · Partner · University · Platform)
  dạng chip. Cột phải = **sơ đồ RBAC 3 tầng** `Organization → Roles/Departments → Permissions` với ví dụ
  "Partner Admin cấp quyền 'xem định danh ứng viên' cho 'Technical Interviewer'"; thêm badge **multi-identity**
  và nhãn nhỏ *"1 org hôm nay → N org khi mở rộng"*.
- **Số liệu:** "11 loại persona · vai trò tự đặt tên · phân quyền theo department · multi-tenant model".
- **Bố cục & màu:** Mỗi nhóm persona 1 màu chip; sơ đồ RBAC monochrome + 1 nhánh highlight indigo.

---

## Slide 10 — Hành trình Sinh viên (Flow 1)

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
- **Trực quan hóa:** **Flow ngang 7 node** (mỗi node 1 pill bo tròn có icon lucide), mũi tên nối. Node 5 phóng
  to thành 1 thẻ "job-intelligence" mini (vòng fit-score + 2 chip gap). Dải "Guest → Auth → Student" đổi màu
  nền nhạt để thể hiện chuyển ngữ cảnh.
- **Số liệu:** Badge "CV snapshot bất biến khi nộp" · "Guest không thấy fit/cạnh tranh".
- **Bố cục & màu:** Node trung tính; node có AI (4,5) viền sky/indigo (info/AI).

---

## Slide 11 — CV Studio

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

## Slide 12 — CV Ingestion Cascade *(câu chuyện kỹ thuật chữ ký)*

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
- **Bố cục & màu:** Gradient chi phí: tầng rẻ = emerald-soft, tầng đắt dần = amber→rose-soft. Nhánh reject =
  VinUni red `#c83538`.

---

## Slide 13 — CV–JD Matching & Competition Intelligence

- **Mục tiêu:** Cho thấy AI ra quyết định **tất định, giải thích được, tôn trọng riêng tư**.
- **Nội dung chữ:** Tiêu đề: **"Điểm khớp tất định, cạnh tranh minh bạch — không phải điểm ma thuật"**.
  - **Công thức fit (tất định, cùng input → cùng số nguyên):**
    `score = round(0.50·skills + 0.25·experience + 0.10·logistics + 0.15·quality)` → **0–100**.
  - **4 dải fit:** 85–100 mạnh · 70–84 tốt · 50–69 khả thi · <50 yếu.
  - **Evidence gaps:** `matched_skills` + `gaps` + cảnh báo CV cũ (>60 ngày).
  - **Lưu có version-stamp:** cache nhanh chỉ dùng khi `content_version == cv.version`; **sửa CV là re-score**.
  - **Learning cache:** phần *giải thích AI* (chỉ cho CV được đề xuất) cache theo `(cv_version, job_version)`;
    điểm tất định **miễn phí**, chỉ phần chữ AI mới tốn credit.
  - **Competition Intelligence:** tín hiệu dựa trên **input thật** (seats/hiring target, số lượng & vận tốc
    ứng tuyển, phân bố chất lượng ứng viên dạng bucket, **fit percentile của SV**, độ tươi deadline, source
    mix) — **không** lộ ứng viên khác/PII/điểm nội bộ; dữ liệu yếu thì **tắt mềm**, không bịa.
- **Trực quan hóa:** Trái = **thẻ score**: donut 0–100 + 4 thanh band đúng trọng số (skills 50% / experience
  25% / logistics 10% / quality 15%) + 2 chip "matched" (emerald) & "gap" (amber). Phải = **thẻ competition**:
  thanh percentile "Bạn ở top X%", chip mức cạnh tranh (Thấp/Vừa/Cao), dòng privacy "Không hiển thị ứng viên
  khác". Guest overlay mờ + khóa 🔒.
- **Số liệu:** "0–100 · 4 band · re-score khi CV đổi · điểm tất định miễn phí".
- **Bố cục & màu:** Donut theo màu band; competition dùng sky/indigo (info). Nhấn dòng privacy.

---

## Slide 14 — AI Career Assistant & Interview Simulator

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
- **Bố cục & màu:** Viền info sky/indigo cho khối AI; thẻ xác nhận là điểm nhấn ("AI an toàn").

---

## Slide 15 — Partner Recruiting OS (Flow 2) + Talent Pool

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
- **Bố cục & màu:** Kanban khoe palette (mỗi cột 1 màu header nhạt). Nhấn khóa 🔒 ở thẻ ẩn danh.

---

## Slide 16 — University Operations Center (Flow 3)

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
- **Trực quan hóa:** **Flow 4 node** với icon (`shield-check`, `building-2`, `workflow`, `bar-chart-3`). Node
  4 phóng to thành mini-dashboard (funnel placement + KPI lương). Badge "min-5 privacy floor" cạnh analytics.
- **Số liệu:** "SLA-aware · immutable active version · min-5 privacy · export cho kiểm định (ABET/AUN-QA)".
- **Bố cục & màu:** Governance = tông trung tính + emerald cho "approved", VinUni red cho "reject/risk".

---

## Slide 17 — Visual Workflow Builder

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
- **Bố cục & màu:** Node AI/ghi dùng viền amber (cần xác nhận); trạng thái ACTIVE = emerald.

---

## Slide 18 — AI Governance, Safety & Trust

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
  Provider masking · Guardrails · Sponsored separation. Có thể thêm dải "UsageContext" nhỏ (principal · org ·
  feature_key · billing_scope).
- **Số liệu:** "3 ledger · idempotency · 20 bộ eval AI · rate-limit 30/60/100".
- **Bố cục & màu:** Slide "niềm tin" → tông trung tính, chấm màu theo vai trò (info/success/warning).

---

## Slide 19 — Kiến trúc & Công nghệ *(platform-ready)*

- **Mục tiêu:** Thuyết phục hội đồng kỹ thuật + **chống lưng cho tầm nhìn nền tảng**: kiến trúc sạch, sẵn sàng mở rộng.
- **Nội dung chữ:** Tiêu đề: **"Kiến trúc DDD theo module — sạch, có kỷ luật, sẵn sàng thành nền tảng"**.
  - **Luồng request:** `Client (Next.js)` → `API (router + Pydantic)` → `Application (service, RBAC ở đây,
    transaction)` → `Domain (models thuần + repo interface)` → `Infrastructure (SQLAlchemy repo, adapter)` → `PostgreSQL`.
  - **Nguyên tắc bất di:** không import chéo module (giao tiếp qua service/event), không business-logic trong
    router, không ORM trong domain, **không JOIN đa-domain trực tiếp cho dashboard** (dùng read model /
    projection: `proj_student_dashboard`, `proj_partner_pipeline`, `proj_university_kpi`).
  - **Event-driven:** **outbox pattern** (`outbox_events` + `analytics_events`) do scheduler rút; **audit ở
    mọi ghi** (`audit_logs`). Pipeline là state machine có version (ADR-0004→0007).
  - **AI Gateway** provider-agnostic: task → chọn model → load-balance → adapter → fallback chain; UsageContext
    + Langfuse + output guard.
  - **→ Vì sao platform-ready:** **Organization multi-tenant RBAC** + **biên module cứng** + **AI gateway
    provider-agnostic** ⇒ có thể vận hành như **nền tảng đa-tổ chức/SaaS** mà không phá kiến trúc.
  - **Tech stack:**
    - *Backend:* Python 3.12 · **FastAPI** · SQLAlchemy 2 async + asyncpg · Pydantic v2 · **PostgreSQL 16 +
      pgvector** · Alembic · **Celery + Redis** · JWT + Argon2 + TOTP 2FA · OIDC/SAML SSO · AI gateway
      (OpenRouter/OpenAI-compatible/Gemini/Anthropic) · **Langfuse** · OCR (PyMuPDF4LLM, Tesseract vie+eng) ·
      pytest · ruff/mypy · **uv**.
    - *Frontend:* **Next.js 15 App Router** · React 19 · TypeScript 5.7 strict · **Tailwind v4 + shadcn/ui** ·
      lucide-react · TanStack Query + Zustand · Recharts · **next-intl (vi/en)** · `@xyflow/react` · `@dnd-kit`
      · Vitest + Playwright.
- **Trực quan hóa:** Trên/trái = **sơ đồ layered dọc** 5 tầng (mỗi tầng 1 băng ngang, nhãn trách nhiệm), băng
  "RBAC" gắn ở tầng Application; nhánh **AI Gateway** bên phải tô indigo-soft; dải đáy **Read Models · Outbox
  · Audit**. Dưới cùng = 2 hàng **chip công nghệ** (Backend / Frontend). Badge nhỏ *"multi-tenant-ready"* cạnh
  tầng Organization/RBAC.
- **Số liệu:** "34 module · biên DDD cứng · outbox + audit + read-model · multi-tenant RBAC".
- **Bố cục & màu:** Monochrome là chính; mỗi tầng 1 sắc xám; **AI Gateway** + badge multi-tenant tô indigo-soft.

---

## Slide 20 — Traction & Mục tiêu 12 tháng

- **Mục tiêu:** Cho hội đồng thấy đích đến đo được + vì sao khả thi (bằng dữ liệu thật). **Trung thực:** sản
  phẩm mới, chưa có traction thật → đây là **MỤC TIÊU 12 tháng**, KHÔNG phải số đã đạt.
- **Nội dung chữ:** Tiêu đề: **"Mục tiêu 12 tháng đầu — và vì sao khả thi"**.
  - **Vì sao khả thi (bằng chứng THẬT):**
    - VinUni khóa cử nhân đầu (2024): **32%** nhận offer từ **McKinsey, BCG, Google, IBM, Bosch…** *trước*
      tốt nghiệp; có mức lương tới **$7.500/tháng** ở nước ngoài → nền tảng *khuếch đại & đo lường* thế mạnh này.
    - Thị trường sẵn: **2,36 triệu** SV · **>940.000** doanh nghiệp · HR-tech VN hướng **~US$1 tỷ**.
    - Sản phẩm đã dựng (slide 6): 34 module · 120 màn hình · 4 bề mặt — sẵn sàng nhận người dùng ngay.
  - **Mục tiêu 12 tháng (targets — ghi rõ "mục tiêu", không phải đã đạt):**
    - **~2.500** SV VinUni active (~70% của 3.500) + alumni onboard.
    - **3.000+** CV tạo/upload · **5.000+** lượt ứng tuyển.
    - **60–100** đối tác tuyển dụng · **500+** JD đăng.
    - **100+** mentor alumni tham gia.
    - **≥90%** job kiểm duyệt trong SLA · career-outcome dashboard phủ **100%** khóa tốt nghiệp.
    - Chuyển đổi trả phí: mục tiêu **5–8%** SV ngoài mua Pro · **20–30** đối tác trả phí.
    - Mở rộng: **1–2** đơn vị/trường thí điểm ngoài VinUni (bàn đạp năm 2).
- **Trực quan hóa:** Trái = **hàng KPI-target tiles** (mỗi tile: nhãn + số mục tiêu lớn tabular + chip amber
  "mục tiêu 12T" để phân biệt rõ với số đã-đạt). Phải = **thẻ "Vì sao khả thi"** 3 proof-point (32% offer khóa
  đầu · thị trường 2,36M SV / 940k DN · sản phẩm đã dựng). Dưới: 1 phễu nhỏ *SV active → CV → ứng tuyển → offer*.
- **Số liệu:** như trên; badge "Targets · 12 tháng".
- **Bố cục & màu:** KPI-target tiles gắn chip amber "mục tiêu" (tách khỏi số đã-đạt); proof-point THẬT dùng
  emerald. Số dùng JetBrains Mono tabular.
- **⚠️ Ghi chú trung thực:** in rõ chữ **"Mục tiêu 12 tháng"** trên slide; đừng trình bày như traction đã đạt.
  Proof-point VinUni 32% là số THẬT (nguồn VinUni.edu.vn 2024) — để riêng, không trộn vào phần target.

---

## Slide 21 — Roadmap, Đường mở rộng & Kết luận

- **Mục tiêu:** Chốt bằng lộ trình khả thi + **đường mở rộng (GTM) + business ask** + logo.
- **Nội dung chữ:** Tiêu đề: **"Lộ trình rõ ràng — và một đường mở rộng có sẵn"**.
  - **6 phase (~36 tuần, đội nhỏ 2–3 kỹ sư + 1 AI engineer):** P0 Foundation (t1–3) · P1 Core Loops (t4–8) ·
    P2 Advanced Hiring/ATS (t9–14) · P3 AI Intelligence (t15–20) · P4 Events + Monetization (t21–27) *(+P4b
    realtime/messaging/workflow)* · P5 University Intelligence (t28–36: mentorship, alumni, career outcomes,
    tích hợp SIS).
  - **Đường mở rộng (beachhead → mở rộng, 3 chặng — đây là phần business đóng deck):**
    1. **VinUni sâu** *(bây giờ)* — dữ liệu xác thực + vòng lặp khép kín, 4 dòng doanh thu.
    2. **Alumni + SV ngoài + người đi làm** *(đã hỗ trợ, tăng trưởng người dùng trả phí)*.
    3. **Nền tảng độc lập / đa-trường** *(sẵn sàng kỹ thuật)* — thêm doanh thu license/SaaS theo tổ chức.
  - **Tầm nhìn:** *"Vòng lặp dữ liệu khép kín Học → Ứng tuyển → Tuyển dụng → Outcome → phản hồi vào chương
    trình học."*
  - **Ask / CTA:** *"Xin phê duyệt **triển khai thí điểm toàn trường VinUni** (Sinh viên + Đối tác + Career
    Services) trong học kỳ tới; kết nối **20–30 đối tác tuyển dụng** khởi động; cấp **nguồn lực vận hành + AI
    budget** cho 12 tháng đầu."*
  - **Kết:** Logo VinUni + **C2-Team-037** + liên hệ.
- **Trực quan hóa:** Trên = **timeline ngang 6 mốc** (P0→P5) với thanh tiến độ tô phần "đã dựng". Dưới = **3
  chặng mở rộng** dạng bậc thang đi lên (VinUni → Alumni/ngoài → Nền tảng) — chặng 3 nét đứt (*sẵn sàng, chưa
  cam kết*). Góc: logo VinUni + gradient hero khép lại (đối xứng slide 1). 1 dòng CTA nổi bật.
- **Số liệu:** "6 phase · ~36 tuần · 4 bề mặt đã dựng · 3 chặng mở rộng".
- **Bố cục & màu:** Timeline theo palette tăng dần; bậc thang mở rộng tô indigo→violet gradient (điểm nhấn cuối).
- **⚠️ Ghi chú trung thực:** chặng 3 là **tầm nhìn + sẵn-sàng-kỹ-thuật**; giữ nét đứt & từ "sẵn sàng", không
  hứa mốc thời gian mở SaaS nếu chưa có kế hoạch thật.

---

## 🔧 Danh sách placeholder cần bạn điền (trước khi pitch)

| Ký hiệu | Ở slide | Trạng thái |
|---|---|---|
| Tên team **C2-Team-037** | 1, 21 | ✅ Đã điền |
| Thị trường (TAM/SAM: 2,36M SV · 940k DN · 67 trường tư…) | 3 | ✅ Đã điền (số thật 2024, có nguồn) |
| Bảng giá (SV Pro 49k · Đối tác 2tr/5tr · license ~150tr/năm) | 7 | ✅ Đã điền (đề xuất, admin cấu hình) |
| Traction/KPI mục tiêu 12 tháng | 20 | ✅ Đã điền (targets + proof VinUni 32%) |
| Ask/CTA (thí điểm toàn trường + 20–30 đối tác + budget) | 21 | ✅ Đã điền |
| `[MÔN/CUỘC THI]` | 1 | ⬜ Bạn điền tên môn/cuộc thi |
| Logo + screenshot | 1, 5, 21 | ⬜ Copy từ `frontend/public/brand/` (xem `assets/README.md`) |

**Nguồn số liệu thị trường (2024):** Tổng cục Thống kê / Bộ GD&ĐT VN (2,36M SV; 314k cử nhân; 243 trường,
67 tư); NSO/VietnamNet (>940k doanh nghiệp); imarcgroup/kenresearch (HR-tech VN); VinUni.edu.vn (khóa đầu
145 cử nhân + 32% offer, 2024). Giá gói là **đề xuất hợp lý cho thị trường VN**, admin cấu hình được.

**Nguyên tắc vàng:** *quy mô/kỹ thuật* dùng số code-verified; *thị trường* dùng số thật có nguồn; *giá & KPI*
là **đề xuất/mục tiêu** (ghi rõ để không nhầm là số đã đạt). Câu chuyện *nền tảng* = **tầm nhìn + sẵn-sàng-kỹ-
thuật**, không phải cam kết V1.
