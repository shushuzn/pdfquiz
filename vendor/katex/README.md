# KaTeX（ vendored ）

页面公式排版用的 [KaTeX](https://katex.org/)，版本 **0.16.11**，许可证 **MIT**（见 `LICENSE`，版权归 Khan Academy 及贡献者）。

## 文件

| 文件 | 说明 |
|---|---|
| `katex.min.js` | 官方 dist 原样，未改动。构建时内嵌进例题页，浏览器里调 `katex.renderToString()` |
| `katex.inline.css` | 官方 `katex.min.css` 的改写版：每个 `@fontface` 的 `src:url(fonts/X.woff2) …` 换成单条 base64 data URI |
| `LICENSE` | 随官方 npm 包一起发布的 MIT 授权原文 |

这里**没有** `fonts/` 目录——字体已经打进 CSS，页面因此不需要任何外部请求，断网、`file://` 直接打开都能正常排版。

## 为什么用 HTML 输出而不是 MathML

沙箱里试过 MathML 输出：Chromium 的 MathML 支持依赖系统 MathJax/CoreText 字体，缺字体时整页公式渲染成豆腐块。HTML 输出 + 内联 woff2 是自包含的，且和 KaTeX 官方站点默认行为一致。

## 重新生成

升级 KaTeX 版本时：

```bash
npm pack katex@0.16.11                  # 得到 katex-0.16.11.tgz
tar -xzf katex-0.16.11.tgz              # 解出 package/dist/
cp package/dist/katex.min.js vendor/katex/katex.min.js
cp package/dist/LICENSE    vendor/katex/LICENSE
python tools/make_katex_css.py package/dist   # 重写 vendor/katex/katex.inline.css
```

`tools/make_katex_css.py` 只吃一个参数（KaTeX dist 目录），输出路径固定在 `vendor/katex/katex.inline.css`；任何一条 `url(...)` 还没变成 `data:` 时它直接报错退出，所以不用担心漏掉某个字体又让页面去请求外部文件。woff/ttf 兜底会被丢掉——现代浏览器全都支持 woff2，留着只会让文件翻倍。

改完之后务必重跑：

```bash
python -m unittest tests.test_examples   # 断言页面里没有外链、字体已内联
python tools/build_examples.py
```
