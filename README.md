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

### 1.1 目录结构：正常的 Python 包布局

> **本节的坑已修复。** 上一版 README 在这里写着「`python -m concept_animator.cli`
> 在原目录名下一次都跑不了，唯一跑法是建一个下划线目录联接」——那是真的：
> 模块全在仓库根目录（目录名 `concept-animator`，连字符不是合法包名字符），
> 而模块之间用相对导入（`from .builder import ...`），所以照抄 README 的命令必然失败：
>
> ```
> $ python -m concept_animator.cli demo
> ModuleNotFoundError: No module named 'concept_animator'
> ```
>
> ~~原 README 的命令照抄必失败~~ → **已重构为 `concept_animator/` 包，现在可直接运行。**
> 仓库根仍是 `concept-animator/`（连字符，GitHub 仓库名不变），包目录是下划线。

```
concept-animator/                 ← 仓库根（clone 下来的目录名）
├── README.md
├── pyproject.toml                ← 新增：pip install -e . / 控制台脚本入口
├── concept_animator/             ← ⭐ 包目录（下划线）
│   ├── __init__.py  schema.py  llm_client.py  builder.py
│   ├── inference.py  render.py  cli.py
│   └── manim_scene.py  manim_scene2.py     （可选：Manim 场景，跑它们才需要 manim）
├── tests/
│   ├── __init__.py
│   └── test_concept_animator.py  ← 5 个 unittest 用例
├── data/                         ← 概念树 JSON（sample / photosynthesis / hopsoncraft_v2 / blocks_demo）
├── output/                       ← 6 个 HTML + 4 个 JSON 产物（见 §3）
├── examples/unrelated/           ← 3 个与本工具无关的旧可视化试验（见 §3，已从 output/ 移出）
└── media/                        ← Manim 渲染产物（可选增强，不是运行前提）
```

**跑法一：零依赖直接跑**（只用标准库，不需要安装任何东西）

```powershell
cd concept-animator
python -m unittest discover -s tests -v
python -m concept_animator.cli demo   --output output/demo.html
python -m concept_animator.cli verify --input data/sample_tree.json
python -m concept_animator.cli render --input data/sample_tree.json --output output/my.html
python -m concept_animator.cli infer  --input data/sample_tree.json --output output/sample_inferred.json
```

**跑法二：按包安装**（`pyproject.toml` 已就绪，可选）

```bash
pip install -e .
concept-animator verify --input data/sample_tree.json
```

`data/` 与 `output/` 是**仓库根下的目录，不在包里面**：所以上面用 `pip install -e .`
（可编辑安装，仍指向源码树）一切正常；如果打成普通 wheel 装到别处再运行，
`demo` 会因为找不到 `data/sample_tree.json` 而报错。这是刻意的取舍——
数据和产物属于仓库内容，不属于包资源。

### 1.2 五个子命令

| 命令 | 输入 | 输出 |
|---|---|---|
| `demo` | 内置 `data/sample_tree.json` | HTML |
| `verify` | 树 JSON | 打印 `OK: <name>, nodes=N, leaves=M`（顺带做全树校验） |
| `infer` | 树 JSON | 加了传递闭包关系的树 JSON |
| `render` | 树 JSON | HTML |
| `build` | `--topic`（可加 `--doc`） | 树 JSON（可加 `--render` 直接出 HTML） |

`verify` 的实际输出（本机 Python 3.12.10 实测，路径已随 `data/` 目录更新）：

```
$ python -m concept_animator.cli verify --input data/sample_tree.json
OK: 机器学习, nodes=18, leaves=14
$ python -m concept_animator.cli verify --input data/photosynthesis_tree.json
OK: 光合作用, nodes=22, leaves=19
$ python -m concept_animator.cli verify --input data/blocks_demo_tree.json
OK: 梯度下降, nodes=5, leaves=3
$ python -m concept_animator.cli verify --input data/hopsoncraft_v2.json
OK: HopsonCraft 体素引擎, nodes=26, leaves=17
```

