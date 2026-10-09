# `examples/unrelated/` — 与本工具无关的历史产物

这里放的是**三个不属于 concept-animator 的文件**，原本混在 `output/` 里。
它们是在做「图表怎么画」的技术选型时留下的试验页，不是 `concept_animator.cli render`
的产物，也不被仓库里任何代码引用。

把它们从 `output/` 移出来，只为一个原因：**`output/` 应该只放这个工具能生成的东西**。
混在一起会让人误判本工具的产出形态——尤其是下面两个页面**必须联网**才能显示，
而 concept-animator 的核心卖点恰恰是「零依赖、单文件、离线可用」。

| 文件 | 字节 | 是什么 | 联网？ |
|---|---|---|---|
| `viz_compare.html` | 5,198 | 从 CDN 加载 **ECharts 5 + echarts-gl 2 + Plotly 2.32**（`cdn.jsdelivr.net` / `cdn.plot.ly`），对比同一组数据的三种渲染（折线 / 柱状 / 3D 曲面）。标题「可视化方案效果对比 · 同一数据三种渲染」 | ⚠️ 需要（3 个 CDN 脚本） |
| `plotly_py_demo.html` | 70,598 | Plotly 生成的图表页，从 CDN 加载 **Plotly 3.7.0**；页面**没有 `<title>` 元素** | ⚠️ 需要（1 个 CDN 脚本） |
| `token-knowledge-map-integrated.html` | 61,622 | 手工制作的另一份讲解页（「Token 生成机制 · 可视化知识包」），和本工具的技术栈无关；无外部脚本 | 否（只有一个 SVG 命名空间 URI，不是网络请求） |

（"联网？"一列是实测的：对三个文件抽出所有 `http(s)://` 引用再看是不是运行时脚本。）

## 为什么保留而不是删掉

`viz_compare.html` 是**「最后为什么选内联 SVG 而不是图表库」这个设计决策的原始证据**：

- 用 ECharts / Plotly 的代价是：产物依赖 CDN（离线打不开）、多一个几百 KB 的运行时、
  和「一张 A4 纸级别的概念讲解页」的体量完全不匹配；
- 而 concept-animator 的 `chart` 块最终是**手写的内联 SVG**——
  `chartSVG()` 直接拼 `<svg class="chart-svg" viewBox="0 0 W H">` +
  `<polyline>` / `<rect>`（`concept_animator/render.py:651-691`），
  整个 `HTML_TEMPLATE` 里**一个 `http(s)://` 都没有**（实测）。
  换来的正是本工具最强的那个属性：生成出来的 HTML 断网、断服务器、双击就能看。

留在这里既是证据，又不会污染 `output/`。
需要清理时，删掉整个目录即可——不影响任何代码路径。
