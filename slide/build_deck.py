#!/usr/bin/env python3
"""VinUni Career Platform — pitch deck 15 slide (v5).

Copy viết như người thuyết trình thật (tiêu đề chuẩn pitch: Vấn đề, Giải pháp,
Quy mô thị trường, Mô hình kinh doanh, Lợi thế cạnh tranh, Kết quả đạt được,
Kiến trúc, Công nghệ, Lộ trình phát triển, Lời mời hợp tác). Design = v10 của
sản phẩm: nền #F8F7F1, card trắng bo góc, ink #171717, palette data-viz, tối đa
1 gradient indigo→violet mỗi slide. Asset thật: logo-dark.png, screenshot sản
phẩm, icon Solar duotone, logo công nghệ. Mỗi slide = 1 @dsCard; deck.html gộp.
"""
import base64, pathlib, re

HERE = pathlib.Path(__file__).parent
ASSETS = HERE / "assets"
LIB = ASSETS / "lib"
DECK = HERE / "deck"
DECK.mkdir(exist_ok=True)
TOTAL = 15

PAL = {"indigo": "#6366f1", "teal": "#14b8a6", "amber": "#f59e0b", "rose": "#f43f5e",
       "sky": "#0ea5e9", "emerald": "#10b981", "violet": "#8b5cf6", "orange": "#f97316",
       "ink": "#171717"}


def datauri(name, mime=None):
    p = ASSETS / name
    if not p.exists():
        return ""
    mime = mime or ("image/jpeg" if p.suffix == ".jpg" else "image/png")
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


LOGO = datauri("logo-dark-480.png")
CAMPUS = datauri("campus-small.jpg")
SHOTS = {k: datauri(v) for k, v in {
    "student": "shot-student-dashboard.png", "cv": "shot-cv-studio.png",
    "partner": "shot-partner-pipeline.png", "uni": "shot-university-outcomes.png"}.items()}


def icon(name, s=24):
    t = (LIB / f"ic-{name}.svg").read_text()
    t = re.sub(r'width="[^"]*"', f'width="{s}"', t, count=1)
    t = re.sub(r'height="[^"]*"', f'height="{s}"', t, count=1)
    return t.replace('<svg ', '<svg style="display:block" ', 1)


def tlogo(name, h=26):
    t = (LIB / f"logo-{name}.svg").read_text()
    t = re.sub(r'\swidth="[^"]*"', '', t, count=1)
    t = re.sub(r'height="[^"]*"', f'height="{h}"', t, count=1)
    return t.replace('<svg ', f'<svg style="height:{h}px;width:auto;display:block" ', 1)


def icbox(name, hexc, box=44, isz=24, rad=12):
    return (f'<span style="display:grid;place-items:center;width:{box}px;height:{box}px;'
            f'border-radius:{rad}px;background:{hexc}14;flex:0 0 auto">{icon(name, isz)}</span>')


CSS = r"""
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#F8F7F1;--card:#fff;--line:#e9e7e1;--ink:#171717;--mut:#57534e;--faint:#a8a29e;
 --indigo:#6366f1;--teal:#14b8a6;--amber:#f59e0b;--rose:#f43f5e;--sky:#0ea5e9;--emerald:#10b981;--violet:#8b5cf6;--orange:#f97316;
 --grad:linear-gradient(135deg,#4f46e5 0%,#6d28d9 55%,#7c3aed 100%)}
html,body{background:#e3e1d9;font-family:-apple-system,"SF Pro Display","Be Vietnam Pro","Segoe UI",Roboto,sans-serif;color:var(--ink);-webkit-font-smoothing:antialiased}
.slide{position:relative;width:100%;aspect-ratio:16/9;background:var(--bg);overflow:hidden;padding:3.6% 4.4% 3.8%;display:flex;flex-direction:column}
.hd{display:flex;gap:.95rem;align-items:flex-start;margin-bottom:1rem}
.no{width:38px;height:38px;border-radius:11px;background:var(--ink);color:#fff;display:grid;place-items:center;font-weight:800;font-size:.95rem;flex:0 0 auto;margin-top:.25rem}
.kick{font-size:.72rem;font-weight:800;text-transform:uppercase;letter-spacing:.16em;color:var(--faint)}
h1.t{font-size:2.15rem;font-weight:800;letter-spacing:-.02em;line-height:1.1;color:var(--ink);margin-top:.12rem}
.st{font-size:.95rem;color:var(--mut);margin-top:.3rem}
.sub{color:var(--mut);line-height:1.45}
.body{flex:1;display:flex;min-height:0;gap:1.2rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;box-shadow:0 10px 26px -16px rgba(23,23,23,.16)}
.chip{display:inline-flex;align-items:center;gap:.45em;border-radius:999px;padding:.4em .85em;font-size:.8rem;font-weight:700}
.pill{background:#fff;border:1px solid var(--line);color:var(--ink)}
.num{font-weight:800;letter-spacing:-.02em;line-height:1;font-variant-numeric:tabular-nums;color:var(--ink)}
.foot{position:absolute;left:4.4%;right:4.4%;bottom:2.2%;display:flex;justify-content:space-between;font-size:.74rem;font-weight:700;color:var(--faint)}
.hero{background:var(--grad);color:#fff;border-radius:18px}
.laptop .scr{background:#171717;border-radius:12px 12px 3px 3px;padding:7px;box-shadow:0 28px 54px -20px rgba(23,23,23,.45)}
.laptop .scr img{width:100%;display:block;border-radius:5px}
.laptop .base{height:12px;width:112%;margin-left:-6%;background:linear-gradient(#eceae4,#cfccc3);border-radius:0 0 11px 11px;position:relative}
.laptop .base::after{content:"";position:absolute;top:0;left:50%;transform:translateX(-50%);width:15%;height:5px;background:#b8b4aa;border-radius:0 0 6px 6px}
.brow{background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden;box-shadow:0 10px 24px -14px rgba(23,23,23,.2);display:flex;flex-direction:column}
.brow .bar{height:22px;background:#f5f4ef;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:5px;padding:0 9px;flex:0 0 auto}
.brow .bar i{width:7px;height:7px;border-radius:99px;display:inline-block}
.brow .imgwrap{flex:1;overflow:hidden;min-height:0}.brow img{width:100%;height:100%;object-fit:cover;object-position:top;display:block}
.brow .lb{font-size:.76rem;font-weight:700;color:var(--ink);padding:.42rem .6rem;display:flex;align-items:center;gap:.5em;flex:0 0 auto}
.deck{max-width:1180px;margin:0 auto}.deck .slide{border-radius:12px;box-shadow:0 12px 44px rgba(0,0,0,.16)}
.navbar{position:fixed;bottom:14px;left:50%;transform:translateX(-50%);z-index:50;background:#171717;color:#fff;border-radius:999px;padding:.45rem 1rem;font-size:.82rem;display:flex;gap:1rem;align-items:center}
.navbar button{background:none;border:none;color:#fff;cursor:pointer;font-size:1.05rem}
@media print{.navbar{display:none}.deck{max-width:none}.deck .slide{box-shadow:none;border-radius:0;page-break-after:always}}
"""


def foot(n):
    return f'<div class="foot"><span>C2-Team-037</span><span>{n:02d} / {TOTAL}</span></div>'


def slide(inner, n):
    return f'<section class="slide">{inner}{foot(n)}</section>'


def doc(inner):
    return ('<!-- @dsCard group="Pitch Deck" -->\n<!doctype html><html lang="vi"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<style>{CSS}</style></head><body>{inner}</body></html>')


def head(no, kick, title, sub=""):
    s = f'<div class="st">{sub}</div>' if sub else ""
    return (f'<div class="hd"><span class="no">{no:02d}</span>'
            f'<div><div class="kick">{kick}</div><h1 class="t">{title}</h1>{s}</div></div>')