> 小坑（本次已加防护）：树的名字是中文，而 Windows 上只要 stdout 不是交互式控制台
> （被重定向到文件、被管道接走、在 CI 里跑），Python 会退回 **locale 编码**
> （美国/欧洲安装是 `cp1252`），于是这一行 `print` 直接抛 `UnicodeEncodeError`
> 而不是打印结果——命令本身没错，输出管道要了命。现在 `cli.py` 在 `main()` 里
> 把 stdout/stderr 钉成 UTF-8 且 `errors="replace"`（`cli.py:109`），
> 所以 `... verify ... > log.txt` 在任何代码页下都安全。

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
`cli.py` 解码文档时依次尝试 `utf-8` / `utf-8-sig` / `gb18030`（`cli.py:88`）。

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

`tests/test_concept_animator.py` 用 `FakeLLM` 精确验证了这条路径：
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
| `data/sample_tree.json` | 18 | 10 → **14** | 7 → **11** |
| `data/hopsoncraft_v2.json` | 26 | 10 → **19** | 3 → 3（自由文本的 before/after 都是中文，推导要求首尾都在本节点的名字集合里，所以没命中） |

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

`_embed_videos`（`render.py:1077-1102`）会把 `video` 块的 `src` 从文件路径换成
`data:video/mp4;base64,...`，让 HTML 保持单文件。树里的 `src` 是**相对仓库根**写的
（例如 `media/videos/manim_scene/480p15/LoadFactor.mp4`），所以查找顺序是
`block["src"]`（相对当前工作目录）→ `os.path.join(仓库根, src)` → `os.path.join(包目录, src)`。
第三项是重构时加的：包目录从仓库根挪到 `concept_animator/` 之后，
只按包目录拼路径会让 4 个视频**静默不内联**（`os.path.isfile` 为假就跳过，不报错），
产物会从 1.31 MB 掉到 ~65 KB 而看不出任何异常。
`output/hopsoncraft_by_llm.html` 现在实测 `data:video/mp4;base64,` 出现 **4** 次、
载荷 1,245,176 字符，说明内联仍然生效。

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
├── pyproject.toml            新增：包元数据 + `concept-animator` 控制台脚本入口
├── concept_animator/         ⭐ 包目录（下划线）
│   ├── __init__.py           `__version__ = "0.1.0"`
│   ├── schema.py             数据模型 + JSON 读/写/校验（191 行）
│   ├── llm_client.py         零依赖 OpenAI 兼容 JSON 客户端 + 提示词（207 行）
│   ├── builder.py            LLM BFS 遍历构建概念树（217 行）
│   ├── inference.py          集合论 / 时序传递闭包推导（139 行）
│   ├── render.py             单文件 HTML 渲染器（1120 行，最大文件）
│   ├── cli.py                5 个子命令（171 行）
│   ├── manim_scene.py        Manim CE 场景：SectionSigma / LoadFactor（82 行）
│   └── manim_scene2.py       Manim CE 场景：HashProbe / MeshVsRaymarch（92 行）
├── tests/
│   ├── __init__.py
│   └── test_concept_animator.py  5 个 unittest 用例（116 行）
├── data/
│   ├── sample_tree.json          机器学习示例树（18 节点）
│   ├── photosynthesis_tree.json  光合作用示例树（22 节点）
│   ├── blocks_demo_tree.json     表达块演示树（5 节点 / 12 块）
│   └── hopsoncraft_v2.json       体素引擎源码走读树（26 节点 / 57 块，含 4 个视频）
├── output/                   10 个文件，约 1.61 MB
├── examples/unrelated/       3 个与本工具无关的旧可视化试验（见下）
└── media/                    102 个文件，约 2.41 MB
```

### `output/` 里到底有什么

**10 个文件**（6 个 HTML + 4 个 JSON），没有图片、没有视频。
下表是**本次全部重渲染之后**的真实字节数——也就是"当前代码能生成的东西"：

| 文件 | 字节 | 来源（可复现的输入） |
|---|---|---|
| `demo.html` | 43,415 | `cli demo`（= `data/sample_tree.json`） |
| `photosynthesis.html` | 45,846 | `cli render` ← `data/photosynthesis_tree.json` |
| `blocks_demo.html` | 39,397 | `cli render` ← `data/blocks_demo_tree.json` |
| `hopsoncraft.html` | 40,121 | `cli render` ← `output/hopsoncraft_tree.json` |
| `sample_inferred.html` | 44,392 | `cli render` ← `output/sample_inferred.json` |
| `hopsoncraft_by_llm.html` | 1,311,123 | `cli render` ← `output/hopsoncraft_by_llm_inferred.json`（内联 4 个 mp4） |
| `hopsoncraft_tree.json` | 6,432 | `cli build` 的树（6 节点 / 3 块） |
| `hopsoncraft_by_llm_inferred.json` | 51,459 | `cli infer` 的产物（26 节点） |
| `photosynthesis_inferred.json` | 14,845 | `cli infer` 的产物（22 节点） |
| `sample_inferred.json` | 12,998 | `cli infer` 的产物（18 节点） |

**上面 6 个 HTML 每一个都验证过：把表里的输入喂给当前代码重新渲染，字节完全相同**
（脚本在仓库外临时跑的：逐个 `cli render` 到临时目录再和提交的产物比 `==`）。

三个不属于本工具的文件已经**移出 `output/`**，放到 `examples/unrelated/`：

| 文件 | 字节 | 为什么移走 |
|---|---|---|
| `plotly_py_demo.html` | 70,598 | Plotly 产物，没有 `<title>` 元素；**从 CDN 加载 Plotly 3.7.0、需要联网** |
| `viz_compare.html` | 5,198 | 从 CDN 加载 **ECharts 5 + echarts-gl 2 + Plotly 2.32** 共 3 个脚本、需要联网 |
| `token-knowledge-map-integrated.html` | 61,622 | 手工制作的另一份讲解页（「Token 生成机制 · 可视化知识包」），不是 `cli render` 的输出 |

移走的理由不是"不好看"，而是**它们和本工具的核心卖点直接冲突**：
本工具的所有图表都是手写内联 SVG（`chart` 块），产物是**零外部请求的单文件**；
而这三个页面里有两个**必须联网**才能显示。混在 `output/` 里会让面试官误判
"这个工具的产物要靠 CDN"。它们被保留而不是删除，是因为
`viz_compare.html` 恰好是"为什么最后选了内联 SVG 而不是图表库"这个设计决策的原始证据——
放在 `examples/unrelated/` 并加了说明（见该目录下的 `README.md`），既是证据又不误导。

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

Manim 的两个场景脚本与概念树的对应关系（读代码确认）。
脚本现在在包目录里，重渲染视频要在**仓库根**执行（`media/` 会落在仓库根下，
和树 JSON 里写的 `media/videos/...` 相对路径一致）：

```bash
pip install -e ".[manim]"          # 只有跑场景才需要 manim
manim -ql concept_animator/manim_scene.py SectionSigma
manim -ql concept_animator/manim_scene2.py HashProbe
```

| 场景 | 讲的什么 | 被哪个节点用 |
|---|---|---|
| `SectionSigma` | `σ(x,y,z) = x + 16(y + 16z)`，3D 体素坐标 → 1D 偏移的双射 | `data/hopsoncraft_v2.json` 第 188 行 |
| `LoadFactor` | `α = n/m`，`E[探测] ≈ 1/(1−α)` 曲线发散，标出扩容阈值 α₀≈0.7 和"危险区 α>0.85" | 第 530 行 |
| `HashProbe` | `h(cx,cz) → 桶 i`，开放寻址探测序列，结尾点出鸽笼原理 | 第 397 行 |
| `MeshVsRaymarch` | 渲染范式对比：CPU 建 mesh 上传 vs GPU 直接走射线 | 第 722 行 |

> 上面这条命令**本次没有实跑**（没有 manim/LaTeX 环境），只核对了脚本位置与
> `media/` 输出目录的相对关系；`media/` 里的 mp4 是原有产物，没有重新生成。

`manim_scene2.py` 的最后一帧文案是「MeshBuilder 整体删除 —— 范式更换，不是优化」——
这暗示视频是从另一个项目（HopsonCraft 体素引擎）的源码走读里抽出来的，
`hopsoncraft.html` 的标题就是「HopsonCraft 体素引擎源码走读」。

---

## 4. 测试

`tests/test_concept_animator.py` 有 **5 个 unittest 用例**，全部通过
（在仓库根执行；`tests/` 是包，所以 `-s tests` 走的是 `tests.test_concept_animator`）：

```
$ python -m unittest discover -s tests -v
test_demo_cli_writes_html ... ok
test_inference_adds_derived_relations ... ok
test_llm_builder_terminates_at_primitives ... ok
test_render_contains_visual_grammar ... ok
test_sample_tree_is_valid ... ok

