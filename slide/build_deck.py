#!/usr/bin/env python3
"""VinUni Career Platform — infographic pitch slides (v3).

Real assets: Solar duotone icons + full-colour tech logos (fetched by
fetch_assets.py into assets/lib/), real product screenshots in device mockups.
Brand: VinUni navy + red. Short copy, dense layouts. Each slide/deck/slide-NN.html
is a standalone @dsCard for /design-sync; deck.html bundles them for present + PDF.
"""
import base64, pathlib, re

HERE = pathlib.Path(__file__).parent
ASSETS = HERE / "assets"
LIB = ASSETS / "lib"
DECK = HERE / "deck"
DECK.mkdir(exist_ok=True)
TOTAL = 21


def datauri(name):
    p = ASSETS / name
    return "" if not p.exists() else f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}"


SHOTS = {k: datauri(v) for k, v in {
    "student": "shot-student-dashboard.png", "cv": "shot-cv-studio.png",
    "partner": "shot-partner-pipeline.png", "uni": "shot-university-outcomes.png"}.items()}


def icon(name, s=26):
    t = (LIB / f"ic-{name}.svg").read_text()
    t = re.sub(r'width="[^"]*"', f'width="{s}"', t, count=1)
    t = re.sub(r'height="[^"]*"', f'height="{s}"', t, count=1)
    return t.replace('<svg ', '<svg style="display:block" ', 1)


def logo(name, h=34):
    t = (LIB / f"logo-{name}.svg").read_text()
    t = re.sub(r'\swidth="[^"]*"', '', t, count=1)
    t = re.sub(r'height="[^"]*"', f'height="{h}"', t, count=1)
    return t.replace('<svg ', f'<svg style="height:{h}px;width:auto;display:block" ', 1)


def icbox(name, color, box=50, isz=28, rad=14):
    return (f'<span style="display:grid;place-items:center;width:{box}px;height:{box}px;'
            f'border-radius:{rad}px;background:{color}16;flex:0 0 auto">{icon(name, isz)}</span>')


MARK = ('<svg viewBox="0 0 44 38" width="{w}" height="{h}">'
        '<path d="M4 8 L22 34 L40 8 L31.5 8 L22 22 L12.5 8 Z" fill="#16386b"/>'
        '<path d="M22 0 l1.9 4 4.4.5-3.3 3 .9 4.3L22 12.6 18.1 14.8l.9-4.3-3.3-3 4.4-.5Z" fill="#c8102e"/></svg>')

