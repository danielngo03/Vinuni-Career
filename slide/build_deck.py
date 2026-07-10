#!/usr/bin/env python3
"""Generate self-contained 16:9 HTML slides for the VinUni Career Platform pitch.

Each slide/deck/slide-NN.html is a standalone card (first line `<!-- @dsCard -->`)
so it can be pushed to claude.ai/design via /design-sync. deck.html bundles them
all for presenting + PDF export. Assets (logo-dark, real screenshots) are embedded
as data-URIs so every file runs offline.
"""
import base64, pathlib

HERE = pathlib.Path(__file__).parent
ASSETS = HERE / "assets"
DECK = HERE / "deck"
DECK.mkdir(exist_ok=True)


def datauri(name: str) -> str:
    p = ASSETS / name
    if not p.exists():
        return ""
    mime = "image/svg+xml" if p.suffix == ".svg" else "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


LOGO = datauri("logo-dark.png")
SHOTS = {
    "student": datauri("shot-student-dashboard.png"),
    "cv": datauri("shot-cv-studio.png"),
    "partner": datauri("shot-partner-pipeline.png"),
    "uni": datauri("shot-university-outcomes.png"),
}

# VinUni chevron mark for footers (lightweight inline SVG)
MARK = '<svg viewBox="0 0 32 26" width="18" height="15" aria-hidden="true"><path d="M2 2 L16 24 L30 2 L23 2 L16 14 L9 2 Z" fill="#171717"/></svg>'

CSS = r"""
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#F8F7F1;--card:#fff;--border:#e5e5e5;--ink:#171717;--muted:#525252;--faint:#8f8f8f;
  --indigo:#6366f1;--teal:#14b8a6;--amber:#f59e0b;--rose:#f43f5e;--sky:#0ea5e9;
  --emerald:#10b981;--violet:#8b5cf6;--orange:#f97316;--vinuni:#c83538;--radius:14px;
  --hero:linear-gradient(135deg,#4f46e5 0%,#6d28d9 55%,#7c3aed 100%);
}
html,body{background:#e9e8e2;font-family:"Plus Jakarta Sans",Inter,"Be Vietnam Pro",system-ui,sans-serif;color:var(--ink);-webkit-font-smoothing:antialiased}
.slide{position:relative;width:100%;aspect-ratio:16/9;background:var(--bg);overflow:hidden;
  display:flex;flex-direction:column;padding:3.2% 3.6% 2.4%;}
.kicker{font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.14em;color:#737373}
h1.title{font-size:2.2rem;font-weight:600;letter-spacing:-.02em;line-height:1.12;margin:.35rem 0 .1rem}
.sub{font-size:1rem;color:var(--muted);max-width:70ch}
.metric{font-family:"JetBrains Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums;font-weight:600}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);box-shadow:0 1px 3px rgba(0,0,0,.06)}
.chip{display:inline-flex;align-items:center;gap:.4em;border-radius:999px;padding:.32em .8em;font-size:.8rem;font-weight:600;border:1px solid var(--border);background:#fff}
.dot{width:.55em;height:.55em;border-radius:999px;display:inline-block}
.hero{background:var(--hero);color:#fff;border-radius:var(--radius)}
.body{flex:1;display:flex;flex-direction:column;justify-content:center;gap:1rem;min-height:0}
.grid{display:grid;gap:1rem}
.foot{display:flex;align-items:center;justify-content:space-between;font-size:.72rem;color:var(--faint);padding-top:1rem}
.foot .brand{display:flex;align-items:center;gap:.5em;font-weight:600;color:var(--muted);letter-spacing:.02em}
.src{font-size:.68rem;color:var(--faint)}
.kpi{padding:1.1rem 1.2rem}
.kpi .lab{font-size:.78rem;color:var(--muted);display:flex;justify-content:space-between;align-items:center}
.kpi .num{font-size:2.1rem;line-height:1.1;margin-top:.3rem}
.kpi .num small{font-size:.9rem;color:var(--faint);font-weight:500}
.icon{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;flex:0 0 auto}
.pill{display:flex;flex-direction:column;align-items:center;gap:.45rem;text-align:center;flex:1}
.pill .b{background:#fff;border:1px solid var(--border);border-radius:12px;padding:.7rem .5rem;width:100%;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.arrow{color:#c4c4c4;font-size:1.3rem;flex:0 0 auto;align-self:center}
.frame{background:#fff;border:1px solid var(--border);border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.07)}
.frame .bar{height:22px;background:#f5f5f5;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:5px;padding:0 9px}
.frame .bar i{width:8px;height:8px;border-radius:999px;background:#d4d4d4;display:inline-block}
.frame img{display:block;width:100%;height:auto}
.frame .cap{font-size:.72rem;color:var(--muted);padding:.4rem .6rem;border-top:1px solid var(--border);font-weight:600}
/* deck viewer */
.deck{max-width:1180px;margin:0 auto}
.deck .slide{border-radius:10px;box-shadow:0 8px 30px rgba(0,0,0,.12);margin:0}
.navbar{position:fixed;bottom:14px;left:50%;transform:translateX(-50%);z-index:50;background:#111;color:#fff;border-radius:999px;padding:.4rem .9rem;font-size:.8rem;display:flex;gap:.8rem;align-items:center;font-family:system-ui}
.navbar button{background:none;border:none;color:#fff;cursor:pointer;font-size:1rem}
@media print{.navbar{display:none}.deck{max-width:none}.deck .slide{box-shadow:none;border-radius:0;page-break-after:always}}
"""


