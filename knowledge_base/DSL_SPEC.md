# NLSTL-DSL 1.0：面向自然语言到信号时序逻辑的受控自然语言规范

文档状态：完整语言设计规范（第一版）。

本文件独立定义 DSL 的语法、语义、合法性约束和 STL 映射。现有知识库仅作为表达方式和覆盖范围的参考，本语言不受现有 AST 文件的结构限制。本文件不包含解析器、编译器或数据集实现。

## 1. 目标与设计原则

NLSTL-DSL 是 NL → DSL → STL 中的中间语言。它使用固定英文短语表达条件、时间量化和状态变化，使用显式分组表达逻辑结构。自然语言输入可以是中文或英文；规范 DSL 的关键字固定为英文。

设计目标：

1. **可读：** 直接表达“持续成立”“至少成立一次”“变为真”等概念。
2. **确定：** 合法文本具有唯一语法解析，在明确的时间模型和信号解释下具有唯一语义。
3. **可组合：** 时序、逻辑和事件结构可以递归组合，不以固定需求模板限制表达能力。
4. **可映射：** 每个结构都有确定的逻辑展开，不需要第二次自然语言推断。
5. **可检查：** 信号、类型、单位、时间边界及参数均有静态约束。

“完整”指本规范所声明语言范围内的词法、文法和语义完整，不表示能够表达任意自然语言需求或所有 STL 扩展。语言不负责替用户决定模糊阈值、修复互相矛盾的需求或推断未声明的物理关系。

本规范中的“必须”“禁止”是规范要求，“建议”是使用建议。形式映射的目标是抽象 STL 及明确标注的扩展，不是某个工具的字符串语法。

## 2. 文档结构与最小示例

一个完整 DSL 文档由版本、时间模型、声明和一个或多个命名需求构成。

```text
language NLSTL version 1;
time model dense;

signal `temperature` : number unit kelvin;
enum `FanState` { `OFF`, `ON` };
signal `fan` : enum `FanState`;

requirement `cooling_response` {
  whenever {
    `temperature` is greater than 353.15 kelvin
  } then {
    at least once in the next [0, 5] seconds {
      throughout the next [0, 10] seconds {
        `fan` is equal to `FanState`.`ON`
      }
    }
  }
}
```

含义：从评价起点起，每当温度高于 353.15 K，就存在一个相对该时刻不晚于 5 秒的时刻，从那里起风扇连续开启 10 秒。该需求不要求风扇在这段运行开始之前关闭。

抽象映射：

\[
G_{[0,\infty)}\bigl(temperature>353.15\ \rightarrow
F_{[0,5]}G_{[0,10]}(fan=FanState.ON)\bigr).
\]

所有公式中的物理量在映射前转换为本规范的基准单位。示例中的数学公式为简洁起见省略单位标记。

多个 `requirement` 各自可单独检查；文档整体满足，当且仅当所有需求在同一个评价时刻都满足。声明顺序不产生执行顺序。语言描述性质，不描述命令执行流程。

## 3. 能力划分与表达边界

### 3.1 逻辑能力

| 能力 | 结构 | 时间模型 |
|---|---|---|
| 核心 | 数值/布尔/枚举条件，逻辑组合，未来 `G/F/U` | dense、sampled |
| 过去扩展 | 过去 `H/O/S` | dense、sampled |
| 边沿扩展 | `becomes true`、`becomes false` | 仅 sampled |
| 语法简写 | `whenever`、`never`、限时保持 | 展开后按所用能力判断 |

逻辑结构不限制嵌套深度；实现可以声明资源上限，但不能把上限当成语言的语义。

过去算子可以作用于含未来算子的子公式，边沿也可以作用于任意公式。这些性质可能需要离线观察未来，不能仅因语法合法就声称可以无延迟在线监测。

### 3.2 不在第一版范围内

- 对对象集合的量化、对象动态创建、空间逻辑。
- 信号值冻结及跨时刻值比较，例如“未来速度比触发时速度高 5”。
- 导数、积分、计数、概率、累计保持时长、恰好发生 N 次。
- 弱 until、release、显式 previous/next 算子的表层语法。
- 任意时间点命名、日历时间、跨需求引用、用户自定义递归宏。
- dense 模型中的边沿检测。
- 定量鲁棒性语义、信号插值、有限轨迹截断评价算法。

这不妨碍通过外部建模提供已经计算好的数值或事件信号；但必须显式声明该信号，其来源不能由 DSL 默默假定。

## 4. 词法规则

### 4.1 字符、空白和注释

- 编码为 UTF-8。关键字和单位大小写敏感，使用文法给出的拼写。
- 空格、制表符和换行只分隔词法单元，不改变语义。
- `#` 到行末为注释；注释内可使用中文。
- 标识符总是用反引号包围，如 `` `speed` ``。内部只允许 ASCII 字母、数字和下划线，且首字符不能为数字。
- 第一版不提供字符串字面量、转义标识符或隐式自然语言别名。
- 标识符不会与关键字混淆；关键字不能替代标识符的反引号。

### 4.2 数值

无符号数 `Number` 满足：

```text
(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?
```

示例：`0`、`0.5`、`12`、`1e-3`。禁止 `01`、`.5`、`1.`、`NaN`。正负号由文法的有符号字面量或一元算术处理。

`infinity` 仅用于时间区间的上界，不是可参与算术的数值。

数值语义按精确十进制有理数解释，不以二进制浮点舍入决定端点或相等性。实际实现若使用有限精度，应报告精度策略。

