# VinUni Career Platform

**Hệ điều hành nghề nghiệp AI-native dành riêng cho VinUniversity.**

> Không phải một trang tuyển dụng, cũng không phải một sản phẩm SaaS bán cho nhiều trường — đây là nền tảng nội bộ chính thức của VinUni, hợp nhất toàn bộ hành trình nghề nghiệp của sinh viên, cựu sinh viên, nhà tuyển dụng đối tác và bộ phận hướng nghiệp vào một hệ thống duy nhất, nơi AI hỗ trợ **thực chất** ở mọi bước chứ không phải để trang trí.

---

## Mô tả ngắn (thẻ Demo Day)

> **VinUni Career Platform** là "hệ điều hành nghề nghiệp" AI-native dành riêng cho VinUniversity, kết nối sinh viên – cựu sinh viên – nhà tuyển dụng – nhà trường trên một nền tảng duy nhất. AI hỗ trợ thực chất ở mọi bước: tạo & tối ưu CV theo phong cách Canva, chấm điểm độ phù hợp CV–JD, luyện phỏng vấn có phản hồi, quản lý toàn bộ vòng đời tuyển dụng và đo lường kết quả việc làm sau tốt nghiệp.

*(Bản 1 dòng cho thẻ hẹp: "Nền tảng nghề nghiệp AI-native của VinUni: tạo CV thông minh, chấm độ phù hợp CV–JD, luyện phỏng vấn AI và quản trị tuyển dụng end-to-end.")*

---

## Mô tả chi tiết

### 1. Bài toán

Trải nghiệm nghề nghiệp trong trường đại học ngày nay bị **phân mảnh** trên hàng loạt công cụ rời rạc, và mỗi nhóm người dùng đều "đau" theo một cách rất cụ thể:

- **Sinh viên & cựu sinh viên** phải xoay xở giữa một job board chung (TopCV, VietnamWorks), LinkedIn, CV viết bằng Word và email. Họ **nộp hồ sơ trong vô định** — không biết CV của mình có khớp với JD không, mức độ cạnh tranh ra sao, hay nên dùng CV nào cho vị trí nào. CV yếu, không được "may đo" bị loại ngay từ vòng lọc. Không có vòng phản hồi về mức độ sẵn sàng nghề nghiệp, cũng không có nơi luyện phỏng vấn.
- **Nhà tuyển dụng / đối tác** nhận về một "cơn lũ" hồ sơ nhiễu, khó tìm được ứng viên phù hợp. Họ thiếu một ATS nhẹ nhàng: không có pipeline nhiều vòng cấu hình được, không có phân quyền theo đội nhóm, không có scorecard, không có tìm kiếm ứng viên thụ động trong một nguồn sinh viên đã được xác thực. Các ATS doanh nghiệp (Greenhouse, Workday) thì quá nặng và không "sinh ra cho môi trường đại học".
- **Bộ phận hướng nghiệp của trường** vận hành trong **mù thông tin**: không kiểm soát được ai đăng tin, khó kiểm duyệt nội dung/quảng cáo ở quy mô lớn, không đo được kết quả việc làm, không đưa dữ liệu khoảng trống kỹ năng ngược lại chương trình đào tạo, và không kiểm soát được chi phí/chất lượng AI. Họ không có các "read model" cấp thể chế cho tỷ lệ có việc, mức lương trung bình, thời gian tuyển dụng hay báo cáo kiểm định.
- **Cả hệ sinh thái** thiếu một ranh giới đáng tin cậy giữa nội dung tự nhiên, nội dung được gợi ý, nội dung tài trợ (quảng cáo) và nội dung được nhà trường tuyển chọn — và thiếu một mô hình quyền riêng tư "consent-first" cho dữ liệu sinh viên.

**Luận điểm sản phẩm:** thay thế chuỗi công cụ rời rạc bằng **một hệ sinh thái được xác thực, có AI hỗ trợ, và được nhà trường quản trị**, nơi AI giúp ích thực chất ở từng bước — chứ không phải một lớp "AI trang trí".

### 2. Giải pháp — một "hệ điều hành nghề nghiệp" thống nhất

