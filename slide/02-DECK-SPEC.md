# DECK SPEC — 15 slide pitch "VinUni Career Platform"

> **Nguồn chân lý của deck là code:** `slide/build_deck.py` sinh ra 15 file `slide/deck/slide-01…15.html`
> (+ `deck.html` để trình chiếu / in PDF). File này mô tả nội dung từng slide để đối chiếu, chỉnh sửa, hoặc
> đưa cho Claude Design tinh chỉnh. Muốn đổi nội dung → sửa `build_deck.py` → chạy `python3 slide/build_deck.py`.
>
> **Nguyên tắc:** mỗi slide MỘT ý chính, kín canvas nhưng có tổ chức (kiểu infographic tư vấn); tiêu đề là
> ngôn ngữ pitch chuẩn (Vấn đề, Giải pháp, Quy mô thị trường, Mô hình kinh doanh, Lợi thế cạnh tranh, Kết quả
> đạt được, Kiến trúc, Công nghệ, Lộ trình, Lời mời hợp tác); từ ngữ tự nhiên như người thuyết trình thật —
> không dùng buzzword. Footer mọi slide: trái `C2-Team-037`, phải `NN / 15`.
>
> **Số liệu:** quy mô hệ thống = đếm từ mã nguồn; thị trường & đối thủ = số thật có nguồn (ghi ở chân slide);
> giá & KPI = đề xuất/mục tiêu (ghi rõ chữ "mục tiêu"). Không bịa số.

---

## Bố cục 4 phần (slide 2 là mục lục)

| Phần | Slide | Nội dung |
|---|---|---|
| Phần 1 — Vấn đề & Giải pháp | 03–06 | Hành trình đứt gãy · nền tảng 4 phân hệ · sản phẩm thật · tính năng AI |
| Phần 2 — Thị trường & Kinh doanh | 07–09 | Quy mô thị trường · mô hình doanh thu · lợi thế cạnh tranh |
| Phần 3 — Kết quả & Công nghệ | 10–12 | Kết quả đạt được · kiến trúc hệ thống · công nghệ sử dụng |
| Phần 4 — Lộ trình & Hợp tác | 13–15 | Lộ trình phát triển · mục tiêu 12 tháng · lời mời hợp tác |

---

## Slide 01 — Trang bìa
- Logo thật `assets/logo-dark-480.png` + "VINUNI CAREER · C2-TEAM-037 · THÁNG 7/2026".
- Tiêu đề "VinUni Career Platform"; phụ đề: *Nền tảng việc làm & phát triển sự nghiệp cho hệ sinh thái VinUni*.
- 1 câu giá trị: kết nối sinh viên – doanh nghiệp – nhà trường, AI hỗ trợ từng bước.
- Phải: **laptop mockup** chứa screenshot thật trang tổng quan sinh viên. Chip: "Sản phẩm đã hoạt động · 4 phân hệ · Song ngữ".

## Slide 02 — Nội dung trình bày (agenda)
- 4 card đánh số Phần 1–4 (icon + mô tả + dải slide) + 1 dòng elevator pitch có logo.

## Slide 03 — Vấn đề: "Hành trình tìm việc của sinh viên đang đứt gãy"
- **Hàng trên:** hành trình 5 bước (Tìm tin → Chuẩn bị CV → Nộp đơn → Chờ phản hồi → Phỏng vấn), mỗi bước một
  điểm nghẽn ✕ đỏ.
- **Hàng giữa:** hệ quả cho 3 bên (Sinh viên / Doanh nghiệp / Nhà trường) — card icon + 1 dòng.
- **Băng dưới (viền đỏ):** vì sao chưa ai giải quyết — ATS quá nặng · job board dừng ở nộp đơn · tự xây tốn kém.

## Slide 04 — Giải pháp: "Một nền tảng cho cả ba bên"
- 4 card phân hệ (tên tiếng Việt tự nhiên): Cổng việc làm công khai · Không gian sinh viên · Bộ máy tuyển dụng ·
  Trung tâm điều hành — mỗi card 3 gạch ✓.
- Phải: **panel gradient duy nhất** "AI hỗ trợ xuyên suốt" (chấm điểm 0–100, hỏi trước khi ghi, đo từng lượt).

## Slide 05 — Sản phẩm: "Giao diện thực tế của sản phẩm"
- Laptop lớn (tổng quan sinh viên) + 3 browser mockup (CV Studio 7 mẫu · pipeline doanh nghiệp · kết quả việc
  làm của trường) — 4 screenshot THẬT trong `assets/shot-*.png`.
