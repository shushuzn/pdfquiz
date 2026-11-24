// 前端功能测试：node functional.mjs <url> [期望题数]
// 直接驱动页面作答，断言判分逻辑与页面无异常。
// 需要本机 Edge/Chrome 带 --remote-debugging-port=9222 启动。
//
// 题库题型不一定齐全（教材卷是翻译类，示例卷是客观题类），
// 所以每组用例先看题库里有没有对应题型，没有就跳过而不是失败。
const [, , url, expectArg] = process.argv;
const EXPECT = expectArg ? Number(expectArg) : null;

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
  if (r.exceptionDetails) throw new Error("JS 异常: " + (r.exceptionDetails.exception?.description || "").slice(0, 300));
  return r.result.value;
};

/* 线上 Pages 偶尔比 readyState 慢半拍：脚本还没执行完就断言会拿不到 __QUIZ__。
   统一等题库和首张题卡都就绪，再开始测试。 */
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
await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 940, deviceScaleFactor: 1, mobile: false });
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
const skip = (name, why) => console.log("– " + name + "  跳过（" + why + "）");

/* 清掉某道题的作答记录并刷新，用于同一道题反复判对/判错。
   进度按题目 id 存，只有老题库才回退到下标。 */
const resetOne = async (idx) => {
  // 页面保存有 120ms 防抖；先等它落盘，否则刚删掉的记录会被旧定时器写回来
  await sleep(250);
  await evaluate(`(() => {
    const k = 'pdfquiz:' + (window.__QUIZ__.meta.id || 'deck');
    const raw = JSON.parse(localStorage.getItem(k) || '{}');
    const q = window.__QUIZ__.questions[${idx}];
    const key = q && q.id ? q.id : String(${idx});
    if (raw.answers) delete raw.answers[key];
    localStorage.setItem(k, JSON.stringify(raw));
  })()`);
  await send("Page.reload");
  await waitQuiz();
  await sleep(250);
};

/* 定位题卡 → 执行作答脚本 → 回读判定结果 */
const answerBy = (idx, js) => evaluate(`(() => {
  const i = ${idx};
  const node = document.querySelector('#stage .q[data-i="'+i+'"]');
  if (!node) return { cls: '', txt: '找不到题卡', granted: false };
  ${js}
  const v = node.querySelector('.verdict');
  return { cls: v.className, txt: v.textContent.trim(), graded: node.classList.contains('graded') };
})()`);

// ---- 1. 题库加载
const meta = await evaluate("({n: window.__QUIZ__.questions.length, types: [...new Set(window.__QUIZ__.questions.map(q=>q.t))]})");
ok("题库加载", meta.n > 0 && (EXPECT === null || meta.n === EXPECT), `题数=${meta.n} 题型=${meta.types.join(",")}`);

const has = (t) => meta.types.includes(t);
const first = (t) => `window.__QUIZ__.questions.findIndex(q=>q.t==='${t}')`;

// ---- 2. 选择题：选对判对、选错判负
if (has("single") || has("truefalse")) {
  const type = has("single") ? "single" : "truefalse";
  const idx = await evaluate(first(type));
  const right = await evaluate(`window.__QUIZ__.questions[${idx}].a[0]`);
  const wrong = await evaluate(`(() => {
    const q = window.__QUIZ__.questions[${idx}];
    const letters = q.t === 'truefalse' ? ['T','F'] : 'ABCDEFGH'.slice(0, q.o.length).split('');
    return letters.find(l => !q.a.includes(l));
  })()`);

  const r1 = await answerBy(idx, `node.querySelector('.opt[data-l="${right}"]').click();`);
  ok("选择题选对判对", /verdict ok/.test(r1.cls), `答案=${right} → ${r1.txt}`);

  await resetOne(idx);
  const r2 = await answerBy(idx, `node.querySelector('.opt[data-l="${wrong}"]').click();`);
  ok("选择题选错判负", /verdict bad/.test(r2.cls), `选 ${wrong} → ${r2.txt}`);
} else {
  skip("选择题判分", "题库无单选题/判断题");
}

