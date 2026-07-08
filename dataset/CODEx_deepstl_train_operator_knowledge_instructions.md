# Codex 任务说明：逐条处理 deepstl_train.csv 并丰富算子知识库

你需要逐条处理当前目录下的 `deepstl_train.csv`，按照既有知识库风格提取 STL 算子知识，并追加到 `./operator_knowledge/`。本文件是执行规范，读取后直接开始处理，不需要重新设计方案。

## 任务目标

1. 逐条读取 `deepstl_train.csv`。
2. 对每条数据的 `STL` 和 `English` 做语义判断。
3. 只提取目标算子及其真实连续组合的知识。
4. 每个算子或连续组合算子单独使用一个文件存储，文件位于 `operator_knowledge/`。
5. 追加前必须检查对应文件中是否已有语义等价知识；已有则跳过，没有才追加。
6. 不按照数据索引组织知识，不把第几条样本写进知识文件。
7. 每处理完一条数据，都向用户输出一行完成提示，说明新增或无新增，以及涉及的算子。

## 必须先读取的文件

开始处理前，先读取这些文件以理解格式和当前知识库状态：

- `knowledge_template_example.txt`
- `extract_operator_candidates.py`
- `operator_knowledge/*.txt`
- `deepstl_train.csv`

如果 `deepstl_train.csv` 不存在，立即告知用户缺少该文件，不要改动知识库。

## 目标算子范围

只处理下面这些基础算子：

- `always`
- `eventually`
- `until`
- `since`
- `historically`
- `once`
- `rise`
- `fall`

也处理：

- `not` 与上述算子的直接组合，例如 `not always(...)`、`not fall(...)`
- 上述算子之间确实连续嵌套或连续使用的组合，例如 `always(eventually(...))`、`eventually(rise(...))`、`not fall(until(...))`

不要处理目标范围之外的算子。

## 连续组合判定规则

组合算子必须同时满足两个条件：

1. STL 结构上确实连续嵌套或连续连接。
2. English 语义上也确实把这两个算子表达成一个混合时序含义。

可以作为组合的例子：

- `not fall(φ)` -> `not_fall`
- `always(eventually(φ))` -> `always_eventually`
- `eventually(rise(φ))` -> `eventually_rise`
- `not fall(φ until ψ)` -> `not_fall_until`
- `φ until not rise(ψ)` 或 `until(..., not rise(...))` -> `until_not_rise`

不能作为组合的例子：

- `rise(φ) -> eventually(ψ)` 不能提取成 `rise_eventually`，因为 `rise` 和 `eventually` 分别位于触发和响应中。
- `always(trigger -> eventually(response))` 可以记录 `always` 和 `eventually`，但不能机械地把 `always_eventually` 当成连续组合，除非 STL 是 `always(eventually(...))` 且自然语言也表达“每个时刻都要求之后最终出现”。
- 一条公式里远距离出现多个算子，不代表这些算子都要组合。

## 脚本职责与 Codex 职责

使用 `extract_operator_candidates.py` 只是为了机械抽取每条数据的 `STL`、`English` 和候选算子结构。该脚本不是语义判断器。

推荐命令：

```bash
python extract_operator_candidates.py --csv deepstl_train.csv --row 1
python extract_operator_candidates.py --csv deepstl_train.csv --from-row 1 --to-row 50
```

Codex 必须自己完成这些语义判断：

- 候选算子是否真的应该提取。
- 候选组合是否是连续组合，而不是触发/响应两侧分别出现。
- 这条样本是否提供了已有知识库中没有的新语义。
- 追加到哪个算子文件。
- 如何把 English 片段修剪、润色成合适的 `cue`。

如果脚本漏掉明显连续组合，可以基于 STL 结构人工判断并追加；必要时可以小范围修正脚本，但修正后必须运行语法检查。

## 知识文件格式

每个文件采用当前知识库已有格式：

```text
operator: eventually_rise
meaning: "eventually(rise(φ)) 表示未来某个时间点必须观察到谓词 φ 从 false 变为 true。"
cases:
  - semantic: "未来指定时间窗口内需要发生某个上升转移事件。"
    cue: "at sometime within the following b time units the scenario that x is shifted to c needs to take place：eventually 的目标不是普通状态，而是 rise 描述的转移事件。"
    pattern: "eventually [a:b] (rise(φ))"
```

新文件命名规则：

- 基础算子：`always.txt`、`eventually.txt`
- 直接组合：用下划线连接，例如 `eventually_rise.txt`、`not_fall_until.txt`
- 文件内 `operator:` 与文件名主体保持一致

