// 移动端交互测试：node mobile.mjs <url>
// 覆盖软键盘收底栏、文本框自增高、横滑翻页、题号面板跳转、字号切换
const [, , url] = process.argv;

const created = await fetch("http://127.0.0.1:9222/json/new?about:blank", { method: "PUT" }).then((r) => r.json());
const ws = new WebSocket(created.webSocketDebuggerUrl);
await new Promise((res) => (ws.onopen = res));

let seq = 0;
const pending = new Map();
const problems = [];
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.method === "Runtime.exceptionThrown") {
    problems.push("异常: " + (msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text).slice(0, 200));
  }
  if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
    problems.push("控制台错误: " + msg.params.entry.text.slice(0, 200));
  }
  if (msg.id && pending.has(msg.id)) {
    const { res, rej } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
  }
};
const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const id = ++seq;
    pending.set(id, { res, rej });
    ws.send(JSON.stringify({ id, method, params }));
  });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const evaluate = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error("JS 异常: " + (r.exceptionDetails.exception?.description || "").slice(0, 300) + " | EXPR: " + expression.slice(0, 160));
  return r.result.value;
};

/* 线上 Pages 偶尔比 readyState 慢半拍，等题库和首张题卡真正就绪再断言 */
const waitQuiz = async (tries = 120) => {
  for (let i = 0; i < tries; i++) {
    try {
      if (await evaluate("!!(window.__QUIZ__ && window.__QUIZ__.questions && document.querySelector('#stage .q'))")) return true;
    } catch (e) { /* 页面还在导航 */ }
    await sleep(100);
  }
  throw new Error("页面在 12 秒内未就绪: " + url);
};