// ---- 3a. 释义类术语：中文释义 + 自评，不要求输入英文
const termIdx = has("term") ? await evaluate(first("term")) : -1;
const termMode = termIdx >= 0 ? await evaluate(`window.__QUIZ__.questions[${termIdx}].mode || ""`) : "";
if (termIdx >= 0 && termMode === "explain") {
  const ui = await evaluate(`(() => {
    const node = document.querySelector('#stage .q[data-i="${termIdx}"]');
    const tag = node.querySelector('.tag.t');
    const f = node.querySelector('.field');
    const labels = [...node.querySelectorAll('.ans .k')].map((x) => x.textContent.trim());
    return {
      tag: tag ? tag.textContent.trim() : '',
      input: !!node.querySelector('input'),
      textarea: !!f && f.tagName === 'TEXTAREA',
      placeholder: f ? f.placeholder : '',
      confirm: !!node.querySelector('[data-act="confirm"]'),
      reveal: !!node.querySelector('[data-act="reveal"]'),
      labels,
      hint: (node.querySelector('.q-actions .hint') || {}).textContent || ''
    };
  })()`);
  ok("释义题按中文释义作答", ui.tag === "术语释义" && ui.textarea && !ui.input && !ui.confirm && ui.reveal &&
    /释义/.test(ui.placeholder) && ui.labels.includes("参考释义") && !/英文/.test(ui.hint),
    `标签=${ui.tag} 控件=${ui.input ? "英文输入框" : ui.textarea ? "释义文本框" : "缺失"} 答案项=${ui.labels.join("/")}`);

  // 自己写一句 → 对照参考答案 → 自评掌握
  const self = await evaluate(`(() => {
    const i = ${termIdx};
    const node = document.querySelector('#stage .q[data-i="'+i+'"]');
    const ta = node.querySelector('.field');
    ta.value = '这是我的中文释义';
    ta.dispatchEvent(new Event('input', {bubbles: true}));
    node.querySelector('[data-act="reveal"]').click();
    const pending = {
      cls: node.querySelector('.verdict').className,
      self: !!node.querySelector('.self-grade')
    };
    node.querySelector('[data-self="yes"]').click();
    return {
      pendingCls: pending.cls,
      pendingSelf: pending.self,
      cls: node.querySelector('.verdict').className,
      txt: node.querySelector('.verdict').textContent.trim(),
      redo: !!node.querySelector('[data-act="redo"]'),
      value: (node.querySelector('.field') || {}).value || '',
      selfGone: !node.querySelector('.self-grade')
    };
  })()`);
  ok("释义题对照后自评", /verdict info/.test(self.pendingCls) && self.pendingSelf &&
    /verdict ok/.test(self.cls) && /掌握/.test(self.txt) && self.redo && self.selfGone && self.value === "这是我的中文释义",
    `自评前=${self.pendingCls} 自评后=${self.txt}`);

  const redo = await evaluate(`(() => {
    const i = ${termIdx};
    const node = document.querySelector('#stage .q[data-i="'+i+'"]');
    const b = node.querySelector('[data-act="redo"]');
    if (!b) return { err: '没有重做按钮' };
    b.click();
    const after = document.querySelector('#stage .q[data-i="'+i+'"]');
    const ta = after.querySelector('.field');
    return {
      graded: after.classList.contains('graded'),
      readOnly: !!(ta && ta.readOnly),
      value: ta ? ta.value : 'x',
      textarea: !!ta && ta.tagName === 'TEXTAREA',
      confirm: !!after.querySelector('[data-act="confirm"]'),
      reveal: !!after.querySelector('[data-act="reveal"]')
    };
  })()`);
  await sleep(250);
  const redoKeys = await evaluate(`(() => {
    const raw = JSON.parse(localStorage.getItem('pdfquiz:' + window.__QUIZ__.meta.id) || '{}');
    return { id: window.__QUIZ__.questions[${termIdx}].id, keys: Object.keys(raw.answers || {}) };
  })()`);
  ok("释义题可重做", !redo.err && !redo.graded && !redo.readOnly && redo.value === "" && redo.textarea &&
    !redo.confirm && redo.reveal && !redoKeys.keys.includes(redoKeys.id),
    redo.err || `已判=${redo.graded} 文本框=${redo.textarea} 内容=${redo.value || "空"}`);
}