### 4.3 单位

第一版采用固定单位表，不允许拼写别名或隐式单位推断。

| 单位关键字 | 维度 | 转换到基准单位 |
|---|---|---|
| `unitless` | 无量纲 | 1 |
| `seconds` | 时间 T | 1 s |
| `milliseconds` | 时间 T | 0.001 s |
| `minutes` | 时间 T | 60 s |
| `meters` | 长度 L | 1 m |
| `centimeters` | 长度 L | 0.01 m |
| `meters_per_second` | L/T | 1 m/s |
| `kilometers_per_hour` | L/T | 5/18 m/s |
| `meters_per_second_squared` | L/T² | 1 m/s² |
| `kelvin` | 温度 Θ | 1 K |
| `radians` | 角度 A | 1 rad |

未带单位的数值是无量纲数值，不能自动继承比较对象的单位。角度在本语言中保留独立维度。第一版不包含摄氏度等带偏移的单位，避免绝对温度与温差运算的混淆。

时间文法中的 `TimeUnit` 仅允许 `seconds`、`milliseconds`、`minutes`。采样间隔也用物理时间描述，不提供含义可能不清楚的 `steps`。

## 5. 完整 EBNF

记号：`=` 定义；`|` 选择；`[ ... ]` 表示可选；`{ ... }` 表示重复零次或多次；双引号中的内容是文本终结符。EBNF 中未加引号的括号用于分组。多词终结符之间允许一个或多个空白或注释分隔，不要求同一行。

文法中出现的字符级标识符、数字规则在本节末定义。词法扫描使用最长合法单元；`>=` 等符号不属于语言的表层比较语法。

```ebnf
Document       = "language", "NLSTL", "version", "1", ";",
                 TimeModel, { Declaration }, Requirement, { Requirement } ;

TimeModel      = "time", "model", "dense", ";"
               | "time", "model", "sampled", "every",
                 Number, TimeUnit, ";" ;

Declaration    = EnumDecl | SignalDecl | ParameterDecl ;
EnumDecl       = "enum", Id, "{", Id, { ",", Id }, "}", ";" ;
SignalDecl     = "signal", Id, ":", Type, ";" ;
ParameterDecl  = "parameter", Id, ":", Type,
                 [ "=", Literal ], ";" ;
Type           = "number", "unit", Unit
               | "boolean"
               | "enum", Id ;

Requirement    = "requirement", Id, Block ;
Block          = "{", Formula, "}" ;

Formula        = "true"
               | "false"
               | Predicate
               | "all", "of", "{", Formula, ";",
                    Formula, ";", { Formula, ";" }, "}"
               | "any", "of", "{", Formula, ";",
                    Formula, ";", { Formula, ";" }, "}"
               | "it", "is", "not", "the", "case", "that", Block
               | "if", Block, "then", Block
               | "whenever", Block, "then", Block
               | "throughout", FutureWindow, Block
               | "at", "least", "once", "in", FutureWindow, Block
               | "throughout", PastWindow, Block
               | "at", "least", "once", "in", PastWindow, Block
               | "keep", Block, "until", FutureWindow, Block
               | "keep", Block, "since", PastWindow, Block
               | "becomes", "true", Block
               | "becomes", "false", Block
               | "never", "in", FutureWindow, Block
               | "within", Duration, "hold", "for", Duration, Block ;

FutureWindow   = "the", "next", Interval, TimeUnit
               | "the", "entire", "future" ;
PastWindow     = "the", "previous", Interval, TimeUnit
               | "the", "entire", "past" ;

Interval       = "[", Bound, ",", Bound, "]"
               | "[", Bound, ",", Bound, ")"
               | "(", Bound, ",", Bound, "]"
               | "(", Bound, ",", Bound, ")"
               | "[", Bound, ",", "infinity", ")"
               | "(", Bound, ",", "infinity", ")" ;
Bound          = Number | Id ;
Duration       = Number, TimeUnit | Id ;

Predicate      = Scalar, "is", Comparator, Scalar
               | Scalar, "is", "in", ValueRange ;
Comparator     = "equal", "to"
               | "not", "equal", "to"
               | "less", "than"
               | "less", "than", "or", "equal", "to"
               | "greater", "than"
               | "greater", "than", "or", "equal", "to" ;
ValueRange     = "[", Scalar, ",", Scalar, "]"
               | "[", Scalar, ",", Scalar, ")"
               | "(", Scalar, ",", Scalar, "]"
               | "(", Scalar, ",", Scalar, ")" ;

Scalar         = Sum ;
Sum            = Product, { ( "+" | "-" ), Product } ;
Product        = Unary, { ( "*" | "/" ), Unary } ;
Unary          = ( "+" | "-" ), Unary | Primary ;
Primary        = Number, [ Unit ]
               | "true" | "false"
               | Id
               | Id, ".", Id
               | "(", Scalar, ")"
               | "absolute", "value", "of", "(", Scalar, ")" ;

Literal        = [ "+" | "-" ], Number, [ Unit ]
               | "true" | "false"
               | Id, ".", Id ;

TimeUnit       = "seconds" | "milliseconds" | "minutes" ;
Unit           = "unitless" | TimeUnit
               | "meters" | "centimeters"
               | "meters_per_second" | "kilometers_per_hour"
               | "meters_per_second_squared"
               | "kelvin" | "radians" ;

Id             = "`", Name, "`" ;
Name           = ( Letter | "_" ), { Letter | Digit | "_" } ;
Letter         = "A" | "B" | "C" | "D" | "E" | "F" | "G"
               | "H" | "I" | "J" | "K" | "L" | "M" | "N"
               | "O" | "P" | "Q" | "R" | "S" | "T" | "U"
               | "V" | "W" | "X" | "Y" | "Z"
               | "a" | "b" | "c" | "d" | "e" | "f" | "g"
               | "h" | "i" | "j" | "k" | "l" | "m" | "n"
               | "o" | "p" | "q" | "r" | "s" | "t" | "u"
               | "v" | "w" | "x" | "y" | "z" ;
Digit          = "0" | "1" | "2" | "3" | "4"
               | "5" | "6" | "7" | "8" | "9" ;
NonzeroDigit   = "1" | "2" | "3" | "4" | "5"
               | "6" | "7" | "8" | "9" ;
Number         = ( "0" | NonzeroDigit, { Digit } ),
                 [ ".", Digit, { Digit } ],
                 [ ( "e" | "E" ), [ "+" | "-" ], Digit, { Digit } ] ;
```