def check_row(text):
    return (f'<div style="display:flex;gap:.5rem;align-items:center;margin-top:.5rem">'
            f'<span style="flex:0 0 auto;display:grid;place-items:center">{icon("check", 17)}</span>'
            f'<span style="font-size:.88rem;color:var(--ink)">{text}</span></div>')


# ═══════════ 01 · TRANG BÌA ═══════════
def s1():
    dots = "".join(f'<span style="width:9px;height:9px;border-radius:99px;background:{c}"></span>'
                   for c in [PAL["indigo"], PAL["teal"], PAL["amber"], PAL["rose"], PAL["sky"], PAL["emerald"], PAL["violet"], PAL["orange"]])
    chips = "".join(f'<span class="chip pill">{t}</span>' for t in
                    ["Sản phẩm đã hoạt động", "4 phân hệ", "Song ngữ Việt – Anh"])
    return f'''<div class="body" style="align-items:center;gap:3rem">
      <div style="flex:1;display:flex;flex-direction:column;gap:1.05rem">
        <div style="display:flex;align-items:center;gap:.85rem">
          <img src="{LOGO}" style="height:54px;width:54px;object-fit:contain">
          <div><div style="font-weight:800;font-size:1.02rem;letter-spacing:.02em">VINUNI CAREER</div>
          <div style="font-size:.78rem;color:var(--faint);font-weight:700">C2-TEAM-037 · THÁNG 7 / 2026</div></div></div>
        <h1 style="font-size:3.1rem;font-weight:800;letter-spacing:-.03em;line-height:1.04">VinUni Career<br>Platform</h1>
        <div style="font-size:1.15rem;font-weight:700;color:var(--ink)">Nền tảng việc làm &amp; phát triển sự nghiệp<br>cho hệ sinh thái VinUni</div>
        <div class="sub" style="font-size:1rem;max-width:46ch">Kết nối sinh viên, doanh nghiệp và nhà trường trên một hệ thống duy nhất — với AI hỗ trợ ở từng bước.</div>
        <div style="display:flex;gap:.55rem">{dots}</div>
        <div style="display:flex;gap:.5rem;flex-wrap:wrap">{chips}</div>
      </div>
      <div style="flex:0 0 46%" class="laptop"><div class="scr"><img src="{SHOTS["student"]}"></div><div class="base"></div></div>
    </div>'''


# ═══════════ 02 · NỘI DUNG TRÌNH BÀY ═══════════
def s2():
    parts = [
        ("Phần 1", "indigo", "idea", "Vấn đề &amp; Giải pháp", "Điểm nghẽn hiện tại, cách chúng tôi giải quyết và sản phẩm thực tế", "Slide 03 – 06"),
        ("Phần 2", "teal", "market", "Thị trường &amp; Kinh doanh", "Quy mô thị trường, mô hình doanh thu và lợi thế cạnh tranh", "Slide 07 – 09"),
        ("Phần 3", "amber", "scale", "Kết quả &amp; Công nghệ", "Những gì đã xây được, kiến trúc và công nghệ sử dụng", "Slide 10 – 12"),
        ("Phần 4", "rose", "growth", "Lộ trình &amp; Hợp tác", "Kế hoạch triển khai, mục tiêu 12 tháng và lời mời đồng hành", "Slide 13 – 15"),
    ]
    cards = "".join(f'''<div class="card" style="padding:1.2rem 1.25rem;display:flex;flex-direction:column;gap:.5rem">
        <div style="display:flex;align-items:center;justify-content:space-between">
          {icbox(ic, PAL[c], 44, 24)}
          <span style="font-size:.78rem;font-weight:800;color:{PAL[c]};text-transform:uppercase;letter-spacing:.08em">{no}</span></div>
        <div style="font-weight:800;font-size:1.06rem">{name}</div>
        <div class="sub" style="font-size:.85rem">{desc}</div>
        <span class="chip" style="background:{PAL[c]}14;color:{PAL[c]};align-self:flex-start;margin-top:.2rem">{rng}</span></div>'''
                    for no, c, ic, name, desc, rng in parts)
    return head(2, "Nội dung", "Nội dung trình bày",
                "Bốn phần chính — từ vấn đề tới lời mời hợp tác.") + f'''
    <div class="body" style="flex-direction:column;gap:1rem">
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;align-content:center;flex:1">{cards}</div>
      <div class="card" style="padding:.8rem 1.2rem;display:flex;align-items:center;gap:.6rem;flex-wrap:wrap">
        <img src="{LOGO}" style="height:22px;width:22px;object-fit:contain">
        <span style="font-size:.86rem"><b>VinUni Career Platform</b> — sinh viên ứng tuyển tự tin hơn, doanh nghiệp tuyển đúng người nhanh hơn, nhà trường đo được kết quả việc làm.</span></div>
    </div>'''


# ═══════════ 03 · VẤN ĐỀ ═══════════
def s3():
    steps = [("1", "search", PAL["sky"], "Tìm tin tuyển dụng", "Lướt nhiều trang, không biết tin nào hợp với mình"),
             ("2", "cv", PAL["violet"], "Chuẩn bị CV", "Một CV nộp mọi nơi — không ai góp ý, không biết còn thiếu gì"),
             ("3", "pipeline", PAL["teal"], "Nộp đơn", "Nộp qua email, form rời rạc — dễ thất lạc"),
             ("4", "clock", PAL["amber"], "Chờ phản hồi", "Im lặng kéo dài, không biết hồ sơ đang ở vòng nào"),
             ("5", "interview", PAL["rose"], "Phỏng vấn", "Chưa từng được luyện tập, trượt không rõ lý do")]
    srow = ""
    for i, (no, ic, c, name, pain) in enumerate(steps):
        srow += f'''<div style="flex:1;display:flex;flex-direction:column;gap:.55rem;position:relative">
          {'<div style="position:absolute;top:25px;left:-12%;width:24%;height:3px;background:#e5e2da"></div>' if i else ''}
          <div style="display:flex;align-items:center;gap:.55rem;position:relative;z-index:1">
            <span style="width:30px;height:30px;border-radius:99px;background:{c};color:#fff;display:grid;place-items:center;font-weight:800;font-size:.8rem;flex:0 0 auto">{no}</span>
            {icbox(ic, c, 40, 22, 11)}</div>
          <div style="font-weight:800;font-size:.98rem">{name}</div>
          <div style="font-size:.82rem;color:{PAL["rose"]};line-height:1.4;font-weight:600">✕ {pain}</div></div>'''
    def actor(color, ic, name, line):
        return f'''<div class="card" style="padding:1.15rem 1.2rem;display:flex;gap:.75rem;align-items:center;flex:1">
          {icbox(ic, color, 48, 26)}
          <div><div style="font-weight:800;font-size:1rem">{name}</div>
          <div class="sub" style="font-size:.85rem;line-height:1.4;margin-top:.15rem">{line}</div></div></div>'''
    return head(3, "Phần 1 · Vấn đề", "Hành trình tìm việc của sinh viên đang đứt gãy",
                "Năm bước, bước nào cũng có điểm nghẽn — và cả ba bên đều chịu hậu quả.") + f'''
    <div class="body" style="flex-direction:column;gap:1rem;justify-content:center">
      <div class="card" style="padding:1.5rem 1.5rem"><div style="display:flex;gap:1.1rem">{srow}</div></div>
      <div style="display:flex;gap:1rem">
        {actor(PAL["sky"], "student", "Sinh viên", "Ứng tuyển thiếu tự tin — 314.000 cử nhân mỗi năm cạnh tranh việc làm")}
        {actor(PAL["teal"], "recruiter", "Doanh nghiệp", "Tuyển chậm, tuyển sai — ứng viên job board chưa được xác thực")}
        {actor(PAL["amber"], "university", "Nhà trường", "Không đo được kết quả việc làm — thiếu số liệu kiểm định")}</div>
      <div class="card" style="padding:1rem 1.3rem;display:flex;align-items:center;gap:.9rem;flex-wrap:wrap;border-left:5px solid {PAL["rose"]}">
        <span style="font-weight:800;font-size:.95rem">Vì sao chưa ai giải quyết?</span>
        <span class="chip" style="background:#fef2f2;color:{PAL["rose"]}">ATS doanh nghiệp — quá nặng &amp; đắt</span>
        <span class="chip" style="background:#fef2f2;color:{PAL["rose"]}">Job board — dừng ở nộp đơn</span>
        <span class="chip" style="background:#fef2f2;color:{PAL["rose"]}">Trường tự xây — quá tốn kém</span>
        <span class="sub" style="font-size:.8rem;margin-left:auto">Dữ liệu đứt gãy giữa sinh viên – doanh nghiệp – nhà trường</span></div>
    </div>'''


