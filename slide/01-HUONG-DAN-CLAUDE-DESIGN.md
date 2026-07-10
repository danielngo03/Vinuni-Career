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
2. Trong Project, **thêm vào Knowledge / upload**:
   - `02-DECK-SPEC.md` + `03-BRAND-DESIGN-SYSTEM.md`
   - **`assets/logo-dark.svg`** (logo đen cho nền sáng) — cho slide 1 + 21 + footer.
   - **4 ảnh thật cho slide 5:** `assets/shot-student-dashboard.png`, `shot-cv-studio.png`,
     `shot-partner-pipeline.png`, `shot-university-outcomes.png`.
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
card, chỉnh từng slide độc lập, dùng lại về sau.

> **Hiểu đúng để không kẹt:** `/design-sync` **KHÔNG tự vẽ slide**. Nó **đẩy các file HTML có sẵn ở máy →
> project trên claude.ai/design** (mỗi file thành 1 card). Vậy nên **BƯỚC 1 là phải có file HTML slide ở máy
> trước** — tạo bằng Claude Code (B1). Sau đó `/design-sync` đưa chúng lên (B2).

### B1 — Tạo 21 file HTML slide ở máy (Claude Code)
Mở **Claude Code** ngay trong repo này, dán yêu cầu:

> *"Đọc `slide/02-DECK-SPEC.md`, `slide/03-BRAND-DESIGN-SYSTEM.md` và `slide/04-MASTER-PROMPT.md`. Tạo 21 file
> HTML tự chứa tại `slide/deck/slide-01.html` … `slide-21.html`. Mỗi file = 1 slide 16:9 hoàn chỉnh, ÍT CHỮ
> (≤ ~40 chữ hiển thị), nhiều biểu đồ/sơ đồ/số to theo đúng spec, dùng chung 1 khối `<style>` design-system.
> Slide 1 & 21 dùng `slide/assets/logo-dark.svg`; slide 5 nhúng 4 ảnh thật trong `slide/assets/shot-*.png`
> dạng data-URI. Dòng ĐẦU mỗi file thêm: `<!-- @dsCard group=\"Pitch Deck\" -->`. Tạo thêm `slide/deck/deck.html`
> gộp cả 21 slide, điều hướng phím ← →, có `@media print` để export PDF landscape."*

- Marker `@dsCard` ở dòng đầu giúp claude.ai/design **tự lập chỉ mục card** cho từng slide.
- Kết quả: `slide/deck/slide-01.html … slide-21.html` (21 card) + `deck.html` (bản trình chiếu/PDF).

### B2 — Đăng nhập & đẩy lên bằng `/design-sync`
1. Trong **Claude Code**, gõ: **`/design-login`** (nếu chưa) để cấp quyền truy cập claude.ai/design cho phiên.
2. Gõ: **`/design-sync`**. Skill sẽ tự làm tuần tự (bạn chỉ cần duyệt):
   - `list_projects` → chọn project design-system có sẵn **hoặc** tạo mới (vd tên *"VinUni Pitch Deck"* — phải
     đúng loại **design system**, tool sẽ tạo giúp nếu bạn chưa có).
   - So sánh `slide/deck/*.html` ở máy với project → hiện **danh sách file sẽ đẩy** để bạn duyệt (`finalize_plan`).
   - Bạn xác nhận → `write_files` đẩy 21 slide + `deck.html` lên. Xong: 21 **card** hiện trong Design System pane.
3. **Sửa từng slide sau này:** chỉ cần sửa `slide-07.html` ở máy rồi chạy lại **`/design-sync`** — nó chỉ đẩy
   đúng file đã đổi (đồng bộ tăng dần, không ghi đè toàn bộ).

### B3 — Xem / trình bày / xuất
- Vào **claude.ai/design** → mở project → xem 21 slide dạng **card lưới**, bấm từng card để xem/sửa/tinh chỉnh.
- Trình chiếu liền mạch + export PDF: mở `slide/deck/deck.html` (bản gộp) → full-screen → `Cmd/Ctrl+P` → Save
  as PDF (Landscape, margin None, bật Background graphics).

> ⚠️ Ghi nhớ về `/design-sync`: project phải đúng **type "design system"** (skill tạo giúp nếu `list_projects`
> trống). Tool đọc file **thẳng từ đĩa** (nội dung không đi qua ngữ cảnh model → an toàn cho file lớn/ảnh). Nó
> chỉ **đồng bộ**, không tự sinh slide — nên B1 (tạo HTML) là bắt buộc trước.

> 💡 **Ngại 2 bước?** Không sao — **Luồng A (Artifacts) nhanh hơn và không cần `/design-sync`**: dán master
> prompt vào claude.ai là ra deck ngay. Chỉ dùng Luồng B khi bạn thực sự muốn lưu 21 slide dạng card trong
> một design-system project để tái sử dụng.

---

## 🧭 Nên chọn luồng nào?

| Nhu cầu | Chọn |
|---|---|
| Cần deck nhanh để pitch, xuất PDF | **Luồng A (Artifacts)** |
| Muốn quản lý 21 slide như thư viện card, chỉnh lẻ từng slide, dùng lại | **Luồng B (design-sync)** |
| Vừa muốn nhanh vừa muốn lưu trên design project | Làm **A trước**, sau đó tách từng slide thành file rồi **sync B** |

---

## 📌 Checklist trước khi pitch

- [ ] `assets/logo-dark.svg` (mark đen) hiện đúng ở slide 1 + 21 + footer trên nền `#F8F7F1`.
- [ ] Slide 5 dùng 4 ảnh THẬT `assets/shot-*.png` (student/cv/partner/university) — đã có sẵn.
- [ ] Số liệu đã điền hết (team C2-Team-037, thị trường, giá, KPI, Ask) — **không còn placeholder**.
- [ ] Mỗi slide ÍT CHỮ, nhiều hình; slide có số thị trường (2, 3, 20) có dòng "Nguồn:" nhỏ ở chân.
- [ ] Chỉ **1 panel gradient indigo→violet mỗi slide** (đúng quy tắc v10) — không lạm dụng.
- [ ] Nhãn `Được tài trợ` / `Quảng cáo` **không bị bỏ** ở business (7), showcase (5), governance (18).
- [ ] Số liệu quy mô (slide 6) khớp với lệnh đếm trong spec.
- [ ] Câu chuyện "nền tảng" (slide 3, 8, 19, 21) giữ khung *tầm nhìn + sẵn-sàng-kỹ-thuật* (vòng/chặng mở rộng
      vẽ nét đứt), không hứa mốc bán SaaS.
- [ ] Thử in PDF landscape: mỗi slide = đúng 1 trang, không tràn.