`Name`、`Number` 及其字符级子规则内部禁止插入空白或注释；反引号与名称之间也禁止空白。`Number` 的字符级定义与第 4.2 节的正则表达式等价。

补充解析规则：

- 文法先识别完整多词比较短语；例如 `less than or equal to` 不可截断成 `less than`。
- 算术从高到低优先级：括号/绝对值、一元正负号、乘除、加减。同级二元算术左结合。
- 逻辑与时序没有隐式优先级；作用域完全由 `Block` 和列表边界决定。
- `all of`、`any of` 至少有两个子公式，每个子公式后必须有分号。
- 其他 `Block` 恰好包含一个公式，不在末尾添加分号；声明必须以分号结束。
- 枚举常量必须写为 `` `EnumName`.`MEMBER` ``，禁止只写成员名。
- `true` 和 `false` 单独出现时为常量公式；在比较操作数位置为布尔标量。比较短语决定是否构成 `Predicate`。
- 自然语言备注只能放在注释中，不得夹入公式作为未解析文本。

## 6. 声明、类型与绑定

### 6.1 名称与作用域

枚举类型、信号、参数和需求名称共享文档级命名空间，必须唯一。枚举成员在各自枚举内唯一，允许不同枚举有同名成员。

所有声明位于需求之前；声明之间允许前向引用枚举类型，按完整声明表解析。参数不能引用另一参数作为默认值，避免默认绑定顺序和循环定义问题。

标量位置的单独 `Id` 只能引用信号或参数；不能引用需求或枚举类型。需求之间不能引用，必须显式书写所需子公式。

### 6.2 类型规则

| 操作 | 允许类型 | 结果 |
|---|---|---|
| `equal to`、`not equal to` | 同维度数值；两个布尔；同一枚举的值 | 公式 |
| 四种大小比较 | 同维度数值 | 公式 |
| `is in` | 被比较值和两个端点均为同维度数值 | 公式 |
| `+`、`-` | 同维度数值 | 原维度数值 |
| `*` | 数值 | 维度相乘 |
| `/` | 数值，且分母满足下述限制 | 维度相除 |
| 一元正负号、绝对值 | 数值 | 原维度数值 |
| 逻辑、时序、边沿操作 | 公式 | 公式 |

禁止布尔与数字的隐式转换，禁止枚举排序，禁止不同枚举之间比较。数值信号每个时刻取有限实数值；布尔和枚举信号每个时刻必须有合法值。

**除法约束：** 分母必须为不含信号的数值表达式，并在参数绑定后可求值得到非零常数。第一版不支持信号作除数，以避免信号某时刻取零使谓词语义未定义。嵌套除法同样逐层检查。

数值范围的两个端点也必须不含信号。绑定后下界不能大于上界；相等时仅允许闭区间。`is in` 不接受无限端点；单侧约束使用大小比较。

例：

```text
signal `speed` : number unit meters_per_second;
parameter `limit` : number unit kilometers_per_hour = 72 kilometers_per_hour;
```

`` `speed` is less than `limit` `` 合法，相当于 `speed < 20 m/s`。`` `speed` is less than 72 `` 不合法，因为 `72` 无量纲。

算术可产生单位表没有直接命名的派生维度；比较双方最终维度一致即可。例如两个以米为单位的信号相乘，可与 `4 meters * 5 meters` 比较。

### 6.3 参数

参数为跨时间不变的量；默认值必须与声明类型一致，数值默认值必须同维度。参数可以不带默认值，此时文档是**参数化规格**。

参数化规格的含义是以绑定为索引的一族公式。具体求值或导出不支持符号参数的目标公式前，必须为每个参数提供一个类型正确的有限绑定。外部显式绑定覆盖默认值；没有显式绑定时使用默认值。

缺失绑定不是 `false`，不能用零或任意常数补齐。完整语言允许参数化规格，但**可直接执行的实例**必须完成绑定及依赖绑定的检查。

### 6.4 时间参数

`Bound` 中的标识符必须引用时间维度的数值参数，不能是信号或无量纲参数。

```text
parameter `deadline` : number unit milliseconds = 5000 milliseconds;
```

`[0, `deadline`] seconds` 表示 `[0 s, 5 s]`：数值端点按区间后的单位解释，参数端点按其已声明的单位换算。不得再把参数值重复乘上后缀单位。