- Băng dưới: chip các tính năng thật khác (ứng tuyển & theo dõi đơn, trợ lý AI, phỏng vấn thử, kho ứng viên,
  sự kiện, quảng cáo có nhãn, kiểm duyệt, tin nhắn/thông báo, báo cáo việc làm).

## Slide 06 — Tính năng AI: "AI hỗ trợ trong từng bước ứng tuyển"
- 3 card demo trực quan: (1) donut **87/100** + 4 thanh trọng số (Kỹ năng 50 · Kinh nghiệm 25 · Chất lượng CV
  15 · Điều kiện 10) — chấm điểm tất định, không tốn phí AI; (2) sửa CV bằng câu lệnh — dòng gạch đỏ → dòng
  xanh + nút Chấp nhận/Từ chối ("bạn duyệt, AI mới được sửa"); (3) trợ lý ảo + thẻ "Xác nhận nộp đơn?" + chip
  phỏng vấn thử theo đúng tin tuyển.

## Slide 07 — Quy mô thị trường
- Trái: **phễu 4 thanh**: 2,36 triệu SV (TAM) → >940.000 DN → 314.000 cử nhân/năm (SAM) → 3.500+ SV & cựu SV
  VinUni (khởi đầu). Nguồn chân slide: TCTK/Bộ GD&ĐT 2024 · VietnamNet · IMARC (~US$1 tỷ HR-tech).
- Phải: "Vì sao là lúc này?" (AI rẻ · kiểm định cần số liệu · Gen-Z) + **kiểm chứng thị trường**: Handshake
  (Mỹ) 20 triệu SV, 1.400 trường, định giá **3,5 tỷ USD** — VN chưa có ai làm + lộ trình mở rộng 3 chặng.

