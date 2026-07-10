# Slide Pitch — VinUni Career Platform

Bộ tài liệu spec để **Claude Design (claude.ai/design)** dựng trọn bộ **21 slide** pitch cho dự án
*VinUni Career Platform*. Tất cả nội dung ở đây đã được **kiểm chứng trực tiếp từ code + docs của dự án**
(không phải nội dung bịa) — bạn chỉ cần đưa cho Claude Design là dựng ra slide đúng, đẹp, chuẩn thương hiệu.

> **Ngôn ngữ deck:** Tiếng Việt (giữ nguyên thuật ngữ kỹ thuật tiếng Anh: FastAPI, RAG, pgvector, ATS…).
> **Đối tượng:** Hội đồng / giám khảo (capstone/thi) → cân bằng *business + kỹ thuật + tính khả thi*.
> **Tỷ lệ:** 16:9. **Nền:** `#F8F7F1` (giấy ấm) + thẻ trắng `#ffffff`, khung monochrome + nhấn màu data-viz.

---

## 📁 Các file trong folder này (đọc theo thứ tự)

| File | Vai trò | Đưa cho Claude Design? |
|---|---|---|
| `README.md` | Bạn đang đọc — mục lục + quick start + danh sách 21 slide | Ngữ cảnh |
| `01-HUONG-DAN-CLAUDE-DESIGN.md` | **Cách kết nối & dùng claude.ai/design** (2 luồng: Artifacts và `/design-sync`), cách export PDF | Đọc để làm theo |
| `02-DECK-SPEC.md` | **Trái tim của bộ này** — spec đầy đủ 21 slide: nội dung chữ + vẽ gì + số liệu + bố cục | ✅ Bắt buộc |
| `03-BRAND-DESIGN-SYSTEM.md` | Hệ thiết kế: bảng màu chính xác, font, bo góc, style biểu đồ, quy tắc layout, do/don't | ✅ Bắt buộc |
| `04-MASTER-PROMPT.md` | **Prompt copy-paste** để dán vào Claude Design → dựng cả deck | ✅ Dán trực tiếp |
| `assets/README.md` | Nơi bỏ logo VinUni + screenshot sản phẩm (nếu có) | Tùy chọn |

---

## 🚀 Quick start (3 bước)

1. Mở **claude.ai/design** (hoặc claude.ai → Artifacts). Tạo project mới.
2. **Upload 3 file**: `02-DECK-SPEC.md`, `03-BRAND-DESIGN-SYSTEM.md`, và (nếu có) logo trong `assets/`.
3. **Dán nội dung `04-MASTER-PROMPT.md`** làm câu lệnh đầu tiên. Claude Design sẽ dựng 1 file HTML deck 16:9
   tự chứa (điều hướng bằng phím mũi tên, in ra PDF được). Xem chi tiết + luồng `/design-sync` ở
   `01-HUONG-DAN-CLAUDE-DESIGN.md`.

> 💡 Nếu 21 slide trong 1 lần là quá dài, hãy yêu cầu Claude Design dựng **theo cụm 5 slide** (1–5, 6–10,
> 11–15, 16–21) rồi ghép — chất lượng từng slide sẽ cao hơn. Master prompt đã hướng dẫn cách này.

---

## 🗂️ Mục lục 21 slide (storyline)

> **Storyline (đã tối ưu cho hội đồng):** front-load *thách thức → tầm nhìn nền tảng → quy mô đã dựng →
> business*, rồi mới vào chiều sâu sản phẩm/AI, đóng deck bằng *roadmap + đường mở rộng + ask*. Motif xuyên
> suốt: **"Ưu tiên VinUni, sẵn sàng thành nền tảng"** (beachhead → mở rộng).

