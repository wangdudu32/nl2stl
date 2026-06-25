# Evaluation Metrics

本文档完全按照当前脚本实现说明 `Formula Accuracy`、`Template Accuracy`、`BLEU`、`Exact Match` 和 `Semantic Robustness` 的计算方法。相关实现来自：

- `formula_accuracy.py`
- `template_accuracy.py`
- `bleu.py`
- `exact_formula_match.py`
- `semantic_robustness.py`
- `stl_metrics_utils.py`
- `stl_syntax_validator.py`

## 通用流程

所有指标都通过 `load_records(file_path)` 读取样本。每条有效样本至少包含：

- `gold_stl`
- `pred_stl`

记数据集中读取到的样本数为 `N`。每个指标先为每条样本计算一个样本分数 `s_i`，最后使用 `mean(scores)` 取宏平均：

```text
Metric = (1 / N) * sum_{i=1}^{N} s_i
```

如果没有读取到任何样本，即 `N = 0`，则 `mean([])` 返回 `0.0`。

所有五个指标都会先检查预测公式 `pred_stl` 的语法：

```text
if not stl_syntax_validator(pred_stl):
    s_i = 0.0
```

`stl_syntax_validator(stl)` 的实现为：

1. `stl` 必须是非空字符串。
2. 用 `extract_variables(stl)` 提取比较表达式中的变量。
3. 创建 `rtamt.StlDiscreteTimeSpecification()`。
4. 将提取出的每个变量声明为 `float`。
5. 设置 `spec.spec = stl` 并调用 `spec.parse()`。
6. 只要上述步骤抛出异常，就判定为语法无效。

注意：该语法检查只直接检查 `pred_stl`。`gold_stl` 不在这些指标入口处统一做语法无效置零处理。

## 公式分词与归一化

`Formula Accuracy`、`Template Accuracy`、`BLEU`、`Exact Match` 以及 `Semantic Robustness` 的完全匹配快速路径都会使用 `tokenize_formula(formula)`。

分词前先调用 `normalize_formula(formula)`，主要归一化规则如下：

- 逻辑连接符：
  - `↔`、`<->` 转为 `IFF`
  - `→`、`⇒`、`=>`、`->` 转为 `IMPLIES`
  - `∧`、`&&`、`&` 转为 `AND`
  - `∨`、`||`、`|` 转为 `OR`
  - `¬`、`!` 转为 `NOT`
- 比较符：
  - `≤` 转为 `<=`
  - `≥` 转为 `>=`
- 时序符号：
  - `□` 转为 `always`
  - `◇` 转为 `eventually`
- 时序操作符大小写归一：
  - `always`、`eventually`、`until`、`weak_until`、`release`、`once`、`historically`、`since`、`rise`、`fall`、`peak`
- 布尔操作符大小写归一：
  - `AND`、`OR`、`NOT`、`IMPLIES`、`IFF`
- 区间写法归一：
  - `op_{[a,b]}`、`op_[a,b]`、`op[a,b]` 转成 `op [ a,b ]`
  - 其中 `op` 包括 `always`、`eventually`、`until`、`weak_until`、`release`、`once`、`historically`、`since`

之后用正则 `TOKEN_RE` 提取 token。提取后继续归一化：

- `=` 和 `==` 都归一为 `==`
- `AND`、`OR`、`NOT`、`IMPLIES`、`IFF` 归一为大写
- 保留 token 中的时序操作符和括号、方括号、逗号等归一为小写
- 数字使用 `Decimal` 归一：
  - 整数值输出为不带小数的字符串
  - 非整数值使用规范化后的十进制字符串
- 其他 token 保持原样

## 位置准确率

`Formula Accuracy` 和 `Template Accuracy` 都使用 `positional_accuracy(gold_tokens, pred_tokens)`。

设：

- `G = [g_1, g_2, ..., g_m]`
- `P = [p_1, p_2, ..., p_n]`
- `D = max(m, n)`

若 `D = 0`，则：

```text
positional_accuracy(G, P) = 0.0
```

否则只比较相同位置上的 token，匹配数为：

```text
M = sum_{j=1}^{m} 1[j <= n and g_j = p_j]
```

位置准确率为：

```text
positional_accuracy(G, P) = M / max(m, n)
```

因此，预测序列比标准序列更短或更长都会通过分母 `max(m, n)` 受到惩罚；不会做编辑距离、对齐或集合匹配。

## Formula Accuracy

脚本入口：`Formula_Accuracy(file_path)`。

对第 `i` 条样本：