Nền tảng phục vụ **bốn màn hình vận hành (operating surface)** riêng biệt — mỗi màn hình là một "trung tâm điều khiển" hằng ngày, không phải một trang chào mừng chung chung:

| Nhân vật | Nhận được gì |
|---|---|
| **Public / Khách (chưa đăng nhập)** | Cổng marketplace nghề nghiệp: duyệt việc làm, công ty, sự kiện, khám phá lương (tổng hợp), gợi ý cá nhân hoá theo phiên (privacy-safe). Các hành động cần đăng nhập (nộp, lưu, xem lương chi tiết, AI) giữ lại ý định của người dùng. |
| **Sinh viên / Người tìm việc** | 4 hạng cấu hình được (Sinh viên VinUni tự xác thực qua SSO/SIS, Cựu sinh viên tự nâng cấp khi tốt nghiệp, Sinh viên ngoài, Người dùng phổ thông). Nhận: CV Studio, chấm điểm phù hợp CV–JD, khám phá cá nhân hoá, trợ lý AI, mô phỏng phỏng vấn, theo dõi hồ sơ, sự kiện. |
| **Đối tác / Nhà tuyển dụng** | Một "recruiting OS": người đăng ký đầu tiên thành Admin tổ chức, tự tạo phòng ban, vai trò và **ma trận phân quyền chi tiết** (tin tuyển, ứng viên, phỏng vấn, offer, talent pool, tìm kiếm thụ động, phân tích, quảng cáo, sự kiện, thanh toán). Nhận: quản lý pipeline, so sánh ứng viên, tìm kiếm ứng viên thụ động, offer, quảng cáo, sự kiện, phân tích. |
| **Quản trị Nhà trường (System Admin)** | "Trung tâm vận hành nền tảng": hàng đợi kiểm duyệt có SLA, quản trị đối tác/mức độ tin cậy, RBAC, quản trị nhà cung cấp AI, phân tích kết quả việc làm, báo cáo tài chính, tự động hoá workflow và audit toàn diện. **Platform Superadmin** là tầng riêng — người duy nhất thấy danh tính nhà cung cấp/mô hình AI thật. |

Trên nền đó là **~34 module nghiệp vụ**, trong đó những màn hình chủ lực gồm:

- **CV Studio** — trình biên tập tài liệu A4 trực quan kiểu Canva (không phải form): chợ template được nhà trường duyệt, chỉnh chữ tại chỗ, kéo–thả khối, thay/cắt ảnh, tự lưu, versioning, xuất PDF. Với CV có sẵn: luồng **"tải lên & đặt tên"**, backend tự trích xuất dữ liệu có cấu trúc. AI soạn/điền/viết lại CV dưới dạng **diff có thể xem lại** — không bao giờ sửa CV một cách âm thầm.
- **Opportunities (Marketplace việc làm)** — tin tuyển với 5 mức hiển thị, tìm kiếm ngữ nghĩa (hiểu ý định, chịu lỗi chính tả, biến thể tiếng Việt), bộ lọc, tin tài trợ với nhãn **"Được tài trợ"** bắt buộc, trang công ty, khám phá lương.
- **Khám phá & Gợi ý cá nhân hoá** — sinh viên đã đăng nhập thấy **điểm phù hợp CV–JD 0–100 kèm giải thích và mã lý do**, CV nào nên dùng cho JD nào, và **thông tin cạnh tranh (competition intelligence)** dựa trên tín hiệu thật (số ghế, khối lượng ứng tuyển, phân bố chất lượng, phân vị của bạn, độ mới của deadline) — không bao giờ lộ PII của ứng viên khác.
- **Recruitment Pipeline (lõi ATS)** — pipeline nhiều vòng cấu hình theo từng tin: giai đoạn có tên, loại giai đoạn (duyệt CV, bài test, phỏng vấn video/onsite, offer…), người phụ trách theo phòng ban/cá nhân, SLA, tự động chuyển vòng, scorecard, rollback/reject/escalate, xem Kanban + danh sách, so sánh ứng viên, template tái sử dụng.
- **Trợ lý nghề nghiệp AI (chatbot)** — tác nhân hội thoại streaming với **33 công cụ được quản trị** (tìm việc, phân tích CV, giải thích độ phù hợp, khoảng trống kỹ năng, benchmark lương, luyện phỏng vấn, kiểm tra "cờ đỏ" JD…). Hành động ghi (nộp, lưu, tối ưu CV, đặt alert) **luôn cần xác nhận của người dùng**.
- **Mô phỏng phỏng vấn AI** — sinh câu hỏi bám sát JD + CV, phản hồi từng câu trả lời (điểm 1–5 + điểm mạnh/điểm cần cải thiện/gợi ý). *(Xem mục 3.3.)*
- **Sự kiện, Quảng cáo, Workflow Builder trực quan, Messaging thể chế, Thông báo đa kênh, Kết quả việc làm & Trí tuệ chương trình đào tạo, và Platform Admin / Quản trị AI** — bao phủ toàn bộ vòng đời.

