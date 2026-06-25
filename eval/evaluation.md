# Evaluation 指标计算说明

本文档按照当前脚本的实际实现说明五个指标的计算方法：

- Formula Accuracy
- Template Accuracy
- BLEU
- Exact Match
- Semantic Robustness

所有指标都先从输入文件中读取样本。每条样本包含：

- `gold_stl`：标准 STL 公式
- `pred_stl`：预测 STL 公式

所有指标最后都对所有样本取平均：

```text
最终指标 = 所有样本分数之和 / 样本总数
```

也就是：

```text
Metric = (score_1 + score_2 + ... + score_N) / N
```

其中：

- `N`：样本总数
- `score_i`：第 `i` 条样本在该指标下的分数

所有五个指标都有一个共同前置规则：

```text
如果 pred_stl 没有通过 stl_syntax_validator 验证：
    score_i = 0
```

`stl_syntax_validator` 的实际逻辑是：将 `pred_stl` 交给 `rtamt.StlDiscreteTimeSpecification()` 解析；如果不是非空字符串，或者解析失败，就认为语法无效。

## 1. Formula Accuracy

Formula Accuracy 衡量的是：`gold_stl` 和 `pred_stl` 分词后，在相同位置上的 token 有多少完全一致。

整体公式：

```text
Formula Accuracy = 所有样本 Formula 分数之和 / 样本总数
```

单个样本的计算：

```text
如果 pred_stl 语法无效：
    score_i = 0

如果 pred_stl 语法有效：
    score_i = matched_i / max(gold_len_i, pred_len_i)
```

其中：

- `gold_tokens_i`：第 `i` 条样本的 `gold_stl` 经过 `tokenize_formula()` 得到的 token 列表
- `pred_tokens_i`：第 `i` 条样本的 `pred_stl` 经过 `tokenize_formula()` 得到的 token 列表
- `gold_len_i`：`gold_tokens_i` 的长度
- `pred_len_i`：`pred_tokens_i` 的长度
- `max(gold_len_i, pred_len_i)`：标准公式和预测公式 token 数量中较大的那个
- `matched_i`：从左到右逐位置比较，位置相同且 token 完全一样的数量

例如：

```text
gold_tokens = [always, [, 0, :, 5, ], speed, <=, 10]
pred_tokens = [always, [, 0, :, 3, ], speed, <=, 10]
```

只有 `5` 和 `3` 不同，所以：

```text
matched = 8
gold_len = 9
pred_len = 9
score = 8 / 9
```

注意：脚本不做编辑距离、不做最长公共子序列、不做集合匹配，只做相同位置 token 的直接比较。预测 token 多了或少了都会因为分母使用较长长度而被惩罚。

## 2. Template Accuracy

Template Accuracy 衡量的是：`gold_stl` 和 `pred_stl` 抽象成模板后，在相同位置上的模板 token 有多少完全一致。

整体公式：

```text
Template Accuracy = 所有样本 Template 分数之和 / 样本总数
```

单个样本的计算：

```text
如果 pred_stl 语法无效：
    score_i = 0

如果 pred_stl 语法有效：
    score_i = matched_i / max(gold_template_len_i, pred_template_len_i)
```

其中：

- `gold_template_tokens_i`：第 `i` 条样本的 `gold_stl` 经过 `template_tokens()` 得到的模板 token 列表
- `pred_template_tokens_i`：第 `i` 条样本的 `pred_stl` 经过 `template_tokens()` 得到的模板 token 列表
- `gold_template_len_i`：`gold_template_tokens_i` 的长度
- `pred_template_len_i`：`pred_template_tokens_i` 的长度
- `max(gold_template_len_i, pred_template_len_i)`：两个模板 token 列表长度中较大的那个
- `matched_i`：从左到右逐位置比较，位置相同且模板 token 完全一样的数量

`template_tokens()` 的脚本规则：

1. 先对公式执行 `tokenize_formula()`。
2. 时间区间会替换成 `I`。

例如：

```text
[0, 5]
[0:5]
```

都会抽象成：

```text
I
```

3. 谓词会替换成 `P_1`、`P_2`、`P_3` 等。

例如：

```text
speed <= 10
distance > 5
```

会被抽象成谓词模板 token。

4. 同一个公式内部，第一次出现的不同谓词是 `P_1`，第二个不同谓词是 `P_2`，依此类推。

