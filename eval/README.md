# STL 指标评估

在 `eval/` 目录运行：

```bash
../.venv/bin/python eval.py
```

默认读取项目中的 `result/DeepSTL_with_dsl_result.txt`。默认路径按脚本位置确定，从其他目录运行也可使用。

指定结果文件：

```bash
../.venv/bin/python eval.py /path/to/result.txt
```

运行环境为 Python 3.10 或更高版本；当前验证使用 RTAMT 0.3.5 及其 ANTLR 依赖。

## 输入与输出

输入支持原有的双层花括号结果模板，以及 JSON 列表：

```json
[
  {"taskid": 0, "gold_stl": "always(sig1 > 2)", "pred_stl": "always(sig1 > 2)"}
]
```

`gold_stl`、`pred_stl` 必填；`taskid` 可省略，省略时使用从 0 开始的记录序号。空文件、缺失字段、重复编号和损坏的输入会报错。

评估结果直接输出到终端，不生成报告文件。

有效预测会先按照 `stl_alignment_rules.md` 做 gold 引导的确定性子树对齐。只有语义指纹一致的子树才能替换，且对齐后的公式必须重新通过语法校验并保持预测公式的整体语义指纹。Exact Formula Match、Formula Accuracy、Template Accuracy 和 BLEU 使用 `aligned_pred_stl`；两项语义指标继续使用原始 `pred_stl`。原始预测、对齐后预测及逐条替换记录都会保留在 `evaluate_file` 返回的明细中。

`nlll`、空字符串、JSON null 和语法非法的预测均按六项 0 分计入总样本数。标准答案非法或计算失败时，汇总分数为 null，命令以非零状态退出，并在终端输出错误原因。

## 指标口径

| 指标 | 定义 |
|---|---|
| Exact Formula Match | 形式对齐后，规范化 token 完全一致的样本比例 |
| Formula Accuracy | 形式对齐后，同位置 token 匹配数除以两序列长度的较大值，再按样本平均 |
| Template Accuracy | 形式对齐后，将时间区间替换为 I、谓词按出现顺序编号后，计算位置匹配率并平均 |
| BLEU | 形式对齐后逐条计算平滑 BLEU 并平均，最高四阶；短公式使用可用阶数 |
| Semantic Robustness | 每条公式对在采样轨迹上的满足性一致比例，再按样本平均 |
| Strict Semantic Robustness | 所有采样轨迹上满足性均一致的样本比例 |

文本指标统一空白、数字写法及支持的算子别名，保留括号和操作数顺序。冗余括号仍可能降低前四项分数。公式校验采用 RTAMT 支持的语法，并额外要求输入恰好包含一个完整表达式、区间满足 `0 <= a <= b`。

两项语义指标共享同一批轨迹，默认参数集中在 `semantic_robustness.py` 顶部：

- 每条样本 10 条轨迹，基础随机种子 13，实际种子为基础种子加记录序号。输入顺序会影响随机种子。
- 沿用旧版最大时域 200：区间下界上取整、上界下取整，端点截断到最大时域；若下界超过上界，则将上界改为下界。
- 轨迹长度沿用旧算法，由调整后最大的单个区间上界确定，至少 10、至多 200；不计算嵌套时间算子的累计时域。
- 仅比较初始时刻的满足性，鲁棒值 `>= 0` 判为满足；不比较鲁棒值的数值差异。
- 规范化 token 完全相同时，两项语义分数直接为 1，不额外采样。

这两项是旧版有限轨迹近似评估，取整、截断及有限轨迹都会影响结果，不构成形式化等价性证明。报告的区间调整统计按样本计数：标准答案或有效预测有对应区间就计入一次，包括走完全匹配快捷路径的样本。

## 单项调用与验证

原有入口函数保留，例如：

```python
from exact_formula_match import Exact_Formula_Match

score = Exact_Formula_Match("../result/DeepSTL_with_dsl_result.txt")
```

测试使用标准库 unittest：

```bash
../.venv/bin/python -B -m unittest discover -v
```
