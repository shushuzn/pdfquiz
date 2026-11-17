"""生成课程首页与课程页。

    python tools/build_hub.py              # 全部课程 + 首页
    python tools/build_hub.py --course polymer-en

站点两层：
    docs/index.html        课程选择，只列课程，不直接展开卷子
    docs/<课程>.html       该课程的卷子列表
    docs/<卷>.html         单份题库（由 out_*/<卷>.quiz.html 同步过来）

课程信息来自仓库根目录 courses.json，卷子题数来自 out_*/decks.json。
同步题库时会把页面里的「返回」链接改成本课程页，避免从卷子跳回首页。
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfquiz.courses import (  # noqa: E402
    course_page,
    deck_page,
    find_course,
    load_courses,
)

DOCS = ROOT / "docs"

TYPE_CN = {
    "trans_en_cn": "英译中",
    "trans_cn_en": "中译英",
    "describe": "英文描述",
    "qa": "英文问答",
    "term": "术语",
    "single": "单选",
    "multiple": "多选",
    "truefalse": "判断",
    "fill": "填空",
    "short": "简答",
}

ORDER = ["trans_en_cn", "trans_cn_en", "describe", "qa", "term",
         "single", "multiple", "truefalse", "fill", "short"]

# 卷子级别的角色，决定卡片上的标签与按钮文案
ROLE = {
    "exam_key": ("考前冲刺", "先做这套"),
    "objective": ("客观题", "刷选择填空"),
    "materials": ("重中之重", "默写材料名"),
    "exam_a": ("模拟考", "开始模考"),
    "exam_b": ("模拟考", "开始模考"),
    "practice": ("精练", "按单元练"),
    "notes": ("速览", "对照重点句"),
    "terms": ("默写", "刷术语"),
    "exam": ("模拟考", "限时自测"),
}

ARROW = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
         '<path d="M5 12h14M12 5l7 7-7 7"/></svg>')
BACK = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
        '<path d="M19 12H5M12 19l-7-7 7-7"/></svg>')

CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --sans: system-ui,-apple-system,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --serif: "Iowan Old Style","Source Han Serif SC","Noto Serif SC","Songti SC",Georgia,serif;
  --paper:#f3f1ec; --surface:#fffefc; --surface2:#f7f4ee;
  --ink:#1b201e; --ink2:#49524f; --muted:#8a938f;
  --line:#e6e1d6; --line2:#d3ccbd;
  --accent:#1f6b5a; --accent-ink:#175246; --accent-soft:#e7f1ed;
  --shadow:0 1px 2px rgba(27,32,30,.04),0 14px 32px -22px rgba(27,32,30,.35);
}
@media (prefers-color-scheme: dark){
  :root{
    --paper:#121614; --surface:#1a201e; --surface2:#202724;
    --ink:#e8ece9; --ink2:#b3bdb8; --muted:#7f8a85;
    --line:#2a322f; --line2:#38423d;
    --accent:#5fb79c; --accent-ink:#8fd3bd; --accent-soft:#1e2f2a;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 16px 36px -24px rgba(0,0,0,.8);
  }
}
html,body{margin:0}
body{
  background:
    radial-gradient(1200px 600px at 82% -8%, color-mix(in srgb, var(--accent) 7%, transparent), transparent 70%),
    var(--paper);
  color:var(--ink); font-family:var(--sans); font-size:15px; line-height:1.7;
  -webkit-font-smoothing:antialiased;
}
a{color:inherit;text-decoration:none}
.wrap{max-width:1080px;margin:0 auto;padding:56px 24px 72px}
.crumb{
  display:inline-flex;align-items:center;gap:7px;margin-bottom:20px;
  font-size:13px;color:var(--ink2);padding:5px 12px 5px 8px;border-radius:999px;
  border:1px solid transparent;transition:border-color .18s,color .18s,background .18s;
}
.crumb svg{width:14px;height:14px;opacity:.7}
.crumb:hover{color:var(--accent);border-color:var(--line);background:var(--surface)}
.head{display:flex;flex-direction:column;gap:14px;margin-bottom:38px}
.kicker{
  font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--accent);
  font-weight:600;display:flex;align-items:center;gap:10px;
}
.kicker::after{content:"";flex:1;height:1px;background:var(--line)}
h1{
  font-family:var(--serif);font-size:clamp(28px,4.4vw,42px);line-height:1.25;
  margin:0;font-weight:600;letter-spacing:-.01em;
}
.lede{margin:0;color:var(--ink2);max-width:56ch;font-size:15.5px}
.meta-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}
.pill{
  font-size:12px;padding:4px 10px;border-radius:999px;background:var(--surface2);
  border:1px solid var(--line);color:var(--ink2);
}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(316px,1fr));gap:16px}
.card{
  display:flex;flex-direction:column;gap:12px;padding:22px 22px 18px;
  background:var(--surface);border:1px solid var(--line);border-radius:16px;
  box-shadow:var(--shadow);transition:transform .18s,border-color .18s,box-shadow .18s;
  position:relative;overflow:hidden;
}
.card::before{
  content:"";position:absolute;inset:0 auto 0 0;width:3px;background:var(--accent);
  opacity:0;transition:opacity .18s;
}
.card:hover{transform:translateY(-2px);border-color:var(--line2)}
.card:hover::before{opacity:1}
.card-top{display:flex;align-items:center;justify-content:space-between;gap:10px}
.tag{
  font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);
  background:var(--accent-soft);border-radius:6px;padding:3px 8px;font-weight:600;
}
.nums{font-size:12.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.nums b{color:var(--ink);font-size:15px;font-weight:600}
.card h2{
  font-family:var(--serif);font-size:19px;margin:0;font-weight:600;line-height:1.35;
  letter-spacing:-.005em;
}
.card p{margin:0;font-size:13.5px;color:var(--ink2)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:2px}
.chip{
  font-size:11.5px;padding:2px 8px;border-radius:6px;background:var(--surface2);
  border:1px solid var(--line);color:var(--ink2);
}
.chip b{color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums}
.go{
  margin-top:auto;padding-top:6px;display:flex;align-items:center;gap:6px;
  color:var(--accent);font-size:13.5px;font-weight:600;
}
.go svg{width:15px;height:15px;transition:transform .18s}
.card:hover .go svg{transform:translateX(3px)}
.plan{
  margin:38px 0 0;padding:20px 22px;border:1px solid var(--line);border-radius:16px;
  background:var(--surface);box-shadow:var(--shadow);
}
.plan h3{
  font-family:var(--serif);font-size:17px;margin:0 0 4px;font-weight:600;
}
.plan .sub{margin:0 0 14px;font-size:13px;color:var(--muted)}
.steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px 20px;margin:0;padding:0;list-style:none}
.steps li{display:flex;gap:10px;font-size:13.5px;color:var(--ink2);line-height:1.6;min-width:0}
.steps li>span:last-child{min-width:0}
.steps .no{
  flex:0 0 22px;height:22px;border-radius:50%;background:var(--accent-soft);color:var(--accent-ink);
  font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;margin-top:1px;
}
.steps b{color:var(--ink);font-weight:600}
.foot{
  margin-top:44px;padding-top:20px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12.5px;display:flex;flex-wrap:wrap;gap:6px 20px;
}
.foot code{
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;
  background:var(--surface2);padding:1px 5px;border-radius:4px;
}
@media (max-width:760px){
  .steps{grid-template-columns:minmax(0,1fr)}
}
@media (max-width:560px){
  .wrap{padding:34px 16px 56px}
  .grid{grid-template-columns:minmax(0,1fr);gap:12px}
  .card{padding:18px 16px 15px}
  h1{font-size:26px}
  .crumb{margin-bottom:16px}
}
"""


