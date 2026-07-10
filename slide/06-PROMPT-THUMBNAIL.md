# Prompt tạo thumbnail — VinUni Career Platform

> **Cách dùng (2 bước):** ① đính kèm **`slide/assets/logo-dark-480.png`** vào chat Gemini / ChatGPT →
> ② dán nguyên khối prompt dưới. Tỷ lệ 16:9.

---

## ⚡ PROMPT SỬA TIẾP ẢNH ĐÃ CÓ (khuyên dùng — dán ngay sau ảnh vừa tạo, cùng đoạn chat)

```
Refine this image. Keep the overall composition, the character, the campus skyline
and all five floating cards EXACTLY as they are. Change ONLY the text block:

1. SHRINK the headline by about 35% — it must occupy at most 40% of the image width,
   still extra-bold ink #171717, two lines:
   "Kết nối Sinh viên,
    Doanh nghiệp & Nhà trường"
2. Replace the bullet subtitle line with ONE short gray #57534e sentence right under
   the headline: "Một nền tảng duy nhất — AI hỗ trợ từng bước."
3. Fill the EMPTY bottom-left corner with a neat row of 3 small white pill chips
   (rounded-full, thin border, soft shadow), each with a tiny pastel icon:
   • violet document icon + "CV thông minh"
   • mini multicolor donut + "Điểm phù hợp 0–100"
   • sky sparkle + "Phỏng vấn thử AI"
4. Rebalance vertical spacing of the left column: lockup top, headline centered
   around the upper third, pill chips anchored near the bottom margin — no large
   empty gaps. Keep all margins even. Render Vietnamese diacritics exactly.
```

---

## ✅ PROMPT CHUẨN (v7 — bản full, dùng khi tạo lại từ đầu)

```
I have attached the OFFICIAL logo: a black geometric chevron "V" mark. Use it EXACTLY
as-is — never redraw, restyle, recolor or distort it.

Create a premium 16:9 hero thumbnail for "VinUni Career Platform" — a university
career platform that connects STUDENTS, COMPANIES and the UNIVERSITY, with AI helping
at every step. FULL FLAT VECTOR ILLUSTRATION, top-tier SaaS hero art (Dribbble /
Behance quality): clean geometry, rounded corners, soft shadows, balanced whitespace.
NOT photorealistic, NOT 3D.

TYPOGRAPHY & LEFT-COLUMN LAYOUT (one modern geometric sans-serif family, like
Inter / SF Pro / Plus Jakarta Sans; render Vietnamese diacritics EXACTLY; the whole
text block stays within the LEFT 40% of the frame, evenly spaced top-to-bottom with
NO large empty gaps):
- Top: brand lockup in one row — attached logo (small) + thin vertical divider "|" +
  "VINUNI CAREER PLATFORM" in bold uppercase ink #171717, slight letter-spacing.
- Upper third: headline, extra-bold ink #171717, tight line-height, MODERATE size
  (each line about 2.5x the lockup text height — impactful but NOT oversized, max
  40% of image width), two lines:
  "Kết nối Sinh viên,
   Doanh nghiệp & Nhà trường"
- Right under it: one short sentence in gray #57534e, ~1/3 headline size:
  "Một nền tảng duy nhất — AI hỗ trợ từng bước."
- Anchored near the BOTTOM margin (fills the lower-left corner): a neat row of 3
  small white pill chips (rounded-full, thin border, soft shadow), each with a tiny
  pastel icon: violet document + "CV thông minh"; mini multicolor donut + "Điểm phù
  hợp 0–100"; sky sparkle + "Phỏng vấn thử AI".

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
