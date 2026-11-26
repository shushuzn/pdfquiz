"""把教材例题数据生成为可离线阅读的「例题精解」页。

    python tools/build_examples.py

数据在 papers_hgyl/examples/chNN.json，先过 check_examples 的同一套校验，
再写入 out_hgyl/examples.quiz.html（文件名沿用构建管线的约定）。
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import examples  # noqa: E402
import hgyl  # noqa: E402

OUT = ROOT / "out_hgyl"

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
.wrap{max-width:920px;margin:0 auto;padding:48px 24px 72px}
.crumb{
  display:inline-flex;align-items:center;gap:7px;margin-bottom:20px;
  font-size:13px;color:var(--ink2);padding:5px 12px 5px 8px;border-radius:999px;
  border:1px solid transparent;transition:border-color .18s,color .18s,background .18s;
}
.crumb svg{width:14px;height:14px;opacity:.7}
.crumb:hover{color:var(--accent);border-color:var(--line);background:var(--surface)}
.head{display:flex;flex-direction:column;gap:12px;margin-bottom:26px}
.kicker{
  font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--accent);
  font-weight:600;display:flex;align-items:center;gap:10px;
}
.kicker::after{content:"";flex:1;height:1px;background:var(--line)}
h1{
  font-family:var(--serif);font-size:clamp(27px,4.2vw,40px);line-height:1.25;
  margin:0;font-weight:600;letter-spacing:-.01em;
}
.lede{margin:0;color:var(--ink2);max-width:62ch;font-size:15.5px}
.meta-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}
.pill{font-size:12px;padding:4px 10px;border-radius:999px;background:var(--surface2);border:1px solid var(--line);color:var(--ink2)}
.bank-note{margin:2px 0 0;color:var(--muted);font-size:13px}
.toc{
  display:flex;flex-wrap:wrap;gap:6px;margin:22px 0 14px;padding:12px;
  background:var(--surface);border:1px solid var(--line);border-radius:14px;
  box-shadow:var(--shadow);
}
.toc a{
  font-size:12.5px;padding:4px 9px;border-radius:7px;background:var(--surface2);
  border:1px solid var(--line);color:var(--ink2);transition:color .16s,border-color .16s;
}
.toc a:hover{color:var(--accent);border-color:var(--line2)}
.toc a b{color:var(--accent);font-weight:600;margin-left:3px;font-variant-numeric:tabular-nums}
.tools{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 10px}
#search{
  flex:1 1 240px;min-width:0;font:inherit;font-size:14px;color:var(--ink);
  background:var(--surface);border:1px solid var(--line);border-radius:9px;
  padding:8px 12px;outline:none;transition:border-color .16s,box-shadow .16s;
}
#search:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
#expandAll{
  font:inherit;font-size:13px;color:var(--accent-ink);background:var(--accent-soft);
  border:1px solid transparent;border-radius:9px;padding:8px 12px;cursor:pointer;white-space:nowrap;
}
#expandAll:hover{border-color:var(--accent)}
#shown{font-size:12.5px;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.chapter{margin-top:34px;scroll-margin-top:18px}
.ch-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;border-bottom:2px solid var(--line);padding-bottom:8px;margin-bottom:14px}
.ch-head h2{font-family:var(--serif);font-size:21px;line-height:1.35;margin:0;font-weight:600}
.ch-head .count{font-size:12.5px;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}
.ex{
  background:var(--surface);border:1px solid var(--line);border-radius:14px;
  padding:18px 20px 16px;margin-bottom:12px;box-shadow:var(--shadow);
}
.ex[hidden]{display:none}
.chapter[hidden]{display:none}
.ex-head{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin-bottom:7px}
.label{
  font-size:11.5px;font-weight:700;letter-spacing:.03em;color:var(--accent-ink);
  background:var(--accent-soft);border-radius:6px;padding:2px 8px;white-space:nowrap;
}
.topic{font-size:15.5px;font-weight:600;line-height:1.5}
.ref{margin-left:auto;font-size:12px;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}
.text{white-space:pre-wrap;overflow-wrap:break-word}
.problem{font-size:15px;line-height:1.85;color:var(--ink)}
.text sup,.text sub{font-size:.72em;line-height:0}
.text sup{vertical-align:super}
.text sub{vertical-align:sub}
.ex-actions{display:flex;align-items:center;gap:12px;margin-top:12px}
.toggle{
  font:inherit;font-size:12.5px;font-weight:600;color:var(--accent-ink);
  background:var(--accent-soft);border:1px solid transparent;border-radius:8px;
  padding:5px 11px;cursor:pointer;transition:border-color .16s;
}
.toggle:hover{border-color:var(--accent)}
.fig{font-size:12px;color:var(--muted)}
.sol{margin-top:14px;border-top:1px dashed var(--line2);padding-top:14px}
.sol[hidden]{display:none}
.sol-k{
  display:inline-block;font-size:11px;font-weight:700;letter-spacing:.08em;color:var(--accent);
  margin-bottom:6px;
}
.steps{font-size:14.5px;line-height:1.95;color:var(--ink2)}
.steps b{color:var(--ink)}
.answer{
  margin-top:12px;padding:9px 12px;border-radius:9px;background:var(--accent-soft);
  font-size:14px;line-height:1.8;color:var(--ink);
}
.answer .k{font-weight:700;color:var(--accent-ink);margin-right:8px;font-size:12.5px}
.note{margin-top:10px;font-size:12.5px;color:var(--muted);line-height:1.7}
.foot{
  margin-top:40px;padding-top:18px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12.5px;line-height:1.8;
}
.foot code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;background:var(--surface2);padding:1px 5px;border-radius:4px}
.empty{display:none;padding:28px 0;text-align:center;color:var(--muted);font-size:14px}
@media (max-width:600px){
  .wrap{padding:30px 15px 52px}
  .ex{padding:15px 15px 13px}
  .problem{font-size:14.5px}
  .ch-head h2{font-size:19px}
  .topic{font-size:14.5px}
  .ref{flex-basis:100%;margin-left:0;font-size:11.5px}
  .steps{font-size:14px}
}
@media print{
  body{background:#fff}
  .wrap{max-width:none;padding:0}
  .crumb,.toc,.tools,.ex-actions{display:none}
  .ex{box-shadow:none;break-inside:avoid;border-color:#ccc}
  .sol[hidden]{display:block!important}
}
"""

