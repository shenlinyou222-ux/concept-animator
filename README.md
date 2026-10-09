# concept-animator — 概念树 → 自包含 HTML 动画讲解页

把一棵**概念树 JSON** 渲染成一个**单文件 HTML 动画讲解页**：
黑底白字、按节点翻页、点击子节点跳转、集合论关系用图形而非文字表达。

工具链本身**零第三方依赖**——只用 Python 标准库（`urllib` / `json` / `dataclasses` / `base64`）。
`media/` 里的 Manim 视频是可选的增强项，不是运行前提。

```
概念树 JSON ──render──▶ 单文件 HTML（内联 JSON + 内联 CSS/JS + 可选的 base64 内联 mp4）
     ▲
     ├── build ── LLM 广度优先遍历（节点是原语则终止）
     └── infer ── 集合论 / 时序关系的传递闭包推导
```

---

## 1. 快速开始

### 1.1 一个必须先说的坑：目录名

仓库目录叫 `concept-animator`，**连字符不是合法的 Python 包名字符**。
所以任何 `python -m concept_animator.xxx` 都**跑不起来**。

```
$ python -m concept_animator.cli demo --output output/demo.html
ModuleNotFoundError: No module named 'concept_animator'
```

而 `cli.py` / `builder.py` / `render.py` 用的全是相对导入（`from .builder import ...`），
所以也不能直接把目录当 flat 模块树导入：

```
$ python -c "import sys; sys.path.insert(0, r'.../concept-animator'); import cli"
ImportError: attempted relative import with no known parent package
```

**当前唯一可行的跑法**是把目录改/软链成合法的包名（下划线），然后从父目录以包方式运行：

```powershell
# 在克隆到的父目录里建一个下划线别名（Windows）
New-Item -ItemType Junction -Path .\concept_animator -Target .\concept-animator

python -m concept_animator.cli demo   --output output/demo.html
python -m concept_animator.cli verify --input concept_animator/sample_tree.json
python -m concept_animator.cli render --input concept_animator/sample_tree.json --output output/my.html
python -m concept_animator.cli infer  --input concept_animator/sample_tree.json --output output/sample_inferred.json
```

```bash
# Linux / macOS
ln -s concept-animator concept_animator
```

或者干脆**把目录重命名为 `concept_animator`**——这也是最干净的做法，
本 README 下面的命令一律用 `concept_animator.` 前缀。

### 1.2 四个子命令

| 命令 | 输入 | 输出 |
|---|---|---|
| `demo` | 内置 `sample_tree.json` | HTML |
| `verify` | 树 JSON | 打印 `OK: <name>, nodes=N, leaves=M`（顺带做全树校验） |
| `infer` | 树 JSON | 加了传递闭包关系的树 JSON |
| `render` | 树 JSON | HTML |
| `build` | `--topic`（可加 `--doc`） | 树 JSON（可加 `--render` 直接出 HTML） |

`verify` 的实际输出（本机 Python 3.12 实测）：

```
$ python -m concept_animator.cli verify --input concept_animator/sample_tree.json
OK: 机器学习, nodes=18, leaves=14
$ python -m concept_animator.cli verify --input concept_animator/photosynthesis_tree.json
OK: 光合作用, nodes=22, leaves=19
$ python -m concept_animator.cli verify --input concept_animator/blocks_demo_tree.json
OK: 梯度下降, nodes=5, leaves=3
$ python -m concept_animator.cli verify --input concept_animator/hopsoncraft_v2.json
OK: HopsonCraft 体素引擎, nodes=26, leaves=17
```

### 1.3 LLM 构建（可选）

`build` 需要 OpenAI 兼容端点，配置走环境变量：

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://api.openai.com/v1"   # 默认值
export OPENAI_MODEL="gpt-4o-mini"                     # 默认值

python -m concept_animator.cli build \
  --topic "光合作用" \
  --output output/photosynthesis.json \
  --max-depth 5 \
  --render output/photosynthesis.html