`Duration` 中的标识符也必须为时间参数。所有时间参数在用于区间或时长时必须满足相应非负/正值约束。

## 7. 时间模型与区间

### 7.1 公共信号模型

信号记为 \(\sigma\)，时间域记为 \(D\)。信号定义于从 0 开始的整个非负时间域，未来无限延伸；起点前没有历史。

- `dense`：\(D=\mathbb R_{\ge0}\)。
- `sampled every Δ unit`：\(D=\{k\Delta\mid k\in\mathbb N_0\}\)，\(\Delta>0\)，换算到秒。

求值时刻 \(t\) 必须属于 \(D\)。默认需求评价时刻为 0；也可以由使用方显式指定 \(t_0\in D\)。改变评价时刻不会把信号历史起点重置为 \(t_0\)。

sampled 只对采样点作量化，不对两个采样点之间插值。dense 的公式语义按所有实数时刻定义；本规范不额外假定线性或分段常数插值。

### 7.2 时间窗口

区间端点经单位换算后必须满足 \(0\le a\le b\)。有限区间必须作为实数集合非空；当 \(a=b\) 时，只允许 `[a,a]`。无限上界始终开放，下界必须有限。

| 表达 | 解释 |
|---|---|
| `the next [a,b] seconds` | 相对当前求值时刻，未来偏移在闭区间内 |
| `the next (a,b] seconds` | 排除偏移 a，包含偏移 b |
| `the previous [a,b] seconds` | 向过去回看 a 到 b 秒 |
| `the entire future` | 未来偏移 `[0,infinity)` |
| `the entire past` | 过去偏移 `[0,infinity)`，受历史起点 0 限制 |

`next` 与 `previous` 的方向不自动排除当前时刻；是否包含当前取决于偏移 0 是否在区间内。

定义：

\[
W^+(t,I)=\{u\in D\mid u-t\in I\},\qquad
W^-(t,I)=\{u\in D\mid t-u\in I\}.
\]

例如 `the previous [2,5] seconds` 对应可用历史中的 \([t-5,t-2]\)，而不是 \([t+2,t+5]\)。若区间超出历史起点，仅对 \(D\) 中实际存在的历史点量化。

sampled 模型中的实数区间可不包含任何采样点，例如 Δ=1 秒、区间 `(0,1)`。这是合法空量化域，按第 8 节处理，不四舍五入端点。

### 7.3 嵌套参照

每进入一个时序算子的子公式，该子公式都在该算子选取或遍历的时刻求值。不存在隐式的“始终相对顶层起点”。

例如 \(F_{[2,5]}G_{[1,3]}P\) 选择 \(u\in[t+2,t+5]\)，再要求 \(P\) 在 \([u+1,u+3]\) 成立；它不要求 \(P\) 在 \(u\) 成立。

规范只支持局部相对时间。自然语言明确引用绝对起点但出现在嵌套关系中的情况，必须先获得等价的局部表达；不能直接套用本地窗口而改变参照点。

## 8. 组合语义与 STL 映射

记 \(\llbracket P\rrbracket\) 为 DSL 公式 P 的抽象逻辑翻译；\(\sigma,t\models P\) 表示 P 在 t 成立。令 \(v_t(e)\) 为标量 e 在 t 的值，数值已换算为基准单位。

### 8.1 原子条件与布尔结构

| DSL | 真值定义 / 映射 |
|---|---|
| `true` / `false` | \(\top\) / \(\bot\) |
| `e is equal to f` | \(v_t(e)=v_t(f)\) |
| `e is not equal to f` | \(v_t(e)\ne v_t(f)\) |
| `e is less than f` | \(v_t(e)<v_t(f)\) |
| `e is less than or equal to f` | \(v_t(e)\le v_t(f)\) |
| `e is greater than f` | \(v_t(e)>v_t(f)\) |
| `e is greater than or equal to f` | \(v_t(e)\ge v_t(f)\) |
| `e is in [l,h]` | \((l\le e)\land(e\le h)\) |
| `e is in [l,h)` | \((l\le e)\land(e<h)\) |
| `e is in (l,h]` | \((l<e)\land(e\le h)\) |
| `e is in (l,h)` | \((l<e)\land(e<h)\) |
| `all of { P; Q; ...; }` | 所有子公式成立，\(P\land Q\land\cdots\) |
| `any of { P; Q; ...; }` | 至少一个子公式成立，包含性或 \(P\lor Q\lor\cdots\) |
| `it is not the case that { P }` | \(\neg P\) |
| `if { P } then { Q }` | \(P\rightarrow Q\)，即 \(\neg P\lor Q\) |

表中 l、h 的求值不随时间变化。数值相等是精确相等，不自动加入容差；若需求要求容差，必须显式用范围或绝对差表示。

所有逻辑子公式均在同一当前求值时刻开始评价。“同时”因此体现为同一时刻上的合取，而不是两个独立存在量词。

### 8.2 单目时序

| DSL | STL | 成立条件 |
|---|---|---|
| `throughout the next I unit { P }` | \(G_I P\) | 对所有 \(u\in W^+(t,I)\)，P 在 u 成立 |
| `at least once in the next I unit { P }` | \(F_I P\) | 存在 \(u\in W^+(t,I)\)，P 在 u 成立 |
| `throughout the previous I unit { P }` | \(H_I P\) | 对所有 \(u\in W^-(t,I)\)，P 在 u 成立 |
| `at least once in the previous I unit { P }` | \(O_I P\) | 存在 \(u\in W^-(t,I)\)，P 在 u 成立 |