// ---- 3b. 填空 / 英文术语：精确比对，前缀不算对
const fillType = has("fill") ? "fill" : has("term") && termMode !== "explain" ? "term" : null;
const cn = fillType === "term" ? "术语" : "填空题";
if (fillType) {
  const idx = await evaluate(first(fillType));
  const ans = await evaluate(`window.__QUIZ__.questions[${idx}].a[0]`);

  const r3 = await answerBy(idx, `
    const f = node.querySelector('.field');
    f.value = ${JSON.stringify(ans)};
    f.dispatchEvent(new Event('input', {bubbles:true}));
    node.querySelector('[data-act="confirm"]').click();`);
  ok(cn + "答对判对", /verdict ok/.test(r3.cls), `答案=${ans} → ${r3.txt}`);

  await resetOne(idx);
  const r4 = await answerBy(idx, `
    const f = node.querySelector('.field');
    f.value = 'zzzz';
    f.dispatchEvent(new Event('input', {bubbles:true}));
    node.querySelector('[data-act="confirm"]').click();`);
  ok(cn + "答错判负", /verdict bad/.test(r4.cls), `输入 zzzz → ${r4.txt}`);

  const r5 = await evaluate(`(() => {
    const node = document.querySelector('#stage .q[data-i="${idx}"]');
    const b = node.querySelector('[data-act="redo"]');
    if (!b) return { err: '没有重做按钮' };
    b.click();
    const after = document.querySelector('#stage .q[data-i="${idx}"]');
    const f = after.querySelector('.field');
    return {
      graded: after.classList.contains('graded'),
      readOnly: !!(f && f.readOnly),
      value: f ? f.value : 'x',
      confirm: !!after.querySelector('[data-act="confirm"]')
    };
  })()`);
  ok(cn + "可重做", !r5.err && !r5.graded && !r5.readOnly && r5.value === "" && r5.confirm,
    r5.err || `已判=${r5.graded} 只读=${r5.readOnly} 内容=${r5.value || "空"}`);

  // 截断前缀不能判对：polymer 与 polymerization 的区别
  if (fillType === "term") {
    // 有多个可接受答案（如 "polyethylene / PE"）的题不能拿来做前缀用例：
    // 截断后正好等于另一个合法答案，判对才是对的
    const longIdx = await evaluate(`window.__QUIZ__.questions.findIndex(q=>q.t==='term' && q.a[0].length>=8 && !/[\\/／|｜；;、]/.test(q.a[0]))`);
    if (longIdx >= 0) {
      const p = await answerBy(longIdx, `
        const full = window.__QUIZ__.questions[${longIdx}].a[0];
        const f = node.querySelector('.field');
        f.value = full.slice(0, Math.max(4, full.length - 4));
        f.dispatchEvent(new Event('input', {bubbles:true}));
        node.querySelector('[data-act="confirm"]').click();`);
      const full = await evaluate(`window.__QUIZ__.questions[${longIdx}].a[0]`);
      ok("术语题前缀不判对", /verdict bad/.test(p.cls), `${full} vs 前缀输入`);
    } else {
      skip("术语题前缀不判对", "没有足够长的术语题");
    }
  }
} else {
  skip("填空类判分", has("term") ? "术语题为释义自评" : "题库无填空题/术语题");
}

