# DeepSTL Knowledge Reverse Plan

## 1. Goal

从 `deepstl_train_14k.csv` 和 `deepstl_test_2k.csv` 中反推出可复用的
DeepSTL 风格 STL→NL 知识库。

知识理解和提取只能由 LLM 完成。程序不得解析、切分、归一化、分类、
抽取、去重或合并知识。

## 2. Program Boundary

唯一允许的数据程序是：

```text
deepstl_knowledge/scripts/read_deepstl_row.py
```

它每次只能读取并返回一条原始记录：

```text
row
split
stl
English
Type
```

程序禁止执行：

```text
STL parsing / AST construction
English segmentation
placeholder replacement
formula or subexpression classification
template or NL-pattern extraction
similarity calculation or deduplication
knowledge aggregation
knowledge-base writing
```

## 3. LLM Row-by-Row Processing

LLM 必须严格逐条处理。处理一条样本时：

```text
1. 调用单条读取器取得该条原始数据。
2. 直接理解 STL 的完整语义。
3. 识别公式骨架。
4. 识别局部时间子表达和嵌套时间子表达。
5. 识别原子谓词、区间、事件修饰符和布尔组合。
6. 在 English 中由 LLM 语义定位对应表达。
7. 生成各层 NL pattern，并替换为语义角色占位符。
8. 检查否定、事件方向、比较符和时间范围是否对齐。
9. 将该条知识放入 LLM 当前维护的 batch。
```

读取下一条之前，LLM 必须完成当前条的理解和提取。

## 4. Batch Rule

每处理完 50 条原始数据算作一个 batch。

```text
第 1 条 → LLM 提取
第 2 条 → LLM 提取
...
第 50 条 → LLM 提取
完成 batch → LLM 更新知识库一次
```

第 1–49 条期间不更新最终知识库文件。解析或对齐困难也不能改变 batch
边界。最后不足 50 条的剩余数据单独合并一次。

## 5. Knowledge Structure

知识库遵循：

```text
deepstl_knowledge/deepstl_knowledge_template.txt
```

采用三层结构：

```text
[formula_templates]
完整公式骨架及公式级连接句式。

[subexpression_templates]
局部时间表达和嵌套时间表达。

[predicates]
原子谓词、区间谓词、修饰符和布尔组合在不同上下文中的表达。
```

时间算子全部采用 DeepSTL 单词形式：

```text
always
eventually
historically
once
until
since
```

嵌套结构写成：

```text
eventually(always(<PRED>))
always(eventually(<PRED>))
```

不得写成 `F(G(...))` 或 `G(F(...))`。

## 6. LLM NL Extraction

公式级 pattern 使用：

```text
<TRIGGER_NL>
<RESPONSE_NL>
<TEMPORAL_RESPONSE_NL>
<NESTED_TEMPORAL_RESPONSE_NL>
<STATE_REQUIREMENT_NL>
```

局部时间 pattern 使用：

```text
<PRED_NL>
<EVENT_REQUIREMENT_NL>
<PRED1_NL>
<PRED2_NL>
```

谓词 pattern 使用信号、数值、状态和区间占位符。

LLM 只能抽取原 English 中实际观察到的表达，不得自由创造未观察到的
句式。无法可靠定位的 NL 不输出，不使用空占位符。

## 7. LLM Deduplication

去重只在同一模板、同一上下文内由 LLM 判断。

仅合并：

```text
完全相同的表达
仅标点、冠词或无意义冗词不同的表达
语义角色和表达结构均相同的高度近重复表达
```

必须保留：

```text
不同 trigger wording
不同 obligation wording
不同 temporal wording
状态与事件表达差异
否定差异
rise/fall/not rise/not fall 差异
```

不使用字符串相似度或自动阈值。

## 8. Output

只生成：

```text
deepstl_knowledge/output/deepstl_knowledge.txt
deepstl_knowledge/output/deepstl_knowledge.json
deepstl_knowledge/output/deepstl_reverse_report.md
```

知识库不包含：

```text
observed_statistics
train/test/total count
pattern support
context count
dedup count
template frequency
<none_high_confidence>
```

没有 NL pattern 的字段或上下文直接省略。

报告只说明处理范围、LLM-only 方法、batch 是否完成、是否存在未解决问题，
不输出模板或 pattern 频次。

## 9. Quality Review

LLM 合并每个 batch 前检查：

```text
公式、子表达和谓词是否分层
所有时间算子是否使用单词形式
NL 是否保留原 STL 的比较方向、否定和事件语义
时间上下界是否对应正确
公式级 pattern 是否引用局部 NL 占位符
知识库是否没有次数统计和空占位符
```

不保存逐条 trace、证据文件或自动解析结果。
