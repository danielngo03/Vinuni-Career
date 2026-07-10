# Slide Pitch — VinUni Career Platform (15 slide)

Bộ pitch deck **15 slide hoàn chỉnh, đã dựng sẵn** cho VinUni Career Platform — tiếng Việt, 16:9, chuẩn
trình bày trước đông người: mỗi slide một ý chính, kín nội dung kiểu infographic, số liệu thật có nguồn,
ảnh chụp thật từ sản phẩm đang chạy.

> **Xem ngay:** mở `deck/deck.html` (phím ←/→) · hoặc project claude.ai/design
> **"VinUni Pitch Deck — C2-037"** → https://claude.ai/design/p/4a48a9a7-b406-4db7-b785-85328b453205

---

## 📁 File trong folder

| File | Vai trò |
|---|---|
| `deck/slide-01…15.html` + `deck/deck.html` | **Deck thành phẩm** (mỗi slide 1 card + bản gộp trình chiếu/PDF) |
| `build_deck.py` | **Nguồn chân lý** — generator sinh toàn bộ deck; sửa slide = sửa file này rồi chạy lại |
| `fetch_assets.py` | Tải icon Solar duotone + logo công nghệ thật (Iconify) vào `assets/lib/` |
| `assets/` | logo-dark (mark đen), 7 screenshot thật, ảnh campus, 42 icon, 13 logo công nghệ |
| `01-HUONG-DAN-CLAUDE-DESIGN.md` | Cách sửa → build → `/design-sync` → xuất PDF + checklist trước khi pitch |
| `02-DECK-SPEC.md` | Spec 15 slide (nội dung + trực quan + bảng nguồn số liệu) |
| `03-BRAND-DESIGN-SYSTEM.md` | Hệ thiết kế: màu, chữ, card, mockup, quy tắc bố cục |
| `04-MASTER-PROMPT.md` | Prompt cho Claude Design khi cần tinh chỉnh mà vẫn giữ chuẩn |
| `05-KICH-BAN-THUYET-TRINH.md` | **Kịch bản nói** khớp từng slide (~9 phút) + hỏi đáp khó + mẹo trình bày |

## 🗂️ 15 slide (4 phần)

| # | Slide | # | Slide |
|---|---|---|---|
| 01 | Trang bìa (logo + laptop sản phẩm thật) | 09 | **Lợi thế cạnh tranh** (số liệu đối thủ + bảng so sánh) |
| 02 | Nội dung trình bày (4 phần) | 10 | **Kết quả đạt được** (34 phân hệ · 120 màn hình · 2.022 test) |
| 03 | **Vấn đề** — hành trình 5 bước đứt gãy | 11 | **Kiến trúc hệ thống** (3 lớp, logo công nghệ thật) |
| 04 | **Giải pháp** — 1 nền tảng, 4 phân hệ | 12 | **Công nghệ** (stack + pipeline đọc CV + khi có sự cố) |
| 05 | **Sản phẩm** — 4 ảnh chụp thật | 13 | **Lộ trình phát triển** (4 cột mốc, mốc 1 đã xong) |
| 06 | **Tính năng AI** (điểm 0–100 · sửa CV · trợ lý) | 14 | **Mục tiêu 12 tháng** (phễu + cam kết vận hành) |
| 07 | **Quy mô thị trường** (phễu TAM→VinUni + Handshake $3,5B) | 15 | **Lời mời hợp tác** (3 đề nghị + ảnh campus) |
| 08 | **Mô hình kinh doanh** (4 nguồn thu + giá) | | |

## 🚀 Sửa & đẩy lại (3 lệnh)

```bash
# 1. sửa nội dung trong build_deck.py (hàm s1()…s15())
python3 slide/build_deck.py            # 2. build lại deck/
# 3. trong Claude Code: /design-sync   # đẩy card đã đổi lên claude.ai/design
```

Xuất PDF: mở `deck/deck.html` → `Cmd/Ctrl+P` → Landscape, margin None, bật Background graphics.

## ✅ Cam kết số liệu

Quy mô hệ thống **đếm từ mã nguồn** (34 phân hệ, 120 màn hình, 2.022 test, 20 bộ eval AI). Thị trường & đối
thủ **số thật có nguồn** in ngay chân slide (TCTK/Bộ GD&ĐT 2024 · TopCV · Forbes/PRNewswire — bảng đầy đủ ở
cuối `02-DECK-SPEC.md`). Giá & KPI là **đề xuất/mục tiêu**, gắn chip "mục tiêu" rõ ràng trên slide. Câu chuyện
mở rộng đa trường trình bày là **định hướng** (mốc viền đứt) — an toàn khi bị hội đồng chất vấn.