// ---- 4. 主观题：作答后走自评，自评结果落到统计
const subType = ["trans_en_cn", "trans_cn_en", "describe", "qa", "short"].find(has);
if (subType) {
  const idx = await evaluate(first(subType));
  const r6 = await evaluate(`(() => {
    const i = ${idx};
    const node = document.querySelector('#stage .q[data-i="'+i+'"]');
    const ta = node.querySelector('.field');
    const btn = node.querySelector('[data-act="reveal"]');
    if (!ta || !btn) return { err: '控件缺失 ta=' + !!ta + ' btn=' + !!btn };
    ta.value = '我的作答';
    ta.dispatchEvent(new Event('input', {bubbles:true}));
    btn.click();
    return { txt: node.querySelector('.verdict').textContent.trim(), self: !!node.querySelector('.self-grade') };
  })()`);

  if (r6.err) {
    ok("主观题走自评", false, r6.err);
  } else {
    ok("主观题走自评", r6.self === true, r6.txt);
    const after = await evaluate(`(() => {
      const node = document.querySelector('#stage .q[data-i="${idx}"]');
      node.querySelector('[data-self="yes"]').click();
      return { cls: node.querySelector('.verdict').className, txt: node.querySelector('.verdict').textContent.trim() };
    })()`);
    ok("自评后标记为掌握", /verdict ok/.test(after.cls), after.txt);
  }
} else {
  skip("主观题自评", "题库无主观题");
}

// ---- 5. 统计口径：已完成 = 对 + 错，且与未做相加等于总题数
const stats = await evaluate(`(() => {
  const num = (s) => Number((document.querySelector(s) || {}).textContent || 0);
  const ring = num('#ringNum'), okN = num('#okNum'), badN = num('#badNum'), left = num('#leftNum');
  const n = window.__QUIZ__.questions.length;
  return { ring, okN, badN, left, n, consistent: ring === okN + badN && okN + badN + left === n };
})()`);
ok("统计口径一致", stats.consistent, `已完成 ${stats.ring} = 对 ${stats.okN} + 错 ${stats.badN}，未做 ${stats.left}，共 ${stats.n}`);

