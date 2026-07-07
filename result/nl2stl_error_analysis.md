# NL->STL Result Error Analysis

统计对象：当前目录 5 个 `*_result.txt` 文件，每个文件 300 条样例。

统计口径：

- `exact_norm`：只忽略空白和 `[a,b]`/`[a:b]` 这类格式差异。
- `canonical_correct`：用项目 `STL2AST.py` 解析成 AST 后比较结构，并额外归一化常见等价形式，例如 `not (x < c)` 与 `x >= c`、`not eventually[I](p)` 与 `always[I](not p)`、`fall(p)` 与 `rise(not p)`。这不是完整形式化语义证明，但比纯字符串匹配更接近实际 NL->STL 质量。
- 错误原因是多标签统计，一个错误样例可能同时计入多个原因。

## Overall

| Strategy file | Parse valid | exact_norm | canonical_correct | Errors |
|---|---:|---:|---:|---:|
| `direct_deepstl_with_deepseek_v4_pro_result.txt` | 289/300 (96.3%) | 42/300 (14.0%) | 152/300 (50.7%) | 148 |
| `deepstl_with_operatorExplain_deepseek_v4_pro_result.txt` | 289/300 (96.3%) | 47/300 (15.7%) | 178/300 (59.3%) | 122 |
| `deepstl_with_ast_deepseek_v4_pro_result.txt` | 284/300 (94.7%) | 110/300 (36.7%) | 153/300 (51.0%) | 147 |
| `deepstl_with_ast_operatorExplain_deepseek_v4_pro_result.txt` | 287/300 (95.7%) | 117/300 (39.0%) | 158/300 (52.7%) | 142 |
| `deepstl_with_ast_template_operator_knowledge_deepseek_v4_pro_result.txt` | 294/300 (98.0%) | 198/300 (66.0%) | 228/300 (76.0%) | 72 |

结论：`deepstl_with_ast_template_operator_knowledge` 最好，结构正确率 76.0%，比第二名 `operatorExplain` 高 16.7 个百分点；它同时也是语法可解析率最高的一版。

## Accuracy By Requirement Type

| Strategy | immediate_response | invariance_reachability | stabilization_recurrence | temporal_response |
|---|---:|---:|---:|---:|
| direct | 66.2% | 48.4% | 35.6% | 54.9% |
| operatorExplain | 72.3% | 62.6% | 43.8% | 59.2% |
| AST | 46.2% | 63.7% | 39.7% | 50.7% |
| AST + operatorExplain | 55.4% | 64.8% | 37.0% | 50.7% |
| AST + template/operator knowledge | 92.3% | 70.3% | 75.3% | 69.0% |

主要变化：

- 模板知识对 `immediate_response` 提升最大，达到 92.3%。
- `stabilization_recurrence` 是所有非模板策略的明显短板，通常只有 35%-44%；模板知识后提升到 75.3%。
- `invariance_reachability` 相对容易，但 direct 仍会频繁把整体 `always/eventually` 分配到子公式上。

## Main Error Causes

| Strategy | Top error causes |
|---|---|
| direct | temporal scope 57/148, distributed temporal over boolean 50/148, top-level/missing outer `always` 34/148 and 29/148, past-time operator cases 24/148 |
| operatorExplain | temporal scope 50/122, distributed temporal over boolean 39/122, top-level/missing outer `always` 38/122 and 30/122, past-time operator cases 23/122 |
| AST | temporal scope 66/147, top-level/missing outer `always` 54/147 and 42/147, distributed temporal over boolean 37/147, past-time operator cases 26/147 |
| AST + operatorExplain | temporal scope 64/142, top-level/missing outer `always` 58/142 and 46/142, distributed temporal over boolean 30/142, past-time operator cases 22/142 |
| AST + template/operator knowledge | temporal scope 28/72, distributed temporal over boolean 22/72, top-level/missing outer `always` 18/72 and 6/72, past-time operator cases 10/72 |

核心错误模式：

1. 时间算子作用域/嵌套错误是主因。
   典型形式是把 `eventually [a:b] (A or B)` 生成成 `eventually A or eventually B`，或者把 `always (A or B)` 生成成 `always A or always B`。这会改变 STL 语义。

2. 顶层结构错误很常见。
   很多样例的 gold 是 `always (trigger -> response)`，预测会漏掉外层 `always`，或把 `always` 只套在 trigger/response 的局部。

3. `stabilization_recurrence` 的双层时间模式难。
   常见混淆是 `always [x:y] (eventually [u:v] (...))` 与 `eventually [u:v] (always [x:y] (...))` 顺序互换，或者漏掉内层 `rise/fall`。

4. `rise/fall` 错误不是最大类，但会造成关键语义偏差。
   典型错误包括漏掉响应里的 `rise`，把状态谓词当事件谓词，或把 `fall(range)` 简化成 bare complement。脚本把 `fall(p)` 与 `rise(not p)` 这类等价变形视为正确，因此剩下的是更实质的事件错误。

5. 过去时算子仍是弱点。
   包含 `once/historically/since` 的样例更容易被改成未来时算子，或在 `since` 左右操作数上加多余的 `once/always`。

6. 语法/输出污染占比不高，但 direct 和纯 operatorExplain 仍有。
   例子包括 `forall t in ... within ...`、`execution_ends`、`tau`、`∞`、以及自然语言解释混入输出。

## Recommendation

后续优化优先级：

1. 保留 `AST + template/operator knowledge` 作为主策略。
2. 在 prompt/AST schema 中显式约束 `always/eventually` 不要跨 `and/or` 分配，除非模板本身要求。
3. 单独加入 `always(trigger -> response)`、`always[x:y](eventually[u:v](...))`、`eventually[x:y](always[u:v](...))` 的 hard examples。
4. 对 `once/historically/since` 和 `rise/fall` 做模板级 few-shot，特别强调事件谓词与状态谓词不能互换。
5. 在生成后加一个轻量 AST 校验器：拒绝自然语言泄漏、`forall/within/execution_ends/tau/∞` 等非目标 STL 产物。

复现命令：

```bash
python analyze_nl2stl_errors.py
```