# ═══════════ 04 · GIẢI PHÁP ═══════════
def s4():
    def surf(color, ic, name, tag, caps):
        rows = "".join(check_row(c) for c in caps)
        return f'''<div class="card" style="padding:1.2rem 1.25rem;display:flex;flex-direction:column;justify-content:center">
          <div style="display:flex;align-items:center;gap:.7rem">{icbox(ic, color, 46, 25)}
            <div><div style="font-weight:800;font-size:1.02rem;line-height:1.1">{name}</div>
            <div style="font-size:.72rem;font-weight:800;color:{color};text-transform:uppercase;letter-spacing:.07em;margin-top:.12rem">{tag}</div></div></div>
          <div style="margin-top:.45rem">{rows}</div></div>'''
    core = f'''<div class="hero" style="padding:1.5rem 1.35rem;display:flex;flex-direction:column;gap:.6rem;justify-content:center;height:100%">
      <img src="{LOGO}" style="height:40px;width:40px;object-fit:contain;filter:invert(1) brightness(2)">
      <div style="font-size:1.35rem;font-weight:800;line-height:1.15">AI hỗ trợ xuyên suốt</div>
      <div style="font-size:.86rem;opacity:.92;line-height:1.45">Từ viết CV, chấm điểm phù hợp tới luyện phỏng vấn — trên cùng một hệ thống.</div>
      <div style="display:flex;flex-direction:column;gap:.4rem;margin-top:.4rem">
        {"".join(f'<div style="display:flex;gap:.5rem;align-items:center;font-size:.82rem"><span style="opacity:.75">●</span>{t}</div>'
                 for t in ["Chấm điểm CV – việc làm 0–100", "Mọi thao tác AI đều hỏi trước khi ghi", "Chi phí AI được đo từng lượt dùng"])}</div></div>'''
    return head(4, "Phần 1 · Giải pháp", "Một nền tảng cho cả ba bên",
                "Bốn phân hệ trên cùng một hệ thống — dữ liệu liền mạch từ CV tới kết quả việc làm.") + f'''
    <div class="body">
      <div style="flex:1;display:grid;grid-template-columns:1fr 1fr;gap:1rem">
        {surf(PAL["sky"], "marketplace", "Cổng việc làm công khai", "Cho mọi người", ["Tìm việc, sự kiện, công ty", "Tra cứu mặt bằng lương", "Không cần tài khoản"])}
        {surf(PAL["indigo"], "dashboard", "Không gian sinh viên", "Cho sinh viên", ["Soạn CV + chấm điểm phù hợp", "Trợ lý AI &amp; luyện phỏng vấn", "Theo dõi đơn ứng tuyển"])}
        {surf(PAL["teal"], "partner", "Bộ máy tuyển dụng", "Cho doanh nghiệp", ["Quy trình tuyển nhiều vòng", "Kho ứng viên + tìm kiếm AI", "Báo cáo tuyển dụng"])}
        {surf(PAL["amber"], "govern", "Trung tâm điều hành", "Cho nhà trường", ["Duyệt tin &amp; quản lý đối tác", "Tự động hoá quy trình", "Thống kê kết quả việc làm"])}</div>
      <div style="flex:0 0 27%">{core}</div>
    </div>'''


# ═══════════ 05 · SẢN PHẨM ═══════════
def brow(src, hexc, ic, label):
    return f'''<div class="brow" style="flex:1;min-height:0">
      <div class="bar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i><i style="background:#28c840"></i></div>
      <div class="imgwrap"><img src="{src}"></div>
      <div class="lb">{icbox(ic, hexc, 24, 15, 7)}{label}</div></div>'''


def s5():
    feats = "".join(f'<span class="chip pill" style="font-size:.73rem">{t}</span>' for t in
                    ["Ứng tuyển &amp; theo dõi đơn", "CV Studio 7 mẫu", "Trợ lý AI", "Phỏng vấn thử",
                     "Kho ứng viên", "Sự kiện tuyển dụng", "Quảng cáo có nhãn", "Kiểm duyệt tin",
                     "Tin nhắn &amp; thông báo", "Báo cáo việc làm"])
    return head(5, "Phần 1 · Sản phẩm", "Giao diện thực tế của sản phẩm",
                "Ảnh chụp trực tiếp từ hệ thống đang chạy — không phải bản vẽ minh hoạ.") + f'''
    <div class="body" style="flex-direction:column;gap:.9rem">
      <div style="display:flex;align-items:stretch;gap:1.3rem;flex:1;min-height:0">
        <div style="flex:0 0 51%;display:flex;flex-direction:column;justify-content:center;gap:.7rem">
          <div class="laptop"><div class="scr"><img src="{SHOTS["student"]}"></div><div class="base"></div></div>
          <div style="display:flex;justify-content:center;align-items:center;gap:.5rem;font-size:.82rem;font-weight:700">
            {icbox("dashboard", PAL["indigo"], 24, 15, 7)}Trang tổng quan của sinh viên</div></div>
        <div style="flex:1;display:flex;flex-direction:column;gap:.8rem">
          {brow(SHOTS["cv"], PAL["violet"], "cv", "CV Studio — 7 mẫu CV, chỉnh sửa trực quan")}
          {brow(SHOTS["partner"], PAL["teal"], "partner", "Quy trình tuyển dụng của doanh nghiệp")}
          {brow(SHOTS["uni"], PAL["amber"], "govern", "Thống kê kết quả việc làm của nhà trường")}</div></div>
      <div class="card" style="padding:.7rem 1.1rem;display:flex;align-items:center;gap:.45rem;flex-wrap:wrap">
        <span style="font-size:.72rem;font-weight:800;color:var(--faint);text-transform:uppercase;letter-spacing:.08em">Và nhiều hơn:</span>{feats}</div>
    </div>'''


# ═══════════ 06 · TÍNH NĂNG AI ═══════════
def donut(pct, color, size=132, label="điểm phù hợp"):
    r = 54; c = 2 * 3.14159 * r
    return f'''<svg viewBox="0 0 140 140" style="width:{size}px;height:{size}px">
      <circle cx="70" cy="70" r="{r}" fill="none" stroke="#eeece6" stroke-width="14"/>
      <circle cx="70" cy="70" r="{r}" fill="none" stroke="{color}" stroke-width="14" stroke-linecap="round"
        stroke-dasharray="{c * pct / 100:.1f} {c:.1f}" transform="rotate(-90 70 70)"/>
      <text x="70" y="66" text-anchor="middle" font-size="30" font-weight="800" fill="#171717">{pct}</text>
      <text x="70" y="88" text-anchor="middle" font-size="10.5" fill="#a8a29e">{label}</text></svg>'''


