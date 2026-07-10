# Slide Pitch — VinUni Career Platform

Bộ tài liệu spec để **Claude Design (claude.ai/design)** dựng trọn bộ **20 slide** pitch cho dự án
*VinUni Career Platform*. Tất cả nội dung ở đây đã được **kiểm chứng trực tiếp từ code + docs của dự án**
(không phải nội dung bịa) — bạn chỉ cần đưa cho Claude Design là dựng ra slide đúng, đẹp, chuẩn thương hiệu.

> **Ngôn ngữ deck:** Tiếng Việt (giữ nguyên thuật ngữ kỹ thuật tiếng Anh: FastAPI, RAG, pgvector, ATS…).
> **Đối tượng:** Hội đồng / giám khảo (capstone/thi) → cân bằng *business + kỹ thuật + tính khả thi*.
> **Tỷ lệ:** 16:9. **Nền:** `#F8F7F1` (giấy ấm) + thẻ trắng `#ffffff`, khung monochrome + nhấn màu data-viz.

---

## 📁 Các file trong folder này (đọc theo thứ tự)

| File | Vai trò | Đưa cho Claude Design? |
|---|---|---|
| `README.md` | Bạn đang đọc — mục lục + quick start + danh sách 20 slide | Ngữ cảnh |
| `01-HUONG-DAN-CLAUDE-DESIGN.md` | **Cách kết nối & dùng claude.ai/design** (2 luồng: Artifacts và `/design-sync`), cách export PDF | Đọc để làm theo |
| `02-DECK-SPEC.md` | **Trái tim của bộ này** — spec đầy đủ 20 slide: nội dung chữ + vẽ gì + số liệu + bố cục | ✅ Bắt buộc |
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

> 💡 Nếu 20 slide trong 1 lần là quá dài, hãy yêu cầu Claude Design dựng **theo cụm 5 slide** (1–5, 6–10,
> 11–15, 16–20) rồi ghép — chất lượng từng slide sẽ cao hơn. Master prompt đã hướng dẫn cách này.

---

## 🗂️ Mục lục 20 slide (storyline)

| # | Tên slide | Vai trò trong câu chuyện |
|---|---|---|
| 01 | **Bìa — VinUni Career Platform** | Logo VinUni + tên sản phẩm + tagline + team |
| 02 | **Thực trạng & Vấn đề** | Nỗi đau của sinh viên · nhà tuyển dụng · nhà trường |
| 03 | **Thị trường & Vì sao là bây giờ** | Hệ sinh thái VinUni · campus-native · làn sóng AI |
| 04 | **Giải pháp: 1 hệ điều hành, 4 bề mặt** | Marketplace · Student · Partner · University *(slide hero)* |
| 05 | **Sản phẩm thực tế (Product Showcase)** | Gallery 4 bề mặt UI theo phong cách v10 |
| 06 | **Phân tích đối thủ** | vs LinkedIn / TopCV·VietnamWorks / Handshake / Greenhouse·Workday |
| 07 | **Người dùng & Phân quyền (Personas + RBAC)** | Bản đồ persona · multi-identity · capability grantable |
| 08 | **Hành trình Sinh viên (Flow 1)** | Khám phá → đăng ký → CV → fit + competition → ứng tuyển → theo dõi |
| 09 | **CV Studio** | Trình soạn CV canvas kiểu Canva · marketplace template · AI sửa có diff |
| 10 | **CV Ingestion Cascade** | Pipeline bóc tách CV phân tầng chi phí (native → OCR → vision-LLM) |
| 11 | **CV–JD Matching & Competition Intelligence** | Điểm khớp 0–100 tất định · evidence gap · tín hiệu cạnh tranh |
| 12 | **AI Career Assistant & Interview Simulator** | ReAct agent 25+ tool · confirm-before-write · mock interview |
| 13 | **Partner Recruiting OS (Flow 2) + Talent Pool** | JD → pipeline/ATS → screen (ẩn danh + fit) → offer · passive search |
| 14 | **University Operations Center (Flow 3)** | Kiểm duyệt → duyệt đối tác → workflow → analytics/career outcomes |
| 15 | **Visual Workflow Builder** | DAG React Flow · DRAFT→TEST→ACTIVE · dry-run · human-confirm node |
| 16 | **AI Governance, Safety & Trust** | Metering + ledger idempotency · che giấu provider · guardrail |
| 17 | **Mô hình kinh doanh & Monetization** | 4 nguồn doanh thu · AI credit/quota · sponsored vs organic |
| 18 | **Kiến trúc tổng quan (Architecture)** | DDD theo module · read-model/outbox/audit · AI gateway |
| 19 | **Công nghệ & Quy mô (Tech Stack + Scale)** | Stack thật + số liệu code-verified (34 module · 2.022 test…) |
| 20 | **Roadmap, Traction & Kết luận** | 6 phase · tầm nhìn · lời kêu gọi + logo |

---

## ✅ Cam kết chính xác

Mọi số liệu "quy mô" trong deck (34 module, 98 migration, 2.022 test, 120 màn hình…) đều được **đếm trực tiếp
từ repo** — xem `02-DECK-SPEC.md` slide 19 để biết lệnh đếm. Các con số **thị trường/tài chính** (TAM, giá gói)
**không có trong docs** → deck để ô placeholder `[ĐIỀN SỐ]` cho bạn tự bổ sung, tránh bịa số trước hội đồng.
