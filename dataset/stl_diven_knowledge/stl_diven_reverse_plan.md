# STL-Diven Knowledge Reverse Plan

## 1. Goal

从 `stl_diven_6970.csv` 的 6970 条原始记录中反推出可复用的 STL→NL
知识库。知识理解、抽取、分类、对齐、去重和合并只能由 LLM 完成。

## 2. Program Boundary

唯一允许的数据读取程序是：

```text
stl_diven_knowledge/scripts/read_stl_diven_row.py
```

它每次只能返回一条原始记录的 `row`、`stl`、`English` 和
`Complexity`。程序不得解析 STL、切分英文、替换占位符、提取模板、
计算相似度、去重、聚合或写入知识库。

`Complexity` 只作为原始参考标签，不能代替 LLM 对公式结构的判断。

## 3. Row-by-Row Processing

LLM 在读取下一条之前，必须完成当前条的完整语义理解、公式骨架识别、
时间子表达识别、谓词识别、English 语义定位、NL pattern 提取以及方向、
否定、时间范围和事件语义检查。

只抽取原 English 中实际观察到且与 STL 可靠对齐的表达。无法可靠定位的
NL 不输出；不使用空占位符。English 存在歧义或错误时，不让可疑表达进入
知识库。

## 4. Batch and TXT Rule

每 50 条构成一个 batch。前 49 条不更新知识文件；第 50 条完成后，由 LLM
合并并更新一次 `stl_diven_knowledge.txt`。共有 139 个完整 batch 和最后
20 条构成的剩余 batch，合计 140 个 batch。

逐条处理和 batch 合并期间只维护 TXT，不创建或更新 JSON。

## 5. Knowledge Structure

知识库使用 `stl_diven_knowledge_template.txt`，包括完整公式、时间子表达、
谓词、谓词修饰符和谓词组合。时间算子统一写为 `always`、`eventually`、
`historically`、`once`、`until`、`since`；嵌套结构不得使用单字母缩写。

## 6. Deduplication

去重仅由 LLM 在同一模板和同一上下文内判断。只合并完全相同或语义角色、
表达结构均相同的高度近重复表达。保留不同 trigger、obligation、temporal、
状态/事件、否定及 rise/fall 表达。不使用字符串相似度或自动阈值。

## 7. Final TXT Review and One-time JSON

6970 条全部合并后，对完整 TXT 进行分层、语义对齐、去重、占位符、时间
算子及无统计信息检查。TXT 通过终检后冻结，再由 LLM 从完整 TXT 一次性
提炼 `stl_diven_knowledge.json`。JSON 不增加 TXT 中没有的知识，也不重新
读取 CSV 或扩写 NL pattern。

## 8. Output

只生成：

```text
stl_diven_knowledge/stl_diven_knowledge.txt
stl_diven_knowledge/stl_diven_knowledge.json
stl_diven_knowledge/stl_diven_reverse_report.md
```

知识库不包含频次、support、context count、dedup count、数据分布、空字段
或逐条 trace。报告只说明处理范围、LLM-only 方法、batch 完成情况、TXT
终检、一次性 JSON 生成情况及是否存在未解决问题。

## 9. Quality Review

每次 batch 合并及最终冻结前检查：

- 公式、子表达和谓词是否正确分层；
- 比较方向、否定、事件语义和时间上下界是否与 STL 一致；
- `not always(P)` 与 `always(not(P))` 是否区分；
- `and/or` 与蕴含的作用域是否正确；
- NL 是否确实在原 English 中出现；
- 是否没有统计信息、空占位符和自动创造的句式。
