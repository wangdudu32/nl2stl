# NL → DSL 核心规则

将 NL 按给定时间模型、信号声明和别名翻译为 NLSTL-DSL。只输出一个公式，不输出声明、解释或代码围栏。只使用已声明名称，不添加原文没有的条件、阈值或时间要求。

## 语法

名称用反引号，如 `` `speed` ``；枚举常量写为 `` `Mode`.`RUN` ``。P、Q 表示可递归嵌套的公式，e、f 表示标量表达式，W 表示时间窗口；这些是下表占位记号，不得直接输出。

| 含义 | 句式 |
|---|---|
| 常量 | `true`、`false` |
| 比较 | `e is equal to f`、`e is not equal to f`、`e is less than f`、`e is less than or equal to f`、`e is greater than f`、`e is greater than or equal to f` |
| 数值范围 | `e is in [l, h]`，端点也可开放 |
| 全部满足 | `all of { P; Q; }` |
| 至少一项满足 | `any of { P; Q; }` |
| 否定 | `it is not the case that { P }` |
| 当前蕴含 | `if { P } then { Q }` |
| 全局响应 | `whenever { P } then { Q }` |
| 持续成立 | `throughout W { P }` |
| 至少一次 | `at least once in W { P }` |
| 强直到 | `keep { P } until W { Q }`，W 必须为未来窗口 |
| 强自从 | `keep { P } since W { Q }`，W 必须为过去窗口 |
| 变真／变假 | `becomes true { P }`、`becomes false { P }`，仅 sampled |

窗口 W 只能写为：

- `the next I seconds`、`the previous I seconds`。
- `the entire future`、`the entire past`。

I 为 `[a,b]`、`[a,b)`、`(a,b]`、`(a,b)`、`[a,infinity)` 或 `(a,infinity)`。有限端点非负、区间非空；相等端点只允许 `[a,a]`。时间常数统一换算成秒，时间参数保留名称。

每个普通花括号块包含一个公式，末尾不加分号；`all of`、`any of` 至少两项，每项末尾必须加分号。不使用 `never` 和 `within ... hold for ...` 简写，按下面的语义展开。

## 必须保留的语义

- 原子条件和 `if` 只作用于当前评价时刻；`whenever` 从当前起全局适用。
- 内层时间窗口相对于外层选中或遍历的时刻。过去 `[a,b]` 回看 `[t-b,t-a]`；无界窗口为 `[0,infinity)`。是否包含当前由端点决定。
- 严格早于截止时间用开端点，不晚于用闭端点；不得猜测未明确的边界。
- 同时成立一次：存在量词内放合取；分别成立一次：合取内放各自的存在量词。
- 并非一直成立：否定 `throughout` 整体；一直不成立：在 `throughout` 内否定。
- d 秒内达到并保持 h 秒：外层至少一次 `[0,d]`，内层持续 `[0,h]`，h>0；不额外要求此前为假或 h 秒后变假。
- until 要求 Q 在窗口内有见证 u，P 在 `[t,u)` 持续；since 要求 Q 在已有历史中有见证 u，P 在 `(u,t]` 持续。见证不必是首次或最近一次。
- 状态为真不等于变真事件。边沿比较相邻采样点，初始样本的变真、变假均为假；dense 禁止边沿。
- dense 对实数时刻量化，sampled 只对采样点量化。起点前无历史；空窗口上持续为真、至少一次为假。无界未来不能截断为日志结束。

## 类型与单位

- 比较双方必须类型兼容：同维度数值、两个布尔或同一枚举；大小比较仅用于数值。无单位数字为无量纲，不自动继承信号单位。
- 合法单位：`unitless`、`seconds`、`milliseconds`、`minutes`、`meters`、`centimeters`、`meters_per_second`、`kilometers_per_hour`、`meters_per_second_squared`、`kelvin`、`radians`。
- 算术允许 `+ - * /`、括号及 `absolute value of (e)`；加减两侧同维度，除数必须不含信号且绑定后非零。
- 数值范围端点必须不含信号且同维度；相等不自动添加容差。
- 参数保留名称；区间参数必须具有时间维度，并按自身单位换算。

## 无法翻译时

信息缺失或关键歧义未解决：只输出 `{"status":"needs_clarification","issues":["具体问题"]}`。
明确超出语言或时间模型能力：只输出 `{"status":"unsupported","issues":["具体原因"]}`。
这两种 JSON 不是 DSL，不能与公式混合输出。只生成上述结构，不发明新算子。