如果对应文件已经存在，只追加新的 `cases` 项。不要重写已有知识，不要重排已有条目。

## 知识提取风格

知识不是机械关键词摘录。必须基于 `STL` 和 `English` 的整体语义进行总结。

`semantic` 写法：

- 概括这个算子结构表达的时序含义。
- 说明时间窗口、有界/无界、持续/最终、过去/未来、事件转移、否定作用域等真正有区分度的信息。
- 不要把变量名、随机常数、样本编号当成知识核心。

`cue` 写法：

- 保留 English 中和该算子语义对应的自然语言片段。
- 片段如果机械、生硬或冗长，要适度修剪和润色。
- 可以在冒号后补充一句解释，说明这个片段如何对应算子语义。
- 不要编造 English 没有支持的语义。
- 不要写 `可润色为`。
- 不要写 `原文片段如`。
- 不要使用转义引号 `\"`。

`pattern` 写法：

- 抽象出 STL 结构，不保留具体变量和常数。
- 用 `φ`、`ψ`、`x`、`c`、`lower`、`upper`、`[a:b]` 等表示通用结构。

特别注意 `always`：

- 有些公式外层 `always` 只是把内部触发-响应规则提升为全局规则。
- 如果 English 没有直接描述全局 `always`，不要硬造 cue。
- 可以简要说明：自然语言重点在内部条件规则，`always` 的作用是让该规则在每个时刻重复检查。

## 判断是否新增知识

追加前必须打开对应算子文件，检查是否已经有语义等价条目。

通常不算新知识的情况：

- 只是变量名不同。
- 只是常数或时间上界不同，但结构和语义相同。
- 只是 English 同义改写，时序含义没有新增。
- 只是触发条件或响应条件换了具体谓词。

通常可以算新知识的情况：

- 有界和无界语义不同。
- 闭区间、开区间、半开区间语义不同。
- `rise` 或 `fall` 的事件类型不同，例如进入区间、离开区间、越过阈值、关系开始成立、关系失效。
- `not` 的作用域不同，例如 `not fall(φ until ψ)` 与 `until(not fall(φ), ψ)` 不同。
- 组合嵌套位置不同，且 English 明确支持这种混合语义。
- 过去时序算子 `once`、`historically`、`since` 的时间方向或窗口语义不同。

## 每条数据的处理流程

对第 `N` 条数据：

1. 运行候选抽取：

```bash
python extract_operator_candidates.py --csv deepstl_train.csv --row N
```

2. 阅读输出中的 `stl`、`english`、`candidates`。
3. 判断候选算子和连续组合是否成立。
4. 对每个成立的算子，打开对应 `operator_knowledge/<operator>.txt`。
5. 判断是否已有语义等价知识。
6. 如果没有，追加一个新的 `cases` 条目；如果文件不存在，按现有格式创建新文件。
7. 输出完成提示，例如：

```text
第 N 条完成：新增 eventually_rise 1 条；always 已有覆盖。
第 N 条完成：always、rise 相关知识已有覆盖，无新增。
```

如果批量读取多条数据，也必须逐条做语义判断并逐条输出完成提示。

## 质量检查

阶段性处理完一批数据后运行：

```bash
python -m py_compile extract_operator_candidates.py
rg -n '可润色为|原文片段如|\\"' operator_knowledge
python -c "from pathlib import Path; import re; files=list(Path('operator_knowledge').glob('*.txt')); print('files', len(files)); print('cases', sum(1 for p in files for line in p.read_text(encoding='utf-8').splitlines() if re.match(r'\s*- semantic:', line)))"
python -c "import csv; print('rows', len(list(csv.DictReader(open('deepstl_train.csv', encoding='utf-8')))))"
```

其中 `rg` 命令没有输出时才是合格结果。

最终完成全部训练集后，把下面内容报告给用户：

- 已处理的总行数。
- `operator_knowledge/` 下知识文件数量。
- `semantic` 条目数量。
- 是否通过脚本语法检查。
- 是否没有发现禁止片段或转义引号。

## 禁止事项

- 不要偷懒批量套模板。
- 不要只看算子名机械生成知识。
- 不要把远距离出现的算子强行组合。
- 不要把触发条件和响应条件两侧的算子强行组合。
- 不要编造 `cue`。
- 不要重复追加已有语义等价知识。
- 不要把数据行号写进知识文件。
- 不要调用外部 LLM；语义判断由当前 Codex 完成，除非用户明确要求外部模型。
- 不要为了追求数量而降低知识质量。