----------------------------------------------------------------------
Ran 5 tests in 0.030s

OK
```

> 这里有一处**本次改动带来的语义变化**，必须说清楚：
> 测试原来用相对导入（`from . import cli`），说明它当初被设计成"包内的一个模块"；
> 现在它是 `tests/` 下的独立测试包，导入改成了绝对导入
> （`from concept_animator import cli`，`tests/test_concept_animator.py:14-18`），
> 样例树的路径也从"同目录下"改成 `DATA_DIR = <仓库根>/data`
> （`tests/test_concept_animator.py:22`）。断言本身**一行没动**。

它们测的不是"跑起来没报错"，而是**五类具体断言**：

1. **数据模型**：`sample_tree.json` 校验通过，节点数恰为 18，首个子节点名是「数据集」。
2. **推导有效**：`infer_tree` 之后 `temporal_relations` 数量严格增加。
3. **视觉语法没被改坏**（最实用的一条）：渲染出的 HTML 必须包含
   `background: var(--bg)`、`--orange-fill: #ff8c00`、`--temporal-edge: #ff8c00`、
   `TREE =`、`data-node-id="`、`history.replaceState`、`child-box.entity`、`child-box.abstract`。
   等于给"黑底 + 橙色对比框 + 节点可点击 + 实体/虚线边框"这些设计约定上了回归锁。