注意：`gold_stl` 和 `pred_stl` 是分别独立编号的。也就是说，gold 中的 `P_1` 和 pred 中的 `P_1` 不要求原始谓词内容相同，只表示“各自公式中的第一个谓词”。

## 3. BLEU

脚本中的指标名是 `BLEU`。它计算的是基于 STL token 序列的样本级 BLEU，然后对所有样本取平均。

整体公式：

```text
BLEU = 所有样本 BLEU 分数之和 / 样本总数
```

单个样本的计算：

```text
如果 pred_stl 语法无效：
    score_i = 0

如果 pred_stl 语法有效：
    score_i = bleu_score(gold_tokens_i, pred_tokens_i)
```

其中：

- `gold_tokens_i`：第 `i` 条样本的 `gold_stl` 经过 `tokenize_formula()` 得到的 token 列表
- `pred_tokens_i`：第 `i` 条样本的 `pred_stl` 经过 `tokenize_formula()` 得到的 token 列表

如果 `gold_tokens_i` 或 `pred_tokens_i` 为空：

```text
score_i = 0
```

否则先确定实际使用到几阶 n-gram：

```text
order = min(4, gold_tokens 长度, pred_tokens 长度)
```

脚本最多计算到 4-gram；如果公式很短，就只计算到实际能计算的阶数。

对每一阶 n-gram，计算 precision：

```text
precision = 匹配到的预测 n-gram 数量 / 预测 n-gram 总数量
```

这里的“匹配到的预测 n-gram 数量”使用 clipped count，也就是：

```text
某个 n-gram 的匹配数量 = min(它在 pred_tokens 中出现的次数, 它在 gold_tokens 中出现的次数)
```

然后对所有 n-gram 的匹配数量求和。

脚本中的平滑规则：

```text
1-gram precision 不加平滑
```

也就是：

```text
1-gram precision = 匹配到的预测 1-gram 数量 / 预测 1-gram 总数量
```

```text
2-gram 及以上 precision 加 1 平滑
```

也就是：

```text
n-gram precision = (匹配到的预测 n-gram 数量 + 1) / (预测 n-gram 总数量 + 1)
```

其中 `n >= 2`。

如果某一阶 precision 小于等于 `0`，该样本 BLEU 直接为 `0`。

长度惩罚 `BP`：

```text
如果 pred_tokens 长度 >= gold_tokens 长度：
    BP = 1

如果 pred_tokens 长度 < gold_tokens 长度：
    BP = exp(1 - gold_tokens 长度 / pred_tokens 长度)
```

单个样本 BLEU：

```text
score_i = BP * 各阶 precision 的几何平均
```

也就是：

```text
score_i = BP * exp(所有 precision 的 log 值之和 / order)
```

其中：

- `BP`：长度惩罚
- `precision`：每一阶 n-gram 的精度
- `order`：实际使用的 n-gram 阶数，最多为 4

## 4. Exact Match

脚本中的函数名是 `Exact_Formula_Match`。它不是直接比较原始字符串，而是比较分词归一化后的 token 列表。

整体公式：

```text
Exact Match = 所有样本 Exact Match 分数之和 / 样本总数
```

单个样本的计算：

```text
如果 pred_stl 语法无效：
    score_i = 0

如果 pred_stl 语法有效，并且 pred_tokens_i 和 gold_tokens_i 完全相同：
    score_i = 1

如果 pred_stl 语法有效，但 pred_tokens_i 和 gold_tokens_i 不完全相同：
    score_i = 0
```

其中：

- `gold_tokens_i`：第 `i` 条样本的 `gold_stl` 经过 `tokenize_formula()` 得到的 token 列表
- `pred_tokens_i`：第 `i` 条样本的 `pred_stl` 经过 `tokenize_formula()` 得到的 token 列表

`pred_tokens_i` 和 `gold_tokens_i` 完全相同的含义是：

```text
长度相同，并且每一个位置上的 token 都相同
```

所以单个样本的分数只可能是：

```text
0 或 1
```

## 5. Semantic Robustness

脚本中的 `Semantic Robustness` 实际计算的是：

```text
预测公式和标准公式在随机生成的 trace 上，满足/不满足结果是否一致
```

它不是直接平均 rtamt 的 robustness 数值。

整体公式：

```text
Semantic Robustness = 所有样本 Semantic 分数之和 / 样本总数
```

单个样本的计算：

```text
如果 pred_stl 语法无效：
    score_i = 0
```

如果 `gold_stl` 和 `pred_stl` 分词后完全相同：