def inline(text: str) -> str:
    """转义后把 **强调** 变成 <b>。"""
    safe = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)


def page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{body}
</div>
</body>
</html>
"""


def course_card(course: dict, decks: list[dict]) -> str:
    total = sum(d.get("count", 0) for d in decks)
    nums = f'<b>{len(decks)}</b> 套' + (f' · <b>{total}</b> 题' if total else "")
    chips = "".join(
        f'<span class="chip">{html.escape(d.get("short") or (course.get("labels") or {}).get(d["id"]) or ROLE.get(d["id"], ("题库",))[0])} <b>{d.get("count", 0)}</b></span>'
        for d in decks
    )
    return f"""      <a class="card" href="{html.escape(course_page(course))}">
        <div class="card-top"><span class="tag">课程</span><span class="nums">{nums}</span></div>
        <h2>{html.escape(course["name"])}</h2>
        <p>{html.escape(course["desc"])}</p>
        <div class="chips">{chips}</div>
        <span class="go">进入课程{ARROW}</span>
      </a>"""


def deck_card(course: dict, deck: dict) -> str:
    role, cta = ROLE.get(deck["id"], ("题库", "开始"))
    prefix = f'{course["name"]} · '
    title = deck["title"][len(prefix):] if deck["title"].startswith(prefix) else deck["title"]
    chips = "".join(
        f'<span class="chip">{TYPE_CN.get(t, t)} <b>{n}</b></span>'
        for t, n in sorted(deck["types"].items(), key=lambda kv: ORDER.index(kv[0]) if kv[0] in ORDER else 99)
    )
    nums = f'<b>{deck["count"]}</b> 题' + (f' · <b>{deck["score"]}</b> 分' if deck.get("score") else "")
    return f"""      <a class="card" href="{html.escape(deck_page(course, deck["id"]))}">
        <div class="card-top"><span class="tag">{role}</span><span class="nums">{nums}</span></div>
        <h2>{html.escape(title)}</h2>
        <p>{html.escape(deck["desc"])}</p>
        <div class="chips">{chips}</div>
        <span class="go">{html.escape(cta)}{ARROW}</span>
      </a>"""


def plan_html(plan: dict) -> str:
    steps = "".join(
        f'<li><span class="no">{i}</span><span>{inline(step)}</span></li>'
        for i, step in enumerate(plan.get("steps") or [], 1)
    )
    sub = f'<p class="sub">{inline(plan["sub"])}</p>' if plan.get("sub") else ""
    return f"""  <section class="plan">
    <h3>{html.escape(plan.get("title") or "刷题顺序")}</h3>
    {sub}
    <ol class="steps">{steps}</ol>
  </section>"""


def render_home(courses: list[dict], decks_by_course: dict[str, list[dict]]) -> str:
    total_decks = sum(len(v) for v in decks_by_course.values())
    total_q = sum(d.get("count", 0) for v in decks_by_course.values() for d in v)
    cards = "\n".join(course_card(c, decks_by_course[c["id"]]) for c in courses)
    body = f"""  <header class="head">
    <div class="kicker">题库 · 共 {len(courses)} 门课程</div>
    <h1>先选课程</h1>
    <p class="lede">每门课单独一套题库，题目按课程归档，答题记录也分开保存。选一门课，再挑要练的卷子。</p>
    <div class="meta-row">
      <span class="pill">共 {total_decks} 套题库</span>
      <span class="pill">共 {total_q} 题</span>
      <span class="pill">离线可用 · 单文件</span>
      <span class="pill">答题记录存在本机</span>
    </div>
  </header>

  <main class="grid">
{cards}
  </main>

  <footer class="foot">
    <span>题库不跨课程混用：每门课一个入口，避免进错卷子。</span>
    <span>进度存在浏览器 <code>localStorage</code>，换设备不同步。</span>
    <span>新增课程：在 <code>courses.json</code> 登记后重跑 <code>tools/build_hub.py</code>。</span>
  </footer>"""
    return page("复习题库 · 选择课程", body)


def render_course(course: dict, decks: list[dict]) -> str:
    total = sum(d.get("count", 0) for d in decks)
    cards = "\n".join(deck_card(course, d) for d in decks)
    pills = [f'<span class="pill">共 {total} 题</span>']
    if course["tagline"]:
        pills.insert(0, f'<span class="pill">{html.escape(course["tagline"])}</span>')
    pills += [
        '<span class="pill">离线可用 · 单文件</span>',
        '<span class="pill">答题记录存在本机</span>',
        '<span class="pill">支持手机与打印</span>',
    ]
    lede = html.escape(course["desc"])
    if course["coverage"]:
        lede += f'范围覆盖 {html.escape(course["coverage"])}。'
    plan = plan_html(course["plan"]) if course.get("plan") else ""
    body = f"""  <a class="crumb" href="index.html">{BACK}全部课程</a>
  <header class="head">
    <div class="kicker">课程题库 · 共 {len(decks)} 套</div>
    <h1>{html.escape(course["name"])}<br>复习题库</h1>
    <p class="lede">{lede}</p>
    <div class="meta-row">
      {"".join(pills)}
    </div>
  </header>

  <main class="grid">
{cards}
  </main>