def s6():
    bands = "".join(f'''<div style="display:flex;align-items:center;gap:.5rem;margin-top:.4rem">
        <span style="font-size:.74rem;color:var(--mut);width:86px;flex:0 0 auto">{n}</span>
        <div style="flex:1;height:7px;border-radius:99px;background:#eeece6"><div style="width:{w}%;height:100%;border-radius:99px;background:{c}"></div></div>
        <span style="font-size:.74rem;font-weight:800;width:32px;text-align:right">{w}%</span></div>'''
                    for n, w, c in [("Kỹ năng", 50, PAL["indigo"]), ("Kinh nghiệm", 25, PAL["teal"]), ("Chất lượng CV", 15, PAL["amber"]), ("Điều kiện", 10, PAL["sky"])])
    fit = f'''<div class="card" style="flex:1;padding:1.15rem;display:flex;flex-direction:column">
      <div style="display:flex;align-items:center;gap:.6rem">{icbox("match", PAL["rose"], 40, 22)}
        <div style="font-weight:800;font-size:.96rem">Chấm điểm CV theo từng tin tuyển dụng</div></div>
      <div style="display:flex;align-items:center;gap:1rem;flex:1">
        {donut(87, PAL["emerald"])}
        <div style="flex:1">{bands}</div></div>
      <div class="sub" style="font-size:.78rem">Cùng một CV, cùng một tin — luôn ra cùng một điểm. Chỉ rõ kỹ năng còn thiếu.</div></div>'''
    diff = f'''<div class="card" style="flex:1;padding:1.15rem;display:flex;flex-direction:column;gap:.55rem">
      <div style="display:flex;align-items:center;gap:.6rem">{icbox("cv", PAL["violet"], 40, 22)}
        <div style="font-weight:800;font-size:.96rem">Sửa CV bằng câu lệnh tự nhiên</div></div>
      <div style="background:#faf9f5;border:1px solid var(--line);border-radius:12px;padding:.75rem .85rem;font-size:.8rem;flex:1;display:flex;flex-direction:column;justify-content:center;gap:.4rem">
        <div style="color:var(--faint);font-style:italic">"Làm nổi bật kinh nghiệm Python của tôi"</div>
        <div style="background:#fef2f2;border-radius:7px;padding:.35rem .55rem;text-decoration:line-through;color:#b91c1c">Tham gia dự án phần mềm của lớp</div>
        <div style="background:#ecfdf5;border-radius:7px;padding:.35rem .55rem;color:#047857">Xây dựng REST API bằng Python/FastAPI phục vụ 2.000 người dùng</div></div>
      <div style="display:flex;gap:.5rem;align-items:center">
        <span class="chip" style="background:var(--ink);color:#fff">Chấp nhận</span>
        <span class="chip pill">Từ chối</span>
        <span class="sub" style="font-size:.74rem;margin-left:auto">Bạn duyệt, AI mới được sửa</span></div></div>'''
    agent = f'''<div class="card" style="flex:1;padding:1.15rem;display:flex;flex-direction:column;gap:.55rem">
      <div style="display:flex;align-items:center;gap:.6rem">{icbox("bot", PAL["sky"], 40, 22)}
        <div style="font-weight:800;font-size:.96rem">Trợ lý ảo &amp; phỏng vấn thử</div></div>
      <div style="background:#faf9f5;border:1px solid var(--line);border-radius:12px;padding:.75rem .85rem;font-size:.8rem;flex:1;display:flex;flex-direction:column;justify-content:center;gap:.5rem">
        <div style="color:var(--faint);font-style:italic">"Tìm 3 việc hợp với CV của tôi rồi nộp việc đầu tiên"</div>
        <div style="background:#fff;border:1px solid var(--line);border-radius:9px;padding:.55rem .65rem">
          <b style="font-size:.8rem">Xác nhận nộp đơn?</b>
          <div class="sub" style="font-size:.75rem">Backend Intern · FPT Software · CV "Nguyễn Minh Anh v3"</div></div></div>
      <div style="display:flex;gap:.4rem;flex-wrap:wrap">
        <span class="chip" style="background:{PAL["sky"]}14;color:{PAL["sky"]}">Trợ lý 25+ thao tác</span>
        <span class="chip" style="background:{PAL["indigo"]}14;color:{PAL["indigo"]}">Phỏng vấn thử theo đúng tin tuyển</span></div></div>'''
    return head(6, "Phần 1 · Tính năng AI", "AI hỗ trợ trong từng bước ứng tuyển",
                "Ba ví dụ tiêu biểu — tất cả đều đang chạy trong sản phẩm.") + f'''
    <div class="body" style="gap:1.1rem">{fit}{diff}{agent}</div>'''


# ═══════════ 07 · QUY MÔ THỊ TRƯỜNG ═══════════
def s7():
    bars = "".join(f'''<div style="display:flex;align-items:center;gap:.8rem;margin-top:.85rem">
        <div style="width:{w}%;min-width:236px;height:54px;border-radius:12px;background:{c};display:flex;align-items:center;justify-content:space-between;gap:.7rem;padding:0 1rem;color:#fff">
          <span style="font-weight:800;font-size:1.05rem;white-space:nowrap">{v}</span><span style="font-size:.75rem;opacity:.92;text-align:right;line-height:1.25">{l}</span></div>
        <span class="chip" style="background:{c}14;color:{c};flex:0 0 auto">{tag}</span></div>'''
                    for w, c, v, l, tag in [
                        (100, PAL["indigo"], "2,36 triệu", "sinh viên đại học Việt Nam", "TAM"),
                        (72, PAL["sky"], ">940.000", "doanh nghiệp đang hoạt động", "Bên tuyển"),
                        (48, PAL["teal"], "314.000", "cử nhân tốt nghiệp mỗi năm", "SAM"),
                        (26, PAL["emerald"], "3.500+", "sinh viên &amp; cựu SV VinUni", "Khởi đầu")])
    why = "".join(f'''<div style="display:flex;gap:.6rem;align-items:center;margin-top:.6rem">
        {icbox(ic, c, 36, 20, 10)}<span style="font-size:.86rem">{t}</span></div>'''
                  for ic, c, t in [("ai", PAL["indigo"], "Chi phí AI giảm mạnh — chấm điểm CV, trợ lý ảo trở nên <b>khả thi</b>"),
                                   ("medal", PAL["amber"], "Kiểm định chất lượng yêu cầu <b>số liệu việc làm</b> của sinh viên"),
                                   ("users", PAL["sky"], "Sinh viên đã quen với sản phẩm số <b>cá nhân hoá</b>")])
    return head(7, "Phần 2 · Thị trường", "Quy mô thị trường",
                "Khởi đầu từ VinUni, hướng tới thị trường việc làm sinh viên cả nước.") + f'''
    <div class="body" style="align-items:center;gap:2rem">
      <div style="flex:1.2">{bars}
        <div class="sub" style="font-size:.72rem;margin-top:.9rem">Nguồn: Tổng cục Thống kê / Bộ GD&amp;ĐT Việt Nam 2024 · VietnamNet · IMARC (thị trường HR-tech VN hướng tới ~1 tỷ USD)</div></div>
      <div style="flex:.8;display:flex;flex-direction:column;gap:.7rem;align-self:center">
        <div class="card" style="padding:1.1rem 1.25rem">
          <div style="font-weight:800;font-size:1rem;margin-bottom:.2rem">Vì sao là lúc này?</div>{why}</div>
        <div class="card" style="padding:.95rem 1.25rem;border-left:5px solid {PAL["emerald"]}">
          <div style="display:flex;gap:.7rem;align-items:center">
            {icbox("medal", PAL["emerald"], 38, 21, 10)}
            <span style="font-size:.84rem"><b>Mô hình đã được kiểm chứng:</b> Handshake (Mỹ) — 20 triệu SV, 1.400 trường, định giá <b>3,5 tỷ USD</b>. Việt Nam chưa có ai làm.</span></div></div>
        <div class="card" style="padding:.85rem 1.25rem;display:flex;gap:.6rem;align-items:center">
          {icbox("growth", PAL["rose"], 34, 19, 10)}
          <span style="font-size:.82rem">Lộ trình: <b>VinUni</b> → cựu SV &amp; SV trường khác → <b>các trường khác</b></span></div></div>
    </div>'''


