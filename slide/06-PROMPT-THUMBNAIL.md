# Prompt tạo thumbnail — VinUni Career Platform

> **Cách dùng (2 bước):** ① đính kèm file **`slide/assets/logo-dark-480.png`** vào chat của Gemini / ChatGPT
> → ② dán nguyên **một prompt duy nhất** dưới đây. Xong. Tỷ lệ 16:9.

---

## ✅ PROMPT CHUẨN (dán nguyên khối này)

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
