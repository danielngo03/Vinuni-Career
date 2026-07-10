# Hướng dẫn dựng & đồng bộ deck 15 slide

Deck này **đã được dựng sẵn bằng code** (`build_deck.py`) và **đã đẩy lên claude.ai/design**. File này hướng
dẫn cách xem, sửa, đẩy lại, và xuất PDF.

## Deck đang ở đâu?

- **File local:** `slide/deck/slide-01.html … slide-15.html` (mỗi slide 1 file, có marker `@dsCard`) và
  `slide/deck/deck.html` (bản gộp để trình chiếu).
- **Trên claude.ai/design:** project **"VinUni Pitch Deck — C2-037"**
  → https://claude.ai/design/p/4a48a9a7-b406-4db7-b785-85328b453205 (id lưu trong `slide/deck/.design-project.json`).

## Quy trình sửa slide (chuẩn)

1. Sửa nội dung/bố cục trong **`slide/build_deck.py`** (mỗi slide là 1 hàm `s1()…s15()`; token màu, card,
   laptop/browser mockup, chart đều là helper sẵn).
2. Chạy: `python3 slide/build_deck.py` → sinh lại `slide/deck/*.html`.
3. Xem thử local: `cd slide/deck && python3 -m http.server 8099` → mở `http://localhost:8099/deck.html`.
4. Đẩy lên claude.ai/design: gõ **`/design-login`** (nếu phiên chưa có quyền) rồi **`/design-sync`** trong
   Claude Code — chỉ file đổi mới được đẩy, mỗi slide là 1 card trong project.

> `/design-sync` chỉ **đồng bộ file HTML có sẵn** lên project — nó không tự vẽ slide. Việc "vẽ" nằm ở
> `build_deck.py`. Cũng có thể nhờ chính Claude Design tinh chỉnh 1 card rồi chép ngược thay đổi về generator.

## Asset (đã có đủ trong `slide/assets/`)

- `logo-dark-480.png` — **logo mark đen chính thức** cho nền sáng `#F8F7F1` (chỉ dùng logo này).
- `shot-student-dashboard.png · shot-cv-studio.png · shot-partner-pipeline.png · shot-university-outcomes.png`
  — 4 screenshot THẬT từ app đang chạy (slide 1, 5) + 3 ảnh dự phòng `shot-partner-talent/dashboard`,
  `shot-university-dashboard`.
- `campus-small.jpg` — ảnh khuôn viên VinUni (slide 15).
- `lib/ic-*.svg` — 42 icon Solar duotone đã tô màu palette; `lib/logo-*.svg` — 13 logo công nghệ thật
  (tải bằng `python3 slide/fetch_assets.py`, chạy lại nếu cần thêm icon).

## Xuất PDF để nộp / trình chiếu offline

Mở `slide/deck/deck.html` → phím `←/→` để chuyển slide → `Cmd/Ctrl + P` → Save as PDF, chọn **Landscape**,
margin **None**, bật **Background graphics** — mỗi slide đúng 1 trang (đã có `@media print`).

## Checklist trước khi pitch

- [ ] `deck.html` chạy mượt 15 slide, không slide nào tràn/hụt.
- [ ] Logo trên bìa + slide 15 là `logo-dark-480.png` (mark đen); footer mọi slide: `C2-Team-037` · `NN / 15`.
- [ ] Slide 5 hiển thị 4 ảnh THẬT; slide 9 có số đối thủ + bảng so sánh; slide có số thị trường (3, 7, 9) có
      dòng "Nguồn" nhỏ.
- [ ] Chip "mục tiêu" (amber) còn nguyên ở slide 14 — không được trình bày như số đã đạt.
- [ ] Nhãn "Được tài trợ" ở slide 8 không bị bỏ.
- [ ] In thử PDF: 15 trang landscape, không vỡ layout.