# ═══════════ 08 · MÔ HÌNH KINH DOANH ═══════════
def s8():
    def stream(color, ic, name, who, price):
        return f'''<div class="card" style="padding:1rem 1.1rem;display:flex;gap:.75rem;align-items:center">
          {icbox(ic, color, 44, 24)}
          <div style="flex:1"><div style="font-weight:800;font-size:.95rem">{name}</div>
            <div class="sub" style="font-size:.76rem">{who}</div></div>
          <span class="chip" style="background:{color}14;color:{color};flex:0 0 auto">{price}</span></div>'''
    ledger = f'''<div class="hero" style="padding:1.35rem 1.3rem;display:flex;flex-direction:column;gap:.55rem;justify-content:center;height:100%">
      <div style="font-size:.72rem;font-weight:800;text-transform:uppercase;letter-spacing:.14em;opacity:.8">Nguyên tắc thu phí</div>
      <div style="font-size:1.3rem;font-weight:800;line-height:1.18">Dùng AI bao nhiêu,<br>tính bấy nhiêu</div>
      <div style="font-size:.84rem;opacity:.92;line-height:1.45">Mỗi lượt AI đều được ghi nhận — chỉ tính phí khi mang lại kết quả.</div>
      <div style="display:flex;flex-direction:column;gap:.4rem;margin-top:.35rem;font-size:.82rem">
        <div>● Sinh viên VinUni: <b>miễn phí</b> (trường tài trợ)</div>
        <div>● Hết hạn mức → <b>mua thêm</b> hoặc nâng gói</div>
        <div>● Trường khác muốn dùng → <b>giấy phép ~150tr₫/năm</b></div></div></div>'''
    return head(8, "Phần 2 · Mô hình kinh doanh", "Mô hình kinh doanh",
                "Bốn nguồn thu — mức giá phù hợp với thị trường Việt Nam.") + f'''
    <div class="body">
      <div style="flex:1;display:flex;flex-direction:column;gap:.85rem;justify-content:center">
        {stream(PAL["teal"], "partner", "Gói doanh nghiệp", "Đăng tin, làm nổi bật, quy trình tuyển đầy đủ", "2 – 5tr₫/tháng")}
        {stream(PAL["amber"], "ads", "Quảng cáo tuyển dụng", "Tin tài trợ, banner — luôn gắn nhãn 'Được tài trợ'", "từ 500k₫/tin")}
        {stream(PAL["indigo"], "student", "Gói sinh viên Pro", "Dành cho sinh viên ngoài VinUni &amp; người đi làm", "49k₫/tháng")}
        {stream(PAL["rose"], "calendar", "Sự kiện &amp; tài trợ", "Ngày hội việc làm, hội thảo, tài trợ thương hiệu", "từ 10tr₫/sự kiện")}
        <div class="sub" style="font-size:.75rem">Mức giá đề xuất, có thể điều chỉnh · giai đoạn đầu thanh toán chuyển khoản</div></div>
      <div style="flex:0 0 32%">{ledger}</div>
    </div>'''


# ═══════════ 09 · LỢI THẾ CẠNH TRANH ═══════════
def s9():
    def comp(no, color, name, kind, stats, lack):
        srows = "".join(f'''<div style="display:flex;align-items:center;gap:.45rem;margin-top:.4rem;background:#faf9f5;border:1px solid var(--line);border-radius:9px;padding:.38rem .55rem">
            {icbox(ic, color, 24, 14, 7)}<div style="min-width:0"><div style="font-size:.62rem;color:var(--faint);font-weight:700;text-transform:uppercase;letter-spacing:.04em">{lb}</div>
            <div style="font-size:.8rem;font-weight:800;line-height:1.1">{v}</div></div></div>''' for ic, lb, v in stats)
        return f'''<div class="card" style="flex:1;padding:.9rem .95rem;display:flex;flex-direction:column;justify-content:center">
          <div style="display:flex;align-items:center;gap:.5rem">
            <span style="width:24px;height:24px;border-radius:99px;background:{color};color:#fff;display:grid;place-items:center;font-weight:800;font-size:.74rem;flex:0 0 auto">{no}</span>
            <div style="min-width:0"><div style="font-weight:800;font-size:.9rem;line-height:1.05">{name}</div>
            <div style="font-size:.68rem;color:var(--faint);font-weight:700">{kind}</div></div></div>
          <div>{srows}</div>
          <div style="margin-top:.55rem;border-top:1px dashed var(--line);padding-top:.5rem;font-size:.72rem;color:{PAL["rose"]};font-weight:700;line-height:1.3">✕ {lack}</div></div>'''
    vin = f'''<div style="flex:1.08;border-radius:18px;padding:2px;background:var(--grad);display:flex">
      <div style="background:#fff;border-radius:16px;padding:.9rem .95rem;flex:1;display:flex;flex-direction:column;justify-content:center">
        <div style="display:flex;align-items:center;gap:.5rem">
          <img src="{LOGO}" style="height:26px;width:26px;object-fit:contain">
          <div><div style="font-weight:800;font-size:.9rem;line-height:1.05">VinUni Career</div>
          <div style="font-size:.68rem;color:{PAL["indigo"]};font-weight:800">CHÚNG TÔI ★</div></div></div>
        <div style="margin-top:.3rem">
          {"".join(f'<div style="display:flex;gap:.4rem;align-items:flex-start;margin-top:.5rem"><span style="flex:0 0 auto">{icon("check", 15)}</span><span style="font-size:.76rem;font-weight:700;line-height:1.3">{t}</span></div>'
                   for t in ["Gắn trực tiếp với nhà trường", "AI chấm CV theo từng tin tuyển", "Theo trọn quy trình tới khi nhận việc", "Miễn phí cho sinh viên VinUni"])}</div></div></div>'''
    feats = [("Gắn với nhà trường", ["✕", "✕", "✓", "✕", "✓"]),
             ("AI chấm điểm CV theo tin tuyển", ["✕", "△", "✕", "✕", "✓"]),
             ("Quy trình tuyển nhiều vòng", ["✕", "✕", "△", "✓", "✓"]),
             ("Số liệu việc làm cho trường", ["✕", "✕", "△", "✕", "✓"])]
    cols = ["LinkedIn", "TopCV", "Handshake", "Greenhouse", "VinUni Career"]
    thead = "".join(f'<th style="padding:.4rem .5rem;font-size:.72rem;{"color:"+PAL["indigo"]+";font-weight:800" if i==4 else "color:var(--mut);font-weight:700"}">{c}</th>' for i, c in enumerate(cols))
    trows = ""
    for fname, marks in feats:
        tds = "".join(f'''<td style="text-align:center;padding:.34rem .5rem;font-weight:800;font-size:.82rem;
            {"background:"+PAL["indigo"]+"10;color:"+PAL["emerald"] if i==4 else ("color:"+PAL["emerald"] if m=="✓" else ("color:"+PAL["amber"] if m=="△" else "color:#d6d3cb"))}">{m}</td>'''
                      for i, m in enumerate(marks))
        trows += f'<tr style="border-top:1px solid var(--line)"><td style="padding:.34rem .5rem;font-size:.76rem;font-weight:700">{fname}</td>{tds}</tr>'
    table = f'''<table style="width:100%;border-collapse:collapse">
      <tr><th style="text-align:left;padding:.4rem .5rem;font-size:.72rem;color:var(--faint);font-weight:700">TIÊU CHÍ</th>{thead}</tr>{trows}</table>'''
    return head(9, "Phần 2 · Cạnh tranh", "Lợi thế cạnh tranh",
                "Từng mảnh đã có người làm rất tốt — nhưng chưa ai ghép đủ cả ba bên trong một trường đại học.") + f'''
    <div class="body" style="flex-direction:column;gap:.8rem">
      <div style="display:flex;gap:.8rem;flex:1;align-items:center">
        {comp(1, "#0077b5", "LinkedIn", "Mạng nghề nghiệp toàn cầu",
              [("globe", "Thành viên", ">1 tỷ toàn cầu"), ("users", "Định vị", "Người đi làm"), ("money", "Chi phí tuyển", "Rất cao")], "Không gắn trường, không có quy trình tuyển")}
        {comp(2, PAL["teal"], "TopCV · VNWorks", "Job board số 1 Việt Nam",
              [("users", "Người dùng", "9,5 triệu+"), ("partner", "Doanh nghiệp", "200.000+"), ("money", "Vốn đầu tư", "Mynavi (Nhật)")], "Dừng ở nộp đơn — không theo các vòng sau")}
        {comp(3, PAL["amber"], "Handshake", "Campus career (Mỹ)",
              [("student", "Sinh viên", "20 triệu"), ("govern", "Trường ĐH", "1.400+"), ("money", "Định giá", "3,5 tỷ USD")], "Chưa vào Việt Nam, AI còn mỏng")}
        {comp(4, PAL["violet"], "Greenhouse", "ATS doanh nghiệp",
              [("money", "Vốn TPG rót", "500 triệu USD"), ("recruiter", "Định vị", "Doanh nghiệp lớn"), ("student", "Cho sinh viên", "Không")], "Đắt, phức tạp — không dành cho sinh viên")}
        {vin}</div>
      <div class="card" style="padding:.55rem .9rem">{table}</div>
      <div style="display:flex;align-items:center;gap:.6rem">
        {icbox("idea", PAL["amber"], 30, 17, 9)}
        <span style="font-size:.8rem"><b>Thị trường đã được kiểm chứng:</b> mô hình campus career được định giá <b>3,5 tỷ USD</b> tại Mỹ — Việt Nam chưa có nền tảng tương đương.
        <span class="sub" style="font-size:.7rem">Nguồn: Forbes/PRNewswire 2022 · TopCV.vn · Mynavi</span></span></div>
    </div>'''