CSS = r"""
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#F8F7F1;--card:#fff;--line:#e7e6e0;--navy:#16386b;--ink:#13233d;--muted:#5b6472;--faint:#9aa1ac;
  --red:#c8102e;--blue:#2563eb;--green:#16a34a;--amber:#d97706;--purple:#7c3aed;--teal:#0d9488;--indigo:#4f46e5;--sky:#0ea5e9}
html,body{background:#dedcd4;font-family:"Be Vietnam Pro","Segoe UI",system-ui,sans-serif;color:var(--ink);-webkit-font-smoothing:antialiased}
.slide{position:relative;width:100%;aspect-ratio:16/9;background:var(--bg);overflow:hidden;padding:3.8% 4.6% 4%;display:flex;flex-direction:column}
.eyebrow{display:inline-flex;align-items:center;gap:.5em;font-size:.74rem;font-weight:700;text-transform:uppercase;letter-spacing:.14em;color:var(--red)}
.eyebrow::before{content:"";width:24px;height:3px;border-radius:2px;background:var(--red)}
h1.t{font-size:2.35rem;font-weight:800;color:var(--navy);letter-spacing:-.02em;line-height:1.08;margin-top:.45rem}
.sub{color:var(--muted);line-height:1.4}
.body{flex:1;display:flex;min-height:0;margin-top:1.4rem;gap:1.3rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:0 8px 22px -12px rgba(16,40,80,.18)}
.chip{display:inline-flex;align-items:center;gap:.45em;border-radius:999px;padding:.42em .9em;font-size:.82rem;font-weight:600}
.num{font-weight:800;color:var(--navy);letter-spacing:-.02em;line-height:1}
.foot{position:absolute;left:4.6%;right:4.6%;bottom:2.3%;display:flex;justify-content:space-between;font-size:.75rem;font-weight:600;color:var(--faint)}
.laptop .scr{background:#0e2748;border-radius:12px 12px 3px 3px;padding:7px;box-shadow:0 26px 50px -18px rgba(14,39,72,.5)}
.laptop .scr img{width:100%;display:block;border-radius:4px}
.laptop .base{height:12px;width:113%;margin-left:-6.5%;background:linear-gradient(#e6e8ee,#c4c9d3);border-radius:0 0 11px 11px;position:relative}
.laptop .base::after{content:"";position:absolute;top:0;left:50%;transform:translateX(-50%);width:15%;height:5px;background:#adb3bf;border-radius:0 0 6px 6px}
.brow{background:#fff;border:1px solid var(--line);border-radius:11px;overflow:hidden;box-shadow:0 8px 22px -12px rgba(16,40,80,.22);display:flex;flex-direction:column}
.brow .bar{height:22px;background:#f3f4f7;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:5px;padding:0 9px;flex:0 0 auto}
.brow .bar i{width:7px;height:7px;border-radius:99px;display:inline-block}
.brow .imgwrap{flex:1;overflow:hidden;min-height:0}.brow img{width:100%;height:100%;object-fit:cover;object-position:top;display:block}
.brow .lb{font-size:.76rem;font-weight:700;color:var(--navy);padding:.4rem .6rem;display:flex;align-items:center;gap:.5em;flex:0 0 auto}
.deck{max-width:1160px;margin:0 auto}.deck .slide{border-radius:12px;box-shadow:0 10px 40px rgba(0,0,0,.14)}
.navbar{position:fixed;bottom:14px;left:50%;transform:translateX(-50%);z-index:50;background:#0e2748;color:#fff;border-radius:999px;padding:.45rem 1rem;font-size:.82rem;display:flex;gap:1rem;align-items:center}
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


def head(eyebrow, title):
    return f'<div><span class="eyebrow">{eyebrow}</span><h1 class="t">{title}</h1></div>'


# ---------------- slides ----------------

def s1():
    dots = "".join(f'<span style="width:9px;height:9px;border-radius:99px;background:{c}"></span>'
                   for c in ["#16386b", "#c8102e", "#2563eb", "#16a34a", "#d97706", "#7c3aed", "#0d9488"])
    chips = "".join(f'<span class="chip" style="background:#fff;border:1px solid var(--line);color:var(--navy)">{t}</span>'
                    for t in ["1 nền tảng", "4 bề mặt", "AI mọi bước", "vi / en"])
    lap = f'<div class="laptop"><div class="scr"><img src="{SHOTS["student"]}"></div><div class="base"></div></div>'
    return f'''<div class="body" style="align-items:center;gap:3rem;margin-top:0">
      <div style="flex:1;display:flex;flex-direction:column;gap:1.1rem">
        <div style="display:flex;align-items:center;gap:.7rem">{MARK.format(w=38, h=32)}
          <span style="font-weight:800;color:var(--navy);letter-spacing:.04em">VINUNI CAREER</span></div>
        <h1 style="font-size:3.15rem;font-weight:800;color:var(--navy);letter-spacing:-.03em;line-height:1.03">VinUni Career<br>Platform</h1>
        <div style="font-size:1.22rem;font-weight:700;color:var(--red)">Hệ điều hành tuyển dụng AI-first của VinUni</div>
        <div class="sub" style="font-size:1.02rem;max-width:42ch">Hợp nhất Sinh viên · Đối tác · Nhà trường trên một nền tảng — sẵn sàng mở rộng cho mọi người.</div>
        <div style="display:flex;gap:.55rem;margin-top:.2rem">{dots}</div>
        <div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.3rem">{chips}</div>
      </div>
      <div style="flex:0 0 46%">{lap}</div></div>'''


def pcard(color, ic, name, pains, effect):
    rows = "".join(f'''<div style="display:flex;gap:.55rem;align-items:flex-start;margin-top:.6rem">
        <span style="color:{color};flex:0 0 auto;font-size:.92rem;font-weight:800;line-height:1.4">✕</span>
        <span style="font-size:.92rem;color:var(--ink);line-height:1.35">{p}</span></div>''' for p in pains)
    return f'''<div class="card" style="flex:1;padding:1.3rem 1.3rem;display:flex;flex-direction:column">
      <div style="display:flex;align-items:center;gap:.75rem">{icbox(ic, color, 54, 30)}
        <div style="font-weight:800;color:var(--navy);font-size:1.15rem">{name}</div></div>
      <div style="margin:.7rem 0">{rows}</div>
      <div style="margin-top:.4rem;border-top:1px dashed var(--line);padding-top:.85rem;display:flex;align-items:center;gap:.5rem">
        <span style="width:26px;height:26px;border-radius:8px;background:{color}16;display:grid;place-items:center;color:{color};font-weight:800;font-size:.9rem;flex:0 0 auto">!</span>
        <span style="font-size:.86rem;color:{color};font-weight:700">{effect}</span></div></div>'''


def s2():
    band = "".join(f'<span class="chip" style="background:#fdecec;color:var(--red)">{t}</span>'
                   for t in ["ATS quá nặng", "Job board quá nông", "Tự xây quá khó"])
    return head("Vấn đề", "Công cụ hướng nghiệp đang rời rạc") + f'''
    <div class="body" style="flex-direction:column;justify-content:center;gap:1.3rem">
      <div class="sub" style="font-size:.98rem;margin-top:-.3rem">Sinh viên, doanh nghiệp và nhà trường đều thiếu một công cụ chung — mỗi bên tự xoay xở với công cụ rời rạc.</div>
      <div style="display:flex;gap:1.3rem">
        {pcard("#2563eb", "student", "Sinh viên", ["Không biết CV nào hợp việc nào", "Không có trợ lý AI &amp; luyện phỏng vấn", "Mù mờ mức độ cạnh tranh"], "Ứng tuyển thiếu tự tin")}
        {pcard("#0d9488", "recruiter", "Nhà tuyển dụng", ["ATS doanh nghiệp nặng &amp; đắt", "Ứng viên job board chưa xác thực", "Không có pipeline gắn campus"], "Tuyển sai người, tốn thời gian")}
        {pcard("#d97706", "university", "Nhà trường", ["Kiểm duyệt &amp; đối tác thủ công", "Không đo được career outcome", "Thiếu dữ liệu cho kiểm định"], "Khó chứng minh chất lượng")}
      </div>
      <div class="card" style="padding:.95rem 1.3rem;display:flex;align-items:center;gap:1rem;flex-wrap:wrap">
        <span style="font-weight:800;color:var(--navy);font-size:.98rem">Vì sao chưa ai giải được?</span>
        <div style="display:flex;gap:.5rem">{band}</div>
        <span class="sub" style="font-size:.82rem;margin-left:auto;color:var(--faint)">2,36 triệu SV · 314.000 cử nhân/năm — thị trường lớn nhưng công cụ vẫn phân mảnh</span>
      </div></div>'''


def stat(color, ic, big, lab):
    return f'''<div class="card" style="padding:1rem 1.15rem;display:flex;gap:.9rem;align-items:center">
      {icbox(ic, color, 48, 26)}
      <div><div class="num" style="font-size:1.75rem">{big}</div><div class="sub" style="font-size:.82rem">{lab}</div></div></div>'''


def s3():
    rings = f'''<svg viewBox="0 0 380 330" style="width:100%;max-width:392px">
      <circle cx="190" cy="162" r="155" fill="none" stroke="#7c3aed" stroke-width="1.6" stroke-dasharray="6 6" opacity=".5"/>
      <circle cx="190" cy="162" r="107" fill="#2563eb0f" stroke="#2563eb" stroke-width="1.6"/>
      <circle cx="190" cy="162" r="60" fill="url(#g3)"/>
      <defs><linearGradient id="g3" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#16386b"/><stop offset="1" stop-color="#3b2f8f"/></linearGradient></defs>
      <text x="190" y="158" text-anchor="middle" fill="#fff" font-size="17" font-weight="800" font-family="Be Vietnam Pro,sans-serif">VinUni</text>
      <text x="190" y="177" text-anchor="middle" fill="#dbe3f4" font-size="11" font-family="Be Vietnam Pro,sans-serif">~3.500 SV · điểm tựa</text>
      <text x="190" y="70" text-anchor="middle" fill="#2563eb" font-size="12" font-weight="700" font-family="Be Vietnam Pro,sans-serif">Alumni · SV ngoài · người đi làm</text>
      <text x="190" y="22" text-anchor="middle" fill="#7c3aed" font-size="12" font-weight="700" font-family="Be Vietnam Pro,sans-serif">Nền tảng đa-trường</text></svg>'''
    stats = (stat("#2563eb", "student", "2,36 triệu", "Sinh viên ĐH toàn VN (TAM)") +
             stat("#16a34a", "trend", "314.000", "Cử nhân tốt nghiệp / năm") +
             stat("#d97706", "university", ">940.000", "Doanh nghiệp đang hoạt động") +
             stat("#7c3aed", "growth", "~US$1 tỷ", "Thị trường HR-tech VN (dự báo)"))
    return head("Thị trường &amp; Cơ hội", "Thị trường lớn, thời điểm chín") + f'''
    <div class="body" style="align-items:center;gap:2rem">
      <div style="flex:0 0 41%;display:flex;justify-content:center">{rings}</div>
      <div style="flex:1;display:flex;flex-direction:column;gap:.85rem">
        <div class="sub" style="font-size:.95rem"><b style="color:var(--navy)">Điểm tựa → mở rộng:</b> thắng sâu ở VinUni bằng dữ liệu đã xác thực, rồi mở ra ngoài — <b>multi-tenant RBAC</b> đã sẵn sàng.</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:.8rem">{stats}</div>
        <div class="sub" style="font-size:.72rem;color:var(--faint)">Nguồn: TCTK / Bộ GD&amp;ĐT VN 2024 · NSO/VietnamNet · imarcgroup. Vòng ngoài = tầm nhìn.</div>
      </div></div>'''


def surf(color, ic, name, tag, caps):
    rows = "".join(f'''<div style="display:flex;gap:.5rem;align-items:center;margin-top:.5rem">
        <span style="color:{color};flex:0 0 auto;display:grid;place-items:center">{icon("check", 17)}</span>
        <span style="font-size:.88rem;color:var(--ink)">{c}</span></div>''' for c in caps)
    return f'''<div class="card" style="padding:1.4rem 1.4rem;display:flex;flex-direction:column;justify-content:center">
      <div style="display:flex;align-items:center;gap:.75rem">{icbox(ic, color, 52, 29)}
        <div><div style="font-weight:800;color:var(--navy);font-size:1.1rem;line-height:1.1">{name}</div>
          <div style="font-size:.74rem;font-weight:700;color:{color};text-transform:uppercase;letter-spacing:.06em;margin-top:.15rem">{tag}</div></div></div>
      <div style="margin-top:.7rem">{rows}</div></div>'''


def s4():
    core = f'''<div style="background:linear-gradient(140deg,#16386b,#3b2f8f);color:#fff;border-radius:18px;padding:1.6rem 1.35rem;
        text-align:center;display:flex;flex-direction:column;gap:.7rem;justify-content:center;height:100%;box-shadow:0 22px 44px -16px rgba(22,56,107,.5)">
      <div style="display:flex;justify-content:center">{MARK.format(w=38, h=33)}</div>
      <div style="font-size:1.45rem;font-weight:800;line-height:1.1">AI-first core</div>
      <div style="font-size:.88rem;opacity:.92;line-height:1.45">CV · matching · trợ lý · phỏng vấn · workflow<br>— AI hữu ích ở mọi bước, có kiểm soát</div>
      <div style="display:flex;flex-direction:column;gap:.4rem;margin-top:.6rem;text-align:left">
        {"".join(f'<div style="display:flex;gap:.5rem;align-items:center;font-size:.82rem"><span style="color:#8ad0ff">●</span>{t}</div>' for t in ["Metering + quota minh bạch", "Human-confirm mọi hành động ghi", "Che giấu provider/model"])}</div></div>'''
    return head("Giải pháp", "Một nền tảng, bốn bề mặt vận hành") + f'''
    <div class="body" style="align-items:stretch;gap:1.4rem">
      <div style="flex:1;display:grid;grid-template-columns:1fr 1fr;gap:1.1rem">
        {surf("#2563eb", "marketplace", "Public Marketplace", "Khách vãng lai", ["Khám phá việc &amp; sự kiện", "Trang công ty đối tác", "Salary explorer công khai"])}
        {surf("#4f46e5", "dashboard", "Student Command Center", "Sinh viên", ["CV Studio + AI fit score", "Trợ lý AI 25+ công cụ", "Luyện phỏng vấn AI"])}
        {surf("#0d9488", "partner", "Partner Recruiting OS", "Nhà tuyển dụng", ["Pipeline ATS đa vòng", "Talent pool + AI search", "Analytics tuyển dụng"])}
        {surf("#d97706", "govern", "University Operations", "Nhà trường", ["Kiểm duyệt &amp; duyệt đối tác", "Workflow tự động hoá", "Career outcomes + kiểm định"])}
      </div>
      <div style="flex:0 0 28%">{core}</div></div>'''


def brow(src, color, ic, label):
    return f'''<div class="brow" style="flex:1;min-height:0"><div class="bar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i><i style="background:#28c840"></i></div>
      <div class="imgwrap"><img src="{src}"></div>
      <div class="lb">{icbox(ic, color, 24, 15, 7)}{label}</div></div>'''


def s5():
    big = f'''<div class="laptop"><div class="scr"><img src="{SHOTS["student"]}"></div><div class="base"></div></div>'''
    return head("Sản phẩm", "Ảnh thật từ sản phẩm đang chạy") + f'''
    <div class="body" style="gap:1.4rem;align-items:stretch">
      <div style="flex:0 0 51%;display:flex;flex-direction:column;justify-content:center;gap:.7rem">
        {big}
        <div class="lb" style="justify-content:center;font-size:.82rem;display:flex;align-items:center;gap:.5em;color:var(--navy);font-weight:700">{icbox("dashboard", "#4f46e5", 24, 15, 7)}Student Command Center — tổng quan sinh viên</div></div>
      <div style="flex:1;display:flex;flex-direction:column;gap:.85rem">
        {brow(SHOTS["cv"], "#7c3aed", "cv", "CV Studio — marketplace template")}
        {brow(SHOTS["partner"], "#0d9488", "partner", "Partner Pipeline — Kanban + AI")}
        {brow(SHOTS["uni"], "#d97706", "govern", "University — Career Outcomes")}
      </div></div>'''


SLIDES = [s1, s2, s3, s4, s5]


def build():
    inners = []
    for i, fn in enumerate(SLIDES, 1):
        inner = slide(fn(), i)
        (DECK / f"slide-{i:02d}.html").write_text(doc(inner), encoding="utf-8")
        inners.append(inner)
    nav = '<div class="navbar"><button onclick="go(-1)">‹</button><span id="pg"></span><button onclick="go(1)">›</button></div>'
    js = ('<script>let i=0;const s=[...document.querySelectorAll(".slide")];'
          'function show(){s.forEach((e,k)=>e.style.display=k===i?"flex":"none");'
          'document.getElementById("pg").textContent=(i+1)+" / "+s.length;}'
          'function go(d){i=Math.max(0,Math.min(s.length-1,i+d));show();}'
          'onkeydown=e=>{if(e.key==="ArrowRight"||e.key===" ")go(1);if(e.key==="ArrowLeft")go(-1);};show();</script>')
    deck = ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>VinUni Career — Pitch</title>'
            f'<style>{CSS}</style></head><body><div class="deck">' + "".join(inners) + "</div>" + nav + js + "</body></html>")
    (DECK / "deck.html").write_text(deck, encoding="utf-8")
    print(f"built {len(SLIDES)} slides + deck.html")


if __name__ == "__main__":
    build()