ARROW = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
         '<path d="M19 12H5M12 19l-7-7 7-7"/></svg>')


def rich(text: str) -> str:
    """转义后只放行 **强调**、^{上标}、_{下标}，不执行任何标签。"""
    s = html.escape(str(text))
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.S)
    s = re.sub(r"\^\{([^{}]*)\}", r"<sup>\1</sup>", s)
    s = re.sub(r"_\{([^{}]*)\}", r"<sub>\1</sub>", s)
    return s


def short_name(stem: str) -> str:
    name = examples.chapter_name(stem)
    return name.split()[0] if " " in name else name


def render(chapters: list[tuple[str, dict]]) -> str:
    total = sum(len(data.get("examples") or []) for _, data in chapters)
    pages = [int(item["ref"][1:]) for _, data in chapters for item in data["examples"]]
    span = f"P{min(pages)}–P{max(pages)}" if pages else "—"
    toc = "".join(
        f'<a href="#{stem}">{html.escape(short_name(stem))}<b>{len(data["examples"])}</b></a>'
        for stem, data in chapters
    )
    parts: list[str] = []
    for stem, data in chapters:
        cards = []
        for item in data["examples"]:
            fig = (
                f'<span class="fig">附图 {html.escape(str(item.get("figure")))}</span>'
                if str(item.get("figure", "")).strip()
                else ""
            )
            note = (
                f'<div class="note text">注：{rich(item["note"])}</div>'
                if str(item.get("note", "")).strip()
                else ""
            )
            cards.append(f"""      <article class="ex" id="{html.escape(item['id'])}">
        <div class="ex-head">
          <span class="label">{html.escape(item['label'])}</span>
          <span class="topic">{html.escape(item['topic'])}</span>
          <span class="ref">教材 {html.escape(item['ref'])}</span>
        </div>
        <div class="problem text">{rich(item['problem'])}</div>
        <div class="ex-actions">
          <button class="toggle" type="button" aria-expanded="false">展开解答</button>
          {fig}
        </div>
        <div class="sol" hidden>
          <div class="sol-k">解</div>
          <div class="steps text">{rich(item['solution'])}</div>
          <div class="answer"><span class="k">答案</span>{rich(item['answer'])}</div>
          {note}
        </div>
      </article>""")
        parts.append(f"""    <section class="chapter" id="{stem}">
      <div class="ch-head"><h2>{html.escape(examples.chapter_name(stem))}</h2><span class="count">{len(data['examples'])} 例</span></div>
{chr(10).join(cards)}
    </section>""")
    body = "\n".join(parts)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>化工原理 · 教材例题精解</title>