# ═══════════ 10 · KẾT QUẢ ĐẠT ĐƯỢC ═══════════
def s10():
    def kpi(color, ic, big, lab):
        return f'''<div class="card" style="padding:1.05rem 1.15rem;display:flex;gap:.8rem;align-items:center">
          {icbox(ic, color, 46, 25)}
          <div><div class="num" style="font-size:1.9rem">{big}</div><div class="sub" style="font-size:.8rem">{lab}</div></div></div>'''
    tiles = (kpi(PAL["indigo"], "layers", "34", "phân hệ backend") +
             kpi(PAL["sky"], "dashboard", "120", "màn hình giao diện") +
             kpi(PAL["emerald"], "check", "2.022", "bài kiểm thử tự động") +
             kpi(PAL["violet"], "ai", "20", "bộ đánh giá chất lượng AI") +
             kpi(PAL["amber"], "globe", "2", "ngôn ngữ (Việt – Anh)") +
             kpi(PAL["rose"], "users", "4", "nhóm người dùng phục vụ"))
    return head(10, "Phần 3 · Kết quả", "Kết quả đã đạt được",
                "Hệ thống hoàn chỉnh, đang chạy — toàn bộ số liệu đếm trực tiếp từ mã nguồn.") + f'''
    <div class="body" style="flex-direction:column;gap:1rem">
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;align-content:center;flex:1">{tiles}</div>
      <div class="card" style="padding:.95rem 1.25rem;display:flex;align-items:center;gap:.9rem;border-left:5px solid {PAL["emerald"]}">
        {icbox("medal", PAL["emerald"], 42, 24)}
        <span style="font-size:.92rem"><b>Nền tảng đầu ra tốt để khuếch đại:</b> khóa cử nhân đầu tiên của VinUni (2024) có <b>32% nhận việc trước khi tốt nghiệp</b> tại McKinsey, BCG, Google, IBM… <span class="sub" style="font-size:.8rem">(vinuni.edu.vn)</span></span></div>
    </div>'''


# ═══════════ 11 · KIẾN TRÚC HỆ THỐNG ═══════════
def s11():
    def box(title, logos_names, rows, chips, color):
        lg = "".join(f'<span style="display:flex;align-items:center;gap:.35rem;font-size:.78rem;font-weight:700">{tlogo(n, 20)}{t}</span>'
                     for n, t in logos_names)
        rw = "".join(f'''<div style="display:flex;gap:.5rem;align-items:center;margin-top:.45rem">
            <span style="flex:0 0 auto;display:grid;place-items:center">{icon("check", 16)}</span>
            <span style="font-size:.82rem">{r}</span></div>''' for r in rows)
        ch = "".join(f'<span class="chip" style="background:{color}12;color:{color};font-size:.7rem;padding:.28em .6em">{c}</span>' for c in chips)
        return f'''<div class="card" style="padding:1.15rem 1.2rem;flex:1;display:flex;flex-direction:column;gap:.55rem;justify-content:center">
          <div style="font-size:.72rem;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:{color}">{title}</div>
          <div style="display:flex;gap:.9rem;flex-wrap:wrap">{lg}</div>
          <div>{rw}</div>
          <div style="display:flex;gap:.35rem;flex-wrap:wrap;margin-top:.2rem">{ch}</div></div>'''
    arrow = '<div style="display:grid;place-items:center;color:#c9c5bb;font-size:1.4rem;font-weight:800">→</div>'
    infra = "".join(f'<span style="display:flex;align-items:center;gap:.4rem;font-size:.78rem;font-weight:700">{tlogo(n, 20)}{t}</span>'
                    for n, t in [("docker-icon", "Docker"), ("digital-ocean-icon", "DigitalOcean"), ("sentry-icon", "Sentry")])
    return head(11, "Phần 3 · Kiến trúc", "Kiến trúc hệ thống",
                "Ba lớp tách bạch, mọi thay đổi đều được ghi vết — sẵn sàng phục vụ nhiều tổ chức.") + f'''
    <div class="body" style="flex-direction:column;gap:.9rem;justify-content:center">
      <div style="display:flex;gap:.7rem;align-items:center">
        {box("Giao diện", [("nextjs-icon", "Next.js 15"), ("react", "React 19"), ("typescript-icon", "TS"), ("tailwindcss-icon", "Tailwind")],
             ["120 màn hình cho 4 nhóm người dùng", "Song ngữ Việt – Anh", "Giao diện sáng / tối"],
             ["App Router", "shadcn/ui", "Playwright"], PAL["sky"])}
        {arrow}
        {box("Xử lý nghiệp vụ", [("fastapi-icon", "FastAPI"), ("python", "Python 3.12")],
             ["34 phân hệ độc lập, ranh giới rõ", "Phân quyền kiểm tra ở tầng dịch vụ", "Mọi thao tác ghi đều có nhật ký"],
             ["tuyển dụng", "hồ sơ CV", "trợ lý AI", "quy trình", "báo cáo", "+29"], PAL["indigo"])}
        {arrow}
        {box("Dữ liệu &amp; AI", [("postgresql", "PostgreSQL 16"), ("redis", "Redis"), ("openai-icon", "Cổng AI")],
             ["Tìm kiếm ngữ nghĩa (pgvector)", "Xử lý nền bằng hàng đợi Celery", "Nhiều nhà cung cấp AI, tự chuyển dự phòng"],
             ["read-models", "giám sát Langfuse", "ẩn danh nhà cung cấp"], PAL["teal"])}</div>
      <div class="card" style="padding:.75rem 1.2rem;display:flex;align-items:center;gap:1.2rem;flex-wrap:wrap">
        <span style="font-size:.74rem;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--faint)">Hạ tầng</span>{infra}
        <span class="chip pill" style="margin-left:auto">{icon("shield", 15)} Thiết kế nhiều tổ chức — thêm trường mới không phải viết lại</span></div>
    </div>'''