`the entire future/past` 分别替换为 \([0,\infty)\)。`F` 只要求至少一次满足，不表示“恰好一次”，也不要求此前为假。

**空量化域规则：** `G/H` 为真，`F/O` 为假。该规则同时适用于采样间隙和历史不足。例如 t=0 时，`throughout the previous (0,5] seconds { false }` 为真，因为没有任何历史点被量化。这是明确的历史起点语义，不代表已观测到 5 秒历史。

若业务需要“必须有足够历史才能判定”，应在应用层选择评价起点或增加显式历史可用信号；不能更改本语言的真值规则而仍声称采用同一语义。

### 8.3 Until：未来强直到

```text
keep { P } until the next I unit { Q }
```

映射为 \(P\ U_I\ Q\)，精确定义：

\[
\sigma,t\models P\ U_I\ Q
\iff
\exists u\in W^+(t,I):
\bigl(\sigma,u\models Q\bigr)\land
\bigl(\forall v\in D\cap[t,u),\ \sigma,v\models P\bigr).
\]

- Q 必须在窗口内成立；没有见证点则公式为假。
- P 从当前 t 开始保持，不能等到区间下界 a 才开始。
- P 不必在见证时刻 u 成立；Q 在 u 必须成立。
- 若 u=t，P 的维持区间为空，因此不要求当前 P 成立。
- u 不必是 Q 第一次成立的时刻；本结构没有“首次发生”限制。
- `the entire future` 使用相同定义的无界版本。

此处半开维持区间是本 DSL 的明确约定。目标工具若使用不同的终点约定，必须验证能否等价转换，禁止只替换算子拼写。

### 8.4 Since：过去强自从

```text
keep { P } since the previous I unit { Q }
```

映射为 \(P\ S_I\ Q\)，精确定义：

\[
\sigma,t\models P\ S_I\ Q
\iff
\exists u\in W^-(t,I):
\bigl(\sigma,u\models Q\bigr)\land
\bigl(\forall v\in D\cap(u,t],\ \sigma,v\models P\bigr).
\]

P 在见证时刻之后直到当前持续成立；不要求在 u 成立。若 u=t，维持区间为空。Q 必须在实际可用的历史窗口内有见证。`the entire past` 使用无界过去窗口。

### 8.5 边沿

仅 sampled 模型允许：

```text
becomes true { P }
becomes false { P }
```

对于 \(t=k\Delta,k\ge1\)：

\[
rise(P,k)=\neg P(k-1)\land P(k),\qquad
fall(P,k)=P(k-1)\land\neg P(k).
\]

式中 \(P(k)\) 简记 \(\sigma,k\Delta\models P\)。在初始样本 k=0，`rise(P)` 与 `fall(P)` **均为假**，因为不存在可观测的前一个样本。

它检测的是相邻采样点的公式真值变化，不保证两个采样点之间没有额外变化。若 P 含未来算子，计算前后两点的 P 可能都需要未来数据。

边沿可保留为上述定义的扩展算子，也可在 sampled+过去扩展中精确展开：

\[
rise(P)=P\land O_{[\Delta,\Delta]}(\neg P),\qquad
fall(P)=\neg P\land O_{[\Delta,\Delta]}P.
\]

根据空历史存在量词为假的规则，这个展开在 k=0 同样使两种边沿为假。禁止使用 \(P\land\neg O_{[\Delta,\Delta]}P\) 代替前一个式子，因为其起点行为不同。

`dense` 文档出现边沿结构是静态错误，不通过隐式微小 ε 或采样假设转换。

### 8.6 自然语言简写

以下三种是唯一内置宏，没有独立于展开式的新语义。

| 简写 | 唯一展开 |
|---|---|
| `whenever { P } then { Q }` | `throughout the entire future { if { P } then { Q } }` |
| `never in W { P }`，W 为 FutureWindow | `throughout W { it is not the case that { P } }` |
| `within d hold for h { P }` | `at least once in the next [0,d] seconds { throughout the next [0,h] seconds { P } }`，d、h 先换算为秒 |

第三项中 `d≥0`、`h>0`，均必须有限。h 表示至少覆盖长度为 h 的闭区间，不表示恰好 h 后结束；也不要求 P 从假变真。

合法示例：

```text
within 5 seconds hold for 10 seconds {
  `fan` is equal to `FanState`.`ON`
}
```

禁止自动把 `if` 加上全局量化，也禁止自动把 `whenever { P }` 改成 `whenever { becomes true { P } }`。P 连续为真时，前者在每个时刻都产生响应义务。

### 8.7 原子谓词与目标 STL 的关系

本 DSL 的数值谓词是同一时刻标量表达式之间的比较，可以视为 STL 的实值谓词函数。比较运算符、算术和枚举符号是抽象表示的一部分。

如果后端只接受某一类原子不等式，输出方必须对支持的比较作等价展开；不支持的算术或相等关系须明确拒绝。枚举编码必须为同一枚举的不同成员分配不同值，并随输出提供编码表。不得利用编码顺序赋予枚举原本不存在的大小关系。

本规范只保证布尔满足语义，不定义不同谓词编码的鲁棒度是否相等。

## 9. 全局、局部和多需求语义

`requirement` 包装本身不增加 `G`。例如：

```text
requirement `initial_speed` {
  `speed` is less than 20 meters_per_second
}
```

仅要求评价时刻速度低于阈值。要表达始终满足，必须显式写：

