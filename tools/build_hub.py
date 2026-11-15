"""生成试卷总览页 docs/index.html。

读 out_exam/decks.json（构建脚本产出），一页列出所有卷子：
题数、满分、题型分布、覆盖范围，点进去就是对应题库。
和题库同一套配色与字体，深浅色都跟系统。
"""

from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECKS = ROOT / "out_exam" / "decks.json"
OUT = ROOT / "docs" / "index.html"

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
    "exam_a": ("模拟考", "开始模考", "100 分正卷 · 60 分钟"),
    "exam_b": ("模拟考", "开始模考", "100 分平行卷 · 60 分钟"),
    "practice": ("精练", "按单元练", "10 个单元逐个过"),
    "notes": ("速览", "对照重点句", "教材原译，考前扫一遍"),
    "terms": ("默写", "刷术语", "中译英，输入即判"),
}

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
.foot{
  margin-top:44px;padding-top:20px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12.5px;display:flex;flex-wrap:wrap;gap:6px 20px;
}
.foot code{
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;
  background:var(--surface2);padding:1px 5px;border-radius:4px;
}
@media (max-width:560px){
  .wrap{padding:34px 16px 56px}
  .grid{grid-template-columns:minmax(0,1fr);gap:12px}
  .card{padding:18px 16px 15px}
  h1{font-size:26px}
}
"""


def card(deck: dict) -> str:
    role, cta, hint = ROLE.get(deck["id"], ("题库", "开始", ""))
    title = html.escape(deck["title"])
    desc = html.escape(deck["desc"])
    chips = "".join(
        f'<span class="chip">{TYPE_CN.get(t, t)} <b>{n}</b></span>'
        for t, n in sorted(deck["types"].items(), key=lambda kv: ORDER.index(kv[0]) if kv[0] in ORDER else 99)
    )
    nums = f'<b>{deck["count"]}</b> 题' + (f' · <b>{deck["score"]}</b> 分' if deck["score"] else "")
    return f"""      <a class="card" href="{deck['id']}.html">
        <div class="card-top"><span class="tag">{role}</span><span class="nums">{nums}</span></div>
        <h2>{title}</h2>
        <p>{desc}</p>
        <div class="chips">{chips}</div>
        <span class="go">{html.escape(cta)}<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg></span>
      </a>"""


def main() -> int:
    if not DECKS.exists():
        print("先跑 python tools/build_exam.py")
        return 1
    decks = json.loads(DECKS.read_text(encoding="utf-8"))
    total = sum(d["count"] for d in decks)
    cards = "\n".join(card(d) for d in decks)

    # 题库原文件放到 docs/ 下，GitHub Pages 才能直接打开；index.html 让给总览页
    (OUT.parent).mkdir(exist_ok=True)
    src_dir = ROOT / "out_exam"
    copied = []
    for d in decks:
        src = src_dir / f"{d['id']}.quiz.html"
        dst = OUT.parent / f"{d['id']}.html"
        if src.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            copied.append(f"{d['id']}.html")
    print("同步：" + ", ".join(copied))


    OUT.write_text(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>高分子材料工程专业英语 · 复习题库</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="head">
    <div class="kicker">期末复习 · 共 {len(decks)} 套</div>
    <h1>高分子材料工程专业英语<br>复习题库</h1>
    <p class="lede">题目全部出自教材原文：每道题的依据句都能逐字回查，不做凭空编题。范围覆盖 PART A 的 UNIT 1、2、3、6、7、10，PART B 的 16、17，PART C 的 22、29。</p>
    <div class="meta-row">
      <span class="pill">共 {total} 题</span>
      <span class="pill">离线可用 · 单文件</span>
      <span class="pill">答题记录存在本机</span>
      <span class="pill">支持手机与打印</span>
    </div>
  </header>

  <main class="grid">
{cards}
  </main>

  <footer class="foot">
    <span>每套题库都是单个 HTML，双击即可作答，无需联网。</span>
    <span>进度存在浏览器 <code>localStorage</code>，换设备不同步。</span>
    <span>主观题无法自动判分，走「对照参考答案 → 自己标记」。</span>
  </footer>
</div>
</body>
</html>
""", encoding="utf-8")
    print(f"写出 {OUT}（{len(decks)} 套 · {total} 题 · {OUT.stat().st_size // 1024} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