def slide_frame(inner: str, n: int, total: int = 21, card=True) -> str:
    """Wrap slide inner HTML with footer. Used both standalone and in deck."""
    foot = (f'<div class="foot"><div class="brand">{MARK} VinUni Career</div>'
            f'<div>VinUni Career Platform &middot; C2-Team-037 &middot; {n:02d}/{total}</div></div>')
    return f'<section class="slide">{inner}{foot}</section>'


def doc(inner: str) -> str:
    """Standalone card file."""
    return ('<!-- @dsCard group="Pitch Deck" -->\n<!doctype html><html lang="vi"><head>'
            '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<style>{CSS}</style></head><body>{inner}</body></html>')


# ---------------- slide content ----------------

def s1():
    dots = "".join(f'<span class="dot" style="background:{c}"></span>' for c in
                   ["#6366f1","#14b8a6","#f59e0b","#f43f5e","#0ea5e9","#10b981","#8b5cf6","#f97316"])
    logo = f'<img src="{LOGO}" alt="VinUni" style="height:52px">' if LOGO else '<b>VinUni</b>'
    return f'''
    <div class="body" style="justify-content:center;gap:1.4rem">
      <div style="display:flex;align-items:center;gap:.9rem">{logo}<span style="font-weight:700;letter-spacing:.04em;font-size:1.1rem">VINUNI CAREER</span></div>
      <h1 class="title" style="font-size:3.4rem;max-width:22ch">VinUni Career Platform</h1>
      <div class="sub" style="font-size:1.25rem;max-width:60ch">Hệ điều hành tuyển dụng chính thức của Đại học VinUni — <b>AI-first</b>, sẵn sàng thành nền tảng.</div>
      <div style="display:flex;gap:.5rem;align-items:center;margin-top:.3rem">{dots}
        <span style="width:64px;height:16px;border-radius:6px;background:var(--hero);margin-left:.6rem"></span></div>
      <div class="sub" style="color:var(--faint);font-size:.95rem">Một nền tảng &middot; Bốn bề mặt vận hành &middot; Toàn bộ vòng đời sự nghiệp</div>
    </div>'''


def persona_card(color, svg, name, pains):
    items = "".join(f'<li style="margin:.22rem 0">{p}</li>' for p in pains)
    return f'''<div class="card" style="padding:1.1rem 1.2rem;flex:1">
      <div class="icon" style="background:{color}1f;color:{color};margin-bottom:.6rem">{svg}</div>
      <div style="font-weight:600;font-size:1rem;margin-bottom:.3rem">{name}</div>
      <ul style="list-style:none;font-size:.82rem;color:var(--muted);line-height:1.35">{items}</ul></div>'''