```text
score_i = 1
```

也就是：

```text
tokenize_formula(gold_stl) == tokenize_formula(pred_stl)
```

时直接给满分，不再生成 trace。

如果二者分词后不完全相同，则继续执行下面步骤。

### 5.1 提取变量

从 `gold_stl` 和 `pred_stl` 中提取变量，并取并集：

```text
variables = gold 中的变量和 pred 中的变量合并后的集合
```

如果没有提取到任何变量：

```text
score_i = 0
```

### 5.2 离散化时间区间

脚本会把公式中的时间区间离散化。

例如：

```text
[35.81:70.49]
```

会变成：

```text
[36:70]
```

规则是：

```text
新区间左端点 = ceil(原左端点)
新区间右端点 = floor(原右端点)
```

并且左右端点最大都会被截断到 `200`。

如果新区间右端点小于新区间左端点，则右端点改成左端点。

### 5.3 构建 rtamt 公式

脚本分别为 gold 和 pred 构建 rtamt specification：

```text
gold_spec
pred_spec
```

所有提取到的变量都会声明为 `float`。

如果这里解析失败，脚本会抛出异常；不会把该样本简单记成 `0`。

### 5.4 确定 trace 长度

脚本使用：

```text
horizon = min(max(gold 最大区间右端点, pred 最大区间右端点, 10), 200)
```

因此：

```text
horizon 最小是 10
horizon 最大是 200
```

每条 trace 的时间点为：

```text
0, 1, 2, ..., horizon
```

所以每条 trace 有：

```text
horizon + 1
```

个时间点。

### 5.5 提取数值阈值

脚本从公式中的比较表达式右侧提取数字阈值。

例如：

```text
speed <= 10
distance > 5
```

会提取：

```text
10, 5
```

如果没有提取到任何数字阈值，则使用：

```text
[0.0]
```

作为生成 trace 的中心值。

### 5.6 随机生成 trace

脚本常量：

```text
TRACE_COUNT = 10
SEED = 13
MAX_HORIZON = 200
```

第 `i` 条样本使用的随机种子是：

```text
13 + 样本下标
```

注意：这里的“样本下标”从 `0` 开始，不是 `taskid`。

每条样本会随机生成 10 条 trace。

每条 trace 中，每个变量都会生成一串数值。生成规则：

1. 初始值随机取在：

```text
最小阈值 - 5 到 最大阈值 + 5
```

2. 每个时间点上：

有 `35%` 概率跳到某个阈值附近：

```text
某个阈值 + [-3, 3] 之间的随机数
```

有 `65%` 概率做随机游走：

```text
当前值 + [-1.5, 1.5] 之间的随机数
```

### 5.7 计算满足性一致率

对每条随机 trace，脚本分别判断：

```text
gold_spec 是否满足
pred_spec 是否满足
```

脚本中的“是否满足”定义为：

```text
rtamt evaluate 的第一个 robustness 值 >= 0
```

也就是：

```text
robustness[0][1] >= 0
```

如果 gold 和 pred 在同一条 trace 上的满足结果相同，就算一次匹配。

单个样本 Semantic 分数：

```text
score_i = 匹配的 trace 数量 / 10
```

例如：

```text
10 条 trace 中有 8 条 gold 和 pred 的满足结果一致
```

则：

```text
score_i = 8 / 10 = 0.8
```

最终：

```text
Semantic Robustness = 所有样本 score_i 的平均值
```

## tokenize_formula 的共同说明

`Formula Accuracy`、`Template Accuracy`、`BLEU`、`Exact Match`，以及 `Semantic Robustness` 的完全匹配快速判断，都会用到 `tokenize_formula()`。

脚本会先对公式做归一化再分词，主要包括：

- `->`、`=>`、`→`、`⇒` 归一为 `IMPLIES`
- `<->`、`↔` 归一为 `IFF`
- `and`、`AND`、`&&`、`∧` 归一为 `AND`
- `or`、`OR`、`||`、`∨` 归一为 `OR`
- `not`、`NOT`、`!`、`¬` 归一为 `NOT`
- `=` 和 `==` 都归一为 `==`
- `≤` 归一为 `<=`
- `≥` 归一为 `>=`
- `□` 归一为 `always`
- `◇` 归一为 `eventually`
- 数字会做规范化，例如整数值去掉多余小数形式

因此，这些指标比较的不是原始字符串，而是归一化后的 token 序列。
