// 批量截图：node shots.mjs <url> <plan.json>
// plan: [{ name, w, h, mobile, js, wait, url }]，url 可逐项覆盖
const [, , url, planPath] = process.argv;
const fs = await import("node:fs/promises");

const plan = JSON.parse(await fs.readFile(planPath, "utf8"));
const created = await fetch(`http://127.0.0.1:9222/json/new?about:blank`, { method: "PUT" }).then((r) => r.json());
const ws = new WebSocket(created.webSocketDebuggerUrl);
await new Promise((res) => (ws.onopen = res));

let seq = 0;
const pending = new Map();
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
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

await send("Page.enable");
await send("Runtime.enable");

for (const item of plan) {
  await send("Emulation.setDeviceMetricsOverride", {
    width: item.w || 1440,
    height: item.h || 940,
    deviceScaleFactor: item.dpr || 1,
    mobile: !!item.mobile,
  });
  await send("Page.navigate", { url: (item.url || url) + (item.hash || "") });
  for (let i = 0; i < 60; i++) {
    const st = await send("Runtime.evaluate", { expression: "document.readyState", returnByValue: true });
    if (st.result.value === "complete") break;
    await new Promise((r) => setTimeout(r, 100));
  }
  await new Promise((r) => setTimeout(r, 450));

  if (item.clear !== false) {
    await send("Runtime.evaluate", { expression: "localStorage.clear()" });
    await send("Page.reload");
    await new Promise((r) => setTimeout(r, 700));
  }

  if (item.js) {
    const r = await send("Runtime.evaluate", { expression: item.js, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) console.error(item.name, "JS 异常:", JSON.stringify(r.exceptionDetails).slice(0, 300));
    await new Promise((r) => setTimeout(r, item.wait || 450));
  }

  const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await fs.writeFile(item.name + ".png", Buffer.from(shot.data, "base64"));
  console.log("✓", item.name + ".png");
}

ws.close();
await fetch(`http://127.0.0.1:9222/json/close/${created.id}`);
process.exit(0);