def s2():
    cap = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 10 12 5 2 10l10 5 10-5Z"/><path d="M6 12v5c0 1 3 3 6 3s6-2 6-3v-5"/></svg>'
    bld = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4M9 6h.01M15 6h.01M9 10h.01M15 10h.01M9 14h.01M15 14h.01"/></svg>'
    lm = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18M6 21V9l6-4 6 4v12M9 21v-6h6v6"/></svg>'
    chips = "".join(f'<span class="chip" style="border-color:#f0c9b0;background:#fdf2ec;color:#b45309">✕ {t}</span>'
                    for t in ["ATS doanh nghiệp quá nặng","Job board quá nông","Tự xây in-house quá khó"])
    return f'''
    <div><div class="kicker">Thực trạng &amp; Thách thức</div>
    <h1 class="title">Hướng nghiệp đại học hôm nay: rời rạc và hời hợt</h1></div>
    <div class="body">
      <div class="grid" style="grid-template-columns:1fr 1fr 1fr">
        {persona_card("#6366f1",cap,"Sinh viên",["Không có tín hiệu độ-phù-hợp cá nhân hoá","Không có trợ lý AI viết/soi CV","Không luyện phỏng vấn, mù mờ cạnh tranh"])}
        {persona_card("#14b8a6",bld,"Nhà tuyển dụng",["ATS doanh nghiệp nặng &amp; đắt","Job board: ứng viên chưa xác thực","Thiếu pipeline &amp; talent pool gắn campus"])}
        {persona_card("#f59e0b",lm,"Nhà trường",["Không kiểm duyệt tập trung","Không quản trị đối tác","Không đo được career outcome / kiểm định"])}
      </div>
      <div style="display:flex;gap:.6rem;flex-wrap:wrap;align-items:center">
        <span style="font-size:.8rem;color:var(--muted);font-weight:600">Vì sao chưa ai giải được:</span>{chips}</div>
      <div class="src">Mỗi năm VN có ~<b>314.000</b> cử nhân ra trường &amp; ~<b>2,36 triệu</b> SV đang học — công cụ vẫn phân mảnh. Nguồn: Bộ GD&amp;ĐT / Tổng cục Thống kê VN, 2024.</div>
    </div>'''


def s3():
    # concentric rings
    rings = '''<svg viewBox="0 0 360 300" style="width:100%;max-width:420px">
      <circle cx="180" cy="150" r="140" fill="none" stroke="#8b5cf6" stroke-width="1.5" stroke-dasharray="5 5" opacity=".6"/>
      <circle cx="180" cy="150" r="95" fill="#6366f114" stroke="#6366f1" stroke-width="1.5"/>
      <circle cx="180" cy="150" r="52" fill="url(#g)" />
      <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4f46e5"/><stop offset="1" stop-color="#7c3aed"/></linearGradient></defs>
      <text x="180" y="146" text-anchor="middle" fill="#fff" font-size="14" font-weight="700">VinUni</text>
      <text x="180" y="163" text-anchor="middle" fill="#fff" font-size="10">~3.500 SV</text>
      <text x="180" y="70" text-anchor="middle" fill="#4f46e5" font-size="11" font-weight="600">Alumni + SV ngoài + người đi làm</text>
      <text x="180" y="24" text-anchor="middle" fill="#7c3aed" font-size="11" font-weight="600">Nền tảng độc lập / đa-trường</text>
    </svg>'''
    tam = "".join(f'<div class="card" style="padding:.8rem 1rem"><div class="metric" style="font-size:1.5rem">{n}</div><div style="font-size:.74rem;color:var(--muted)">{l}</div></div>'
                  for n,l in [("2,36 triệu","Sinh viên ĐH toàn VN (TAM)"),("~314.000","Cử nhân tốt nghiệp / năm"),(">940.000","Doanh nghiệp đang hoạt động"),("~US$1 tỷ","Thị trường HR-tech VN (dự báo)")])
    return f'''
    <div><div class="kicker">Cơ hội thị trường &amp; Tầm nhìn nền tảng</div>
    <h1 class="title">Bắt đầu từ VinUni — kiến trúc sẵn sàng thành nền tảng cho mọi người</h1></div>
    <div class="body"><div style="display:flex;gap:1.6rem;align-items:center">
      <div style="flex:0 0 42%;display:flex;justify-content:center">{rings}</div>
      <div style="flex:1;display:flex;flex-direction:column;gap:.9rem">
        <div class="sub" style="font-size:.92rem"><b>Beachhead → mở rộng:</b> thắng sâu ở VinUni (danh tính đã xác thực + vòng lặp dữ liệu khép kín), rồi mở ra ngoài — <b>multi-tenant RBAC</b> đã sẵn, đã phục vụ cả SV ngoài / người đi làm.</div>
        <div class="grid" style="grid-template-columns:1fr 1fr">{tam}</div>
      </div></div>
      <div class="src">Nguồn: Tổng cục Thống kê / Bộ GD&amp;ĐT VN 2024 (2,36M SV · 314k cử nhân · 243 trường, 67 tư) · NSO/VietnamNet (&gt;940k DN) · imarcgroup/kenresearch (HR-tech). Vòng ngoài = tầm nhìn, chưa cam kết.</div>
    </div>'''


def surface_card(color, svg, name, kws):
    ch = "".join(f'<span style="font-size:.72rem;color:var(--muted)">{k}</span>' for k in kws)
    return f'''<div class="card" style="padding:1rem 1.1rem">
      <div class="icon" style="background:{color}1f;color:{color};margin-bottom:.5rem">{svg}</div>
      <div style="font-weight:600;font-size:.95rem">{name}</div>
      <div style="display:flex;flex-direction:column;gap:.1rem;margin-top:.3rem">{ch}</div></div>'''


