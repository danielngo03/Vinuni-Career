# MASTER PROMPT — dán vào Claude Design / Artifacts

> Copy toàn bộ khối dưới đây làm câu lệnh **đầu tiên** trong Claude Design (đã upload kèm `02-DECK-SPEC.md` và
> `03-BRAND-DESIGN-SYSTEM.md`). Nếu công cụ không cho đính kèm, **dán luôn nội dung 2 file đó** trước prompt.

---

```
Bạn là designer + front-end dev. Hãy dựng một BỘ SLIDE PITCH 21 slide cho dự án
"VinUni Career Platform" thành MỘT FILE HTML TỰ CHỨA (self-contained), tỷ lệ 16:9,
điều hướng bằng phím ← →, in ra PDF landscape được (mỗi slide = đúng 1 trang).

NGUỒN NỘI DUNG (bắt buộc bám sát, không tự bịa):
- Nội dung + bố cục + "vẽ gì" từng slide: theo file 02-DECK-SPEC.md (21 slide, đã đánh số 01–21).
- Hệ màu, font, bo góc, component, layout grammar: theo file 03-BRAND-DESIGN-SYSTEM.md.
Nếu 2 file đã được đính kèm/nhúng ở trên, hãy đọc và tuân thủ tuyệt đối. Không thêm nội dung
ngoài spec, không tự bịa số. TẤT CẢ số liệu, tên team (C2-Team-037), giá, KPI, Ask, logo và
4 ảnh thật đã có sẵn trong spec/assets — hãy dùng ĐÚNG, KHÔNG để chỗ trống, KHÔNG bịa thêm.

NGÔN NGỮ: Tiếng Việt, giữ nguyên thuật ngữ kỹ thuật tiếng Anh (FastAPI, RAG, pgvector, ATS,
CV–JD matching, ReAct agent, DAG...). Đối tượng: hội đồng/giám khảo capstone → cân bằng
business + kỹ thuật + tính khả thi.

YÊU CẦU THIẾT KẾ (tuân thủ 03-BRAND-DESIGN-SYSTEM.md):
- Nền mỗi slide #F8F7F1; card trắng #ffffff, bo góc 14px, viền 1px #e5e5e5, bóng cực nhẹ.
- Khung monochrome (thang xám, ink #171717); nhấn bằng palette data-viz (indigo #6366f1,
  teal #14b8a6, amber #f59e0b, rose #f43f5e, sky #0ea5e9, emerald #10b981, violet #8b5cf6,
  orange #f97316). Màu chỉ dùng đúng ngữ nghĩa (emerald=tốt, amber=sponsored/cảnh báo,
  đỏ VinUni #c83538=danger/brand, sky/indigo=info/AI).
- TỐI ĐA 1 panel gradient indigo→violet (linear-gradient(135deg,#4f46e5,#6d28d9 55%,#7c3aed))
  mỗi slide, dùng cho slide hero/KPI nổi bật (đặc biệt slide 4 và 21).
- Font Plus Jakarta Sans (nhúng qua Google Fonts hoặc system fallback); MỌI số/metric dùng
  JetBrains Mono tabular-nums.
- Mỗi slide có: kicker (11px uppercase xám) + tiêu đề + logo nhỏ VinUni + số trang ở footer.
- Icon: chỉ dùng inline SVG kiểu lucide (nét mảnh monochrome). KHÔNG dùng emoji làm icon.
- KHÔNG gỡ nhãn "Được tài trợ"/"Quảng cáo" ở slide 5, 7 và 18. KHÔNG phơi tên provider/model AI.
- Vẽ đúng các sơ đồ mà spec yêu cầu (flow node, pipeline bậc thang, layered architecture,
  bull's-eye thị trường, ma trận 2×2 đối thủ, Kanban, DAG, donut score, timeline roadmap...).
  Ưu tiên SVG/HTML+CSS thuần, KHÔNG phụ thuộc thư viện ngoài. File phải chạy offline.

TRỰC QUAN — ÍT CHỮ (RẤT QUAN TRỌNG):
- Mỗi slide 1 ý chính, hiển thị TỐI ĐA ~30–45 chữ. KHÔNG dán nguyên đoạn văn từ spec lên slide.
  Phần "Nội dung chữ" trong spec là NGUỒN Ý để bạn CHẮT LỌC thành: tiêu đề ngắn + 3–4 chip/label
  + biểu đồ/sơ đồ/icon + số to. Nếu một slide toàn chữ → bạn đang làm SAI, hãy chuyển thành hình.
- Ưu tiên: số lớn (metric tiles), sơ đồ/flow, biểu đồ (donut/bar/funnel), icon có nhãn, bảng gọn.
  Câu dài → rút thành cụm từ. Bullet dài → thành chip. Đoạn văn → thành sơ đồ.
- Slide 5 (Product Showcase): dùng 4 ẢNH CHỤP THẬT trong assets/ (shot-student-dashboard.png,
  shot-cv-studio.png, shot-partner-pipeline.png, shot-university-outcomes.png) — nhúng data-URI,
  đặt trong khung "browser frame" bo góc. KHÔNG vẽ lại mock (đã có ảnh thật).
- NGUỒN SỐ LIỆU: slide nào hiển thị số thị trường (slide 2, 3, 20) phải có 1 dòng "Nguồn: …" cỡ
  nhỏ (10–11px, xám) ở chân slide — nội dung nguồn đã ghi trong spec, đừng bỏ.

KỸ THUẬT:
- 1 file HTML, CSS trong <style>, JS nhỏ để chuyển slide (← → , Space, click), hiện số trang.
- Thêm @media print để mỗi .slide là 1 trang landscape (page-break-after: always), ẩn nút UI.
- Responsive: khung 16:9 co giãn theo màn hình, nội dung không tràn.
- Logo: dùng assets/logo-dark.svg (mark ĐEN cho nền sáng #F8F7F1) ở slide 1 (lớn) + slide 21 +
  logo nhỏ footer. Nhúng data-URI để chạy offline.

CÁCH LÀM (để chất lượng cao):
- Dựng LẦN LƯỢT theo cụm: trước tiên slide 01–05 thật kỹ trong 1 artifact và cho tôi xem.
- Sau khi tôi duyệt, dựng tiếp 06–10, 11–15, 16–21 cùng một hệ style/CSS.
- Cuối cùng gộp tất cả vào 1 file HTML deck duy nhất, giữ nguyên style và thứ tự 01→20.

Bắt đầu bằng slide 01–05.
```

