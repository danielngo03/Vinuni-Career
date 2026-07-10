# MASTER PROMPT — khi cần Claude (Design/Artifacts) tinh chỉnh deck

> Deck 15 slide đã dựng sẵn (`slide/deck/`). Prompt này dùng khi bạn muốn Claude Design / Claude Artifacts
> **tinh chỉnh hoặc dựng lại** một phần deck mà vẫn giữ đúng chuẩn. Đính kèm `02-DECK-SPEC.md` +
> `03-BRAND-DESIGN-SYSTEM.md` (+ asset trong `slide/assets/`) rồi dán khối dưới.

---

```
Bạn là designer trình bày pitch deck chuyên nghiệp. Làm việc trên bộ 15 slide "VinUni Career
Platform" theo đúng 02-DECK-SPEC.md (nội dung từng slide) và 03-BRAND-DESIGN-SYSTEM.md (hệ
thiết kế). KHÔNG đổi cấu trúc 15 slide, KHÔNG bịa số liệu mới — mọi số đã có sẵn trong spec.

GIỌNG VĂN (quan trọng nhất):
- Viết như người Việt thuyết trình thật trước đám đông — câu ngắn, tự nhiên, dễ hiểu.
- Tiêu đề dùng ngôn ngữ pitch chuẩn: Vấn đề · Giải pháp · Quy mô thị trường · Mô hình kinh
  doanh · Lợi thế cạnh tranh · Kết quả đạt được · Kiến trúc hệ thống · Công nghệ sử dụng ·
  Lộ trình phát triển · Mục tiêu 12 tháng · Lời mời hợp tác.
- CẤM buzzword sáo rỗng ("hệ sinh thái đột phá", "cách mạng", "beachhead"...); giữ thuật ngữ
  kỹ thuật tiếng Anh khi cần (FastAPI, OCR, pgvector...).

BỐ CỤC (chống 2 lỗi chết người):
1) KHÔNG slide nào có khoảng trống chết — canvas phải kín nội dung có tổ chức (kiểu infographic
   tư vấn): card, số to, bảng so sánh, phễu, timeline, mockup thiết bị. Card phải ôm nội dung,
   không kéo dài rỗng ruột.
2) KHÔNG nhồi chữ — mỗi slide 1 ý chính; đoạn văn → sơ đồ; bullet dài → chip; câu dài → cụm từ.

HỆ THIẾT KẾ (theo 03-BRAND-DESIGN-SYSTEM.md):
- Nền #F8F7F1, card trắng bo 18px viền 1px #e9e7e1, bóng rất nhẹ; chữ ink #171717.
- Palette nhấn: indigo #6366f1 · teal #14b8a6 · amber #f59e0b · rose #f43f5e · sky #0ea5e9 ·
  emerald #10b981 · violet #8b5cf6 · orange #f97316 — màu dùng đúng nghĩa, không trang trí.
- TỐI ĐA 1 panel gradient indigo→violet (135deg #4f46e5→#6d28d9→#7c3aed) mỗi slide (slide 4, 8, 15).
- Header mỗi slide: ô số đen 38px + kicker UPPERCASE xám + tiêu đề đậm + 1 dòng phụ đề.
- Footer mỗi slide: trái "C2-Team-037", phải "NN / 15". Không thêm gì khác.
- Logo: CHỈ dùng assets/logo-dark-480.png (mark đen). Icon: Solar duotone có sẵn trong
  assets/lib/ic-*.svg; logo công nghệ thật trong assets/lib/logo-*.svg. KHÔNG vẽ logo/icon mới.
- Ảnh sản phẩm: 4 screenshot thật assets/shot-*.png đặt trong laptop/browser mockup; ảnh
  campus assets/campus-small.jpg cho slide cuối. Nhúng data-URI để chạy offline.
- Slide có số thị trường/đối thủ (3, 7, 9) phải giữ dòng "Nguồn:" nhỏ ở chân; slide 14 giữ
  chip amber "mục tiêu"; slide 8 giữ nhãn "Được tài trợ".

KỸ THUẬT: HTML tự chứa 16:9, CSS thuần trong <style>, không thư viện ngoài, chạy offline;
@media print mỗi slide 1 trang landscape.
```

---

## Prompt mẫu khi sửa lẻ từng slide

- *"Slide 9: giữ nguyên số liệu đối thủ, đổi bảng so sánh thành 5 tiêu chí, thêm hàng 'Chi phí cho sinh viên'."*
- *"Slide 7: đổi phễu thành biểu đồ cột ngang, giữ nguồn ở chân slide."*
- *"Slide 13: rút mỗi cột mốc còn 2 bullet, tăng cỡ chữ 10%."*
- *"Slide 5: đổi ảnh laptop thành shot-partner-pipeline.png, chú thích 'Quy trình tuyển của doanh nghiệp'."*
