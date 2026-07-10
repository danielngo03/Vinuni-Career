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
AI-powered university career platform.

SCENE: a friendly Vietnamese university student (early 20s, warm confident smile,
smart-casual shirt) sitting at a laptop, positioned on the right half of the frame,
looking at the camera. Around the laptop float translucent frosted-glass UI panels
with rounded corners and soft shadows:
 (1) a CV/resume checklist panel with green checkmarks,
 (2) a circular match-score ring showing "87",
 (3) a job card with a small briefcase icon,
 (4) an AI chat panel with a sparkle icon,
 (5) a university analytics panel with a graduation cap and tiny bar chart.
BACKGROUND: a bright modern university campus — glass buildings, trees, a few
students walking with backpacks — softly blurred and washed out into a warm cream
white haze (#F8F7F1 tone) so the foreground pops. Soft optimistic daylight.

TEXT BLOCK (left half, on the clean cream area, left-aligned with a thin vertical
gradient accent bar from indigo #4f46e5 to violet #7c3aed):
 line 1 — small uppercase label, indigo #4f46e5, bold: "VINUNI CAREER PLATFORM"
 line 2 — big bold headline, near-black ink #171717: "Cho Sinh Viên Thời AI"
          (render the Vietnamese diacritics EXACTLY; the word "AI" in violet #7c3aed)
 line 3 — small gray #57534e: "CV • Việc làm • Phỏng vấn AI"

COLOR SYSTEM: warm cream white base #F8F7F1 (NOT blue, NOT teal cast), white/glass
panels, near-black ink text, primary accents indigo #4f46e5 → violet #7c3aed, small
touches of emerald #10b981 (checkmarks), amber #f59e0b and sky #0ea5e9 in tiny chart
details only. No navy background, no neon, no dark mode.

STYLE: photo-illustrative blend like premium tech-product key visuals — realistic
person, clean vector-glass UI panels, high detail, crisp light. Trustworthy, modern,
optimistic. No watermark, no extra logos, no gibberish text — only the three text
lines above and the attached logo.
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