```text
requirement `speed_limit` {
  throughout the entire future {
    `speed` is less than 20 meters_per_second
  }
}
```

文档 \(R_1,\ldots,R_n\) 的整体映射为 \(\bigwedge_i\llbracket R_i\rrbracket\)。保留需求名称用于定位，但名称不参与真值计算。

嵌套 `whenever` 同样相对其当前求值时刻向未来展开，不具有“只触发一次”的特殊含义。全局响应中前件一直为假时公式为真，这是蕴含的正常空满足，不自动添加触发必须发生的要求。

## 10. 规范表达与等价性

### 10.1 建议的规范输出

为减少 NL → DSL 标签的表面差异，规范输出遵循：

1. 保留版本与时间模型；声明位于需求前。
2. 名称使用反引号，缩进两个空格，每层分组显式书写。
3. 所有时间单位规范为 `seconds`；其他数值单位保留已声明单位或等价基准单位，但一个数据任务应固定一种策略。
4. 未指定局部时间上界且确实表达整个未来/过去时，使用 `the entire future/past`。
5. 常见全局条件响应用 `whenever`；限时保持可使用内置简写，也可展开，但同一训练任务必须固定选择。本规范默认规范标签**展开限时保持和 never，保留 whenever**。
6. 保留原始逻辑子项顺序和明确的否定作用域；不为追求短公式擅自重写。
7. 参数名称、枚举及需求名称保留，避免规范化丢失领域含义。

确定语义不要求所有逻辑等价公式都只有一种文本。规范输出是减少表面变体的约定，不是完备的逻辑等价判定算法。

### 10.2 可用但不强制的布尔等价式

在本规范的二值语义下：

\[
\neg F_I P\equiv G_I\neg P,\quad
\neg G_I P\equiv F_I\neg P,
\]
\[
\neg O_I P\equiv H_I\neg P,\quad
\neg H_I P\equiv O_I\neg P.
\]

这些式子也遵守空量化域规则。不能把 \(\neg(P\ U_I\ Q)\) 直接变成 \((\neg P)\ U_I\ Q\)，不能交换 `F` 与 `G` 的顺序，也不能把 \(F(P\land Q)\) 分配为 \(FP\land FQ\)。

## 11. 合法性与错误分类

语法合法不代表类型正确，也不代表需求可满足。按以下顺序判断：词法/语法、名称解析、类型和单位、参数绑定、区间与算术约束、模型能力、目标方言能力。

| 错误类别 | 触发条件 | 处理原则 |
|---|---|---|
| `SYNTAX_ERROR` | 缺括号、非法短语、列表不足两项等 | 拒绝解释该文本 |
| `DUPLICATE_NAME` | 文档级重名或枚举内成员重名 | 要求消除重名 |
| `UNKNOWN_NAME` | 未声明信号、参数、类型或枚举成员 | 不发明信号映射 |
| `TYPE_MISMATCH` | 布尔排序、跨枚举比较等 | 不做隐式强制转换 |
| `UNIT_MISMATCH` | 比较或加减维度不一致 | 不猜测遗漏单位 |
| `UNBOUND_PARAMETER` | 执行实例缺参数绑定 | 保留参数化状态，不能给出实例真值 |
| `INVALID_INTERVAL` | 负边界、上下界颠倒、有限实数空区间 | 不交换或裁剪端点 |
| `INVALID_DURATION` | Δ≤0、保持时长≤0、延迟<0 | 不自动改为最小正数 |
| `INVALID_ARITHMETIC` | 分母含信号或常量分母为零 | 拒绝该表达式 |
| `INVALID_RANGE_BOUND` | 数值范围端点含信号或无效 | 使用普通比较表达动态关系 |
| `MODEL_UNSUPPORTED` | dense 中出现边沿 | 不隐式转换为 sampled |
| `TARGET_UNSUPPORTED` | 后端无法保留开端点、过去算子或谓词等 | 拒绝该目标导出，DSL 本身可仍合法 |

不满足的性质不是语法错误。例如 `all of { true; false; }` 是合法但永不满足的公式。静态检查不承诺完成一般可满足性分析。

下列是 NL → DSL 阶段的未决信息，不能作为 DSL 公式节点：

- “尽快”“稳定一段时间”等没有确定阈值或时间。
- “在范围内”没有端点包含性，且领域没有显式约定。
- “当 P 时”无法确定指持续状态还是从假变真。
- 代词或领域术语无法唯一对应信号。
- “直到”无法确定是否要求目标最终发生。

这些情况应由翻译系统向外报告待澄清内容。本规范不定义交互协议；禁止把 `unknown` 或自然语言占位语句当成可以直接执行的公式。

## 12. 成对示例：容易混淆的语义

本节代码为公式片段，放入 `requirement` 的外层花括号即可。假定有以下声明；含边沿的示例采用 1 秒采样模型，其余示例可使用两种时间模型。

```text
signal `p` : boolean;
signal `q` : boolean;
signal `speed` : number unit meters_per_second;
```

公式简记 P 为 `` `p` is equal to true ``，Q 同理。这些 P、Q 是说明记号，不是可直接写入 DSL 的标识符占位语法。

### 12.1 持续成立 / 至少一次

```text
throughout the next [0, 5] seconds {
  `p` is equal to true
}
```

```text
at least once in the next [0, 5] seconds {
  `p` is equal to true
}
```

分别为 \(G_{[0,5]}P\) 与 \(F_{[0,5]}P\)。P 只在第 3 秒成立时，第二项可以满足，第一项不满足。