**Mô hình kinh doanh** (đều thuộc sở hữu VinUni, không có doanh thu "license cho trường khác"): gói đối tác (hạn mức đăng tin, spotlight), quảng cáo đối tác (banner, tin tài trợ, email blast), gói đăng ký của người dùng (mua thêm tín dụng AI/tính năng cao cấp), và gói sự kiện. V1 dùng thanh toán chuyển khoản thủ công; các cổng VNPay/MoMo/ZaloPay là giai đoạn sau.

### 3. Giải pháp kỹ thuật

Đây không phải một sản phẩm demo — nó là một **hệ thống kỹ thuật quy mô sản xuất**, thiết kế theo Domain-Driven Design với ranh giới module rõ ràng.

#### 3.1. Kiến trúc & công nghệ

| Lớp | Công nghệ |
|---|---|
| **Backend** | Python 3.12 · FastAPI (async) · SQLAlchemy 2.0 async · Pydantic v2 · Alembic · **PostgreSQL 16 + pgvector** (embedding/RAG) + pg_trgm/unaccent (tìm kiếm tiếng Việt không dấu) · Redis + Celery (tác vụ nền) · PyMuPDF/pdfplumber/Tesseract (OCR `vie+eng`) · argon2 + PyJWT + TOTP 2FA |
| **Frontend** | Next.js 15 (App Router, React Server Components) · React 19 · **TypeScript strict** · Tailwind CSS 4 · next-intl (song ngữ vi/en) · TanStack Query + Zustand · React Hook Form + Zod · React Flow (workflow builder) · Recharts |
| **AI** | Cổng AI trung lập nhà cung cấp (provider-agnostic) · registry bí danh mô hình · fallback chain + circuit breaker · RAG hybrid (pgvector + BM25 + RRF) + reranker · khoá API mã hoá AES tại chỗ |
| **Chất lượng** | ruff · mypy · pytest (asyncio) · TypeScript `tsc` · ESLint · Playwright E2E · Vitest · pre-commit · kiểm tra đồng bộ i18n vi/en |

**Phong cách kiến trúc:**
- **Modular monolith** phân tầng nghiêm ngặt cho từng module: `api/` (chỉ HTTP) → `application/` (use case, RBAC, transaction) → `domain/` (thực thể & bất biến) → `infrastructure/` (repository, adapter ngoài).
- **Event-driven qua Transactional Outbox** (`outbox_events`) — đảm bảo giao dịch nhất quán, publish sau khi persist, retry/backoff, dead-letter.
- **CQRS / read-model materialized** cho mọi dashboard (`proj_student_dashboard`, `proj_partner_pipeline`, `proj_university_kpi`) — cấm join đa domain trực tiếp trên dashboard.
- **RBAC thực thi ở tầng service** (không chỉ ở router), vai trò/phòng ban cấu hình được (không hardcode tên vai trò), **audit trên mọi thao tác ghi**, soft delete, optimistic concurrency, cô lập đa tổ chức (tenant).
- Được định hướng bởi **14 ADR** (stage engine tuyển dụng, scorecard, phỏng vấn, offer, sự kiện, quảng cáo, subscription, messaging, mức độ tin cậy nền tảng…).