await send("Page.enable");
await send("Runtime.enable");
await send("Log.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 1 });
await send("Emulation.setFocusEmulationEnabled", { enabled: true }).catch(() => {});
await send("Page.navigate", { url });
await waitQuiz();
await evaluate("localStorage.clear()");
await send("Page.reload");
await waitQuiz();
await sleep(300);

const results = [];
const ok = (name, pass, detail) => {
  results.push({ name, pass });
  console.log((pass ? "✓ " : "✗ ") + name + (detail ? "  " + detail : ""));
};

// 输入框相关用例需要有作答框的题；优先跳到多行文本框，没有再到单行输入
const FIELD = await evaluate(`(() => {
  const qs = window.__QUIZ__.questions;
  const MULTI = ['short', 'trans_en_cn', 'trans_cn_en', 'describe', 'qa'];
  let idx = qs.findIndex((q) => MULTI.includes(q.t));
  const grow = idx >= 0;
  if (idx < 0) idx = qs.findIndex((q) => ['fill', 'term'].includes(q.t));
  if (idx > 0) {
    const k = 'pdfquiz:' + (window.__QUIZ__.meta.id || 'deck');
    const s = JSON.parse(localStorage.getItem(k) || '{}');
    s.cur = idx;
    localStorage.setItem(k, JSON.stringify(s));
  }
  return { idx, grow };
})()`);
if (FIELD.idx > 0) {
  await send("Page.reload");
  await waitQuiz();
  await sleep(300);
}

// ---- 1. 底栏在手机上固定于视口底部
const nav = await evaluate(`(() => {
  const n = document.querySelector('#navbar');
  const cs = getComputedStyle(n);
  const r = n.getBoundingClientRect();
  return { pos: cs.position, bottom: Math.round(window.innerHeight - r.bottom), h: Math.round(r.height) };
})()`);
ok("底栏固定吸底", nav.pos === "fixed" && nav.bottom <= 2 && nav.h >= 56, JSON.stringify(nav));

// ---- 2. 正文为底栏留出空间，末尾内容不被遮挡
const pad = await evaluate(`(() => {
  const a = document.querySelector('.q.active');
  const stage = document.querySelector('#stage');
  const pb = parseFloat(getComputedStyle(stage).paddingBottom);
  const r = a.getBoundingClientRect();
  return { pb: Math.round(pb), bottomVsNav: Math.round(document.querySelector('#navbar').getBoundingClientRect().top - r.bottom) };
})()`);
ok("正文避开底栏", pad.pb >= 84, "padding-bottom=" + pad.pb + "px");

if (FIELD.idx < 0) {
  console.log("– 聚焦输入时收起底栏  跳过（题库无输入题）");
  console.log("– 文本框自增高  跳过（题库无输入题）");
} else {
// ---- 3. 聚焦输入框时收起底栏（软键盘会盖住它）
const kbd = await evaluate(`(async () => {
  const f = document.querySelector('.q.active .field');
  f.focus();
  await new Promise(r => setTimeout(r, 60));
  const on = document.body.classList.contains('kbd');
  const disp = getComputedStyle(document.querySelector('#navbar')).display;
  f.blur();
  await new Promise(r => setTimeout(r, 160));
  const off = !document.body.classList.contains('kbd');
  return { on, disp, off };
})()`);
ok("聚焦输入时收起底栏", kbd.on && kbd.disp === "none" && kbd.off, JSON.stringify(kbd));

if (!FIELD.grow) {
  console.log("– 文本框自增高  跳过（题库只有单行输入题）");
} else {
// ---- 4. 文本框随内容长高
const grow = await evaluate(`(async () => {
  const f = document.querySelector('.q.active .field');
  const h0 = f.getBoundingClientRect().height;
  f.value = '这是一段用来撑开文本框的很长很长的译文。'.repeat(20);
  f.dispatchEvent(new Event('input', { bubbles: true }));
  await new Promise(r => setTimeout(r, 80));
  const h1 = f.getBoundingClientRect().height;
  return { h0: Math.round(h0), h1: Math.round(h1) };
})()`);
ok("文本框自增高", grow.h1 > grow.h0 + 60, grow.h0 + " → " + grow.h1 + "px");
// 复原输入框，否则它撑高后会盖住下面的横滑测试触点
await evaluate(`(async () => {
  const f = document.querySelector('.q.active .field');
  f.value = '';
  f.dispatchEvent(new Event('input', { bubbles: true }));
  f.blur();
  await new Promise(r => setTimeout(r, 120));
})()`);
}
}

// ---- 5. 横滑翻页
const swipeStart = await evaluate("document.querySelector('#posNow').textContent");
// 触点放在题干区，避开输入框（输入框内的横向滑动是在选文字，不应翻页）
const tapY = await evaluate(`(() => {
  window.scrollTo(0, 0);
  const r = document.querySelector('.q.active .stem').getBoundingClientRect();
  return Math.round(Math.min(window.innerHeight - 80, Math.max(80, r.top + r.height / 2)));
})()`);
await sleep(120);
const touch = (type, x, y) =>
  send("Input.dispatchTouchEvent", {
    type,
    touchPoints: type === "touchEnd" ? [] : [{ x, y, radiusX: 8, radiusY: 8, force: 1 }],
  });
await touch("touchStart", 330, tapY);
await touch("touchMove", 250, tapY + 2);
await touch("touchMove", 160, tapY + 4);
await touch("touchEnd", 130, tapY + 4);
await sleep(400);
const swipeNext = await evaluate("document.querySelector('#posNow').textContent");
ok("左滑进入下一题", swipeStart !== swipeNext, `第 ${swipeStart} 题 → 第 ${swipeNext} 题`);

await touch("touchStart", 130, tapY);
await touch("touchMove", 230, tapY + 2);
await touch("touchMove", 320, tapY + 4);
await touch("touchEnd", 350, tapY + 4);
await sleep(400);
const swipeBack = await evaluate("document.querySelector('#posNow').textContent");
ok("右滑退回上一题", swipeBack === swipeStart, `回到第 ${swipeBack} 题`);

// ---- 6. 题号面板：开关、分组、跳转
const sheet1 = await evaluate(`(async () => {
  document.querySelector('#posBtn').click();
  await new Promise(r => setTimeout(r, 260));
  const el = document.querySelector('#sheet');
  const open = el.classList.contains('show');
  const cells = el.querySelectorAll('.qcell').length;
  const total = window.__QUIZ__.questions.length;
  const groups = [...el.querySelectorAll('.qgrid-t')].map(n => n.textContent.trim());
  return { open, cells, total, groups: groups.slice(0, 3), h: Math.round(el.getBoundingClientRect().height) };
})()`);
ok("题号面板可打开且题号齐全", sheet1.open && sheet1.cells === sheet1.total, `${sheet1.cells} 个题号，面板高 ${sheet1.h}px`);

const jump = await evaluate(`(async () => {
  document.querySelector('[data-sheet-scope="type"]').click();
  await new Promise(r => setTimeout(r, 150));
  const cells = [...document.querySelectorAll('.qcell')];
  // 按题型分组后，组内题号应递增；跨组题号会回卷，这是分组本身的结构
  const groups = [...document.querySelectorAll('#sheetBody .qgrid-grp')].map((g) =>
    [...g.querySelectorAll('.qcell')].map((n) => Number(n.textContent.trim()))
  );
  const sorted = groups.every((g) => g.every((v, i) => i === 0 || v > g[i - 1]));
  const total = window.__QUIZ__.questions.length;
  document.querySelector('.qcell[data-goto="' + (total - 1) + '"]').click();
  await new Promise(r => setTimeout(r, 300));
  return {
    sorted,
    cells: cells.length,
    total,
    closed: !document.querySelector('#sheet').classList.contains('show'),
    now: document.querySelector('#posNow').textContent,
    expect: String(total),
    sec: document.querySelector('#crumbSec').textContent,
  };
})()`);
ok("按题型分组后组内题号递增", jump.sorted && jump.cells === jump.total, "");
ok("点题号跳转并关闭面板", jump.closed && jump.now === jump.expect, `跳到第 ${jump.now} 题 · ${jump.sec}`);

// ---- 7. 字号三档
const fs = await evaluate(`(async () => {
  const stem = document.querySelector('.q.active .stem');
  const h = () => parseFloat(getComputedStyle(stem).fontSize);
  const a = h();
  document.querySelector('[data-fs-btn="lg"]').click();
  await new Promise(r => setTimeout(r, 60));
  const b = h();
  document.querySelector('[data-fs-btn="sm"]').click();
  await new Promise(r => setTimeout(r, 60));
  const c = h();
  document.querySelector('[data-fs-btn="md"]').click();
  return { a, b, c, saved: localStorage.getItem('pdfquiz:fs') };
})()`);
ok("字号可调且能记住", fs.b > fs.a && fs.c < fs.a && fs.saved === "md", `标准 ${fs.a} / 大 ${fs.b} / 小 ${fs.c}`);

// ---- 8. 搜索：抽屉里各项不重叠
const drawer = await evaluate(`(async () => {
  document.querySelector('#menuBtn').click();
  await new Promise(r => setTimeout(r, 320));
  const side = document.querySelector('#side');
  const inner = document.querySelector('.chapters');
  return {
    open: side.classList.contains('open'),
    w: Math.round(side.getBoundingClientRect().width),
    // 章节列表若自成滚动区，手机上只能看到几行
    chaptersScrolls: inner.scrollHeight > inner.clientHeight + 4,
  };
})()`);
ok("抽屉适配手机宽度", drawer.open && drawer.w <= 330, "宽 " + drawer.w + "px");
ok("章节列表不再嵌套滚动", drawer.chaptersScrolls === false, "");

ok("无 JS 异常", problems.length === 0, problems.slice(0, 3).join(" | "));

console.log("\n通过 " + results.filter((r) => r.pass).length + "/" + results.length);
ws.close();
process.exit(results.every((r) => r.pass) ? 0 : 1);
