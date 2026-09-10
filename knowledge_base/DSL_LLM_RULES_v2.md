# DSL 表述定义

## 1. 基础约定

- 信号使用反引号包围，如 `` `sig1` ``，名称不携带预设含义。比较对象可以是信号或数字；数字不附加物理单位。
- 时间使用抽象的 `time units`。有限时间区间 `[a, b]` 包含两端，满足 `0 ≤ a ≤ b`。
- `P`、`Q` 表示任意子表达式，`e`、`f` 表示信号或数字，`W` 表示时间窗口。这些是定义中的占位符，实际书写时替换为具体内容。
- 普通 `{ ... }` 内恰好一个表达式，不加末尾分号。`all of`、`any of` 内至少两个表达式，每项以分号结束。
- 以下结构均可递归组合；花括号决定作用域。单独的比较只在当前求值时刻判断，不隐含持续要求。

## 2. 比较表述

| 形式 | 含义 | 例子 |
|---|---|---|
| `e is equal to f` | e 等于 f | `` `sig1` is equal to `sig2` `` |
| `e is not equal to f` | e 不等于 f | `` `sig1` is not equal to 0 `` |
| `e is less than f` | e 严格小于 f | `` `sig1` is less than 5 `` |
| `e is less than or equal to f` | e 小于或等于 f | `` `sig1` is less than or equal to 5 `` |
| `e is greater than f` | e 严格大于 f | `` `sig1` is greater than 2 `` |
| `e is greater than or equal to f` | e 大于或等于 f | `` `sig1` is greater than or equal to 2 `` |

## 3. 逻辑表述

### 全部满足

**形式：** `all of { P; Q; }`

**含义：** 所有子表达式在同一求值时刻都成立。允许两项以上。

**例子：** sig1 大于 2 且不超过 5，即位于范围 `(2, 5]`。

```text
all of {
  `sig1` is greater than 2;
  `sig1` is less than or equal to 5;
}
```

### 至少一项满足

**形式：** `any of { P; Q; }`

**含义：** 至少一个子表达式成立，允许多个同时成立。

**例子：** sig1 小于 0，或 sig2 大于 10，也允许两项都成立。

```text
any of {
  `sig1` is less than 0;
  `sig2` is greater than 10;
}
```

### 否定

**形式：** `it is not the case that { P }`

**含义：** 花括号内的整个表达式不成立。

**例子：** sig1 不位于闭区间 `[2, 5]`。

```text
it is not the case that {
  all of {
    `sig1` is greater than or equal to 2;
    `sig1` is less than or equal to 5;
  }
}
```

## 4. 条件表述

### 当前条件蕴含

**形式：** `if { P } then { Q }`

**含义：** 在当前求值时刻，若 P 成立，则 Q 必须成立；P 不成立时该表达式成立。不要求未来时刻也适用。

**例子：** 当前 sig1 大于 5 时，sig2 必须等于 1。

```text
if {
  `sig1` is greater than 5
} then {
  `sig2` is equal to 1
}
```

### 全局条件响应

**形式：** `whenever { P } then { Q }`

**含义：** 从当前起，每个 P 成立的时刻都要求 Q 在该时刻成立。Q 若包含时间窗口，其窗口相对于该时刻计算。不额外要求 P 必须发生。

**例子：** 从当前起，每当 sig1 大于 5，sig2 都必须同时等于 1。

```text
whenever {
  `sig1` is greater than 5
} then {
  `sig2` is equal to 1
}
```

## 5. 时间窗口

W 只能使用以下四种形式。t 为所在表达式的当前求值时刻。

| 形式 | 含义 | 例子 |
|---|---|---|
| `the next [a, b] time units` | 未来区间 `[t+a, t+b]` | `the next [2, 5] time units`：当前之后第 2 至第 5 个时间单位 |
| `the previous [a, b] time units` | 已有历史中的区间 `[t-b, t-a]` | `the previous [2, 5] time units`：回看第 2 至第 5 个时间单位 |
| `the entire future` | 当前及全部未来 | `the entire future`：没有未来截止时间 |
| `the entire past` | 全部已有历史及当前 | `the entire past`：没有有限回看上界 |

偏移 0 包含当前。嵌套表达式的窗口相对于外层选中或遍历的时刻，不始终相对于顶层起点。过去窗口只覆盖实际已有历史。

## 6. 时间表述

### 持续成立

**形式：** `throughout W { P }`

**含义：** 窗口 W 内每个时刻 P 都成立。W 可以是未来、过去、有界或无界窗口。

**例子：** 从当前起的 0 至 5 个时间单位内，sig1 始终小于 10。

```text
throughout the next [0, 5] time units {
  `sig1` is less than 10
}
```

**过去无界例子：** 全部已有历史及当前，sig1 始终等于 sig2。

