# BRAND & DESIGN SYSTEM — bộ slide 15 trang

Hệ thiết kế của deck (đã cài trong `build_deck.py` — biến CSS `:root`). Bám ngôn ngữ thị giác v10 của chính
sản phẩm: nền giấy ấm + card trắng + ink làm màu hành động + palette data-viz có nghĩa.

## 1. Màu

```
Nền slide   #F8F7F1      Card        #ffffff      Viền   #e9e7e1
Ink (chữ/hành động) #171717   Chữ phụ #57534e   Chữ mờ #a8a29e
Palette nhấn: indigo #6366f1 · teal #14b8a6 · amber #f59e0b · rose #f43f5e
              sky #0ea5e9 · emerald #10b981 · violet #8b5cf6 · orange #f97316
Gradient hero (tối đa 1 panel/slide): linear-gradient(135deg,#4f46e5 0%,#6d28d9 55%,#7c3aed 100%)
```

Màu dùng đúng nghĩa: emerald = tốt/đã xong · amber = cảnh báo/"mục tiêu"/"Được tài trợ" · rose = điểm nghẽn/
thiếu · sky/indigo = thông tin/AI. Persona: sinh viên sky · doanh nghiệp teal · nhà trường amber.

## 2. Chữ & khối

- Font hệ thống (SF/Segoe/Be Vietnam Pro fallback) — không phụ thuộc webfont để chạy offline.
- Header slide: **ô số đen 38px bo 11px** + kicker UPPERCASE (0.72rem, xám, tracking .16em) + tiêu đề 2.15rem
  weight 800 tracking −.02em + 1 dòng phụ đề 0.95rem xám.
- Card: bo **18px**, viền 1px `#e9e7e1`, bóng `0 10px 26px -16px rgba(23,23,23,.16)`. Chip: pill bo tròn.
- Số liệu: weight 800, `tabular-nums`.
- **Footer mọi slide:** trái `C2-Team-037` · phải `NN / 15` (0.74rem, xám mờ). Không thêm gì khác.

## 3. Asset (tất cả trong `slide/assets/`)

| Loại | File | Quy tắc |
|---|---|---|
| Logo | `logo-dark-480.png` | **Logo duy nhất được dùng** (mark đen, nền trong suốt). Trên panel gradient: thêm `filter:invert(1) brightness(2)`. |
| Screenshot | `shot-*.png` (7 file) | Ảnh thật từ app — luôn đặt trong laptop/browser mockup, không dán trần. |
| Ảnh | `campus-small.jpg` | Khuôn viên VinUni — slide kết, có overlay caption. |
| Icon | `lib/ic-*.svg` (42) | Solar **bold-duotone** đã tô màu palette — đặt trong ô `background:{màu}14` bo 10–12px. Không vẽ icon tay, không emoji. |
| Logo công nghệ | `lib/logo-*.svg` (13) | Logo thật (Next.js, React, Python, FastAPI, Postgres, Redis…) — chỉ dùng ở slide kiến trúc/công nghệ. |

Tải lại/bổ sung asset: `python3 slide/fetch_assets.py` (Iconify API).

## 4. Mockup & chart (helper sẵn trong generator)

- **Laptop**: màn `#171717` bo 12px + đế gradient — cho screenshot chính.
- **Browser**: thanh 3 chấm macOS + ảnh `object-fit:cover` + nhãn icon — cho screenshot phụ.
- **Donut** (điểm 0–100), **phễu thanh ngang** (thị trường/mục tiêu), **timeline cột mốc** (lộ trình),
  **bảng so sánh ✓/△/✕** (cạnh tranh — cột VinUni tô `indigo10`), **card đối thủ** (số + dòng ✕ thiếu).

## 5. Quy tắc bố cục (chống lỗi đã gặp)

1. Mỗi slide **một ý chính** — nhưng canvas phải **kín nội dung có tổ chức**; card ôm nội dung
   (`justify-content:center`, không kéo rỗng ruột), lưới dùng `align-content:center`.
2. Tối đa **1 panel gradient**/slide (hiện ở slide 4, 8, 15).
3. Chữ như người thuyết trình thật — câu ngắn; cấm buzzword; đoạn văn → sơ đồ, bullet dài → chip.
4. Số thị trường/đối thủ phải kèm dòng "Nguồn:" nhỏ; số mục tiêu phải gắn chip amber "mục tiêu".
5. Không gỡ nhãn "Được tài trợ"; không lộ tên nhà cung cấp AI.