```

`--doc source.md` 会把源文档前 6000 字符塞进提示词（`llm_client.py:195`），
让模型**基于文档讲解并逐字引用**，而不是自由发挥。
`cli.py` 解码文档时依次尝试 `utf-8` / `utf-8-sig` / `gb18030`（`cli.py:74`）。

---

## 2. 核心机制

### 2.1 遍历终止条件：原语

LLM 遍历（`builder.py::ConceptBuilder.build`）是一个 **BFS**（`collections.deque`），
不是 DFS。每个出队的节点调一次 `_ask_llm`，把返回的 `subconcepts` 挂成子节点，
非原语的子节点入队。

终止条件是这套设计里唯一的硬概念：

```
is_primitive = true  →  不再展开
primitive_kind ∈ {"physical", "math"}
```

- `physical`：真实的物理实体
- `math`：简单的数学抽象（函数、集合、矩阵、向量、公式、算法……）

`_apply_result` 里还有两条防跑偏机制：

1. **重复概念当引用节点终止**：`child_name in seen` → 强制 `is_primitive = true`、
   `primitive_kind = "math"`，summary 追加「（已在上文出现，作为引用节点终止）」（`builder.py:154-158`）。
   这是为了**保证落盘的结构真的是树**，不是图。
2. **深度预算兜底**：`depth >= max_depth` 时走 `_expand_with_budget_fallback`——
   再问一次模型，仍不原语的子节点直接标成原语，summary 追加「（达到深度上限，按终止原语处理）」（`builder.py:202-217`）。

`test_concept_animator.py` 用 `FakeLLM` 精确验证了这条路径：
`ConceptBuilder(fake, max_depth=3).build("A")` 必须**只调用模型 2 次**
（`self.assertEqual(fake.calls, 2)`），且所有叶子节点都是带 `primitive_kind` 的原语。

### 2.2 集合论 / 时序关系的传递闭包

`inference.py::infer_tree` 对每个节点推导出**蕴含但没被显式声明**的关系：

- `subset_of` 的传递闭包：`A ⊆ B` 且 `B ⊆ C` ⟹ `A ⊆ C`
- `superset_of` 反向后并入 `subset_of`：`A ⊇ B` ⟹ `B ⊆ A`，再求闭包
- 时序关系的传递闭包：`A before B` 且 `B before C` ⟹ `A before C`

闭包用 BFS 实现（`_transitive_closure`），并对每个源点去重，所以不会产生重复边。
推导出来的关系会带 `note` 标注来源：`"由集合论传递闭包推导"` /
`"由 superset_of 反向后传递推导"` / `"由时间先后关系传递推导"`。

**实测效果**（本机跑 `infer` 前后对比）：

| 树 | 节点 | 集合关系（前→后） | 时序关系（前→后） |
|---|---|---|---|
| `sample_tree.json` | 18 | 10 → **14** | 7 → **11** |
| `hopsoncraft_v2.json` | 26 | 10 → **19** | 3 → 3（自由文本的 before/after 都是中文，`__init__` 的推导要求首尾都在本节点的名字集合里，所以没命中） |

第二行的反面结果值得记：**推导不是万能的**，LLM 生成的中文关系名对不上节点名时，
闭包就一条都推不出来。这是设计上的保守选择（宁可少推，不推错），但也意味着
"LLM 写的引用名"必须和"子节点名"对齐才有用。

### 2.3 渲染：单文件 HTML

`render.py` 的结构很直白：

```python
HTML_TEMPLATE = r"""<!DOCTYPE html> ... """   # render.py:23-1074，一个 1000+ 行的 raw 字符串
def render_html(tree):  _embed_videos(tree); return HTML_TEMPLATE.replace("__TITLE__", ...).replace("__TREE_JSON__", ...)
def render_to_file(tree, path):  ...
```

产物是**单个 HTML 文件**，没有任何外部依赖（不引 CDN、不引 `.js`/`.css`）：

- 整棵树的 JSON 直接内联进 `<script>`（`TREE = {...}`），页面不 fetch 任何东西
- CSS + JS 全在 `<style>` / `<script>` 里
- `video` 块的 mp4 会被 base64 内联（见 §2.5）

页面结构（对应 `docs` 里那份"渲染规则"）：

| 区域 | 行为 |
|---|---|
| 顶部 | 当前节点 + 祖先链；相邻父节点在左，根/祖父在最右，灰色、无解释 |
| 中部 | 当前节点的 `summary` / `explanation` 句子 / 对比概念（橙色实底框）/ 表达块 |
| 右侧列 | `formula` 类型块被**单独抽出来**放右栏（`render.py:757-760`），标题「公式与状态方程」 |
| 底部 | 子节点框：`is_primitive` 走 `.child-box.entity`（实线），否则 `.child-box.abstract`（虚线），并带 `type-tag`（数学原语 / 物理实体 / 待展开概念） |
| 下方 | SVG 关系图（`viewBox="0 0 1600 800"`），集合论关系用「大图形包含/相交/相离」表达 |
| 底部进度条 | `currentIndex + 1 / order.length` |

交互：

- 左右方向键切换节点，空格播放/暂停（自动按 `order` 顺序翻页）
- 每个节点可点击 → `goToId(node.id)` → 写 URL hash（`history.replaceState` + `hashchange` 监听），
  所以**可以深链到某个概念**（`页面.html#节点id`）