| # | Tên slide | Vai trò trong câu chuyện |
|---|---|---|
| 01 | **Bìa — VinUni Career Platform** | Logo VinUni + tên sản phẩm + tagline + team |
| 02 | **Thực trạng & Thách thức** | Nỗi đau SV · nhà tuyển dụng · nhà trường + vì sao chưa ai giải được |
| 03 | **Cơ hội thị trường & Tầm nhìn nền tảng** | Beachhead VinUni → alumni/SV ngoài → nền tảng độc lập *(business)* |
| 04 | **Giải pháp: 1 hệ điều hành, 4 bề mặt** | Marketplace · Student · Partner · University *(slide hero)* |
| 05 | **Sản phẩm thực tế (Product Showcase)** | Gallery 4 bề mặt UI theo phong cách v10 |
| 06 | **Quy mô & Mức độ hoàn thiện** | Bằng chứng "đã dựng thật" — 34 module · 2.022 test · 120 màn hình *(de-risk)* |
| 07 | **Mô hình kinh doanh & Doanh thu** | 4 dòng doanh thu (ai trả) · AI credit · kinh tế khi mở rộng *(business sâu)* |
| 08 | **Phân tích đối thủ & Định vị** | Ma trận 2×2 · moat kép: hào phòng thủ + bệ phóng mở rộng |
| 09 | **Người dùng & Phân quyền (Personas + RBAC)** | Persona · multi-identity · multi-tenant-ready |
| 10 | **Hành trình Sinh viên (Flow 1)** | Khám phá → đăng ký → CV → fit + competition → ứng tuyển → theo dõi |
| 11 | **CV Studio** | Trình soạn CV canvas kiểu Canva · marketplace template · AI sửa có diff |
| 12 | **CV Ingestion Cascade** | Pipeline bóc tách CV phân tầng chi phí (native → OCR → vision-LLM) |
| 13 | **CV–JD Matching & Competition Intelligence** | Điểm khớp 0–100 tất định · evidence gap · tín hiệu cạnh tranh |
| 14 | **AI Career Assistant & Interview Simulator** | ReAct agent 25+ tool · confirm-before-write · mock interview |
| 15 | **Partner Recruiting OS (Flow 2) + Talent Pool** | JD → pipeline/ATS → screen (ẩn danh + fit) → offer · passive search |
| 16 | **University Operations Center (Flow 3)** | Kiểm duyệt → duyệt đối tác → workflow → analytics/career outcomes |
| 17 | **Visual Workflow Builder** | DAG React Flow · DRAFT→TEST→ACTIVE · dry-run · human-confirm node |
| 18 | **AI Governance, Safety & Trust** | Metering + ledger idempotency · che giấu provider · guardrail |
| 19 | **Kiến trúc & Công nghệ (platform-ready)** | DDD theo module · read-model/outbox/audit · AI gateway · stack · multi-tenant |
| 20 | **Traction & Mục tiêu 12 tháng** | Mục tiêu 12T + proof VinUni 32% offer + thị trường 2,36M SV *(business)* |
| 21 | **Roadmap, Đường mở rộng & Kết luận** | 6 phase · 3 chặng mở rộng (GTM) · ask/CTA + logo *(business đóng)* |

---

## ✅ Cam kết chính xác

Mọi số liệu "quy mô" trong deck (34 module, 98 migration, 2.022 test, 120 màn hình…) đều được **đếm trực tiếp
từ repo** — xem `02-DECK-SPEC.md` slide 06 (Quy mô) để biết lệnh đếm. Số **thị trường** (2,36M SV · 940k DN ·
67 trường tư · VinUni 32% offer khóa đầu) là **số thật 2024 có nguồn** (Tổng cục Thống kê VN, NSO, VinUni.edu.vn
— liệt kê ở cuối `02-DECK-SPEC.md`). **Giá gói & KPI** là **đề xuất/mục tiêu hợp lý** (ghi rõ "đề xuất"/"mục
tiêu" để không nhầm là số đã đạt). Chỉ còn `[MÔN/CUỘC THI]` và logo là bạn tự thêm. Câu chuyện *nền tảng* (slide
3, 8, 19, 21) trình bày là **tầm nhìn + sẵn-sàng-kỹ-thuật**, không phải cam kết V1 "bán cho trường khác" — an
toàn khi bị hội đồng vặn.
