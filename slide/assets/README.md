# assets/ — logo & ảnh thật cho deck

Folder này **đã có sẵn** logo + screenshot thật để Claude Design nhúng vào slide. Không cần bạn thêm gì nữa.

## ✅ Logo (đã có)
- **`logo-dark.svg`** / **`logo-dark.png`** — dùng cái này! Đây là **logo mark ĐEN cho nền SÁNG** (`#F8F7F1`).
  *(Xác nhận từ `frontend/globals.css`: "logo-dark.* = black mark for light bg".)* → slide 1 (lớn) + slide 21 + footer.
- Nếu làm slide nền tối thì mới dùng `logo-light.*` (mark trắng cho nền tối) — copy từ `frontend/public/brand/`.

## ✅ Screenshot THẬT (đã chụp từ app đang chạy — dùng cho slide 5 Product Showcase)
| File | Bề mặt | Nội dung nổi bật |
|---|---|---|
| `shot-student-dashboard.png` | Student | Tổng quan sinh viên: hero monochrome + KPI tiles + phỏng vấn sắp tới |
| `shot-cv-studio.png` | Student · CV Studio | Hero + **marketplace 7 template CV** + "CV đã hoạt động 1/5" |
| `shot-partner-pipeline.png` | Partner | Pipeline ứng viên: KPI + donut + card "AI Theo dõi Pipeline" + bảng tiến độ |
| `shot-university-outcomes.png` | University | Kết quả nghề nghiệp: banner riêng-tư + donut tin cậy + top nhà tuyển dụng |
| `shot-partner-talent.png` | Partner *(dự phòng)* | Talent Pool AI search |
| `shot-partner-dashboard.png` | Partner *(dự phòng)* | Tổng quan đối tác |
| `shot-university-dashboard.png` | University *(dự phòng)* | Tổng quan nhà trường |

> Đây là ảnh **thật** từ app (persona student/partner/university, ngôn ngữ vi, theme sáng) — dùng trực tiếp,
> không cần vẽ lại mock. Nếu muốn thêm góc khác, chạy lại app và chụp bổ sung.

## Cách nhúng để deck chạy offline (tự chứa)
- Convert mỗi PNG → **data-URI base64** rồi dán thẳng vào `<img src="data:image/png;base64,…">`.
  Lệnh gợi ý (macOS): `base64 -i shot-student-dashboard.png | pbcopy` (đã copy vào clipboard).
- Trong Claude Design: upload ảnh rồi bảo *"nhúng ảnh này dạng data-URI vào slide 5, đặt trong khung trình duyệt bo góc"*.
- Đặt ảnh trong khung "browser frame" (thanh 3 chấm giả macOS) bo 14px, `max-width:100%`, giữ tỉ lệ.

## Lưu ý thương hiệu
- Đỏ VinUni chuẩn: `#c83538`. Không bóp méo tỉ lệ logo, không đổi màu logo.
- Giữ clear-space quanh logo; nền `#F8F7F1` hợp với `logo-dark` (mark đen, nền trong suốt).