<style>{CSS}</style>
</head>
<body>
<noscript><style>.sol[hidden]{{display:block}}.toggle{{display:none}}</style></noscript>
<div class="wrap">
  <a class="crumb hub-link" href="hgyl.html">{ARROW}返回课程</a>
  <header class="head">
    <div class="kicker">教材例题 · 共 {total} 例</div>
    <h1>化工原理<br>例题精解</h1>
    <p class="lede">把教材正文里的例题按章收在一起：先自己做一遍，再展开解答对照思路。页码是印刷页码，可以翻回教材核对原题与原图。</p>
    <div class="meta-row">
      <span class="pill">{total} 例</span>
      <span class="pill">{len(chapters)} 章</span>
      <span class="pill">{span}</span>
      <span class="pill">离线可用 · 单文件</span>
    </div>
    <p class="bank-note">例题转写自教材，公式按网页排版做了线性化整理；个别数值如受扫描清晰度影响，以教材原页为准。例题不计入题库题数。</p>
  </header>

  <nav class="toc" aria-label="章节目录">{toc}</nav>
  <div class="tools">
    <input id="search" type="search" placeholder="搜索编号、主题或题干…" aria-label="搜索例题">
    <button id="expandAll" type="button">全部展开</button>
    <span id="shown">显示 {total} / {total}</span>
  </div>

  <main>
{body}
    <div class="empty" id="empty">没有匹配的例题，换个关键词试试。</div>
  </main>

  <footer class="foot">
    <span>来源：《化工原理》（第四版），杨祖荣主编，化学工业出版社。例题文字与解题思路转写自教材，仅供课程复习。</span><br>
    <span>页码为印刷页码；PDF 页码 = 印刷页码 + 9。数据在 <code>papers_hgyl/examples/</code>，校验用 <code>tools/check_examples.py</code>。</span>
  </footer>
</div>
<script>
(function () {{
  var cards = Array.prototype.slice.call(document.querySelectorAll('.ex'));
  var all = document.getElementById('expandAll');
  var search = document.getElementById('search');
  var shown = document.getElementById('shown');
  var empty = document.getElementById('empty');
  var openAll = false;

  cards.forEach(function (card) {{
    var btn = card.querySelector('.toggle');
    var sol = card.querySelector('.sol');
    btn.addEventListener('click', function () {{
      var open = sol.hidden;
      sol.hidden = !open;
      btn.textContent = open ? '收起解答' : '展开解答';
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      card.classList.toggle('open', open);
    }});
  }});

  all.addEventListener('click', function () {{
    openAll = !openAll;
    cards.forEach(function (card) {{
      var btn = card.querySelector('.toggle');
      var sol = card.querySelector('.sol');
      sol.hidden = !openAll;
      btn.textContent = openAll ? '收起解答' : '展开解答';
      btn.setAttribute('aria-expanded', openAll ? 'true' : 'false');
      card.classList.toggle('open', openAll);
    }});
    all.textContent = openAll ? '全部收起' : '全部展开';
  }});

  function filter() {{
    var q = search.value.trim().toLowerCase();
    var n = 0;
    cards.forEach(function (card) {{
      var text = card.getAttribute('data-text');
      var hit = !q || text.indexOf(q) >= 0;
      card.hidden = !hit;
      if (hit) n++;
    }});
    Array.prototype.forEach.call(document.querySelectorAll('.chapter'), function (sec) {{
      var any = Array.prototype.some.call(sec.querySelectorAll('.ex'), function (c) {{ return !c.hidden; }});
      sec.hidden = !any;
    }});
    shown.textContent = '显示 ' + n + ' / ' + cards.length;
    empty.style.display = n ? 'none' : 'block';
  }}

  cards.forEach(function (card) {{
    var head = card.querySelector('.ex-head').textContent;
    var problem = card.querySelector('.problem').textContent;
    var sol = card.querySelector('.sol').textContent;
    card.setAttribute('data-text', (head + ' ' + problem + ' ' + sol).toLowerCase());
  }});
  search.addEventListener('input', filter);
  filter();
}})();
</script>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    errs = examples.validate_all()
    if errs:
        print("例题数据未通过校验：")
        for e in errs:
            print(f"  ✗ {e}")
        return 1
    chapters = [(stem, examples.load(stem)) for stem in hgyl.ORDER if examples.EXPECTED[stem]]
    html_text = render(chapters)
    OUT.mkdir(exist_ok=True)
    target = OUT / "examples.quiz.html"
    target.write_text(html_text, encoding="utf-8")
    total = sum(len(data["examples"]) for _, data in chapters)
    print(f"例题 {total} 例、{len(chapters)} 章 → out_hgyl/{target.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))