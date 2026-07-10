# Prompt tạo thumbnail — VinUni Career Platform

> **Cách dùng (2 bước):** ① đính kèm file **`slide/assets/logo-dark-480.png`** vào chat của Gemini / ChatGPT
> → ② dán nguyên **một prompt duy nhất** dưới đây. Xong. Tỷ lệ 16:9.

---

## ✅ PROMPT CHUẨN (dán nguyên khối này)

```
I have attached the OFFICIAL logo of this product: a black geometric chevron "V" mark.
Use the attached logo EXACTLY as-is — do not redraw, restyle, recolor or distort it.

Create a modern, premium 16:9 thumbnail for "VinUni Career Platform" — a university
career platform connecting students, companies and the university.

STYLE: clean flat vector illustration with very subtle soft shadows, top-tier SaaS
marketing style (Dribbble / Behance quality), crisp, minimal, generous whitespace,
no clutter. NOT 3D render, NOT photorealistic, no stock photos.

BACKGROUND: warm paper cream #F8F7F1, perfectly flat.

COMPOSITION:
- Left side: the attached black logo mark placed above a big bold headline
  "VinUni Career Platform" in near-black ink #171717, modern geometric sans-serif,
  tight letter spacing. Under the headline, a thin row of 8 small colored dots:
  indigo #6366f1, teal #14b8a6, amber #f59e0b, rose #f43f5e, sky #0ea5e9,
  emerald #10b981, violet #8b5cf6, orange #f97316.
- Right side: a floating cluster of 4 white rounded cards (soft shadows, 18px-style
  rounded corners), connected by thin dotted lines:
  (1) the largest card: a donut/progress ring chart with the number "87" in the
      center and a small green "match" chip;
  (2) a CV/resume document card with a green checkmark;
  (3) an AI chat bubble card with a sparkle icon;
  (4) a card with a graduation cap and a small briefcase side by side.
- One single accent: a smooth diagonal gradient ribbon flowing behind the card
  cluster, from indigo #4f46e5 to violet #7c3aed — the ONLY gradient in the image.

COLOR DISCIPLINE: cream background, white cards, near-black text, plus the 8 accent
colors above only. No navy backgrounds, no neon, no dark mode.

MOOD: trustworthy, modern, optimistic — a real working product, not a concept.
TEXT ON IMAGE: only "VinUni Career Platform", spelled exactly. No other words.
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