4. **遍历真的会终止**：`FakeLLM` 精确计数模型调用次数 = 2，且所有叶子都带合法 `primitive_kind`。
5. **CLI 端到端**：`cmd_demo` 返回 0、文件存在、内容含「机器学习」。

#### ⚠️ 一个真实的教训：测试通过 ≠ 提交的产物是新的

第 3 条测试用的是**当场新渲染的** HTML（`render_html(self.tree)`，渲染到
`tempfile.TemporaryDirectory()` 里），**不是**仓库里 `output/*.html` 那份提交产物。
所以"5/5 通过"**从来没有**保证过 `output/` 里的文件是当前代码渲染的。

这不是假设——上一轮核查就把这个坑踩实了：仓库里 6 个 HTML 产物中，有 5 个是**旧模板**
渲染的（缺 `blocks` 表达块的整套 CSS：`.blocks` / `.block.formula` / `table.symtab` /
`.block-video` / `.mathcol`），其中最老的 `sample_inferred.html` 还缺
`data-node-id="` / `history.replaceState` / `child-box.entity` / `child-box.abstract`
——即**在"节点可点击"这个功能之前**就渲染好了。而测试一直是绿的，因为测试只测它自己
刚渲染出来的东西。

顺带纠正上一轮 README 里的一处具体判断：它写 `demo.html`「缺少 `child-box.entity` /
`child-box.abstract` 类名与 `history.replaceState`」——这两点**实测是不对的**
（`demo.html` 里这 4 个串都在），它缺的是表达块 CSS，重渲染后 31,777 → **43,415** B
（上一轮 README 写的 42,364 B 也不是本机实测值）。结论（产物过期）成立，细节要按实测改。