## Slide 08 — Mô hình kinh doanh
- 4 dòng doanh thu (ai trả + giá neo): Gói doanh nghiệp 2–5tr₫/th · Quảng cáo từ 500k₫/tin (luôn nhãn "Được
  tài trợ") · Gói SV Pro 49k₫/th (SV ngoài) · Sự kiện từ 10tr₫.
- Phải: **panel gradient** "Dùng AI bao nhiêu, tính bấy nhiêu" — SV VinUni miễn phí; hết hạn mức mua thêm;
  trường khác: giấy phép ~150tr₫/năm. Ghi chú: giá đề xuất; V1 chuyển khoản.

## Slide 09 — Lợi thế cạnh tranh (slide dày số liệu nhất)
- **Hàng trên — 4 card đối thủ + 1 card VinUni (viền gradient ★):** mỗi đối thủ có số thật:
  - LinkedIn — mạng nghề nghiệp toàn cầu — >1 tỷ thành viên; chi phí tuyển rất cao. ✕ không gắn trường.
  - TopCV·VNWorks — job board số 1 VN — 9,5 triệu+ người dùng, 200.000+ DN, vốn Mynavi. ✕ dừng ở nộp đơn.
  - Handshake — campus career Mỹ — 20 triệu SV, 1.400+ trường, định giá 3,5 tỷ USD. ✕ chưa vào VN.
  - Greenhouse — ATS doanh nghiệp — TPG rót 500 triệu USD. ✕ đắt, không dành cho SV.
  - VinUni Career ★ — gắn trực tiếp với trường · AI chấm CV từng tin · theo trọn quy trình · miễn phí SV VinUni.
- **Bảng so sánh ✓/△/✕** 4 tiêu chí × 5 cột (cột VinUni tô nền).
- **Insight:** mô hình campus career được định giá 3,5 tỷ USD ở Mỹ — VN chưa có nền tảng tương đương.
  Nguồn: Forbes/PRNewswire 2022 · TopCV.vn · Mynavi.

## Slide 10 — Kết quả đạt được
- 6 KPI tile (số đếm từ mã nguồn): **34** phân hệ backend · **120** màn hình · **2.022** bài kiểm thử · **20**
  bộ đánh giá AI · **2** ngôn ngữ · **4** nhóm người dùng.
- Băng emerald: khóa cử nhân đầu VinUni (2024) — **32% nhận việc trước tốt nghiệp** (McKinsey, BCG, Google, IBM…).

## Slide 11 — Kiến trúc hệ thống
- 3 khối nối mũi tên, **logo công nghệ thật**: Giao diện (Next.js 15, React 19, TS, Tailwind — 120 màn hình,
  song ngữ, sáng/tối) → Xử lý nghiệp vụ (FastAPI, Python 3.12 — 34 phân hệ độc lập, phân quyền tầng dịch vụ,
  nhật ký mọi thao tác) → Dữ liệu & AI (PostgreSQL 16 + pgvector, Redis, Cổng AI — tìm kiếm ngữ nghĩa, hàng
  đợi Celery, nhiều nhà cung cấp AI tự dự phòng).
- Băng hạ tầng: Docker · DigitalOcean · Sentry + chip "thiết kế nhiều tổ chức — thêm trường mới không viết lại".

## Slide 12 — Công nghệ sử dụng (đậm chất hệ thống thật)
- Trái: lưới 12 logo công nghệ + chip "AI có kiểm soát" (đo từng lượt, hỏi trước khi ghi, không lộ nhà cung
  cấp, giới hạn tần suất, nhật ký) + card **"Khi có sự cố thì sao?"**: AI lỗi → tự chuyển nhà cung cấp dự
  phòng; chấm điểm CV là thuật toán tất định — chạy cả khi không có AI; OCR xử lý ngay trên máy chủ, ảnh gửi
  AI được hạ độ phân giải.
- Phải: card **"Đọc CV tự động — PDF, Word, ảnh scan"** 5 bước gắn nhãn chi phí (chặn file hỏng → đọc chữ
  PDF/Word miễn phí → OCR tiếng Việt+Anh miễn phí → AI đọc ảnh khi cần → chuẩn hoá kỹ năng 0–100); chú thích:
  file không phải CV bị từ chối rõ ràng — không bao giờ bịa dữ liệu.

## Slide 13 — Lộ trình phát triển
- 4 cột mốc nối nhau, mỗi mốc 3 bullet: **Xây dựng nền tảng (✓ đã xong)** → Thí điểm toàn trường (Q3/2026) →
  Vận hành chính thức (2027) → Mở rộng (sau 2027, viền đứt — cấp phép ~150tr₫/năm/trường).
- Băng dưới: chi phí thí điểm chủ yếu là vận hành + ngân sách AI.

## Slide 14 — Mục tiêu 12 tháng tới
- Phễu mục tiêu (mỗi thanh gắn chip amber "mục tiêu"): 2.500 SV dùng (~70%) → 3.000+ CV → 5.000+ lượt ứng
  tuyển → 60–100 doanh nghiệp.
- Card "Cam kết vận hành": 100+ cố vấn cựu SV · 90% tin duyệt đúng hạn · 5–8% người ngoài trả phí · 1–2 đơn vị
  ngoài VinUni dùng thử. Chân: vì sao khả thi (sản phẩm xong, 32% khóa đầu, thị trường 2,36M SV).

## Slide 15 — Lời mời hợp tác
- **Panel gradient**: logo + "Cùng đưa VinUni Career vào học kỳ tới" + 3 đề nghị: (1) phê duyệt thí điểm toàn
  trường; (2) giới thiệu 20–30 doanh nghiệp đối tác; (3) ngân sách vận hành 12 tháng. Chip C2-Team-037 + email.
- Phải: **ảnh thật khuôn viên VinUni** + băng "Học tập → Ứng tuyển → Đi làm → Phản hồi về trường" (vòng tròn khép kín).

---

## Nguồn số liệu

| Nhóm | Số | Nguồn |
|---|---|---|
| Quy mô hệ thống | 34 phân hệ · 120 màn hình · 2.022 test · 20 bộ eval AI | đếm trực tiếp từ mã nguồn repo |
| Thị trường VN 2024 | 2,36M SV · 314k cử nhân/năm · >940k DN · 243 trường | Tổng cục Thống kê / Bộ GD&ĐT · VietnamNet |
| HR-tech VN | hướng tới ~US$1 tỷ | IMARC / Ken Research |
| VinUni | ~3.500 SV công suất · khóa đầu 32% nhận việc sớm | vinuni.edu.vn (2024) |
| TopCV | 9,5 triệu+ người dùng · 200.000+ DN · vốn Mynavi | topcv.vn · baodautu.vn |
| Handshake | 20 triệu SV · 1.400+ trường · định giá 3,5 tỷ USD | Forbes · PRNewswire (2022) |
| Greenhouse | TPG đầu tư 500 triệu USD (2021) | công bố TPG/Greenhouse |
| Giá & KPI | SV Pro 49k · DN 2–5tr · license ~150tr/năm · phễu mục tiêu | đề xuất của nhóm (ghi rõ trên slide) |

**Không còn placeholder nào.** Muốn đổi số/từ ngữ: sửa `build_deck.py`, chạy lại, rồi `/design-sync` đẩy lên.