```text
if pred_stl_i 语法无效:
    s_i = 0.0
else:
    G_i = tokenize_formula(gold_stl_i)
    P_i = tokenize_formula(pred_stl_i)
    s_i = positional_accuracy(G_i, P_i)
```

最终：

```text
Formula Accuracy = (1 / N) * sum_{i=1}^{N} s_i
```

其中 `positional_accuracy` 的精确定义见上一节。

## Template Accuracy

脚本入口：`Template_Accuracy(file_path)`。

该指标先用 `template_tokens(formula)` 将 STL token 序列抽象成模板 token，再计算位置准确率。

`template_tokens(formula)` 的实现规则如下：

1. 先执行 `tokenize_formula(formula)`。
2. 从左到右扫描 token。
3. 如果当前位置是区间：

```text
[ number (, 或 :) number ]
```

则整个 5-token 区间被替换为：

```text
I
```

4. 如果当前位置是谓词开头：

```text
identifier comparator (number 或 identifier)
```

其中 `comparator` 属于：

```text
<, <=, >, >=, ==, !=, =
```

则从当前位置起收集谓词 token，直到遇到以下停止 token：

```text
), AND, OR, IMPLIES, IFF, until, weak_until, release, since
```

或遇到以下 token：

```text
(, [, ], ,, :, comparator
```

收集到的谓词 tuple 会映射为当前公式内部的 `P_k`。同一个公式内第一次出现的不同谓词依次映射为 `P_1`、`P_2`、...

5. 如果当前位置是非保留字 identifier，但不构成上述谓词，则该 identifier 也映射为当前公式内部的 `P_k`。
6. 其他 token 保持不变。

注意：`template_tokens(gold_stl)` 和 `template_tokens(pred_stl)` 分别独立建立 `P_k` 映射。因此 `P_1` 表示各自公式中第一次出现的谓词模板，并不要求 gold 和 pred 的谓词文本相同。

对第 `i` 条样本：

```text
if pred_stl_i 语法无效:
    s_i = 0.0
else:
    G_i = template_tokens(gold_stl_i)
    P_i = template_tokens(pred_stl_i)
    s_i = positional_accuracy(G_i, P_i)
```

最终：

```text
Template Accuracy = (1 / N) * sum_{i=1}^{N} s_i
```

## BLEU

脚本入口：`BLEU(file_path)`。

该指标使用 `bleu_score(gold_tokens, pred_tokens, max_n=4)`，是基于 STL token 序列的样本级平滑 BLEU，然后对样本做宏平均。

对第 `i` 条样本：

```text
if pred_stl_i 语法无效:
    s_i = 0.0
else:
    G_i = tokenize_formula(gold_stl_i)
    P_i = tokenize_formula(pred_stl_i)
    s_i = bleu_score(G_i, P_i, max_n=4)
```

若 `G_i` 或 `P_i` 为空，则：

```text
s_i = 0.0
```

否则令：

```text
m = len(G_i)
n = len(P_i)
K = max(1, min(4, m, n))
```

对每个 `r = 1, 2, ..., K`：

- 统计预测 token 序列中的 `r`-gram 计数 `C_P`
- 统计标准 token 序列中的 `r`-gram 计数 `C_G`
- 预测 `r`-gram 总数：

```text
T_r = sum_{gram} C_P(gram)
```

- 裁剪匹配数：

```text
C_r = sum_{gram} min(C_P(gram), C_G(gram))
```

如果 `T_r = 0`，直接返回 `0.0`。

一阶精度不做平滑：

```text
p_1 = C_1 / T_1
```

二阶及以上精度使用加一平滑：

```text
p_r = (C_r + 1) / (T_r + 1), r >= 2
```

如果任意 `p_r <= 0`，直接返回 `0.0`。

长度惩罚为：

```text
BP = 1.0,                         if n >= m
BP = exp(1 - m / n),              if n < m
```

样本 BLEU 为：

```text
bleu_score(G_i, P_i) = BP * exp((1 / K) * sum_{r=1}^{K} log(p_r))
```

最终：

```text
BLEU = (1 / N) * sum_{i=1}^{N} s_i
```

## Exact Match

脚本入口：`Exact_Formula_Match(file_path)`。

该指标不是比较原始字符串，而是比较 `tokenize_formula` 后的 token 列表。

对第 `i` 条样本：

```text
if pred_stl_i 语法无效:
    s_i = 0.0
else:
    G_i = tokenize_formula(gold_stl_i)
    P_i = tokenize_formula(pred_stl_i)
    s_i = 1.0 if P_i == G_i else 0.0
```

最终：

```text
Exact Match = (1 / N) * sum_{i=1}^{N} s_i
```

## Semantic Robustness