**本次的做法**：把 6 个 HTML 产物**全部**用当前代码重渲染，并且逐个验证
"输入 → 重新渲染 → 字节完全相同"（见 §3 的表）。这样 `output/` 才真的等于
"当前代码能生成的东西"。维护时记住一句话：**改完模板要重跑产物，测试不会替你发现这件事。**

---

## 5. 已知边界 / 未完成

### 5.1 明确的缺陷

> 本节保留上一轮核查写下的原始判断（划掉的部分表示**本次已修复**），
> 后面追加本次新发现的问题。**没被划掉的都还没修**——它们是已知边界，不是待办清单。

1. ~~**`python -m concept_animator.cli` 在原目录名下一次都跑不了。**（§1.1）
   这是最影响"clone 下来就能跑"体验的一条。修法只需要重命名目录（或在父目录建一个
   下划线软链），但当前状态是坏的——**任何人按 README 复制粘贴都会在第一步失败**。~~
   → **已修复**：重构成 `concept_animator/` 包 + `tests/` + `data/` + `pyproject.toml`，
   README 里的命令现在可以照抄直接跑（§1.1）。
   （对照：同一批作品集里的 `rogue-dshrl` 干净克隆后命令行直接可用；
   `godot-avatar-skeleton` 需要先让 Godot 扫描一次项目。现在这个仓库也是"照抄即可"。）
2. ~~**`output/` 里的 HTML 是旧模板渲染的，和当前代码不一致。**
   `output/demo.html`（31,777 B）缺少测试断言要求的 `child-box.entity` /
   `child-box.abstract` 类名与 `history.replaceState`，而同一棵树重渲染得到
   42,364 B 的新版本。**提交产物没跟着模板更新**。~~
   → **已修复**：6 个 HTML 产物全部用当前代码重渲染，并逐个验证字节可复现（§3）。
   细节上更正两点：`demo.html` 里 `child-box.entity` / `child-box.abstract` /
   `history.replaceState` **本来就都在**，它真正缺的是表达块 CSS；
   重渲染是 31,777 → **43,415** B（不是 42,364）。真正缺节点可点击特性的是
   `sample_inferred.html`（30,555 → 44,392 B）。教训完整写进 §4。
3. ~~**`output/` 里混了三个不属于本工具的文件**（`plotly_py_demo.html`、`viz_compare.html`、
   `token-knowledge-map-integrated.html`），其中两个依赖 CDN、需要联网，与工具
   "自包含单文件、零依赖"的核心卖点直接冲突。（§3）~~
   → **已修复**：三个文件移到 `examples/unrelated/` 并加了该目录的说明（§3）。
4. **`_embed_videos` 会原地修改传入的树对象。**（未修）它把 `block["src"]` 直接改成
   `data:video/mp4;base64,...`（`render.py:1102`）。所以对**同一个 `ConceptNode` 对象**
   调两次 `render_html`，第二次会把一段 base64 字符串当成文件路径去找，
   找不到就**保留第一次的 data URI**（因为 `os.path.isfile` 对它为假）——
   目前侥幸不会崩，但这是隐式副作用，换个顺序调用就会坏。
   （本次只改了它的**查找路径**，没动这个副作用——按"除导入与路径外不改逻辑"的边界。）
5. **`llm_client.py` 的报错信息指向一个不存在的选项。**（未修）构造失败时提示
   「Use `--offline` to generate the demo tree」（`llm_client.py:58`），
   但 `cli.py` 里**没有 `--offline` 参数**。这是一句会把人带沟里的错误提示。
