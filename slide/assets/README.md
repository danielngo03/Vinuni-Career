# assets/ — logo & hình ảnh cho deck

Bỏ các file hình vào đây rồi tham chiếu trong Claude Design.

## Cần có
- Logo VinUni cho **slide 1** (lớn) + **slide 20** + logo nhỏ ở footer mọi slide.
- **Logo đã có sẵn trong repo** — copy từ `frontend/public/brand/` sang folder này:
  - `logo-light.svg` — logo nét, nền sáng (khuyến nghị cho nền `#F8F7F1`) ✅
  - `logo-dark.svg` — bản cho nền tối (nếu làm slide dark)
  - `vinuni-logo.png` / `vinuni-logo-text.png` — bản PNG (logo + logo kèm chữ)
  - `VinUniversity.webp` / `VinUniversity.png` — bản đầy đủ
  - `../images/vinuni-campus.png` — ảnh campus (có thể dùng nền mờ slide bìa nếu muốn)
  - Lệnh nhanh: `cp frontend/public/brand/logo-light.svg slide/assets/`

## Nên có (tăng sức thuyết phục slide 5 — Product Showcase)
Screenshot sản phẩm thật (chụp khi chạy app local), đặt tên rõ:
- `shot-student-dashboard.png`
- `shot-cv-studio.png`
- `shot-partner-pipeline.png`
- `shot-university-analytics.png`

> Nếu không có screenshot, Claude Design sẽ **vẽ lại mock UI** theo design system (spec slide 5 đã mô tả) —
> vẫn đúng thương hiệu, chỉ kém "thật" hơn ảnh chụp.

## Cách nhúng để file HTML chạy offline
- Ưu tiên **embed data-URI** (base64) trực tiếp trong HTML để deck tự chứa, gửi đi đâu cũng chạy.
- Trong Claude Design, upload ảnh rồi yêu cầu: *"nhúng ảnh này dạng data-URI vào slide X"*.

## Lưu ý thương hiệu
- Đỏ VinUni chuẩn: `#c83538`. Không bóp méo tỷ lệ logo, không đổi màu logo.
- Giữ khoảng trống (clear space) quanh logo; nền `#F8F7F1` hợp với logo nền trong suốt.
