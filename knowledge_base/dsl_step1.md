# 第一阶段：NL → DSL

## 1. 占位符与书写约定

| 记号 | 含义 |
|---|---|
| `e`、`f` | 信号或数值，如 `` `sig1` ``、`5.2` |
| `P`、`Q` | 任意完整 DSL 子表达式，可递归嵌套 |
| `a`、`b` | 时间下界与上界，满足 `0 ≤ a ≤ b` |
| `I` | 有限闭区间 `[a, b]`，包含两个端点 |
| `W` | 完整时间窗口，形式见下表 |

这些是规则占位符，实际表达式必须替换为具体内容，不是需要声明的信号或符号参数。

- 信号名称原样保留。数字可为整数或小数，不带物理单位。比较对象也可为另一信号。
- 时间使用抽象的 `time units`，不默认表示秒；时间端点与信号值阈值是不同的量。
- 普通 `{ ... }` 内恰好一个表达式，末尾不加分号；`all of`、`any of` 至少两项，每项以分号结束。
- 所有子表达式均可递归组合，花括号决定作用域。单独的比较不隐含全局要求。

| 时间窗口 W | 含义（t 为当前求值时刻） |
|---|---|
| `the next I time units` | 未来 `[t+a, t+b]` |
| `the previous I time units` | 已有历史中的 `[t-b, t-a]` |
| `the entire future` | 当前及全部未来 |
| `the entire past` | 全部已有历史及当前 |

内层时间窗口相对于外层选中或遍历的时刻；响应窗口相对于触发时刻。偏移 0 包含当前。本版有限时间窗口均为闭区间，数值范围仍区分开闭边界。

## 2. 全部可用表述与解释

| DSL 表述 | 含义 |
|---|---|
| `e is equal to f` | e 等于 f |
| `e is not equal to f` | e 不等于 f |
| `e is less than f` | e 严格小于 f |
| `e is less than or equal to f` | e 小于或等于 f |
| `e is greater than f` | e 严格大于 f |
| `e is greater than or equal to f` | e 大于或等于 f |
| `all of { P; Q; }` | 所有子表达式在同一求值时刻成立，允许多项 |
| `any of { P; Q; }` | 至少一项成立，允许同时成立，允许多项 |
| `it is not the case that { P }` | 花括号内的完整表达式不成立 |
| `if { P } then { Q }` | 当前若 P 成立则 Q 必须成立；P 为假时成立 |
| `whenever { P } then { Q }` | 从当前起，每个 P 成立的时刻都要求 Q 成立 |
| `throughout W { P }` | W 内每个时刻 P 都成立；适用全部四种窗口 |
| `at least once in W { P }` | W 内存在 P 成立的时刻；适用全部四种窗口 |
| `keep { P } until W { Q }` | W 为未来窗口；必须有 Q 成立的时刻 u，P 从当前 t 保持到 u 之前，即 `[t,u)` |
| `keep { P } since W { Q }` | W 为过去窗口；必须有 Q 成立的时刻 u，P 从 u 之后保持到当前 t，即 `(u,t]` |
| `becomes true { P }` | P 的真值由假变真，而不只是当前为真 |
| `becomes false { P }` | P 的真值由真变假，而不只是当前为假 |

- 数值范围用两个比较的合取表达；范围外否定整个合取。圆括号范围端点用严格比较，方括号端点用非严格比较。
- “至少一次”不表示恰好一次，也不要求此前为假。保持一段时间不要求开始前为假或结束后变假。
- until/since 不要求 Q 的见证为首次或最近一次；u=t 时维持区间为空。否定可以包围任何完整子表达式。
- 边沿也可作用于逻辑或时间表达式；变化方向针对条件真值，不等于数值升降。观测方式及初始边沿由信号模型确定。
- 过去仅包含已有历史；空窗口上持续为真，至少一次为假。

## 3. 必要示例

示例中的时间边界均采用上述闭区间约定。简单比较不单独举例。示例编号与第二阶段对应。

### E01 范围与合取

NL:

The value of sig1 must be greater than 2 and less than or equal to 5 at the current instant.

DSL:

```text
all of {
  `sig1` is greater than 2;
  `sig1` is less than or equal to 5;
}
```

### E02 析取

NL:

At the current instant, sig1 must be below 0 or sig2 must be above 10; both conditions may hold.

DSL:

```text
any of {
  `sig1` is less than 0;
  `sig2` is greater than 10;
}
```

### E03 否定整个范围

NL:

At the current instant, sig1 must be outside the range [2, 5].

DSL:

```text
it is not the case that {
  all of {
    `sig1` is greater than or equal to 2;
    `sig1` is less than or equal to 5;
  }
}
```

### E04 条件变真

NL:

At the current sample, the transition that sig1 decreases from above 5 to at most 5 must be observed.

DSL:

```text
becomes true {
  `sig1` is less than or equal to 5
}
```

### E05 条件变假

NL:

At the current sample, the transition that sig1 ceases to equal sig2 must be observed.

DSL:

```text
becomes false {
  `sig1` is equal to `sig2`
}
```

### E06 否定边沿

NL:

At the current sample, the transition that sig1 goes above 5 must not be detected.

DSL:

```text
it is not the case that {
  becomes true {
    `sig1` is greater than 5
  }
}
```

### E07 仅当前的条件蕴含

NL:

Only at the current instant, if sig1 is greater than 5, then sig2 must equal 1.

DSL:

```text
if {
  `sig1` is greater than 5
} then {
  `sig2` is equal to 1
}
```

### E08 全局即时响应