- 子节点框可点击跳转
- 切页有 `fade-swap` CSS 动画（靠 `void lecture.offsetWidth` 强制重排来重启动画）

### 2.4 表达块（10 种类型）

每个节点除了句子式讲解，还能带类型化的 `blocks`。`schema.py::BLOCK_TYPES` 是唯一白名单，
`ConceptNode.validate()` 会对每个 block 检查 `type` 是否在里面，不在就抛 `ValueError`。

| type | 字段 | 渲染为 |
|---|---|---|
| `formula` | `text`, `caption?` | 数学衬线体，**被抽到右栏** |
| `analogy` | `text` | 「类比」标签块 |
| `example` | `title?`, `text` | 「例子」块 |
| `quote` | `text`, `source?` | 「原文引用」块（讲文档时溯源用） |
| `callout` | `text`, `tone: warn\|key` | 标签随 tone 变「注意」/「关键点」 |
| `steps` | `items: []` | `<ol class="steps">` 编号时间线 |
| `table` | `columns`, `rows` | `<table class="block-table">` |
| `chart` | `chart: bar\|line`, `title?`, `unit?`, `data:[{label,value}]` | **内联 SVG**（`viewBox` 0 0 W H，无图表库） |
| `quiz` | `question`, `answer`, `hint?` | 点击揭晓的自测问答 |
| `video` | `src`, `caption?` | `<video controls autoplay loop muted playsinline>` |

`builder.py` 限制每节点最多 6 个块（`[:6]`），系统提示词要求每个节点至少 1 个、最多 4 个。

### 2.5 视频内联：单文件产物的代价

`_embed_videos`（`render.py:1077-1091`）会把 `video` 块的 `src` 从文件路径换成
`data:video/mp4;base64,...`，让 HTML 保持单文件。搜索路径依次是
`block["src"]` 和 `os.path.join(包目录, block["src"])`。

代价是**体积**。实测 `output/hopsoncraft_by_llm.html`：

| 项 | 值 |
|---|---|
| 文件总字节 | 1,311,123 |
| 其中 base64 视频载荷字符数 | 1,245,176 |
| 占比 | **95%** |
| 内联的 mp4 个数 | 4 |

也就是说这个 1.25 MB 的页面里，**只有约 65 KB 是文字/结构/样式/脚本**，其余全是 4 个
Manim 动画视频。这是一个明确的取舍：可离线单文件分发，代价是体积和"改一个公式要重生成整页"。

---

## 3. 目录与产物

```
concept-animator/
├── schema.py                 数据模型 + JSON 读/写/校验（191 行）
├── llm_client.py             零依赖 OpenAI 兼容 JSON 客户端 + 提示词（207 行）
├── builder.py                LLM BFS 遍历构建概念树（217 行）
├── inference.py              集合论 / 时序传递闭包推导（139 行）
├── render.py                 单文件 HTML 渲染器（1109 行，最大文件）
├── cli.py                    5 个子命令（135 行）
├── test_concept_animator.py  5 个 unittest 用例（111 行）
├── manim_scene.py            Manim CE 场景：SectionSigma / LoadFactor（82 行）
├── manim_scene2.py           Manim CE 场景：HashProbe / MeshVsRaymarch（92 行）
├── sample_tree.json          机器学习示例树（18 节点）
├── photosynthesis_tree.json  光合作用示例树（22 节点）
├── blocks_demo_tree.json     表达块演示树（5 节点 / 12 块）
├── hopsoncraft_v2.json       体素引擎源码走读树（26 节点 / 57 块，含 4 个视频）
├── output/                   13 个文件，约 1.63 MB
└── media/                    102 个文件，约 2.41 MB
```

### `output/` 里到底有什么

全是 **HTML**（13 个文件），没有图片、没有视频。按来源分三类：

