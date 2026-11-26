# 教材例题插图整理说明

「例题精解」页里的教材插图裁自扫描原页，按例题的 `figure` 字段内嵌显示。
新增插图或重裁时按本文操作；图片只用于阅读页，不参与题库。

## 数据位置

- 图片：`papers_hgyl/examples/figures/chNN-figX-YY.webp`
- 索引：`papers_hgyl/examples/figures/chNN.json`

索引格式：

```json
{
  "schema": 1,
  "chapter": "第1章 流体流动与输送机械",
  "figures": {
    "图1-8": {
      "file": "ch01-fig1-08.webp",
      "page": "P13",
      "width": 510,
      "height": 532
    }
  }
}
```

- 键必须与例题 JSON 的 `figure` 字段逐字一致，包括 `图6-32(a)(b)` 这种写法。
- `page` 是插图实际所在的**印刷页码**，不一定等于例题起始页。
- `width` / `height` 是实际保存的像素尺寸。

## 找图与裁剪

源文件：`/uploads/file_00wigxg2zzrb438iuqly-14857141.pdf`，435 页扫描版。
**PDF 页码 = 印刷页码 + 9**。

1. 在例题起始页前后几页找图题「图 x-y」。可以先把候选页渲染出来用 Read 看，
   也可以 OCR 辅助：

   ```bash
   pdftoppm -f 22 -l 24 -r 300 -png PDF /tmp/fig_ch01/p
   tesseract /tmp/fig_ch01/p-022.png stdout -l chi_sim --psm 6 2>/dev/null | grep "图 1-8"
   ```

2. 确认图题所在页后，用 300 dpi 渲染该页：

   ```bash
   pdftoppm -f 22 -l 22 -r 300 -png PDF /tmp/fig_ch01/hi
   python3 -c "from PIL import Image; print(Image.open('/tmp/fig_ch01/hi-022.png').size)"
   ```

3. 估算插图外框（像素），用统一脚本裁剪、去白边、转 WebP：

   ```bash
   python3 tools/crop_figure.py \
     --page /tmp/fig_ch01/hi-022.png \
     --box 930,520,2040,1000 \
     --out papers_hgyl/examples/figures/ch01-fig1-08.webp \
     --page-ref P13
   ```

   脚本会输出一行 JSON（含 width/height），直接抄进索引。

4. 用 Read 打开生成的 webp 检查：
   - 必须完整：坐标轴、刻度、图内标注、箭头、图例都要在；
   - 不能带正文段落、图题、相邻插图；
   - 不能裁掉边缘文字；四周留一点白边即可。

   不合格就调整 `--box` 重裁。宁可多留 10 像素白边，也不要裁掉标注。

5. 写 `figures/chNN.json`，键齐全。

## 硬性要求

- 只写 `papers_hgyl/examples/figures/` 下本章的图片和 `chNN.json`；
  不改例题 JSON、tools、docs、其他章节，不跑 git。
- 一图一文件，不共用。文件名全小写，图号补零：`图1-8` → `ch01-fig1-08.webp`；
  `图6-32(a)(b)` → `ch06-fig6-32ab.webp`。
- 保存宽度不超过 720px（脚本自动缩放），WebP 质量 82。
- 图片背景保持白色，不要抠图、不要加滤镜。
- 页码必须是图题实际所在页，不是猜的。

## 校验

```bash
python3 tools/check_figures.py ch01
```

必须输出「索引、文件、页码、尺寸通过」。最后一行是「共 N 张，全部通过」。