{plan}

  <footer class="foot">
    <span>每套题库都是单个 HTML，双击即可作答，无需联网。</span>
    <span>进度存在浏览器 <code>localStorage</code>，换设备不同步。</span>
    <span>主观题无法自动判分，走「对照参考答案 → 自己标记」。</span>
  </footer>"""
    return page(f'{course["name"]} · 复习题库', body)


HUBLINK = re.compile(r'<a class="hub-link" href="[^"]*">(.*?)</a>', re.S)


def retarget_hublink(text: str, href: str, label: str = "返回课程") -> str:
    """把题库页面里的返回链接指向当前课程页。"""
    def sub(m: re.Match) -> str:
        inner = m.group(1).replace("全部试卷", label).replace("返回课程", label)
        return f'<a class="hub-link" href="{html.escape(href)}">{inner}</a>'
    return HUBLINK.sub(sub, text, count=1)


def load_decks(course: dict) -> list[dict]:
    path = ROOT / course["out"] / "decks.json"
    if not path.exists():
        return []
    decks = json.loads(path.read_text(encoding="utf-8"))
    wanted = course["decks"]
    if not wanted:
        return decks
    order = {name: i for i, name in enumerate(wanted)}
    return sorted([d for d in decks if d["id"] in order], key=lambda d: order[d["id"]])


def sync_decks(course: dict, decks: list[dict]) -> tuple[list[str], list[str]]:
    """把卷子页面同步到 docs/，并改写返回链接。"""
    DOCS.mkdir(exist_ok=True)
    href = course_page(course)
    copied, missing = [], []
    for deck in decks:
        src = ROOT / course["out"] / f'{deck["id"]}.quiz.html'
        dst = DOCS / deck_page(course, deck["id"])
        if src.exists():
            text = src.read_text(encoding="utf-8")
            dst.write_text(retarget_hublink(text, href), encoding="utf-8")
            copied.append(dst.name)
        elif dst.exists():
            dst.write_text(retarget_hublink(dst.read_text(encoding="utf-8"), href), encoding="utf-8")
            copied.append(dst.name)
        else:
            missing.append(deck["id"])
    return copied, missing


def main(argv: list[str]) -> int:
    courses = load_courses(ROOT)
    only = None
    if "--course" in argv:
        i = argv.index("--course")
        if i + 1 >= len(argv):
            print("--course 后面要跟课程 id")
            return 2
        only = argv[i + 1]
        find_course(courses, only)
        courses = [c for c in courses if c["id"] == only]

    decks_by_course = {c["id"]: load_decks(c) for c in courses}
    for course in courses:
        decks = decks_by_course[course["id"]]
        if not decks:
            print(f'跳过 {course["id"]}：{course["out"]}/decks.json 不存在，先跑 tools/build_exam.py')
            continue
        copied, missing = sync_decks(course, decks)
        out = DOCS / course_page(course)
        out.write_text(render_course(course, decks), encoding="utf-8")
        total = sum(d.get("count", 0) for d in decks)
        print(f'{course["id"]}: {len(decks)} 套 · {total} 题 → {out.name}'
              + (f'（同步 {len(copied)} 份题库）' if copied else ""))
        if missing:
            print("  缺页面：" + ", ".join(missing))

    if only is None:
        # 首页只列真的构建过的课程
        built = [c for c in courses if decks_by_course[c["id"]]]
        if not built:
            print("没有任何课程可展示")
            return 1
        DOCS.mkdir(exist_ok=True)
        home = DOCS / "index.html"
        home.write_text(render_home(built, decks_by_course), encoding="utf-8")
        print(f"写出 {home}（{len(built)} 门课程）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
