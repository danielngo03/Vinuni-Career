# BRAND & DESIGN SYSTEM — cho bộ slide

Hệ thiết kế slide **bám đúng design system thật của sản phẩm** (v10 "Monochrome Shell + Data-viz Content" —
`docs/DESIGN.md §1.1.2` + `frontend/src/app/globals.css`). Claude Design phải dùng đúng các token dưới đây.

---

## 1. Nền & khung tổng (deck-level)

- **Nền slide:** `#F8F7F1` (giấy ấm — lựa chọn của bạn). **Thẻ/card:** trắng tinh `#ffffff`.
  > Lưu ý: sản phẩm thật dùng canvas `#fafafa` (trắng lạnh). `#F8F7F1` là biến thể "giấy ấm" cố ý cho slide —
  > **giữ nhất quán toàn deck**, và card luôn `#ffffff` để tương phản với nền.
- **Khung monochrome (SHELL):** mọi tiêu đề/chữ/viền dùng thang xám; **không** dùng đen tuyền `#000` trên
  trắng tuyền. Ink hành động: `#171717`.
- **Bo góc:** card `14px` (rounded-xl); chip/badge/dot bo tròn hoàn toàn (pill); ô icon `10px`.
- **Viền & bóng:** **viền 1px `#e5e5e5` gánh hình khối**; bóng gần như vô hình
  (`shadow-sm: 0 1px 3px rgba(0,0,0,.06)`). Triết lý: "công cụ vận hành nghiêm túc — viền sắc nét hơn là glow".

---

## 2. Bảng màu chính xác (dán nguyên vào Claude Design)

### 2.1 Thang xám SHELL (monochrome — khung, chữ, viền)
```
50 #fafafa · 100 #f5f5f5 · 200 #e5e5e5 · 300 #d4d4d4 · 400 #a3a3a3 · 500 #737373
600 #525252 · 700 #404040 · 800 #262626 · 900 #171717 · 950 #0a0a0a
```
- Nền slide `#F8F7F1` · Card `#ffffff` · Viền `#e5e5e5` · Chữ chính `#171717` · Chữ phụ `#525252` ·
  Chữ mờ/muted `#8f8f8f` · Kicker/eyebrow `#737373`.

### 2.2 Palette DATA-VIZ (CONTENT — biểu đồ, KPI, chip, trạng thái) — thứ tự khóa, colorblind-safe
```
indigo  #6366f1   teal   #14b8a6   amber  #f59e0b   rose   #f43f5e
sky     #0ea5e9   emerald #10b981  violet #8b5cf6   orange #f97316
```
- Mỗi màu có tint `-soft` ~12% để đổ nền chip/tile, ví dụ indigo-soft `rgba(99,102,241,0.12)`.
- **Chuỗi biểu đồ phân loại** đi theo đúng thứ tự: indigo → teal → amber → rose → sky → emerald → violet → orange.

### 2.3 Màu ngữ nghĩa (dùng ĐÚNG ý nghĩa, không trang trí)
- **Thành công / tốt:** emerald `#10b981`
- **Cảnh báo / SPONSORED:** amber `#f59e0b`  ← nhãn `Được tài trợ`/`Quảng cáo` **luôn amber, không gỡ**
- **Nguy hiểm / thương hiệu VinUni:** đỏ VinUni `#c83538` (RGB 200,53,56)
- **Thông tin / AI:** sky `#0ea5e9` hoặc indigo `#6366f1`

### 2.4 Gradient hero (ĐIỂM NHẤN — tối đa 1 panel/slide)
```
linear-gradient(135deg, #4f46e5 0%, #6d28d9 55%, #7c3aed 100%)   /* chữ trắng */
```
- Chỉ dùng cho **1** khối tóm tắt/hero mỗi slide. **Không** dùng làm nền cả slide. **Không** quá 1 lần/slide.

### 2.5 Thương hiệu VinUni
- Đỏ VinUni `#c83538` (dùng cho logo/điểm nhấn thương hiệu & trạng thái "danger/risk").
- Xanh VinUni cũ `#2e548a` đã **remap sang xám** trong shell v10 — **không** dùng làm accent nền xanh/navy.

---

## 3. Typography

- **Font chính:** **Plus Jakarta Sans** (heading + body). Fallback: Inter / Be Vietnam Pro.
- **Font số/metric:** **JetBrains Mono** (`tabular-nums`) — dùng cho mọi con số KPI, score, lương, %.
- **Thang chữ khóa (size / line-height / weight):**
  ```
  display  30–56 / 1.15 / 600   (tiêu đề bìa & hero — có thể phóng to cho slide)
  h1       24 / 32 / 600
  h2       20 / 28 / 600
  h3       16 / 24 / 600
  body     14 / 20 / 400
  small    13 / 18 / 400
  caption  12 / 16 / 500
  metric   30 / 1 / 600  tabular-nums
  kicker   11 / — / 600  UPPERCASE, letter-spacing 0.12em, màu #737373
  ```
- Heading dùng **letter-spacing âm nhẹ** (−0.02em → −0.01em). Weight cho phép: 400/500/600/700.