```text
throughout the entire past {
  `sig1` is equal to `sig2`
}
```

### 至少成立一次

**形式：** `at least once in W { P }`

**含义：** 窗口 W 内至少存在一个时刻使 P 成立。不表示恰好一次，也不要求此前为假。W 可以使用全部四种窗口。

**例子：** 回看 2 至 5 个时间单位的已有历史内，sig1 至少有一个时刻等于 1。

```text
at least once in the previous [2, 5] time units {
  `sig1` is equal to 1
}
```

**未来无界例子：** 当前或未来某个时刻，sig1 等于 1。

```text
at least once in the entire future {
  `sig1` is equal to 1
}
```

若窗口内没有可评价时刻，持续表达式为真，至少一次表达式为假。

## 7. 保持关系

### 直到

**形式：** `keep { P } until W { Q }`，W 必须为未来窗口。

**含义：** W 内必须存在 Q 成立的时刻 u；P 从当前 t 持续到 u 之前，即 `[t,u)`。不要求 P 在 u 成立，也不要求 u 是 Q 首次成立的时刻。

**例子：** 未来第 2 至第 5 个时间单位内必须有 sig2 等于 1 的时刻，此前从当前起 sig1 一直小于 10。

```text
keep {
  `sig1` is less than 10
} until the next [2, 5] time units {
  `sig2` is equal to 1
}
```

无界形式使用 `until the entire future`，仍要求 Q 最终成立。

### 自从

**形式：** `keep { P } since W { Q }`，W 必须为过去窗口。

**含义：** W 内必须存在 Q 成立的历史时刻 u；P 从 u 之后持续到当前 t，即 `(u,t]`。不要求 P 在 u 成立，也不要求 u 是 Q 最近一次成立的时刻。

**例子：** 回看 1 至 5 个时间单位内曾有 sig2 等于 1 的时刻，此后直到当前 sig1 一直小于 10。

```text
keep {
  `sig1` is less than 10
} since the previous [1, 5] time units {
  `sig2` is equal to 1
}
```

无界形式使用 `since the entire past`，仍要求已有历史中存在 Q 的见证。两种保持关系在 u=t 时，P 的维持区间均为空。

## 8. 变化表述

### 变真

**形式：** `becomes true { P }`

**含义：** P 的真值由假变真，而不只是当前为真。

**例子：** sig1 从大于 5 变为不超过 5。

```text
becomes true {
  `sig1` is less than or equal to 5
}
```

### 变假

**形式：** `becomes false { P }`

**含义：** P 的真值由真变假，而不只是当前为假。

**例子：** sig1 从等于 sig2 变为不等于 sig2。

```text
becomes false {
  `sig1` is equal to `sig2`
}
```

P 可以是完整的逻辑或时间表达式。变化方向针对条件真值，不针对数值升降。具体变化观测方式和初始时刻处理由所采用的信号模型确定，本 DSL 不指定采样间隔。

## 9. 组合示例

### 条件触发后的限时响应

每当 sig1 大于 20，sig2 必须在相对该时刻的 0 至 3 个时间单位内至少等于 1 一次。

```text
whenever {
  `sig1` is greater than 20
} then {
  at least once in the next [0, 3] time units {
    `sig2` is equal to 1
  }
}
```

### 达到后保持

未来 0 至 5 个时间单位内，存在一个时刻，从该时刻起 sig1 持续等于 1 至少 10 个时间单位。不要求保持开始前为假，也不要求 10 个时间单位后变假。

```text
at least once in the next [0, 5] time units {
  throughout the next [0, 10] time units {
    `sig1` is equal to 1
  }
}
```

### 持续要求限时达到

未来 0 至 5 个时间单位内的每个时刻，都要求 sig1 在相对该时刻的 0 至 10 个时间单位内至少等于 1 一次。

```text
throughout the next [0, 5] time units {
  at least once in the next [0, 10] time units {
    `sig1` is equal to 1
  }
}
```

### 否定完整时间要求

未来 0 至 5 个时间单位内，sig1 并非始终大于 5；只需有一个时刻不大于 5。

```text
it is not the case that {
  throughout the next [0, 5] time units {
    `sig1` is greater than 5
  }
}
```

### 否定变化事件

当前未发生“sig1 大于 5”这一条件由假变真的变化；sig1 可以已经持续大于 5。

```text
it is not the case that {
  becomes true {
    `sig1` is greater than 5
  }
}
```

### 过去条件与未来响应

每当回看 0 至 8 个时间单位的已有历史中 sig1 曾大于等于 1，都要求 sig2 在相对当前的第 2 至第 5 个时间单位内至少等于 sig3 一次。

```text
whenever {
  at least once in the previous [0, 8] time units {
    `sig1` is greater than or equal to 1
  }
} then {
  at least once in the next [2, 5] time units {
    `sig2` is equal to `sig3`
  }
}
```