# ═══════════ 12 · CÔNG NGHỆ ═══════════
def s12():
    steps = "".join(f'''<div style="display:flex;align-items:center;gap:.7rem;margin-top:.5rem">
        <span style="width:26px;height:26px;border-radius:8px;background:{c}18;color:{c};display:grid;place-items:center;font-weight:800;font-size:.8rem;flex:0 0 auto">{i}</span>
        <span style="flex:1;font-size:.83rem">{t}</span>
        <span class="chip" style="background:{c}14;color:{c};font-size:.68rem;padding:.25em .6em">{cost}</span></div>'''
                    for i, t, c, cost in [
                        (1, "Kiểm tra an toàn — chặn file hỏng, file giả CV", PAL["ink"], "chặn sớm"),
                        (2, "Đọc chữ trực tiếp từ PDF / Word", PAL["emerald"], "miễn phí"),
                        (3, "OCR file scan — tiếng Việt + tiếng Anh", PAL["teal"], "miễn phí"),
                        (4, "AI đọc ảnh — chỉ khi 3 bước trên chưa đủ", PAL["amber"], "chi phí thấp"),
                        (5, "Chuẩn hoá — mỗi kỹ năng chấm mức 0–100", PAL["indigo"], "1 lần")])
    resil = "".join(f'''<div style="display:flex;gap:.55rem;align-items:center;margin-top:.5rem">
        {icbox(ic, c, 32, 18, 9)}<span style="font-size:.8rem;line-height:1.35">{t}</span></div>'''
                    for ic, c, t in [
                        ("shield", PAL["emerald"], "AI gặp sự cố → <b>tự chuyển nhà cung cấp dự phòng</b>, hệ thống không dừng"),
                        ("match", PAL["rose"], "Chấm điểm CV là <b>thuật toán tất định</b> — chạy được cả khi không có AI, không tốn phí"),
                        ("lock", PAL["indigo"], "OCR xử lý <b>ngay trên máy chủ</b>; ảnh gửi AI được hạ độ phân giải")])
    gov = "".join(f'<span class="chip pill" style="font-size:.73rem">{t}</span>' for t in
                  ["Đo lường từng lượt AI", "Hỏi trước khi ghi dữ liệu", "Không lộ nhà cung cấp AI", "Giới hạn tần suất dùng", "Nhật ký mọi thao tác"])
    stack = "".join(f'''<div style="display:flex;flex-direction:column;align-items:center;gap:.4rem">
        <span class="card" style="width:56px;height:56px;display:grid;place-items:center;border-radius:14px">{tlogo(n, 29)}</span>
        <span style="font-size:.68rem;font-weight:700;color:var(--mut)">{t}</span></div>'''
                    for n, t in [("nextjs-icon", "Next.js"), ("react", "React"), ("typescript-icon", "TypeScript"),
                                 ("tailwindcss-icon", "Tailwind"), ("python", "Python"), ("fastapi-icon", "FastAPI"),
                                 ("postgresql", "Postgres"), ("redis", "Redis"), ("docker-icon", "Docker"),
                                 ("digital-ocean-icon", "DO Cloud"), ("sentry-icon", "Sentry"), ("openai-icon", "Cổng AI")])
    return head(12, "Phần 3 · Công nghệ", "Công nghệ sử dụng",
                "Công nghệ phổ biến, ổn định — và hệ thống được thiết kế để không phụ thuộc vào một nhà cung cấp AI nào.") + f'''
    <div class="body" style="gap:1.2rem">
      <div style="flex:1.05;display:flex;flex-direction:column;justify-content:center;gap:.9rem">
        <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:.8rem 0">{stack}</div>
        <div class="card" style="padding:.75rem 1.05rem;display:flex;align-items:center;gap:.5rem;flex-wrap:wrap">
          <span style="font-size:.72rem;font-weight:800;color:var(--faint);text-transform:uppercase;letter-spacing:.08em">AI có kiểm soát:</span>{gov}</div>
        <div class="card" style="padding:.85rem 1.05rem">
          <div style="font-weight:800;font-size:.9rem">Khi có sự cố thì sao?</div>{resil}</div></div>
      <div class="card" style="flex:.95;padding:1.1rem 1.2rem;align-self:center">
        <div style="display:flex;align-items:center;gap:.6rem;margin-bottom:.3rem">{icbox("cv", PAL["violet"], 40, 22)}
          <div style="font-weight:800;font-size:.95rem">Đọc CV tự động — PDF, Word, ảnh scan</div></div>
        {steps}
        <div class="sub" style="font-size:.76rem;margin-top:.65rem">Bước rẻ chạy trước, AI chỉ dùng khi thật sự cần. File không phải CV bị từ chối rõ ràng — <b>không bao giờ bịa dữ liệu</b>.</div></div>
    </div>'''


# ═══════════ 13 · LỘ TRÌNH PHÁT TRIỂN ═══════════
def s13():
    miles = [
        ("check", PAL["emerald"], "Xây dựng nền tảng", "2025 – nay", True,
         ["4 phân hệ, 120 màn hình, AI đầy đủ", "2.022 bài kiểm thử tự động", "Song ngữ Việt – Anh, sáng / tối"]),
        ("flag", PAL["indigo"], "Thí điểm toàn trường", "Q3 / 2026", False,
         ["Toàn bộ sinh viên &amp; phòng hướng nghiệp", "20–30 doanh nghiệp đối tác đầu tiên", "Thu thập phản hồi, hoàn thiện sản phẩm"]),
        ("growth", PAL["sky"], "Vận hành chính thức", "2027", False,
         ["60–100 doanh nghiệp đồng hành", "Ngày hội việc làm, mạng cựu sinh viên", "Bật nguồn thu: gói doanh nghiệp, quảng cáo"]),
        ("globe", PAL["violet"], "Mở rộng", "Sau 2027", False,
         ["Cấp phép cho các trường đại học khác", "~150tr₫/năm/trường", "Kiến trúc nhiều tổ chức đã sẵn sàng"]),
    ]
    cards = ""
    for i, (ic, c, name, time, done, bullets) in enumerate(miles):
        badge = (f'<span class="chip" style="background:{PAL["emerald"]}14;color:{PAL["emerald"]}">✓ đã xong</span>'
                 if done else f'<span class="chip" style="background:{c}14;color:{c}">{time}</span>')
        dash = "border-style:dashed;" if i == 3 else ""
        rows = "".join(f'''<div style="display:flex;gap:.45rem;align-items:flex-start;margin-top:.42rem">
            <span style="color:{c};font-weight:800;font-size:.78rem;flex:0 0 auto;line-height:1.4">●</span>
            <span style="font-size:.8rem;line-height:1.38">{b}</span></div>''' for b in bullets)
        cards += f'''<div style="flex:1;display:flex;flex-direction:column;position:relative">
          {'<div style="position:absolute;top:24px;left:-13%;width:26%;height:4px;background:' + (PAL["emerald"] if i == 1 else "#e5e2da") + ';z-index:0"></div>' if i else ''}
          <div class="card" style="padding:1.1rem 1.15rem;display:flex;flex-direction:column;gap:.45rem;position:relative;z-index:1;height:100%;{dash}">
            <div style="display:flex;align-items:center;justify-content:space-between">{icbox(ic, c, 44, 24)}{badge}</div>
            <div style="font-weight:800;font-size:1rem">{name}</div>
            <div>{rows}</div></div></div>'''
    return head(13, "Phần 4 · Lộ trình", "Lộ trình phát triển",
                "Phần khó nhất — xây dựng nền tảng — đã hoàn thành. Trọng tâm tiếp theo là triển khai và mở rộng.") + f'''
    <div class="body" style="flex-direction:column;justify-content:center;gap:.9rem">
      <div style="display:flex;gap:1rem;flex:1;align-items:stretch;max-height:340px">{cards}</div>
      <div class="card" style="padding:.75rem 1.2rem;display:flex;align-items:center;gap:.8rem;flex-wrap:wrap">
        {icbox("idea", PAL["amber"], 32, 18, 9)}
        <span style="font-size:.82rem">Chi phí giai đoạn thí điểm chủ yếu là <b>vận hành &amp; ngân sách AI</b> — hạ tầng nhẹ, không cần đội ngũ lớn.</span></div>
    </div>'''