6. **`output/photosynthesis_inferred.json` 与输入完全相同。**（未修，属实测结论）
   `photosynthesis_tree.json` 的 8 条集合关系里没有一条 `subset_of` / `superset_of`，
   3 条时序关系也没形成可传递的链，所以 `infer` 是空操作（字节数 14,845 → 14,845）。
   这不算 bug，但说明**推导的命中率强依赖 LLM 输出的关系类型**——而提示词里
   `subset_of` 只是 8 个选项之一。
7. **`infer` 的产物关系顺序不可复现。**（未修，本次新发现）
   `_transitive_closure`（`inference.py:44-62`）最后 `return list(seen_pairs)`，
   而 `seen_pairs` 是 `set`——遍历顺序跟 `PYTHONHASHSEED` 走。
   实测：对同一棵树跑两次 `infer`，**关系内容完全相同**（集合论意义上一模一样），
   但**关系的排列顺序不同**，落盘 JSON 字节数也不同。
   后果：`output/sample_inferred.json` 无论提交哪一版，只要重跑一次 `infer`
   就会显示为"被修改"，而语义零变化。一行 `sorted(...)` 就能修，
   但那属于改逻辑，本次按边界没动。
8. ~~**`verify` 在 stdout 被重定向时因中文树名崩掉。**（本次新发现并修复）~~
   Windows 上 stdout 不是交互式控制台时，Python 退回 locale 编码（`cp1252`），
   `print(f"OK: {tree.name}, ...")` 直接抛 `UnicodeEncodeError`
   ——命令没错，**输出管道**要了命。`cli.py:109` 新增 `_configure_stdio()`：
   把 stdout/stderr 钉成 UTF-8 且 `errors="replace"`，不碰任何数据逻辑。

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

- **`render.py` 是单文件 1120 行**，其中 `HTML_TEMPLATE` 一个 raw 字符串占了 **1051 行**
  （第 23–1074 行）。HTML/CSS/JS 全部嵌在 Python 字符串里，
  **没有语法高亮、没有 lint、没有被任何测试直接覆盖**（测试只是对渲染结果做子串断言）。
  这是这份代码里最该重构的地方——拆成模板文件或至少独立成 `.html` 资源。
  （这也是 §4 那个"产物悄悄过期"的温床：模板改了没人看得见。）
- **`builder.py` 的 `_pick()` 是个多余的一层**（`return payload.get(key, default)`，
  直接写 `.get()` 就行），看起来是重构残留。
- **提示词里有相互冲突的要求**：规则 8 说"每节点 0-4 个 block"，
  规则 9 又说"必须有至少 1 个 block，最多 4 个"（`llm_client.py:126,136`）。
  同时 `builder.py:127` 的代码上限是 **6**，三处口径都不一致。
- ~~**没有 `pyproject.toml` / `setup.py`**，所以"安装"这件事没有正式入口，
  这也是 §5.1 那个目录名问题一直没被解决的根因。~~
  → **已修复**：新增 `pyproject.toml`（setuptools + PEP 660 可编辑安装），
  实测在干净 venv 里 `pip install -e .` 成功，并注册了 `concept-animator` 控制台脚本：
  `concept-animator verify --input data/sample_tree.json` → `OK: 机器学习, nodes=18, leaves=14`。
  `manim` 列为 optional extra（`pip install -e ".[manim]"`），因为只有两个场景脚本需要它。
- **`__init__.py` 里的 `__version__ = "0.1.0"` 没有任何地方引用或校验**，
  树的 JSON 里也没有版本字段——**旧树文件在新代码下能不能正确渲染，没有任何保障**。

### 5.4 没有 LLM 的验证