| 文件 | 字节 | 来源 |
|---|---|---|
| `demo.html` | 31,777 | `cli demo` |
| `photosynthesis.html` | 34,152 | `cli render` |
| `blocks_demo.html` | 37,085 | `cli render` |
| `hopsoncraft.html` | 37,809 | `cli render` |
| `sample_inferred.html` | 30,555 | `cli render`（输入是 infer 的产物） |
| `hopsoncraft_by_llm.html` | 1,311,123 | `cli render`（内联 4 个 mp4） |
| `hopsoncraft_tree.json` | 6,432 | `cli build` 的树（6 节点 / 3 块） |
| `hopsoncraft_by_llm_inferred.json` | 51,459 | `cli infer` 的产物（26 节点） |
| `photosynthesis_inferred.json` | 14,845 | `cli infer` 的产物（22 节点） |
| `sample_inferred.json` | 12,998 | `cli infer` 的产物（18 节点） |
| `plotly_py_demo.html` | 70,598 | **不是本工具的产物**（见下） |
| `token-knowledge-map-integrated.html` | 61,622 | **不是本工具的产物**（见下） |
| `viz_compare.html` | 5,198 | **不是本工具的产物**（见下） |

后三个我核对过内容，它们是**另外做的可视化方案试验遗留**，不是 `cli render` 的输出：

- `viz_compare.html`：从 CDN 加载 **ECharts 5 + echarts-gl 2 + Plotly 2.32**，
  对比「同一数据三种渲染」（折线 / 柱状 / 3D 曲面）。页面自己写着"需联网加载 CDN"。
- `plotly_py_demo.html`：Plotly 产物，`<title>` 是空的。
- `token-knowledge-map-integrated.html`：标题「Token 生成机制 · 可视化知识包」，
  手工制作的另一份讲解页。

它们既不在 `.gitignore` 的排除范围内，也不被任何代码引用。
**把这三个文件混在 `output/` 里会让人误判工具的产出形态**，建议移到 `experiments/` 或删掉。

### `media/` 里到底有什么

102 个文件，约 2.41 MB。这是 **Manim CE 的渲染中间产物和成品**，不是本工具自己生成的：

| 子目录 | 内容 |
|---|---|
| `media/videos/manim_scene/480p15/` | `SectionSigma.mp4`（370,893 B）、`LoadFactor.mp4`（139,458 B）+ 分片 |
| `media/videos/manim_scene2/480p15/` | `HashProbe.mp4`（220,239 B）、`MeshVsRaymarch.mp4`（203,291 B）+ 分片 |
| `media/Tex/` | MathTex 的 `.tex` / `.svg` / `.aux` / `.log`（LaTeX 编译缓存） |
| `media/texts/` | Manim `Text` 对象转出的 `.svg`（43 个） |

`media/` 里的 4 个 mp4 正是 `hopsoncraft_v2.json` 里 4 个 `video` 块引用的文件
（路径形如 `media/videos/manim_scene/480p15/SectionSigma.mp4`），
也是 `hopsoncraft_by_llm.html` 里被 base64 内联的那 4 个。

Manim 的两个场景脚本与概念树的对应关系（读代码确认）：

| 场景 | 讲的什么 | 被哪个节点用 |
|---|---|---|
| `SectionSigma` | `σ(x,y,z) = x + 16(y + 16z)`，3D 体素坐标 → 1D 偏移的双射 | `hopsoncraft_v2.json` 第 188 行 |
| `LoadFactor` | `α = n/m`，`E[探测] ≈ 1/(1−α)` 曲线发散，标出扩容阈值 α₀≈0.7 和"危险区 α>0.85" | 第 530 行 |
| `HashProbe` | `h(cx,cz) → 桶 i`，开放寻址探测序列，结尾点出鸽笼原理 | 第 397 行 |
| `MeshVsRaymarch` | 渲染范式对比：CPU 建 mesh 上传 vs GPU 直接走射线 | 第 722 行 |

`manim_scene2.py` 的最后一帧文案是「MeshBuilder 整体删除 —— 范式更换，不是优化」——
这暗示视频是从另一个项目（HopsonCraft 体素引擎）的源码走读里抽出来的，
`hopsoncraft.html` 的标题就是「HopsonCraft 体素引擎源码走读」。

---

## 4. 测试

`test_concept_animator.py` 有 **5 个 unittest 用例**，全部通过：