# ═══════════ 14 · MỤC TIÊU 12 THÁNG ═══════════
def s14():
    fun = "".join(f'''<div style="display:flex;align-items:center;gap:.7rem;margin-top:.65rem">
        <div style="width:{w}%;min-width:190px;height:46px;border-radius:11px;background:{c};color:#fff;display:flex;align-items:center;justify-content:space-between;gap:.6rem;padding:0 .9rem">
          <span style="font-weight:800;white-space:nowrap">{v}</span><span style="font-size:.74rem;opacity:.92;text-align:right">{l}</span></div>
        <span class="chip" style="background:{PAL["amber"]}18;color:#b45309;flex:0 0 auto;font-size:.7rem">mục tiêu</span></div>'''
                   for w, c, v, l in [(100, PAL["indigo"], "2.500", "sinh viên sử dụng (~70% toàn trường)"),
                                      (76, PAL["violet"], "3.000+", "CV được tạo trên hệ thống"),
                                      (54, PAL["sky"], "5.000+", "lượt ứng tuyển"),
                                      (34, PAL["teal"], "60–100", "doanh nghiệp đồng hành")])
    side = "".join(f'''<div style="display:flex;gap:.6rem;align-items:center;margin-top:.55rem">
        {icbox(ic, c, 36, 20, 10)}<span style="font-size:.84rem">{t}</span></div>'''
                   for ic, c, t in [("talent", PAL["teal"], "<b>100+</b> cựu sinh viên làm cố vấn"),
                                    ("clock", PAL["ink"], "<b>90%</b> tin tuyển được duyệt đúng hạn"),
                                    ("money", PAL["emerald"], "<b>5–8%</b> người dùng ngoài trường trả phí"),
                                    ("globe", PAL["violet"], "<b>1–2</b> đơn vị ngoài VinUni dùng thử")])
    return head(14, "Phần 4 · Mục tiêu", "Mục tiêu 12 tháng tới",
                "Các chỉ số cụ thể để đánh giá giai đoạn thí điểm — nền tảng đã sẵn sàng đón người dùng.") + f'''
    <div class="body" style="align-items:center;gap:1.8rem">
      <div style="flex:1.15">{fun}</div>
      <div class="card" style="flex:.85;padding:1.2rem 1.3rem">
        <div style="font-weight:800;font-size:.95rem">Cam kết vận hành</div>{side}
        <div style="border-top:1px dashed var(--line);margin-top:.8rem;padding-top:.7rem" class="sub"><span style="font-size:.78rem">Cơ sở để tin: sản phẩm đã hoàn thiện, 32% khóa đầu có việc sớm, thị trường 2,36 triệu sinh viên.</span></div></div>
    </div>'''


# ═══════════ 15 · LỜI MỜI HỢP TÁC ═══════════
def s15():
    asks = "".join(f'''<div style="display:flex;gap:.65rem;align-items:center;margin-top:.6rem">
        <span style="width:30px;height:30px;border-radius:9px;background:rgba(255,255,255,.16);display:grid;place-items:center;font-weight:800;font-size:.82rem;flex:0 0 auto">{i}</span>
        <span style="font-size:.92rem">{t}</span></div>'''
                    for i, t in [(1, "Phê duyệt <b>thí điểm toàn trường</b> trong học kỳ tới"),
                                 (2, "Giới thiệu <b>20–30 doanh nghiệp đối tác</b> đầu tiên"),
                                 (3, "Cấp <b>ngân sách vận hành 12 tháng</b> cho giai đoạn thí điểm")])
    return f'''<div class="body" style="align-items:stretch;gap:1.4rem;margin-top:.4rem">
      <div class="hero" style="flex:1.1;padding:2rem 2.1rem;display:flex;flex-direction:column;justify-content:center;gap:.9rem">
        <img src="{LOGO}" style="height:46px;width:46px;object-fit:contain;filter:invert(1) brightness(2)">
        <div style="font-size:2.05rem;font-weight:800;line-height:1.12">Cùng đưa VinUni Career<br>vào học kỳ tới</div>
        <div style="font-size:.95rem;opacity:.92">Nền tảng đã sẵn sàng. Chúng tôi cần ba điều để bắt đầu:</div>
        <div>{asks}</div>
        <div style="display:flex;gap:.6rem;margin-top:.4rem;align-items:center">
          <span class="chip" style="background:#fff;color:#171717">C2-Team-037</span>
          <span style="font-size:.85rem;opacity:.85">danielngo0302@gmail.com</span></div></div>
      <div style="flex:.9;display:flex;flex-direction:column;gap:.8rem">
        <div class="card" style="flex:1;overflow:hidden;position:relative">
          <img src="{CAMPUS}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover">
          <div style="position:absolute;left:0;right:0;bottom:0;background:linear-gradient(transparent,rgba(23,23,23,.72));color:#fff;padding:1.6rem 1.1rem .8rem;font-size:.82rem;font-weight:700">Khuôn viên VinUniversity · Hà Nội</div></div>
        <div class="card" style="padding:.9rem 1.1rem;display:flex;justify-content:space-between;align-items:center;gap:.6rem">
          <span style="font-size:.84rem;font-weight:800">Học tập → Ứng tuyển → Đi làm → Phản hồi về trường</span>
          <span class="chip" style="background:{PAL["emerald"]}14;color:{PAL["emerald"]};flex:0 0 auto">vòng tròn khép kín</span></div></div>
    </div>'''


SLIDES = [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12, s13, s14, s15]


def build():
    inners = []
    for i, fn in enumerate(SLIDES, 1):
        inner = slide(fn(), i)
        (DECK / f"slide-{i:02d}.html").write_text(doc(inner), encoding="utf-8")
        inners.append(inner)
    for p in DECK.glob("slide-*.html"):
        if int(p.stem.split("-")[1]) > len(SLIDES):
            p.unlink()
    nav = '<div class="navbar"><button onclick="go(-1)">‹</button><span id="pg"></span><button onclick="go(1)">›</button></div>'
    js = ('<script>let i=0;const s=[...document.querySelectorAll(".slide")];'
          'function show(){s.forEach((e,k)=>e.style.display=k===i?"flex":"none");'
          'document.getElementById("pg").textContent=(i+1)+" / "+s.length;}'
          'function go(d){i=Math.max(0,Math.min(s.length-1,i+d));show();}'
          'onkeydown=e=>{if(e.key==="ArrowRight"||e.key===" ")go(1);if(e.key==="ArrowLeft")go(-1);};show();</script>')
    deck = ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>VinUni Career Platform — Pitch Deck</title>'
            f'<style>{CSS}</style></head><body><div class="deck">' + "".join(inners) + "</div>" + nav + js + "</body></html>")
    (DECK / "deck.html").write_text(deck, encoding="utf-8")
    print(f"built {len(SLIDES)} slides + deck.html")


if __name__ == "__main__":
    build()
