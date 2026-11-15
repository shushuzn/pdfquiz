// 首屏性能探针：node perf.mjs <url> [宽] [高]
// 输出 DOM 节点数、DOMContentLoaded 耗时、脚本执行耗时。用来判断大字库是否卡顿。
const [, , url, w = 390, h = 844] = process.argv;
const list = await (await fetch("http://127.0.0.1:9222/json/list")).json();
const page = list.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();
await new Promise((r) => (ws.onopen = r));
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) {
    const { res, rej } = pending.get(m.id);
    pending.delete(m.id);
    m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result);
  }
};
const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const i = ++id;
    pending.set(i, { res, rej });
    ws.send(JSON.stringify({ id: i, method, params }));
  });

await send("Page.enable");
await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", {
  width: +w, height: +h, deviceScaleFactor: 2, mobile: +w < 700,
});
await send("Page.navigate", { url });
await new Promise((r) => setTimeout(r, 1200));

const r = await send("Runtime.evaluate", {
  expression: `(() => {
    const nav = performance.getEntriesByType("navigation")[0] || {};
    return JSON.stringify({
      nodes: document.querySelectorAll("*").length,
      qnodes: document.querySelectorAll("#stage .q").length,
      dcl: Math.round(nav.domContentLoadedEventEnd || 0),
      load: Math.round(nav.loadEventEnd || 0),
      msgs: (window.__QUIZ__ ? window.__QUIZ__.questions.length : 0)
    });
  })()`,
  returnByValue: true,
});
console.log(r.result.value);
ws.close();