#### 3.2. Hệ AI — vì sao *không phải* "một cái vỏ bọc ChatGPT"

AI ở đây là **kỹ thuật hệ thống cấp sản xuất**, không phải chuyển tiếp prompt:

1. **Cổng AI trung lập nhà cung cấp** — mọi lời gọi đi qua một giao diện duy nhất; không module nào chạm trực tiếp vào SDK của nhà cung cấp. Có **circuit breaker** theo từng nhà cung cấp (ngưỡng 5 lỗi, mở 60s, dò half-open) + **chuỗi fallback có thứ tự** (A→B→C) chỉ nhảy khi gặp lỗi khả dụng tạm thời.
2. **Chấm điểm CV–JD tất định (deterministic)** — trái tim kỹ thuật: một điểm sản phẩm 0–100 **thuần tất định** (cùng đầu vào → cùng điểm, nên xếp hạng/cache/kiểm thử được, và **giải thích được mà không cần gọi mô hình**), version-stamp để tự tính lại khi thuật toán đổi. 6 band trọng số theo HR thật (kỹ năng 0.30, kinh nghiệm 0.22, phạm vi/tác động 0.15, bằng cấp 0.13, kỹ năng mềm 0.10, quỹ đạo 0.10), có cổng năng lực (CV sai ngành bị hạ điểm để kỹ năng mềm không "cứu" được), taxonomy 13 ngành (vi+en), toán tenure theo khoảng ngày thật, và **so khớp đa ngôn ngữ bằng chuẩn hoá dịch** ("quản lý chuỗi cung ứng" khớp "supply chain management"). *Nhóm phát triển thậm chí đã A/B-test và **loại bỏ** một tầng embedding vì thực nghiệm cho thấy nó không hoạt động (recall 0) — quyết định dựa trên bằng chứng, không theo hype.*
3. **Mô hình không bao giờ được tin để tạo cấu trúc/dữ kiện** — chỉnh CV bằng ngôn ngữ tự nhiên đi qua một **allowlist 9 thao tác được validate** + kiểm tra bịa đặt (fabrication check); trích xuất được validate; câu trả lời RAG được **xác minh trích dẫn** (nguồn không có thật bị thay bằng cụm an toàn).
4. **Cascade trích xuất CV theo bậc chi phí** — text gốc (miễn phí) → OCR cục bộ (Tesseract) → **vision-LLM giá rẻ** chỉ cho ảnh/PDF scan nhiều cột. Đầu ra **có cấu trúc, sẵn sàng cho matching** (một mục cho mỗi công việc/bằng cấp; kỹ năng có mức 0–100). File rỗng/không-phải-CV/hỏng bị từ chối rõ ràng và **không bao giờ bị bịa thành CV**.
5. **Đo lường, hạn mức & ngân sách đầy đủ** — mọi lời gọi AI có giá trị đi qua `UsageContext` với **sổ cái tín dụng bền vững + idempotency** (retry/redelivery không bao giờ tính phí hai lần). Chỉ tính phí khi có **kết quả thành công hiển thị cho người dùng**; chấm điểm tất định, OCR cục bộ và lỗi provider là **miễn phí**. Kiệt hạn mức được định tuyến theo nhân vật: sinh viên → nâng gói; đối tác → gói tổ chức; nhân sự nhà trường → quy trình xin cấp thêm với admin (không bao giờ là lời mời mua hàng).
6. **An toàn & riêng tư như một cổng chặn** — `input_guard` che PII **trước khi** mô hình nhìn thấy (email, số điện thoại VN, CCCD/CMND, khoá API) và chặn các mẫu prompt-injection; `output_guard` bôi xoá mọi rò rỉ tên nhà cung cấp/mô hình/token; **người dùng cuối không bao giờ biết mô hình nào trả lời**.
7. **Đánh giá (eval) như một cổng CI** — **19 họ eval**, mỗi họ đủ 5 nhóm (happy-path, đối kháng, ranh giới riêng tư, đầu vào kém, fallback); PR bị **chặn merge** nếu có bài ranh-giới-riêng-tư bị rò rỉ hoặc tỉ lệ happy-path < 80%.