// ---- 6. 进度按题目 ID 保存；题库换题后旧下标进度必须自动作废
const allIds = await evaluate("window.__QUIZ__.questions.every(q=>q.id)");
if (allIds) {
  const idx = await evaluate(`(() => {
    const qs = window.__QUIZ__.questions;
    const m = qs.findIndex(q => q.t === 'multiple');
    return m >= 0 ? m : qs.findIndex(q => q.t === 'single' || q.t === 'truefalse');
  })()`);
  if (idx >= 0) {
    await resetOne(idx);
    const q = await evaluate(`window.__QUIZ__.questions[${idx}]`);
    const answerJs = q.t === "multiple"
      ? q.a.map((l) => `node.querySelector('.opt[data-l="${l}"]').click();`).join("") +
        `node.querySelector('[data-act="confirm"]').click();`
      : `node.querySelector('.opt[data-l="${q.a[0]}"]').click();`;

    await answerBy(idx, answerJs);
    await sleep(300);
    const before = await evaluate(`(() => {
      const k = 'pdfquiz:' + window.__QUIZ__.meta.id;
      const raw = JSON.parse(localStorage.getItem(k) || '{}');
      const keys = Object.keys(raw.answers || {});
      return { key: window.__QUIZ__.questions[${idx}].id, keys, numeric: keys.filter(x => /^\\d+$/.test(x)), sig: raw.sig || '' };
    })()`);
    ok("进度按题目 ID 保存", before.keys.includes(before.key) && before.numeric.length === 0 && !!before.sig,
      `键=${before.keys.join(",") || "空"} 签名=${before.sig || "无"}`);

    // 伪造一份旧版进度：数组下标当键、没有签名
    await evaluate(`(() => {
      const k = 'pdfquiz:' + window.__QUIZ__.meta.id;
      const raw = JSON.parse(localStorage.getItem(k) || '{}');
      raw.answers = { '0': { picked: ['A'], graded: true } };
      raw.marked = [0];
      raw.sig = 'stale';
      localStorage.setItem(k, JSON.stringify(raw));
    })()`);
    await send("Page.reload");
    await waitQuiz();
    await sleep(1000);

    const after = await evaluate(`(() => {
      const k = 'pdfquiz:' + window.__QUIZ__.meta.id;
      const raw = JSON.parse(localStorage.getItem(k) || '{}');
      const t = document.querySelector('#toast');
      return {
        keys: Object.keys(raw.answers || {}),
        marked: raw.marked || [],
        sig: raw.sig || '',
        toast: t && t.classList.contains('show') ? t.textContent.trim() : ''
      };
    })()`);
    ok("旧下标进度自动作废", after.keys.length === 0 && after.marked.length === 0 && after.sig === before.sig,
      `答案=${after.keys.length} 标记=${after.marked.length} 提示=${after.toast || "无"}`);

    const r = await answerBy(idx, answerJs);
    ok("作废后可重新作答", /verdict ok/.test(r.cls), r.txt);

    // 只是增删了题目时，能对上 ID 的记录应保留，只有下标记录被清掉
    await sleep(300);
    await evaluate(`(() => {
      const k = 'pdfquiz:' + window.__QUIZ__.meta.id;
      const raw = JSON.parse(localStorage.getItem(k) || '{}');
      raw.answers['0'] = { picked: ['A'], graded: true };
      raw.marked = [0];
      raw.sig = 'stale';
      localStorage.setItem(k, JSON.stringify(raw));
    })()`);
    await send("Page.reload");
    await waitQuiz();
    await sleep(1000);
    // 跳到这道题，让卡片进入已判定态（不同卷子第一题不一定是多选）
    await evaluate("document.querySelector('#posBtn').click()");
    await sleep(150);
    await evaluate(`(() => {
      const c = document.querySelector('[data-goto="${idx}"]');
      if (c) c.click();
    })()`);
    await sleep(250);
    const mixed = await evaluate(`(() => {
      const k = 'pdfquiz:' + window.__QUIZ__.meta.id;
      const raw = JSON.parse(localStorage.getItem(k) || '{}');
      const node = document.querySelector('#stage .q[data-i="${idx}"]');
      const t = document.querySelector('#toast');
      return {
        key: window.__QUIZ__.questions[${idx}].id,
        keys: Object.keys(raw.answers || {}),
        marked: raw.marked || [],
        sig: raw.sig || '',
        graded: node ? node.classList.contains('graded') : false,
        toast: t ? t.textContent.trim() : ''
      };
    })()`);
    ok("换库保留有效记录", mixed.keys.includes(mixed.key) && !mixed.keys.includes("0") &&
      mixed.marked.length === 0 && mixed.sig === before.sig && mixed.graded && mixed.toast.includes("保留"),
      `键=${mixed.keys.join(",")} 标记=${mixed.marked.length} 提示=${mixed.toast || "无"}`);

    const hasRedo = await evaluate(`!!document.querySelector('#stage .q[data-i="${idx}"] [data-act="redo"]')`);
    await evaluate(`(() => {
      const b = document.querySelector('#stage .q[data-i="${idx}"] [data-act="redo"]');
      if (b) b.click();
    })()`);
    await sleep(300);
    const redone = await evaluate(`(() => {
      const raw = JSON.parse(localStorage.getItem('pdfquiz:' + window.__QUIZ__.meta.id) || '{}');
      const node = document.querySelector('#stage .q[data-i="${idx}"]');
      return {
        graded: node ? node.classList.contains('graded') : true,
        confirm: !!(node && node.querySelector('[data-act="confirm"]')),
        keys: Object.keys(raw.answers || {})
      };
    })()`);
    ok("可单题重做", hasRedo && !redone.graded && redone.confirm && !redone.keys.includes(mixed.key),
      `按钮=${hasRedo} 已判=${redone.graded} 确认键=${redone.confirm}`);

    const r3 = await answerBy(idx, answerJs);
    ok("重做后可再次提交", /verdict ok/.test(r3.cls), r3.txt);

    // 同一 ID 但题目内容改过：记录里的指纹对不上，旧作答必须失效
    await sleep(300);
    const fpBefore = await evaluate(`(() => {
      const k = 'pdfquiz:' + window.__QUIZ__.meta.id;
      const raw = JSON.parse(localStorage.getItem(k) || '{}');
      const key = window.__QUIZ__.questions[${idx}].id;
      const rec = (raw.answers || {})[key] || {};
      if (rec.fp) rec.fp = 'stale';
      localStorage.setItem(k, JSON.stringify(raw));
      return { key, has: !!raw.answers[key], fp: typeof rec.fp };
    })()`);
    await send("Page.reload");
    await waitQuiz();
    await sleep(1000);
    await evaluate("document.querySelector('#posBtn').click()");
    await sleep(150);
    await evaluate(`(() => {
      const c = document.querySelector('[data-goto="${idx}"]');
      if (c) c.click();
    })()`);
    await sleep(250);
    const fpStale = await evaluate(`(() => {
      const k = 'pdfquiz:' + window.__QUIZ__.meta.id;
      const raw = JSON.parse(localStorage.getItem(k) || '{}');
      const node = document.querySelector('#stage .q[data-i="${idx}"]');
      const t = document.querySelector('#toast');
      return {
        key: window.__QUIZ__.questions[${idx}].id,
        kept: !!(raw.answers || {})[window.__QUIZ__.questions[${idx}].id],
        sig: raw.sig || '',
        graded: node ? node.classList.contains('graded') : true,
        toast: t ? t.textContent.trim() : ''
      };
    })()`);
    ok("题目改动后旧作答失效", fpBefore.has && !fpStale.kept && fpStale.sig === before.sig &&
      !fpStale.graded && fpStale.toast.includes("改动"), `保留=${fpStale.kept} 已判=${fpStale.graded}`);

    // 老记录没有指纹时只补指纹，不当作改题，作答继续有效
    const r4 = await answerBy(idx, answerJs);
    await sleep(300);
    await evaluate(`(() => {
      const k = 'pdfquiz:' + window.__QUIZ__.meta.id;
      const raw = JSON.parse(localStorage.getItem(k) || '{}');
      const key = window.__QUIZ__.questions[${idx}].id;
      if (raw.answers[key]) delete raw.answers[key].fp;
      localStorage.setItem(k, JSON.stringify(raw));
    })()`);
    await send("Page.reload");
    await waitQuiz();
    await sleep(1000);
    await evaluate("document.querySelector('#posBtn').click()");
    await sleep(150);
    await evaluate(`(() => {
      const c = document.querySelector('[data-goto="${idx}"]');
      if (c) c.click();
    })()`);
    await sleep(250);
    const fpBackfill = await evaluate(`(() => {
      const k = 'pdfquiz:' + window.__QUIZ__.meta.id;
      const raw = JSON.parse(localStorage.getItem(k) || '{}');
      const rec = (raw.answers || {})[window.__QUIZ__.questions[${idx}].id] || {};
      const node = document.querySelector('#stage .q[data-i="${idx}"]');
      const v = node ? node.querySelector('.verdict') : null;
      return { graded: !!v && /verdict ok/.test(v.className), fp: typeof rec.fp, present: 'fp' in rec };
    })()`);
    ok("缺指纹的老记录保留并补齐", /verdict ok/.test(r4.cls) && fpBackfill.graded && fpBackfill.present && fpBackfill.fp === "string",
      `作答=${r4.txt} 已判=${fpBackfill.graded} 指纹=${fpBackfill.fp}`);
  } else {
    skip("进度存储", "题库无单选题/多选题");
  }
} else {
  skip("进度存储", "题库未带题目 ID");
}

// ---- 7. JS 无异常
ok("无 JS 异常", problems.length === 0, problems.slice(0, 3).join(" | "));

console.log("\n通过 " + results.filter((r) => r.pass).length + "/" + results.length);
ws.close();
process.exit(results.every((r) => r.pass) ? 0 : 1);