### 12.2 共同一次 / 分别一次

```text
at least once in the next [0, 5] seconds {
  all of {
    `p` is equal to true;
    `q` is equal to true;
  }
}
```

```text
all of {
  at least once in the next [0, 5] seconds {
    `p` is equal to true
  };
  at least once in the next [0, 5] seconds {
    `q` is equal to true
  };
}
```

分别为 \(F_{[0,5]}(P\land Q)\) 与 \(F_{[0,5]}P\land F_{[0,5]}Q\)。若 P 仅在第 1 秒、Q 仅在第 4 秒成立，只有第二项满足。

### 12.3 并非一直成立 / 一直不成立

```text
it is not the case that {
  throughout the next [0, 5] seconds {
    `p` is equal to true
  }
}
```

```text
throughout the next [0, 5] seconds {
  it is not the case that {
    `p` is equal to true
  }
}
```

分别为 \(\neg G_{[0,5]}P\) 和 \(G_{[0,5]}\neg P\)。前者只需有一个时刻 P 为假，后者要求全部时刻为假。

### 12.4 状态触发 / 边沿触发

```text
whenever {
  `p` is equal to true
} then {
  at least once in the next [0, 2] seconds {
    `q` is equal to true
  }
}
```

```text
whenever {
  becomes true {
    `p` is equal to true
  }
} then {
  at least once in the next [0, 2] seconds {
    `q` is equal to true
  }
}
```

分别为 \(G(P\to F_{[0,2]}Q)\) 与 \(G(rise(P)\to F_{[0,2]}Q)\)。在 sampled 模型中，若 P 在样本 1 变真并一直为真，Q 仅在样本 2 为真，第二项满足，第一项因后续响应缺失而不满足。

### 12.5 当前条件 / 全局条件

```text
if { `p` is equal to true } then { `q` is equal to true }
```

```text
whenever { `p` is equal to true } then { `q` is equal to true }
```

分别为 \(P\to Q\) 和 \(G(P\to Q)\)。评价时刻 P 为假不代表第二个需求在未来也满足。

### 12.6 最终保持 / 持续可达

```text
at least once in the next [0, 5] seconds {
  throughout the next [0, 10] seconds {
    `p` is equal to true
  }
}
```

```text
throughout the next [0, 5] seconds {
  at least once in the next [0, 10] seconds {
    `p` is equal to true
  }
}
```

分别为 \(F_{[0,5]}G_{[0,10]}P\) 和 \(G_{[0,5]}F_{[0,10]}P\)。前者要求存在连续维持区间；后者允许不同起点由不同的未来见证满足，也可能由同一个见证满足。

### 12.7 严格截止 / 包含截止

```text
at least once in the next [0, 5) seconds {
  `p` is equal to true
}
```

```text
at least once in the next [0, 5] seconds {
  `p` is equal to true
}
```

如果 P 在窗口中仅于第 5 秒成立，只有第二项满足。禁止把开端点偷偷改为闭端点。

### 12.8 过去曾经 / 过去一直

```text
at least once in the previous [0, 5] seconds {
  `p` is equal to true
}
```

```text
throughout the previous [0, 5] seconds {
  `p` is equal to true
}
```

分别为 \(O_{[0,5]}P\) 和 \(H_{[0,5]}P\)。两者都包含当前时刻；要排除当前，使用 `(0,5]`。

### 12.9 Until / 两个独立要求

```text
keep { `p` is equal to true }
until the next [2, 5] seconds { `q` is equal to true }
```

```text
all of {
  throughout the next [0, 2] seconds { `p` is equal to true };
  at least once in the next [2, 5] seconds { `q` is equal to true };
}
```

第一项要求 P 保持到某个 Q 见证之前，可能超过第 2 秒；第二项只要求 P 保持到第 2 秒。因此两者不等价。第一项并不要求 P 在 Q 的见证时刻继续成立。

### 12.10 否定边沿 / 否定状态

```text
it is not the case that {
  becomes true { `p` is equal to true }
}
```

```text
it is not the case that { `p` is equal to true }
```

分别为 \(\neg rise(P)\) 和 \(\neg P\)。P 连续为真时，“没有变真事件”仍为真，但“状态为假”为假。

## 13. 其他构造示例

以下也为公式片段，相关名称须预先声明。

### 13.1 数值范围与容差

```text
`speed` is in [10 meters_per_second, 20 meters_per_second)
```

映射为 \(10\le speed<20\)，实际输出可拆为合取。

```text
absolute value of (`speed` - 15 meters_per_second)
is less than or equal to 0.5 meters_per_second
```

映射为 \(|speed-15|\le0.5\)。容差由文本明确给出，不由相等运算默认附加。

### 13.2 Since

```text
keep { `p` is equal to true }
since the previous [1, 5] seconds { `q` is equal to true }
```

过去 1 到 5 秒内存在 Q 成立的时刻，从该时刻之后到现在 P 持续成立，映射为 \(P\ S_{[1,5]}\ Q\)。不要求所选时刻是 Q 最近一次或第一次成立。

### 13.3 变假

```text
becomes false { `p` is equal to true }
```

当前样本 P 为假、上一样本 P 为真；初始样本为假。

### 13.4 全局重复响应

```text
throughout the entire future {
  at least once in the next (0, 5] seconds {
    `p` is equal to true
  }
}
```