---

## Prompt phụ (khi cần chỉnh sửa) — ví dụ mẫu

- *"Slide 12: vẽ pipeline 6 tầng theo bậc thang dọc, mỗi tầng gắn nhãn chi phí Free/Rẻ/Rẻ+, nhánh reject màu
  đỏ VinUni ở tầng 1. Bên phải thêm thẻ 'Structured Output' minh họa 1 entry role/org/timeframe + thanh skill 0–100."*
- *"Slide 19: layered architecture 5 tầng dọc Client→API→Application(RBAC)→Domain→Infrastructure→PostgreSQL,
  tách nhánh AI Gateway bên phải tô indigo-soft, dải xương sống Read Models · Outbox · Audit ở đáy, badge
  'multi-tenant-ready' cạnh tầng Organization; 2 hàng chip công nghệ Backend/Frontend ở dưới."*
- *"Slide 06: hàng 6 KPI tile — 34 module, 98 migration, 2.022 test, 120 màn hình, vi/en, 20 bộ eval AI — số
  dùng JetBrains Mono cỡ lớn; 1 tile dùng gradient hero cho con số 2.022 test."*
- *"Slide 07: 4 thẻ doanh thu (ghi rõ 'ai trả') hội tụ vào thẻ AI Credit Ledger; bên phải mũi tên 'VinUni →
  Tổ chức mới (+ license/SaaS)'; giữ 1 chip 'Được tài trợ' màu amber."*
- *"Slide 03: 3 vòng mở rộng đồng tâm VinUni (~3.500 SV) → Alumni/SV ngoài → Nền tảng độc lập (67 trường tư ·
  2,36M SV · 940k DN, vòng ngoài nét đứt); chip 'HR-tech VN → ~US$1 tỷ'."*
- *"Slide 20: hàng KPI-target tiles (2.500 SV active · 3.000 CV · 5.000 ứng tuyển · 60–100 đối tác · 100
  mentor) mỗi tile gắn chip amber 'mục tiêu 12T'; bên phải thẻ 'Vì sao khả thi' 3 proof-point (VinUni 32%
  offer khóa đầu · 2,36M SV/940k DN · sản phẩm đã dựng); dưới là phễu SV→CV→ứng tuyển→offer."*
- *"Giảm bớt màu ở slide 10, chỉ node AI (bước 4,5) viền sky; các node còn lại trung tính."*
- *"Export: thêm CSS print để mỗi slide vừa đúng 1 trang A4 ngang, ẩn thanh điều hướng khi in."*

---

## Nếu dùng luồng `/design-sync` (mỗi slide = 1 file)

Thay câu cuối master prompt bằng:

```
Thay vì 1 file gộp, hãy tạo 21 file HTML tự chứa: slide-01.html … slide-21.html trong thư mục
slide/deck/. Mỗi file là 1 slide 16:9 hoàn chỉnh, dùng CHUNG một khối <style> design-system.
Dòng đầu mỗi file thêm: <!-- @dsCard group="Pitch Deck" --> để claude.ai/design lập card.
```
Sau đó chạy `/design-sync` trong Claude Code để đẩy `slide/deck/*.html` lên project claude.ai/design
(xem `01-HUONG-DAN-CLAUDE-DESIGN.md` — Luồng B).