#### 3.3. Điểm nhấn: Mô phỏng phỏng vấn AI (*đang được mở rộng*)

Phỏng vấn được triển khai như **ba bề mặt kết nối**, đóng kín vòng lặp từ luyện tập của sinh viên đến phỏng vấn thật của nhà tuyển dụng:

- **Luyện phỏng vấn / mô phỏng cho sinh viên** — AI sinh **3–10 câu hỏi có cấu trúc** (loại: behavioral / technical / situational / motivation; kèm `hint` và `rubric`) **bám sát JD** (tiêu đề, công ty, mô tả, kỹ năng yêu cầu) cộng ngữ cảnh tuỳ chọn của sinh viên. Người dùng trả lời từng câu và nhận **phản hồi coaching (điểm 1–5 + khen / cần cải thiện / gợi ý)**. Màn hình mô phỏng có vòng điểm động, tiến trình từng câu và màn tổng kết (điểm trung bình, câu mạnh/yếu nhất). Mọi lời gọi AI **suy giảm mượt mà** về ngân hàng câu hỏi tĩnh khi mất kết nối (gắn cờ `is_fallback`, không bao giờ ném lỗi).
- **Công cụ mock phỏng vấn trong chatbot** — trợ lý AI chạy nhanh một câu hỏi mô phỏng theo vòng ngay trong hội thoại.
- **Pipeline phỏng vấn thật cho nhà tuyển dụng** — đối tác lên lịch phỏng vấn theo giai đoạn hồ sơ, với người phỏng vấn được phân công, **link họp mã hoá Fernet tại chỗ**, nhắc lịch T-24h/T-1h idempotent và cổng scorecard chặn chuyển vòng. Ứng viên ẩn danh phải qua "reveal handshake" trước khi lên lịch.

**Đang xây dựng (bản demo này đang hoàn thiện):** một lớp **"trí nhớ phỏng vấn" (interview memory)** — lưu lịch sử luyện tập theo phiên (thuộc phạm vi sinh viên, audit chỉ trên metadata) và một **điểm sẵn sàng phỏng vấn tất định 0–100** với band `developing → emerging → progressing → interview_ready`, xu hướng cải thiện/giảm sút, và trạng thái trung thực `not_enough_data` khi chưa đủ dữ liệu (không bao giờ bịa số). Tính năng được nối vào hệ **"năng lượng AI" (AI energy)** dùng chung để tính hạn mức công bằng, kèm test cho lịch sử, độ sẵn sàng và metering.

Điểm đáng pitch về kỹ thuật: câu hỏi chỉ sinh từ dữ kiện thật của JD (không bịa thông tin công ty/lương); **hai prompt phiên bản riêng** cho sinh câu hỏi (temp 0.5) và chấm câu trả lời (temp 0.3, điểm kẹp 1–5); điểm sẵn sàng **tính không cần gọi mô hình** (tái lập được, trung thực); mọi văn bản tự do qua `input_guard`; prompt cấm câu hỏi phân biệt đối xử; câu trả lời luyện tập **không bao giờ hiển thị cho nhà tuyển dụng**.

### 4. Tính khả thi

Đây không phải slide ý tưởng — nó là một **codebase đang chạy được đầu-cuối**. Vài con số đo trực tiếp từ mã nguồn:

| Hạng mục | Quy mô |
|---|---|
| Module nghiệp vụ backend | **34** |
| Endpoint REST | **455** (trên 78 router) |
| Bảng cơ sở dữ liệu | **126** (87 migration Alembic có upgrade/downgrade) |
| Test backend | **1.893 hàm test** trên 182 file (~48k dòng test) |
| Công cụ AI trong trợ lý | **33** (RBAC theo nhân vật; mọi tool "ghi" bắt buộc thẻ xác nhận + audit) |
| Họ dữ liệu đánh giá AI | **19** (mỗi họ 5 nhóm; leak-check bắt buộc pass 100%) |
| Prompt pack phiên bản hoá | **~30** |
| Route giao diện | **117** (song ngữ vi/en) trên **342** component |
| Tổng mã ứng dụng | **~227.000 dòng** (114k backend + 112k frontend) |