脚本入口：`Semantic_Robustness(file_path)`。

该指标名称为 Semantic Robustness，但当前脚本实际计算的是采样轨迹上的满足性一致率，而不是 rtamt robustness 数值本身的平均值。

常量：

```text
TRACE_COUNT = 10
MAX_HORIZON = 200
SEED = 13
```

对第 `i` 条样本，入口函数使用样本下标 `index` 传入随机种子：

```text
seed_i = SEED + index
```

若 `pred_stl_i` 语法无效：

```text
s_i = 0.0
```

否则调用：

```text
s_i = semantic_robustness_for_pair(gold_stl_i, pred_stl_i, seed_i)
```

`semantic_robustness_for_pair` 的计算步骤如下。

### 1. token 完全相同则直接为 1

如果：

```text
tokenize_formula(gold_stl_i) == tokenize_formula(pred_stl_i)
```

则：

```text
s_i = 1.0
```

### 2. 提取变量

否则取 gold 和 pred 中变量集合的并集，并排序：

```text
variables = sorted(extract_variables(gold_stl_i) union extract_variables(pred_stl_i))
```

`extract_variables` 只从比较表达式中提取变量。比较表达式左侧变量一定加入集合；右侧如果整体也是 identifier，则也加入集合。

如果没有提取到任何变量：

```text
s_i = 0.0
```

### 3. 离散化时间区间

对 gold 和 pred 分别执行 `discretize_intervals(formula)`。匹配形如：

```text
[ start,end ] 或 [ start:end ]
```

的数字区间，并替换为：

```text
[ceil(start) : max(ceil(start), floor(end))]
```

同时 `ceil(start)` 和 `floor(end)` 都会被 `MAX_HORIZON = 200` 截断：

```text
start' = min(ceil(start), 200)
end' = min(floor(end), 200)
interval = [start' : max(start', end')]
```

### 4. 构建 rtamt specification

对变量集合中的每个变量声明 `float`，分别解析 gold 和 pred：

```text
gold_spec = build_spec(discretized_gold, variables)
pred_spec = build_spec(discretized_pred, variables)
```

如果解析或后续计算出现异常，入口函数会抛出 `RuntimeError`，不会把该样本记为 `0.0`。

### 5. 确定轨迹长度

先分别取离散化后公式中所有区间右端点的最大值，没有区间则为 `0.0`，然后向上取整。轨迹 horizon 为：

```text
horizon = min(max(max_interval_end(gold), max_interval_end(pred), 10), 200)
```

生成的时间点为：

```text
time = [0, 1, ..., horizon]
```

因此每条 trace 长度为 `horizon + 1`。

### 6. 提取数值阈值

从 gold 和 pred 拼接后的公式中提取所有比较符右侧的数字阈值：

```text
thresholds = extract_numeric_thresholds(gold + " " + pred)
```

比较符包括：

```text
<=, >=, ==, !=, <, >, =
```

若没有提取到阈值，后续生成轨迹时使用：

```text
centers = [0.0]
```

否则：

```text
centers = thresholds
```

### 7. 随机生成 10 条 trace

随机数生成器为：

```text
rng = random.Random(seed_i)
```

每条 trace 中，每个变量独立生成。对每个变量：

1. 初始值：

```text
current ~ Uniform(min(centers) - 5.0, max(centers) + 5.0)
```

2. 对 `horizon + 1` 个时间点逐步生成值：

以 `0.35` 概率重置到某个中心附近：

```text
current = choice(centers) + Uniform(-3.0, 3.0)
```

否则做随机游走：

```text
current = current + Uniform(-1.5, 1.5)
```

每一步得到的 `current` 追加到该变量的值序列中。

### 8. 满足性一致率

对每条生成的 trace，分别计算 gold 和 pred 的 rtamt robustness：

```text
robustness = spec.evaluate(trace)
```

脚本将公式是否满足定义为：

```text
satisfies(spec, trace) = bool(robustness and robustness[0][1] >= 0)
```

也就是只看 `evaluate` 结果第一个时间点的 robustness 值是否大于等于 `0`。

令第 `k` 条 trace 上的满足性一致指示函数为：

```text
a_k = 1[satisfies(gold_spec, trace_k) == satisfies(pred_spec, trace_k)]
```

样本 Semantic Robustness 分数为：

```text
s_i = (1 / TRACE_COUNT) * sum_{k=1}^{TRACE_COUNT} a_k
```

由于 `TRACE_COUNT = 10`，所以：

```text
s_i = matches / 10
```

最终：

```text
Semantic Robustness = (1 / N) * sum_{i=1}^{N} s_i
```