- **`build` 这条路径我（以及上一轮核查）都没有验证过。** `cli build` 需要
  `OPENAI_API_KEY`，没有配，所以**一次都没跑过**。
  `output/hopsoncraft_by_llm.html`（文件名叫 `_by_llm`）看起来是 `build` 路径的产物，
  但**生成它的模型、提示词版本、耗时都没有记录**，
  也无法从产物反向确认它确实是 `cli build` 生成的而不是手写的树。
  `output/hopsoncraft_tree.json` 只有 6 节点 / 3 块，而 `data/hopsoncraft_v2.json`
  有 26 节点 / 57 块，两者不是同一次的东西，仓库里也没有记录说明谁是谁的前身。
  （本次只确认了一件事：`data/hopsoncraft_v2.json` 与
  `output/hopsoncraft_by_llm_inferred.json` **在忽略三类关系字段后完全相等**，
  即后者是后者的 `infer` 版本。）
- 所以"LLM 构建这条路径能否端到端复现"，依然给不出证据（下次至少该补一个 `FakeLLM`
  覆盖 `_expand_with_budget_fallback` 的用例）。
- `tests/test_concept_animator.py` 里的 `FakeLLM` 只覆盖了 A→{B,C}, B→{D,E} 这两层，
  **没有覆盖**：深度预算兜底、重复概念引用终止、畸形关系被 `_parse_relations` 跳过、
  `blocks` 类型过滤这些分支。
- **Manim 场景没有跑过**：`manim_scene.py` / `manim_scene2.py` 需要装 manim + LaTeX，
  本次只读代码、没有重渲染视频（`media/` 里的 mp4 沿用原有产物）。

### 5.5 本次（结构重构这一轮）做的事

- **重构成标准包布局**：`concept_animator/`（包）、`tests/`、`data/`、
  `examples/unrelated/`，仓库根保留连字符名字；全部用 `git mv` 移动，**保留文件历史**。
- **修的导入**：`tests/test_concept_animator.py` 从相对导入（`from . import cli`）
  改成绝对导入（`from concept_animator import cli`）——它是这次唯一需要改导入的文件，
  包内 5 个模块的相对导入因为整体搬进包目录而**自动仍然成立**。
- **修的路径**：`cli.py` 的样例树位置（`<包目录>/sample_tree.json` →
  `<仓库根>/data/sample_tree.json`）、`render.py::_embed_videos` 的视频查找根
  （包目录 → 仓库根，否则 4 个 mp4 会静默不内联）、测试里的 `DATA_DIR`。
- **新增**：`pyproject.toml`、`tests/__init__.py`、`.gitignore` 补打包产物规则、
  `cli.py` 的 stdout UTF-8 防护（§5.1-8）。
- **重渲染**：6 个 HTML 产物全部重新生成，并验证"输入 → 渲染 → 字节完全相同"。
- **实测跑过**（全部在本机 Python 3.12.10）：
  `unittest`（5/5）、`verify`（4 棵树）、`render`（6 个产物）、`demo`、`infer`（1 棵）、
  `pip install -e .`（干净 venv）+ 控制台脚本。
- 分析用的临时脚本都写在仓库外（`%TEMP%`），**没有留在仓库里**；
  仓库内改动的文件见本条上半部分的清单 + README 本身。

---

## 关于 AI 辅助

本仓库的代码与文档均在**大量 AI 辅助**下完成（Claude Code / DeepSeek Harness 等 agent 工具，
协作方式是「人定方向与验收标准，AI 执行与自查，人逐项核对」）。README 本身也是 AI 起草、人工核对后的产物。

写这一节不是为了免责，而是因为**这就是它真实的工作方式**，而且它解释了这个仓库的一些特征：

- 每个数字都要求有出处（代码、日志或 `docs/evidence/`），**查不到就标「未核实」**
- 多处被推翻的早期说法**保留在「已知边界」里**，没有悄悄删掉
- 交付前做过机器核查，修掉过几处写错的声明

> 判断与把关是人做的，AI 承担执行与自查。