**Đã chứng minh chạy được (local):** đăng nhập/2FA, tạo & tối ưu CV, tải CV lên và trích xuất có cấu trúc, chấm điểm CV–JD kèm giải thích, nộp hồ sơ với snapshot CV bất biến, pipeline tuyển dụng nhiều vòng, chatbot AI **gọi công cụ thật** (đã smoke-test với lời gọi AI thật, chi phí ~$0.0001/lượt nhờ định tuyến mô hình giá rẻ), luyện phỏng vấn AI với fallback, và lịch phỏng vấn phía nhà tuyển dụng.

**Trung thực về trạng thái (một điểm cộng về độ tin cậy):** dự án phân biệt rạch ròi các mức `implemented` / `API wired` / `browser verified` / `E2E verified` thay vì tuyên bố "hoàn thành" chung chung. Hệ thống đang ở giai đoạn **beta/hardening**: phần lớn cổng chất lượng đã xanh, với một số ít mục đang được ổn định — tất cả theo dõi công khai trong `docs/IMPLEMENTATION_STATUS.md` kèm lệnh chạy và bằng chứng pass/fail.

**Về vận hành, nền tảng được thiết kế local-first** (không bắt buộc Docker để chạy app), OCR/AI/email đều nhẹ theo mặc định, nên dễ chạy demo và dễ mở rộng dần lên hạ tầng thật.

Điểm cộng về quy trình: sản phẩm được xây bằng một **quy trình kỹ thuật kỷ luật, lấy tài liệu làm nguồn sự thật** (một bộ ~27 tài liệu đặc tả sản phẩm/kiến trúc/bảo mật/AI) cùng các cổng chất lượng tự động — cho thấy khả năng đưa một hệ thống lớn từ đặc tả đến sản phẩm chạy được một cách bài bản.

### 5. Hướng phát triển

**Ngắn hạn (đang làm / kế tiếp):**
- Hoàn thiện **trí nhớ & độ sẵn sàng phỏng vấn**, tiến tới chế độ phỏng vấn nhập vai (hội thoại/giọng nói) với câu hỏi đào sâu thích ứng.
- Đóng các cổng chất lượng còn lại và nâng độ phủ **E2E verified** cho các luồng trọng yếu (đăng ký → CV → nộp → pipeline → offer).
- Kiểm thử trình duyệt & khả năng tiếp cận (WCAG 2.1 AA) trên breakpoint 375/768/1024/1440, hai theme sáng/tối.

**Trung hạn:**
- **Tích hợp sâu hệ VinUni**: SSO/IdP (OIDC/SAML), đồng bộ SIS (nhập học/tốt nghiệp), lịch học thuật (định thời gợi ý việc/thực tập), dashboard chỉ-đọc cho giảng viên.
- **Vòng lặp trí tuệ chương trình đào tạo**: đưa dữ liệu khoảng trống kỹ năng ("83% hồ sơ CS bị loại vì thiếu kỹ năng cloud") ngược lại cho khoa/chương trình.
- Cổng thanh toán VNPay/MoMo/ZaloPay; phân tích tuyển dụng & báo cáo kiểm định nâng cao.

**Dài hạn / quy mô sản xuất:**
- Triển khai production theo mục tiêu phi chức năng đã đặt trong đặc tả: **~5.000 người dùng đồng thời** (thiết kế cho 20.000), **500.000+ CV**, uptime 99,5%, p95 API < 500ms, mã hoá CV AES-256, audit lưu 2 năm.
- Mở rộng độ phủ eval AI, giám sát online (lấy mẫu 1% để con người rà soát), và tiến tới ứng dụng di động.

---

<sub>VinUni Career Platform · nền tảng nội bộ dành riêng cho VinUniversity · thiết kế "Monochrome" tối giản cao cấp, song ngữ Việt–Anh. AI luôn là cố vấn — con người ra quyết định cuối cùng; danh tính nhà cung cấp/mô hình AI được ẩn hoàn toàn khỏi người dùng cuối theo nguyên tắc AI có trách nhiệm.</sub>