每个时刻之后严格未来的 5 秒内都有 P 成立的见证，映射为 \(G F_{(0,5]}P\)。它不要求以恰好 5 秒的固定周期发生。

### 13.5 禁止事件

```text
never in the next [0, 10] seconds {
  becomes true { `p` is equal to true }
}
```

在 sampled 模型中映射为 \(G_{[0,10]}\neg rise(P)\)。它禁止新的变真边沿，并不要求 P 一直为假。

### 13.6 时间相等与延后无界

```text
at least once in the next [3, 3] seconds {
  `p` is equal to true
}
```

要求恰好偏移 3 秒的时间点 P 成立。若 sampled 模型中没有该采样点，存在量词为假。

```text
throughout the next (5, infinity) seconds {
  `p` is equal to true
}
```

严格超过当前 5 秒后的所有时刻 P 都成立，不要求第 5 秒本身成立。

### 13.7 析取、不等与算术

```text
any of {
  `p` is not equal to true;
  `speed` / 2 is greater than 5 meters_per_second;
}
```

含义为 P 为假，或者速度的一半大于 5 m/s，也允许两者同时成立。常量无量纲分母 `2` 合法；若分母改成信号则不合法。

```text
all of {
  `speed` is greater than or equal to 0 meters_per_second;
  `speed` is less than 20 meters_per_second;
}
```

显式表达闭下界、开上界，与第 13.1 节相应范围谓词的展开方式一致。

## 14. 完整参数化文档示例

```text
language NLSTL version 1;
time model sampled every 100 milliseconds;

enum `Mode` { `IDLE`, `RUN` };
signal `mode` : enum `Mode`;
signal `speed` : number unit meters_per_second;
signal `ready` : boolean;
parameter `limit` : number unit meters_per_second = 20 meters_per_second;
parameter `deadline` : number unit seconds = 2 seconds;

requirement `speed_bound` {
  throughout the entire future {
    `speed` is less than or equal to `limit`
  }
}

requirement `run_response` {
  whenever {
    becomes true {
      `mode` is equal to `Mode`.`RUN`
    }
  } then {
    at least once in the next [0, `deadline`] seconds {
      `ready` is equal to true
    }
  }
}

requirement `run_history` {
  whenever {
    `mode` is equal to `Mode`.`RUN`
  } then {
    at least once in the previous [0, 1] seconds {
      `ready` is equal to true
    }
  }
}
```

默认绑定下，整体逻辑为：

\[
G(speed\le20)
\land G(rise(mode=RUN)\rightarrow F_{[0,2]}ready)
\land G(mode=RUN\rightarrow O_{[0,1]}ready).
\]

其中 sampled 的 Δ=0.1 秒；初始已经处于 RUN 不构成进入 RUN 的边沿。过去窗口包含当前，所以第三项允许由当前 ready 满足。若需要严格先于当前，应显式改用 `(0,1]`。

## 15. 有限轨迹与目标适配边界

语言真值定义于第 7 节的完整信号。有限日志只是信号的部分观测：未来缺失不自动等于未来为假，也不自动等于需求满足。

对有限日志给出三值结果、截断结果或鲁棒度属于监测器的额外契约，必须标明，不能冒充本规范完整信号上的二值真值。特别是无界最终、无界始终不能通过擅自替换为“日志结束前”保持原语义。

目标适配应至少声明以下能力：

- dense 或 sampled，以及采样间隔。
- 有限开闭区间、单点区间、非零下界的无界区间。
- 过去算子及第 8 节的历史起点规则。
- until/since 的维持端点约定。
- 边沿初始值，或相同语义的展开能力。
- 数值、布尔、枚举及原子算术支持。
- 参数是保留符号还是先绑定。

在均匀 sampled 模型中，时间窗口可以精确转为整数偏移集合。例如 \(\Delta=1\) 秒时 `(0,5)` 对应偏移 `{1,2,3,4}`。这种转换必须按集合等价进行；dense 模型不能用减去任意 ε 模拟开区间。

“可解析”“可由目标工具执行”和“与原始 NL 意图一致”是三个不同检查对象。一个编译映射即使严格保留 DSL 语义，也不能单独证明 NL 翻译正确。

## 16. 语言覆盖与验收清单

| 需求组成 | 规范位置 |
|---|---|
| 标识符、数值、注释、单位 | 第 4 节 |
| 完整文本结构与递归文法 | 第 5 节 |
| 类型、声明、参数、算术 | 第 6 节 |
| 时间方向、开闭边界、参照点 | 第 7 节 |
| 数值/布尔/枚举条件 | 第 8.1 节 |
| 未来持续、未来可达 | 第 8.2 节 |
| 历史持续、过去曾经 | 第 8.2 节 |
| 强直到、强自从 | 第 8.3—8.4 节 |
| 变真、变假及其否定 | 第 8.5 节、第 12.10 节 |
| 条件响应、禁止、限时保持 | 第 8.6 节 |
| 多需求与全局/局部作用域 | 第 9 节 |
| 规范写法与等价性边界 | 第 10 节 |
| 错误及未决自然语言信息 | 第 11 节 |
| 成对语义示例和完整文档 | 第 12—14 节 |
| 有限轨迹与目标适配 | 第 15 节 |

一个实现声称符合 NLSTL-DSL 1.0 时，应能依据本文件完成全部文法解析、类型与单位检查，并遵守其宣称支持的能力的语义。若只支持其中一个子集，应明确列出该子集；不得静默丢弃、近似或改写不支持的结构。