NL:

Globally, whenever sig1 is greater than 5, sig2 must equal 1 at the same instant.

DSL:

```text
whenever {
  `sig1` is greater than 5
} then {
  `sig2` is equal to 1
}
```

### E09 有界未来持续

NL:

For every instant from 2 to 5 time units after now, including both endpoints, sig1 must remain below 10.

DSL:

```text
throughout the next [2, 5] time units {
  `sig1` is less than 10
}
```

### E10 有界未来至少一次

NL:

There must be a time from 2 to 5 time units after now, including both endpoints, at which sig1 is below 10.

DSL:

```text
at least once in the next [2, 5] time units {
  `sig1` is less than 10
}
```

### E11 有界过去持续

NL:

At every available instant from 2 to 5 time units ago, including both endpoints, sig1 must have been below 10.

DSL:

```text
throughout the previous [2, 5] time units {
  `sig1` is less than 10
}
```

### E12 有界过去至少一次

NL:

There must have been a time from 2 to 5 time units ago, including both endpoints, at which sig1 was below 10.

DSL:

```text
at least once in the previous [2, 5] time units {
  `sig1` is less than 10
}
```

### E13 无界未来持续

NL:

From now on, sig1 must always remain equal to sig2.

DSL:

```text
throughout the entire future {
  `sig1` is equal to `sig2`
}
```

### E14 无界未来至少一次

NL:

There must eventually be a time, possibly now, at which sig1 equals sig2, with no deadline.

DSL:

```text
at least once in the entire future {
  `sig1` is equal to `sig2`
}
```

### E15 无界过去持续

NL:

Throughout all available history, including now, sig1 must have remained equal to sig2.

DSL:

```text
throughout the entire past {
  `sig1` is equal to `sig2`
}
```

### E16 无界过去至少一次

NL:

At some time in the available history, possibly now, sig1 must have equaled sig2.

DSL:

```text
at least once in the entire past {
  `sig1` is equal to `sig2`
}
```

### E17 有界直到

NL:

There must be a time from 2 to 5 time units after now, including both endpoints, at which sig2 equals 1; from now until just before that time, sig1 must stay below 10.

DSL:

```text
keep {
  `sig1` is less than 10
} until the next [2, 5] time units {
  `sig2` is equal to 1
}
```

### E18 有界自从

NL:

There must have been a time from 1 to 5 time units ago, including both endpoints, at which sig2 equaled 1; after that time through now, sig1 must have stayed below 10.

DSL:

```text
keep {
  `sig1` is less than 10
} since the previous [1, 5] time units {
  `sig2` is equal to 1
}
```

### E19 无界直到

NL:

Sig2 must eventually equal 1, possibly now; sig1 must stay below 10 from now until just before that time.

DSL:

```text
keep {
  `sig1` is less than 10
} until the entire future {
  `sig2` is equal to 1
}
```

### E20 无界自从

NL:

There must be a time in the available history, possibly now, at which sig2 equaled 1; sig1 must have stayed below 10 after that time through now.

DSL:

```text
keep {
  `sig1` is less than 10
} since the entire past {
  `sig2` is equal to 1
}
```

### E21 共同成立一次

NL:

Within the first 5 time units, including now and the endpoint, there must be a single instant at which sig1 and sig2 both equal 1.

DSL:

```text
at least once in the next [0, 5] time units {
  all of {
    `sig1` is equal to 1;
    `sig2` is equal to 1;
  }
}
```

### E22 分别成立一次

NL:

Within the first 5 time units, including now and the endpoint, sig1 and sig2 must each equal 1 at least once, possibly at different instants.

DSL:

```text
all of {
  at least once in the next [0, 5] time units {
    `sig1` is equal to 1
  };
  at least once in the next [0, 5] time units {
    `sig2` is equal to 1
  };
}
```

### E23 并非一直成立

NL:

It must not be true that sig1 stays above 5 at every instant in the first 5 time units, including now and the endpoint.

DSL:

```text
it is not the case that {
  throughout the next [0, 5] time units {
    `sig1` is greater than 5
  }
}
```

### E24 一直不成立

NL:

At every instant in the first 5 time units, including now and the endpoint, the condition that sig1 is above 5 must be false.

DSL:

```text
throughout the next [0, 5] time units {
  it is not the case that {
    `sig1` is greater than 5
  }
}
```

### E25 限时响应

NL:

Globally, whenever sig1 is greater than 20, sig2 must equal 1 at least once within the following 3 time units, including the trigger instant and the deadline.

DSL:

```text
whenever {
  `sig1` is greater than 20
} then {
  at least once in the next [0, 3] time units {
    `sig2` is equal to 1
  }
}
```

### E26 达到后保持

NL:

There must be a time in the first 5 time units, possibly now, from which sig1 equals 1 continuously for at least 10 time units; both intervals include their endpoints.

DSL:

```text
at least once in the next [0, 5] time units {
  throughout the next [0, 10] time units {
    `sig1` is equal to 1
  }
}
```

### E27 持续要求限时达到

NL:

For every instant in the first 5 time units, sig1 must equal 1 at least once within the next 10 time units relative to that instant; both intervals include their endpoints.

DSL:

```text
throughout the next [0, 5] time units {
  at least once in the next [0, 10] time units {
    `sig1` is equal to 1
  }
}
```

### E28 过去条件与未来响应

NL:

Globally, whenever sig1 has been at least 1 at some available instant in the preceding 8 time units, including the current instant, sig2 must equal sig3 at some time from 2 to 5 time units later, including both endpoints.

DSL:

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