---

## 4. Component pattern (Claude Design tái sử dụng cho mọi slide)

- **KPI tile:** `rounded-xl border bg-white p-4 shadow-sm` · số lớn tabular (JetBrains Mono) · 1 delta pill
  bo tròn (emerald ↑ / rose ↓) · 1 ô icon `rounded-lg` màu palette-soft.
- **Chip / status:** pill bo tròn = chấm màu + nền `-soft` + chữ đậm cùng tông. (vd "Strong fit" = emerald).
- **Card:** trắng, viền 1px `#e5e5e5`, bóng cực nhẹ; hover nâng viền lên `#d4d4d4`.
- **Flow node:** pill/box bo 14px, icon lucide bên trái, mũi tên nối mảnh; node "AI/ghi" viền sky/amber.
- **Biểu đồ (Recharts style):** gridline `#e5e5e5`, tooltip bo 10px, area fill gradient nhẹ, chuỗi theo thứ
  tự palette. Donut/score dùng màu band tương ứng.
- **Icon:** **chỉ lucide-react** (nét mảnh monochrome). **Heart = yêu thích job** (không nhầm bookmark). Không
  dùng emoji làm icon UI (emoji trong file spec này chỉ để bạn đọc).

---

## 5. Layout grammar cho mỗi slide (khung lặp lại)

```
┌────────────────────────────────────────────────────────────┐
│ KICKER (11px, uppercase, xám)                    ● logo nhỏ │
│ Tiêu đề slide (h1/display, ink #171717)                     │
│ ── dòng phụ ngắn (body, #525252) ──                         │
│                                                             │
│   [ Vùng nội dung: card trắng / flow / biểu đồ / KPI ]      │
│   • tối đa 1 panel gradient indigo→violet                   │
│                                                             │
│ footer: tên deck • VinUni • 07 / 20  (số trang)             │
└────────────────────────────────────────────────────────────┘
```
- **Lưới:** 12 cột, gutter thoáng, lề rộng. Ưu tiên **khoảng trắng** (premium = restraint).
- **Mật độ:** mỗi slide 1 ý chính; ≤ 3–4 gạch đầu dòng/khối; đừng nhồi chữ.

---

## 6. Cheat-sheet "on-brand" (8 quy tắc Claude Design phải theo)

1. **Nền `#F8F7F1`, card `#ffffff`** — nhất quán toàn deck; không đen/trắng tuyền.
2. **Khung xám, nhấn có ý nghĩa** — màu chỉ mang ý nghĩa (emerald=tốt, amber=sponsored/cảnh báo, đỏ VinUni=
   danger/brand, sky/indigo=info/AI). Dữ liệu phân loại theo thứ tự palette.
3. **Tối đa 1 gradient indigo→violet mỗi slide** (hero rule). Không blob gradient, không glow.
4. **Card:** rounded 14px, viền 1px `#e5e5e5`, bóng gần như không. Sắc nét, không bóng bẩy.
5. **Chữ:** Plus Jakarta Sans; heading tracking âm nhẹ; **mọi số dùng mono tabular**.
6. **Khoảng trắng rộng, 1 ý/slide.** Năng lượng Linear/Vercel/ops-tool, không marketing filler.
7. **Colorblind-safe & light+dark:** ưu tiên light cho slide; nếu làm dark, dùng canvas `#0a0a0a`, card
   `#111111`, viền `#262626`, chữ `#ededed`.
8. **KHÔNG bao giờ** gỡ nhãn `Được tài trợ`/`Quảng cáo`; **KHÔNG** phơi tên provider/model AI, token, latency.

---

## 7. Skeleton CSS gợi ý (để Claude Design khởi tạo nhanh — tùy chọn)

```css
:root{
  --bg:#F8F7F1; --card:#ffffff; --border:#e5e5e5; --ink:#171717; --muted:#525252; --faint:#8f8f8f;
  --indigo:#6366f1; --teal:#14b8a6; --amber:#f59e0b; --rose:#f43f5e;
  --sky:#0ea5e9; --emerald:#10b981; --violet:#8b5cf6; --orange:#f97316;
  --vinuni:#c83538; --radius:14px;
  --hero:linear-gradient(135deg,#4f46e5 0%,#6d28d9 55%,#7c3aed 100%);
  --font:"Plus Jakarta Sans",Inter,"Be Vietnam Pro",system-ui,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,monospace;
}
.slide{aspect-ratio:16/9; background:var(--bg); color:var(--ink); font-family:var(--font);
  padding:48px 64px; }
.card{background:var(--card); border:1px solid var(--border); border-radius:var(--radius);
  box-shadow:0 1px 3px rgba(0,0,0,.06); }
.kicker{font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.12em; color:#737373;}
.metric{font-family:var(--mono); font-weight:600; font-variant-numeric:tabular-nums;}
.hero{background:var(--hero); color:#fff; border-radius:var(--radius);}
@media print{ .slide{ page-break-after:always; } }  /* mỗi slide 1 trang khi in PDF landscape */
```
