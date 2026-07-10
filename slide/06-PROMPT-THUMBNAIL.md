# Prompt tạo thumbnail — VinUni Career Platform

> **Cách dùng (2 bước):** ① đính kèm file **`slide/assets/logo-dark-480.png`** vào chat của Gemini / ChatGPT
> → ② dán nguyên **một prompt duy nhất** dưới đây. Xong. Tỷ lệ 16:9.

---

## ✅ PROMPT CHUẨN v5 — trắng đen chủ đạo, logo lockup trên đầu (dán nguyên khối này)

```
I have attached the OFFICIAL logo of this product: a black geometric chevron "V" mark.
Use the attached logo EXACTLY as-is — do not redraw, restyle, recolor or distort it.

Create a modern, premium 16:9 hero thumbnail for "VinUni Career Platform" — an
AI-powered university career platform. FULL FLAT VECTOR ILLUSTRATION style, like
top-tier SaaS landing-page hero art (Dribbble / Behance quality): clean shapes,
smooth rounded corners, subtle soft shadows. NOT photorealistic, NOT 3D.

OVERALL COLOR RULE — MONOCHROME FIRST: the design is essentially BLACK & WHITE on a
warm cream background #F8F7F1. All text, the accent bar, icons, outlines and the
student's clothing are near-black ink #171717, white and grays ONLY. Small colors are
allowed ONLY inside the data/UI details: emerald #10b981 checkmarks and "match" chip,
a multicolor donut ring (indigo #6366f1, teal #14b8a6, amber #f59e0b), tiny bar chart
bars, and a few small scattered accent dots. NO purple/violet theme, no gradient bar,
no colored clothing, no navy, no neon.

TOP-LEFT BRAND LOCKUP: the attached black logo mark (small), then a thin vertical
divider line "|", then bold uppercase ink text "VINUNI CAREER PLATFORM" — all on one
horizontal line, like a professional website header.

TEXT BLOCK (left half, below the brand lockup, left-aligned):
 line 1 — huge bold headline in ink #171717: "Cho Sinh Viên Thời AI"
          (render the Vietnamese diacritics EXACTLY; keep "AI" ink black too)
 line 2 — small gray #57534e: "CV • Việc làm • Phỏng vấn AI"

SCENE (right half): a cheerful vector-illustrated Vietnamese university student
(simple friendly face, BLACK or charcoal sweater over a white shirt) at a laptop.
Around them float clean WHITE rounded UI cards with thin ink icons, soft shadows,
connected by thin dotted ink lines:
 (1) a "Match-score" card with a multicolor donut ring showing "87" and a small
     emerald "match" chip,
 (2) a CV/resume checklist card with emerald checkmarks,
 (3) an "AI chat" card with a black sparkle icon,
 (4) a "Job" card with a black briefcase icon,
 (5) an "Analytics" card with a black graduation cap and a tiny colored bar chart.
Background: a very light gray flat vector campus skyline (geometric buildings, clock
tower, trees, two tiny walking students in grayscale) plus a few small scattered
dots (mostly gray, 2-3 tiny colored ones) and one thin curved dotted line.

MOOD: clean, confident, editorial — like a serious product, not a toy. No watermark,
no extra logos, no gibberish text — only the lockup text, the two headline lines, and
short English labels on the UI cards (Match-score, AI chat, Job, Analytics).
```

---

## Bản cũ v4 (nhiều màu tím — giữ để so sánh)

```
I have attached the OFFICIAL logo of this product: a black geometric chevron "V" mark.
Place the attached logo EXACTLY as-is in the bottom-left corner — do not redraw,
restyle, recolor or distort it.

Create a modern, premium 16:9 hero thumbnail for "VinUni Career Platform" — an
AI-powered university career platform. FULL FLAT VECTOR ILLUSTRATION style, like
top-tier SaaS landing-page hero art (Dribbble / Behance quality, Notion / Slack
illustration vibes): clean shapes, smooth rounded corners, subtle soft shadows,
lively but disciplined. NOT photorealistic, NOT 3D render, no real photos.

SCENE (right half of the frame): a cheerful vector-illustrated Vietnamese university
student character (simple friendly face, smart-casual shirt) sitting at a laptop.
Floating around the character, clean white rounded UI cards with soft shadows,
connected by thin dotted lines:
 (1) a circular match-score ring showing "87" with a small emerald "match" chip,
 (2) a CV/resume checklist card with emerald green checkmarks,
 (3) an AI chat bubble card with a violet sparkle icon,
 (4) a job card with a small briefcase icon,
 (5) a small analytics card with a graduation cap and tiny bar chart.
Behind the character: a simplified flat vector campus skyline (geometric buildings,
a clock tower, trees, two tiny walking student figures) in very light muted tones
so the foreground pops. A few floating accent dots and one thin curved dotted path
across the background for a sense of motion.

TEXT BLOCK (left half, on clean cream space, left-aligned, with a thin vertical
gradient accent bar from indigo #4f46e5 to violet #7c3aed):
 line 1 — small uppercase bold label in indigo #4f46e5: "VINUNI CAREER PLATFORM"
 line 2 — big bold headline in near-black ink #171717: "Cho Sinh Viên Thời AI"
          (render the Vietnamese diacritics EXACTLY; color the word "AI" violet #7c3aed)
 line 3 — small gray #57534e: "CV • Việc làm • Phỏng vấn AI"

COLOR SYSTEM: warm cream background #F8F7F1 (NOT blue or teal cast), white cards,
near-black ink text; primary accent indigo #4f46e5 → violet #7c3aed (gradient allowed
only on the accent bar and ONE soft ribbon behind the card cluster); small meaningful
touches of emerald #10b981 (checkmarks), amber #f59e0b, sky #0ea5e9 and teal #14b8a6
in chart details and tiny chips. No navy background, no neon, no dark mode.

MOOD: optimistic, trustworthy, energetic — a real working product. No watermark, no
extra logos, no gibberish text — only the three text lines above and the attached logo.
```

---

## Tuỳ chọn thêm (chỉ khi cần)

- **Thêm phụ đề tiếng Việt** — chèn vào trước dòng `TEXT ON IMAGE`, và sửa dòng đó thành "only the headline
  and this subtitle":
  ```
  Add one small subtitle under the headline, in gray #57534e:
  "Nền tảng việc làm cho sinh viên - doanh nghiệp - nhà trường"
  ```
  ⚠️ Chữ Việt có dấu hay bị vẽ sai — kiểm tra kỹ, sai thì bỏ phụ đề.
- **Negative prompt** (Midjourney `--no`, hoặc dán thêm nếu ảnh ra lỗi):
  ```
  no 3D render, no photorealism, no glassmorphism, no neon glow, no dark/navy
  background, no laptop, no computer screen, no stock photo people, no watermark,
  no gibberish text, no extra logos, no clutter
  ```

## 💡 Mẹo nhanh

- Logo trong ảnh ra bị lệch so với file đính kèm → nhắc: *"the logo must match the attached file exactly"*
  rồi generate lại. Chắc ăn 100%: bảo *"leave the logo area empty"* rồi tự dán `logo-dark-480.png` bằng Canva.
- Chữ "VinUni Career Platform" sai chính tả → generate lại 2–3 lần, hoặc để trống chữ rồi tự chèn (font đậm,
  màu #171717).
- Midjourney không nhận logo đính kèm kiểu này — tạo nền + cụm card trước, chèn logo và chữ sau bằng Canva.
- Cần bản vuông 1:1 (avatar): thêm *"square 1:1, stack the headline below the logo, card cluster underneath"*.