def s4():
    comp='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m16 8-6 2-2 6 6-2 2-6Z"/></svg>'
    dash='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/></svg>'
    bag='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 7h12l1 14H5L6 7Z"/><path d="M9 7a3 3 0 0 1 6 0"/></svg>'
    lm='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18M6 21V9l6-4 6 4v12"/></svg>'
    return f'''
    <div><div class="kicker">Giải pháp</div>
    <h1 class="title">Một nền tảng AI-first, bốn bề mặt vận hành</h1></div>
    <div class="body"><div style="display:flex;gap:1.2rem;align-items:stretch">
      <div class="hero" style="flex:0 0 30%;padding:1.4rem;display:flex;flex-direction:column;justify-content:center;gap:.5rem">
        <div style="font-size:.72rem;text-transform:uppercase;letter-spacing:.12em;opacity:.85">AI-first core</div>
        <div style="font-size:1.5rem;font-weight:600;line-height:1.15">AI trợ giúp thật ở mọi bước</div>
        <div style="font-size:.82rem;opacity:.9">Không phải demo trang trí — CV, matching, trợ lý, phỏng vấn, workflow.</div>
      </div>
      <div class="grid" style="grid-template-columns:1fr 1fr;flex:1">
        {surface_card("#0ea5e9",comp,"Public Marketplace",["Khám phá việc/sự kiện/công ty","Salary explorer cho khách"])}
        {surface_card("#6366f1",dash,"Student Command Center",["CV-first · fit score · ứng tuyển","Trợ lý AI · luyện phỏng vấn"])}
        {surface_card("#14b8a6",bag,"Partner Recruiting OS",["JD · pipeline ATS · talent pool","Quảng cáo · analytics"])}
        {surface_card("#f59e0b",lm,"University Operations",["Kiểm duyệt · quản trị đối tác","Workflow · career outcomes"])}
      </div>
    </div></div>'''


def shot(src, cap):
    img = f'<img src="{src}" alt="{cap}">' if src else f'<div style="padding:2rem;text-align:center;color:#aaa">{cap}</div>'
    return f'<div class="frame"><div class="bar"><i></i><i></i><i></i></div>{img}<div class="cap">{cap}</div></div>'


def s5():
    return f'''
    <div><div class="kicker">Sản phẩm thực tế</div>
    <h1 class="title">Sản phẩm đang chạy — ảnh chụp thật, không phải mock</h1></div>
    <div class="body"><div class="grid" style="grid-template-columns:1fr 1fr;gap:.9rem">
      {shot(SHOTS["student"],"Student Dashboard — tổng quan sinh viên")}
      {shot(SHOTS["cv"],"CV Studio — marketplace 7 template")}
      {shot(SHOTS["partner"],"Partner Pipeline — Kanban + AI + donut")}
      {shot(SHOTS["uni"],"University — Kết quả nghề nghiệp (privacy-safe)")}
    </div>
    <div class="src">Ảnh chụp thật từ app (persona student/partner/university, theme sáng) &middot; 120 màn hình &middot; light + dark &middot; colorblind-safe palette.</div>
    </div>'''


SLIDES = [s1, s2, s3, s4, s5]


def build():
    inners = []
    for i, fn in enumerate(SLIDES, 1):
        inner = slide_frame(fn(), i)
        (DECK / f"slide-{i:02d}.html").write_text(doc(inner), encoding="utf-8")
        inners.append(inner)
    # combined deck
    nav = ('<div class="navbar"><button onclick="go(-1)">‹</button>'
           '<span id="pg">1 / %d</span><button onclick="go(1)">›</button></div>' % len(SLIDES))
    js = ('<script>let i=0;const s=[...document.querySelectorAll(".slide")];'
          'function show(){s.forEach((e,k)=>e.style.display=k===i?"":"none");'
          'document.getElementById("pg").textContent=(i+1)+" / "+s.length;}'
          'function go(d){i=Math.max(0,Math.min(s.length-1,i+d));show();}'
          'onkeydown=e=>{if(e.key==="ArrowRight"||e.key===" ")go(1);if(e.key==="ArrowLeft")go(-1);};show();</script>')
    deck = ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>VinUni Career — Pitch</title>'
            f'<style>{CSS}</style></head><body><div class="deck">' + "".join(inners) + "</div>" + nav + js + "</body></html>")
    (DECK / "deck.html").write_text(deck, encoding="utf-8")
    print(f"built {len(SLIDES)} slides + deck.html in {DECK}")


if __name__ == "__main__":
    build()
