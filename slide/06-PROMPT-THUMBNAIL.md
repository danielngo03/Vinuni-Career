# Prompt tạo thumbnail — VinUni Career Platform

> **Cách dùng (2 bước):** ① đính kèm **`slide/assets/logo-dark-480.png`** vào chat Gemini / ChatGPT →
> ② dán nguyên khối prompt dưới. Tỷ lệ 16:9.

---

## ✅ PROMPT CHUẨN (v6 — dán nguyên khối này)

```
I have attached the OFFICIAL logo: a black geometric chevron "V" mark. Use it EXACTLY
as-is — never redraw, restyle, recolor or distort it.

Create a premium 16:9 hero thumbnail for "VinUni Career Platform" — a university
career platform that connects STUDENTS, COMPANIES and the UNIVERSITY, with AI helping
at every step. FULL FLAT VECTOR ILLUSTRATION, top-tier SaaS hero art (Dribbble /
Behance quality): clean geometry, rounded corners, soft shadows, balanced whitespace.
NOT photorealistic, NOT 3D.

TYPOGRAPHY (one modern geometric sans-serif family, like Inter / SF Pro / Plus
Jakarta Sans; render Vietnamese diacritics EXACTLY):
- Top-left brand lockup, one row: attached logo (small) + thin vertical divider "|" +
  "VINUNI CAREER PLATFORM" in bold uppercase ink #171717, slight letter-spacing.
- Headline below, LARGE (dominant element of the left half, ~4x the lockup size),
  extra-bold ink #171717, tight line-height, two lines:
  "Kết nối Sinh viên,
   Doanh nghiệp & Nhà trường"
- Subtitle, medium gray #57534e, ~1/4 headline size:
  "CV thông minh • Điểm phù hợp 0–100 • Phỏng vấn thử AI"
- Keep generous margins; text block occupies the left 45% on clean cream space.

COLOR SYSTEM (this is the product's real design language — follow strictly):
- Background: warm cream #F8F7F1. Text: ink #171717 + gray. NO purple theme, no navy,
  no neon, no gradients.
- UI cards: pure white, rounded, thin light border, soft shadow — and every card icon
  sits inside a small SOFT PASTEL TINTED rounded square, exactly like a modern
  dashboard: CV icon on soft violet tint #8b5cf6, chat sparkle on soft sky tint
  #0ea5e9, briefcase on soft teal tint #14b8a6, graduation cap on soft amber tint
  #f59e0b, checkmarks emerald #10b981. Donut ring multicolor: indigo #6366f1, teal
  #14b8a6, amber #f59e0b, emerald #10b981. These pastel chips + chart colors are what
  make the image lively — use them confidently, but ONLY inside the cards.
- Student character: charcoal/ink sweater with white collar (monochrome clothing);
  warm friendly face.
- Background skyline: light warm-gray campus (buildings, clock tower), muted soft
  green trees, two tiny grayscale walking students; a few small palette-colored dots
  and one thin curved dotted line for motion. Ground shadow under the scene.

SCENE (right 55%): the student at a laptop, centered among 5 floating white cards
connected by thin dotted lines:
 (1) "Match-score" card with the multicolor donut showing "87" + emerald "match" chip
 (2) CV checklist card with emerald checkmarks (violet-tinted CV icon)
 (3) "AI chat" card with sparkle icon (sky tint)
 (4) "Job" card with briefcase icon (teal tint)
 (5) "Analytics" card with graduation cap + tiny multicolor bar chart (amber tint)

MOOD: bright, warm, professional, optimistic — a polished real product. No watermark,
no extra logos, no gibberish text; only the lockup, the 2-line headline, the subtitle,
and short card labels (Match-score, AI chat, Job, Analytics).
```

---

## Tuỳ chọn & mẹo

- **Chữ Việt sai dấu** → generate lại 2–3 lần; vẫn sai thì bảo *"leave the text areas empty"* rồi tự chèn
  chữ bằng Canva (font Plus Jakarta Sans / Inter đậm, màu #171717).
- **Logo bị vẽ lại lệch** → nhắc *"the logo must match the attached file exactly"*; chắc ăn nhất: chừa trống
  lockup rồi tự ghép logo + chữ bằng Canva.
- **Ảnh ra vẫn nhạt/xám quá** → thêm: *"increase color presence inside the cards: bigger pastel icon chips,
  bolder donut ring"*. Ngược lại nếu loè loẹt: *"reduce colored dots in the background"*.
- **Negative prompt** (Midjourney `--no`): `purple theme, navy background, neon, 3D render, photorealism,
  glassmorphism, watermark, extra logos, gibberish text, clutter`.
- Cần bản vuông 1:1: *"square 1:1 — lockup top, headline under it, scene below"*.
