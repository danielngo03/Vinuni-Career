# Hướng dẫn dùng Claude Design để dựng 21 slide

Tài liệu này giải thích **chính xác** claude.ai/design là gì, và **2 luồng** để biến bộ spec trong folder
`slide/` thành một deck 21 slide hoàn chỉnh. Chọn 1 trong 2 — khuyến nghị **Luồng A** cho nhanh, dùng
**Luồng B** nếu bạn muốn quản lý từng slide như một "component" trong một design-system project.

---

## 0. Hiểu đúng công cụ (để không kỳ vọng sai)

- **claude.ai/design** là không gian **design-system project** trên claude.ai: bạn đẩy các file HTML preview
  lên, mỗi file hiển thị thành một **card** trong Design System pane. Nó **không phải** "máy tạo slide" bấm
  một nút ra 21 slide — nó là nơi *chứa & xem* các artifact HTML bạn tạo ra.
- **Artifacts trên claude.ai** mới là nơi Claude **sinh ra** HTML/React trực tiếp từ prompt và xem preview
  ngay. Đây là cách nhanh nhất để dựng deck.
- **`/design-sync`** (skill trong Claude Code) + tool `DesignSync` là cầu nối: đồng bộ **file HTML local →
  claude.ai/design project** (từng component một, không ghi đè hàng loạt). Dùng khi bạn đã có sẵn các file
  slide HTML trên máy và muốn đưa lên design project.

> Tóm lại: **Artifacts để *tạo* deck, claude.ai/design để *lưu & trình bày* các slide dưới dạng card.**

---

## 🅰️ Luồng A — Nhanh nhất: Claude Artifacts (khuyến nghị)

**Kết quả:** 1 file HTML tự chứa, 16:9, điều hướng bằng phím `←`/`→`, in ra PDF được.

1. Vào **claude.ai** → tạo **Project** mới (ví dụ tên *"VinUni Pitch Deck"*).
2. Trong Project, **thêm vào Knowledge / upload** 2 file:
   - `02-DECK-SPEC.md`
   - `03-BRAND-DESIGN-SYSTEM.md`
   - (kèm logo VinUni nếu có, xem `assets/README.md`)
3. Mở một chat trong Project, **dán toàn bộ nội dung `04-MASTER-PROMPT.md`**.
4. Claude trả về một **Artifact HTML**. Yêu cầu chỉnh sửa bằng ngôn ngữ tự nhiên, ví dụ:
   - *"Slide 12 vẽ pipeline theo chiều dọc, mỗi tầng 1 hàng, thêm nhãn chi phí Free/Rẻ/Rẻ+"*
   - *"Dùng đúng gradient hero indigo→violet ở slide 4 và 21, các slide khác tối đa 1 panel gradient"*
5. **Chia cụm nếu deck dài:** nếu 21 slide 1 lần bị cắt/nhạt, bảo Claude:
   *"Dựng trước slide 1–5 thật kỹ trong 1 artifact"* → duyệt → *"Dựng tiếp 6–10 cùng style"* … rồi cuối cùng
   *"Gộp tất cả vào 1 file HTML deck duy nhất, giữ nguyên style"*.
6. **Export PDF:** mở Artifact ở chế độ full-screen → `Ctrl/Cmd + P` → *Save as PDF* → chọn **khổ ngang
   (Landscape)**, **margin = None**, bật *Background graphics*. (Master prompt yêu cầu Claude thêm CSS
   `@media print` để mỗi slide vừa đúng 1 trang A-landscape.)

---

## 🅱️ Luồng B — claude.ai/design + `/design-sync` (mỗi slide = 1 card)

Dùng khi bạn muốn **21 slide nằm gọn trong 1 design-system project** trên claude.ai/design, xem dạng lưới
card, chỉnh từng slide độc lập.

**B1. Tạo file slide HTML local (dùng Claude Code + plugin `frontend-design`)**
- Ở máy, mở Claude Code trong repo. Yêu cầu:
  *"Đọc `slide/02-DECK-SPEC.md` và `slide/03-BRAND-DESIGN-SYSTEM.md`. Tạo 20 file HTML tự chứa tại
  `slide/deck/slide-01.html` … `slide-21.html`, mỗi file là 1 slide 16:9 hoàn chỉnh theo đúng spec, dùng
  chung 1 khối `<style>` design-system. Dòng đầu mỗi file thêm marker `<!-- @dsCard group=\"Pitch Deck\" -->`."*
- Marker `@dsCard` giúp claude.ai/design tự lập chỉ mục card cho từng slide.

**B2. Đồng bộ lên claude.ai/design bằng `/design-sync`**
- Trong Claude Code, chạy skill: **`/design-sync`**.
- Skill sẽ: `list_projects` (chọn/ tạo project design-system) → dựng **diff** giữa `slide/deck/*.html`
  local và project → cho bạn duyệt danh sách file sẽ ghi → `finalize_plan` → `write_files` đẩy từng slide lên.
- Đồng bộ **tăng dần, từng file** — sửa `slide-07.html` rồi chạy lại `/design-sync` chỉ đẩy slide 7.

**B3. Trình bày / xuất**
- Mỗi slide là 1 card trong Design System pane của claude.ai/design. Để trình chiếu liền mạch, vẫn nên có
  thêm 1 file `deck.html` gộp (Luồng A bước 6) để export PDF.

> ⚠️ Lưu ý kỹ thuật `/design-sync`: project phải đúng **type `PROJECT_TYPE_DESIGN_SYSTEM`** (tạo mới nếu
> `list_projects` trống). Tool đọc nội dung file **thẳng từ đĩa** — nội dung không đi qua ngữ cảnh model, nên
> an toàn cho file lớn. Đây là công cụ *đồng bộ component*, không phải trình tạo slide — bạn vẫn tạo HTML ở B1.

---

## 🧭 Nên chọn luồng nào?

| Nhu cầu | Chọn |
|---|---|
| Cần deck nhanh để pitch, xuất PDF | **Luồng A (Artifacts)** |
| Muốn quản lý 21 slide như thư viện card, chỉnh lẻ từng slide, dùng lại | **Luồng B (design-sync)** |
| Vừa muốn nhanh vừa muốn lưu trên design project | Làm **A trước**, sau đó tách từng slide thành file rồi **sync B** |

---

## 📌 Checklist trước khi pitch

- [ ] Logo VinUni đã đặt ở `assets/` và xuất hiện đúng ở slide 1 + 21.
- [ ] Số liệu đã điền sẵn (team C2-Team-037, thị trường, giá, KPI) — chỉ cần thêm `[MÔN/CUỘC THI]` (slide 1) + logo.
- [ ] Chỉ **1 panel gradient indigo→violet mỗi slide** (đúng quy tắc v10) — không lạm dụng.
- [ ] Nhãn `Được tài trợ` / `Quảng cáo` **không bị bỏ** ở business (7), showcase (5), governance (18).
- [ ] Số liệu quy mô (slide 6) khớp với lệnh đếm trong spec.
- [ ] Câu chuyện "nền tảng" (slide 3, 8, 19, 21) giữ khung *tầm nhìn + sẵn-sàng-kỹ-thuật* (vòng/chặng mở rộng
      vẽ nét đứt), không hứa mốc bán SaaS.
- [ ] Thử in PDF landscape: mỗi slide = đúng 1 trang, không tràn.