```
$ python -m unittest concept_animator.test_concept_animator -v
test_demo_cli_writes_html ... ok
test_inference_adds_derived_relations ... ok
test_llm_builder_terminates_at_primitives ... ok
test_render_contains_visual_grammar ... ok
test_sample_tree_is_valid ... ok

----------------------------------------------------------------------
Ran 5 tests in 0.027s

OK
```

它们测的不是"跑起来没报错"，而是**四类具体断言**：

1. **数据模型**：`sample_tree.json` 校验通过，节点数恰为 18，首个子节点名是「数据集」。
2. **推导有效**：`infer_tree` 之后 `temporal_relations` 数量严格增加。
3. **视觉语法没被改坏**（最实用的一条）：渲染出的 HTML 必须包含
   `background: var(--bg)`、`--orange-fill: #ff8c00`、`--temporal-edge: #ff8c00`、
   `TREE =`、`data-node-id="`、`history.replaceState`、`child-box.entity`、`child-box.abstract`。
   等于给"黑底 + 橙色对比框 + 节点可点击 + 实体/虚线边框"这些设计约定上了回归锁。
4. **遍历真的会终止**：`FakeLLM` 精确计数模型调用次数 = 2，且所有叶子都带合法 `primitive_kind`。
5. **CLI 端到端**：`cmd_demo` 返回 0、文件存在、内容含「机器学习」。

注意第 3 条的一个边界：测试用的是**自己新渲染的** HTML（`render_html(self.tree)`），
**不是**仓库里 `output/*.html` 那份提交产物。所以测试通过**不能保证 `output/` 里的
文件是当前代码渲染的**——见 §5。

---

## 5. 已知边界 / 未完成

### 5.1 明确的缺陷

1. **`python -m concept_animator.cli` 在原目录名下一次都跑不了。**（§1.1）
   这是最影响"clone 下来就能跑"体验的一条。修法只需要重命名目录（或在父目录建一个
   下划线软链），但当前状态是坏的——**任何人按 README 复制粘贴都会在第一步失败**。
   （对比：同一批作品集里的 `rogue-dshrl` 我实测过，干净克隆后命令行直接可用；
   `godot-avatar-skeleton` 需要先让 Godot 扫描一次项目。三个仓库里只有这个是这样
   "文档给的命令一定失败"的硬故障。）
2. **`output/` 里的 HTML 是旧模板渲染的，和当前代码不一致。** 我重渲染后逐项比对：
   `output/demo.html`（31,777 B）缺少测试断言要求的 `child-box.entity` / `child-box.abstract`
   类名与 `history.replaceState`，而同一棵树重渲染得到 42,364 B 的新版本。
   **提交产物没跟着模板更新**——这是"仓库里的成品 ≠ 代码能生成的东西"的典型情况。
3. **`output/` 里混了三个不属于本工具的文件**（`plotly_py_demo.html`、`viz_compare.html`、
   `token-knowledge-map-integrated.html`），其中两个依赖 CDN、需要联网，与工具
   "自包含单文件、零依赖"的核心卖点直接冲突。（§3）
4. **`_embed_videos` 会原地修改传入的树对象。** 它把 `block["src"]` 直接改成
   `data:video/mp4;base64,...`（`render.py:1091`）。所以对**同一个 `ConceptNode` 对象**
   调两次 `render_html`，第二次会把一段 base64 字符串当成文件路径去找，
   找不到就**保留第一次的 data URI**（因为 `os.path.isfile` 对它为假）——
   目前侥幸不会崩，但这是隐式副作用，换个顺序调用就会坏。
5. **`llm_client.py` 的报错信息指向一个不存在的选项。** 构造失败时提示
   「Use `--offline` to generate the demo tree」（`llm_client.py:58`），
   但 `cli.py` 里**没有 `--offline` 参数**。这是一句会把人带沟里的错误提示。
6. **`output/photosynthesis_inferred.json` 与输入完全相同。**
   `photosynthesis_tree.json` 的 8 条集合关系里没有一条 `subset_of` / `superset_of`，
   3 条时序关系也没形成可传递的链，所以 `infer` 是空操作（字节数 14,845 → 14,845）。
   这不算 bug，但说明**推导的命中率强依赖 LLM 输出的关系类型**——而提示词里
   `subset_of` 只是 8 个选项之一。

### 5.2 设计上没做的事

