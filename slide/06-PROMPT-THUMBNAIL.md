# Prompt tạo thumbnail — VinUni Career Platform

> Dán prompt vào **Gemini / ChatGPT (DALL·E) / Midjourney**. Ảnh model tiếng Anh hiểu tốt hơn nên prompt
> chính viết bằng tiếng Anh; chữ hiển thị trên ảnh giữ tối thiểu (chữ tiếng Việt có dấu hay bị vẽ sai —
> có phiên bản riêng bên dưới nếu bạn vẫn muốn thử). Tỷ lệ khuyên dùng: **16:9**.

---

## 🎯 Prompt chính (khuyên dùng)

```
A modern, premium 16:9 product thumbnail for "VinUni Career Platform" — a university
career & recruitment platform connecting students, companies and the university.

STYLE: clean flat vector illustration with very subtle soft shadows, top-tier SaaS
marketing style (Dribbble / Behance quality), crisp and minimal, generous whitespace,
absolutely no clutter. NOT 3D render, NOT photorealistic.

BACKGROUND: warm paper cream #F8F7F1, perfectly flat.

MAIN COMPOSITION:
- Left side: big bold headline text "VinUni Career Platform" in near-black ink #171717,
  modern geometric sans-serif, tight letter spacing. Above the headline sits a small
  black geometric chevron logo mark (a downward-pointing "V" arrow built from tangram
  triangles). Under the headline, a thin row of 8 small colored dots: indigo #6366f1,
  teal #14b8a6, amber #f59e0b, rose #f43f5e, sky #0ea5e9, emerald #10b981,
  violet #8b5cf6, orange #f97316.
- Right side: a sleek laptop mockup (dark #171717 frame) floating slightly, screen
  showing a clean dashboard UI: white rounded cards on light background, a small
  donut chart with "87" in the middle, colorful KPI chips, a kanban board column.
- Floating around the laptop, 3 small white rounded cards (18px corner radius look,
  soft shadow): (1) a CV/resume document with a green check, (2) a chat bubble with
  an AI sparkle icon, (3) a graduation cap icon next to a tiny briefcase — connected
  to the laptop by thin dotted lines.
- One single accent: a smooth diagonal gradient ribbon/panel from indigo #4f46e5 to
  violet #7c3aed behind or beneath the laptop — the only gradient in the image.

COLOR DISCIPLINE: cream background, white cards, near-black text, and the 8 accent
colors above only. No navy blue backgrounds, no neon, no dark mode.

MOOD: trustworthy, modern, optimistic — a real product, not a concept.
Text on image: ONLY "VinUni Career Platform". Spell it exactly, no other words.
```

## ✂️ Bản ngắn (nếu tool giới hạn độ dài)

```
Modern flat vector 16:9 SaaS thumbnail, warm cream background #F8F7F1. Bold black
headline "VinUni Career Platform" (spelled exactly) with a small black tangram-style
chevron V logo and a row of 8 tiny colored dots (indigo, teal, amber, rose, sky,
emerald, violet, orange). Right side: floating dark laptop showing a clean dashboard
with white rounded cards, a donut chart reading "87", colorful chips. Around it, three
small white rounded cards with soft shadows: resume with green check, AI chat bubble
with sparkle, graduation cap + briefcase, linked by dotted lines. One indigo-to-violet
gradient ribbon behind the laptop. Crisp, minimal, premium, Dribbble quality. No 3D,
no photo, no dark background, no extra text.
```

## 🇻🇳 Bản có phụ đề tiếng Việt (rủi ro chữ bị sai dấu — kiểm tra kỹ)

Thêm vào cuối prompt chính, trước dòng "Text on image":

```
Add one small subtitle line under the headline, in gray #57534e:
"Nền tảng việc làm cho sinh viên - doanh nghiệp - nhà trường"
```
> Nếu chữ Việt bị vẽ sai, bỏ phụ đề và quay lại bản chỉ có "VinUni Career Platform".

## 🚫 Negative prompt (Midjourney `--no` hoặc dán thêm cho Gemini/DALL·E)

```
no 3D render, no photorealism, no glassmorphism, no neon glow, no dark/navy background,
no stock photo people, no watermark, no gibberish text, no extra logos, no clutter
```

## 💡 Mẹo

- **Tỷ lệ:** chọn 16:9 (Midjourney thêm `--ar 16:9`). Cần vuông cho avatar thì đổi thành 1:1 và bảo
  "stack the headline above the laptop".
- Chữ trên ảnh là điểm yếu của model — nếu "VinUni Career Platform" bị sai chính tả, generate lại 2–3 lần
  hoặc bảo *"fix the spelling of the headline text"*; đường cùng thì để ảnh trống chữ rồi tự chèn chữ bằng
  Canva/Figma (font đậm, màu #171717).
- Muốn giống deck hơn nữa: đưa kèm ảnh chụp slide 01 (trang bìa) cho Gemini/ChatGPT và nói *"match this
  visual style and color system"*.
- 3 biến thể thử nhanh: (a) đổi laptop thành **điện thoại + laptop cạnh nhau**; (b) thay 3 card nổi bằng
  **vòng tròn 3 nhân vật flat**: sinh viên – nhà tuyển dụng – nhà trường nối mũi tên vòng tròn quanh logo;
  (c) phóng to **donut 87/100** thành nhân vật chính giữa, laptop lùi về sau.