- **没有分层/增量渲染**：改一个节点要整棵重渲染，没有 diff 或增量更新。
- **没有多篇讲解的打包 / 索引页**：一个树一个 HTML。原 README 把"支持多篇讲解打包"
  列在"后续可扩展"，我核对属实——没做。
- **导航只有一种顺序**：`order` 是按树的遍历顺序生成的一维序列，
  没有可选 DFS/BFS 路径切换（原 README 也承认）。
- **Allen 时间区间关系没做全**：`schema.py::TEMPORAL_RELATIONS` 定义了 7 种
  （`before` / `after` / `during` / `starts` / `finishes` / `overlaps` / `meets`），
  但**推导只处理 `before/after` 的有向闭包**，渲染也只是"一条橙色虚线箭头"，
  没有区间几何动画。
- **`spatial_relations` 的 `relation` 是自由文本**（`schema.py:94` 只校验非空），
  所以 `contains` / `near` / `inside` 拼错了也不会报错——校验强度低于 `set_relations`。
- **没有真正的"实体/抽象"视觉区分之外的语义**：`primitive_kind` 只影响边框样式和一个标签。

### 5.3 工程质量上的短板

- **`render.py` 是单文件 1109 行**，其中 `HTML_TEMPLATE` 一个 raw 字符串占了 **1051 行**
  （第 23–1074 行）。HTML/CSS/JS 全部嵌在 Python 字符串里，
  **没有语法高亮、没有 lint、没有被任何测试直接覆盖**（测试只是对渲染结果做子串断言）。
  这是这份代码里最该重构的地方——拆成模板文件或至少独立成 `.html` 资源。
- **`builder.py` 的 `_pick()` 是个多余的一层**（`return payload.get(key, default)`，
  直接写 `.get()` 就行），看起来是重构残留。
- **提示词里有相互冲突的要求**：规则 8 说"每节点 0-4 个 block"，
  规则 9 又说"必须有至少 1 个 block，最多 4 个"（`llm_client.py:126,136`）。
  同时 `builder.py:127` 的代码上限是 **6**，三处口径都不一致。
- **没有 `pyproject.toml` / `setup.py`**，所以"安装"这件事没有正式入口，
  这也是 §5.1 那个目录名问题一直没被解决的根因。
- **`__init__.py` 里的 `__version__ = "0.1.0"` 没有任何地方引用或校验**，
  树的 JSON 里也没有版本字段——**旧树文件在新代码下能不能正确渲染，没有任何保障**。

### 5.4 没有 LLM 的验证

- **`build` 这条路径我没有验证过。** `cli build` 需要 `OPENAI_API_KEY`，我没有配，
  所以这次**一次都没跑过** `build`。`output/hopsoncraft_by_llm.html`（文件名叫
  `_by_llm`）看起来是 `build` 路径的产物，但**生成它的模型、提示词版本、耗时都没有记录**，
  我也无法从产物反向确认它确实是 `cli build` 生成的而不是手写的树。
  `output/hopsoncraft_tree.json` 只有 6 节点 / 3 块，而 `hopsoncraft_v2.json` 有 26 节点 / 57 块，
  两者不是同一次的东西，仓库里也没有记录说明谁是谁的前身。
- 所以"LLM 构建这条路径能否端到端复现"，我给不出证据（下次至少该补一个 `FakeLLM`
  覆盖 `_expand_with_budget_fallback` 的用例）。
- `test_concept_animator.py` 里的 `FakeLLM` 只覆盖了 A→{B,C}, B→{D,E} 这两层，
  **没有覆盖**：深度预算兜底、重复概念引用终止、畸形关系被 `_parse_relations` 跳过、
  `blocks` 类型过滤这些分支。

### 5.5 我这次做的事

- 读完了 `schema.py` / `llm_client.py` / `builder.py` / `inference.py` / `cli.py` /
  `test_concept_animator.py` / `manim_scene.py` / `manim_scene2.py`，以及 `render.py` 的
  结构层（模板头、JS 主逻辑、块渲染、`_embed_videos`）。
- **实际跑了**：`unittest`（5/5 通过）、`verify`（4 棵树）、`render`（5 棵树）、
  `infer`（1 棵树），并量了输出字节数、base64 占比、各树的节点/关系/块统计。
- 统计脚本是我临时写的，产物都放在仓库外并已删除；**仓库内除本 README 外没有改动任何文件**。
