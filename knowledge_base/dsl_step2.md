# 第二阶段：DSL → STL

## 1. 占位符与书写约定

| 记号 | 含义 |
|---|---|
| `e`、`f` | 信号或数值，如 `` `sig1` ``、`5.2` |
| `P`、`Q` | 任意完整 DSL 子表达式，可递归嵌套 |
| `a`、`b` | 时间下界与上界，满足 `0 <= a <= b` |
| `I` | 有限闭区间 `[a, b]`，包含两个端点 |
| `W` | 完整时间窗口，形式见下表 |

这些是规则占位符，实际表达式必须替换为具体内容，不是需要声明的信号或符号参数。

- 信号名称原样保留并加反引号，如 `` `sig1` ``；不预设物理含义。数字可为整数或小数，不带物理单位。比较对象也可为另一信号。
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

## 2. 全部表述的转换对应

`T(P)` 表示将 DSL 子表达式 P 递归转换成 STL；`V(e)` 表示输出信号名或数值：信号去掉反引号，名称和数值保持不变。`T`、`V` 都是规则记号，不出现在最终公式中。

### 比较、逻辑、条件与变化

| DSL | STL |
|---|---|
| `e is equal to f` | `(V(e) == V(f))` |
| `e is not equal to f` | `not(V(e) == V(f))` |
| `e is less than f` | `(V(e) < V(f))` |
| `e is less than or equal to f` | `(V(e) <= V(f))` |
| `e is greater than f` | `(V(e) > V(f))` |
| `e is greater than or equal to f` | `(V(e) >= V(f))` |
| `all of { P; Q; }` | `(T(P) and T(Q))` |
| `any of { P; Q; }` | `(T(P) or T(Q))` |
| `it is not the case that { P }` | `not(T(P))` |
| `if { P } then { Q }` | `(T(P) -> T(Q))` |
| `whenever { P } then { Q }` | `always(T(P) -> T(Q))` |
| `becomes true { P }` | `rise(T(P))` |
| `becomes false { P }` | `fall(T(P))` |

多项 `all of`、`any of` 保留原顺序，用同一连接符连接全部子公式；不丢失任何一项。

### 有界时序

时间窗口的 `[a, b] time units` 转为 `[a:b]`，数值不缩放。

| DSL | STL |
|---|---|
| `throughout the next [a, b] time units { P }` | `always[a:b](T(P))` |
| `at least once in the next [a, b] time units { P }` | `eventually[a:b](T(P))` |
| `throughout the previous [a, b] time units { P }` | `historically[a:b](T(P))` |
| `at least once in the previous [a, b] time units { P }` | `once[a:b](T(P))` |
| `keep { P } until the next [a, b] time units { Q }` | `(T(P) until[a:b] T(Q))` |
| `keep { P } since the previous [a, b] time units { Q }` | `(T(P) since[a:b] T(Q))` |

### 无界时序

| DSL | STL |
|---|---|
| `throughout the entire future { P }` | `always(T(P))` |
| `at least once in the entire future { P }` | `eventually(T(P))` |
| `throughout the entire past { P }` | `historically(T(P))` |
| `at least once in the entire past { P }` | `once(T(P))` |
| `keep { P } until the entire future { Q }` | `(T(P) until T(Q))` |
| `keep { P } since the entire past { Q }` | `(T(P) since T(Q))` |

### 转换约束

- 先递归转换子表达式，再套用对应形式。保留括号作用域、左右顺序、否定层次和时间嵌套；示例可省略原子比较的冗余外括号。
- 不把状态自动改成边沿，不把 `if` 自动加上全局量化，不交换“持续”与“至少一次”，不把无界范围替换成日志长度。
- until 采用强直到：Q 的见证时刻为 u，P 在 `[t,u)` 成立；since 采用强自从，P 在 `(u,t]` 成立。目标解释器须采用相同端点约定。
- `historically/once/since` 为过去时态扩展，`rise/fall` 为边沿扩展；保留算子，不猜测采样间隔。目标解释器须支持相应能力及一致的信号模型。

## 3. 必要示例

以下 DSL 与第一阶段同编号示例完全一致。

### E01 范围与合取

DSL:

```text
all of {
  `sig1` is greater than 2;
  `sig1` is less than or equal to 5;
}
```

STL:

```text
(sig1 > 2 and sig1 <= 5)
```

### E02 析取

DSL:

```text
any of {
  `sig1` is less than 0;
  `sig2` is greater than 10;
}
```

STL:

```text
(sig1 < 0 or sig2 > 10)
```

### E03 否定整个范围

DSL:

```text
it is not the case that {
  all of {
    `sig1` is greater than or equal to 2;
    `sig1` is less than or equal to 5;
  }
}
```

STL:

```text
not(sig1 >= 2 and sig1 <= 5)
```

### E04 条件变真

DSL:

```text
becomes true {
  `sig1` is less than or equal to 5
}
```

STL:

```text
rise(sig1 <= 5)
```

### E05 条件变假

DSL:

```text
becomes false {
  `sig1` is equal to `sig2`
}
```

STL:

```text
fall(sig1 == sig2)
```

### E06 否定边沿

DSL:

```text
it is not the case that {
  becomes true {
    `sig1` is greater than 5
  }
}
```

STL:

```text
not(rise(sig1 > 5))
```

### E07 仅当前的条件蕴含

DSL:

```text
if {
  `sig1` is greater than 5
} then {
  `sig2` is equal to 1
}
```

STL:

```text
(sig1 > 5 -> sig2 == 1)
```

### E08 全局即时响应

DSL:

```text
whenever {
  `sig1` is greater than 5
} then {
  `sig2` is equal to 1
}
```

STL:

```text
always(sig1 > 5 -> sig2 == 1)
```

### E09 有界未来持续

DSL:

```text
throughout the next [2, 5] time units {
  `sig1` is less than 10
}
```

STL:

```text
always[2:5](sig1 < 10)
```

### E10 有界未来至少一次

DSL:

```text
at least once in the next [2, 5] time units {
  `sig1` is less than 10
}
```

STL:

```text
eventually[2:5](sig1 < 10)
```

### E11 有界过去持续

DSL:

```text
throughout the previous [2, 5] time units {
  `sig1` is less than 10
}
```

STL:

```text
historically[2:5](sig1 < 10)
```

### E12 有界过去至少一次

DSL:

```text
at least once in the previous [2, 5] time units {
  `sig1` is less than 10
}
```

STL:

```text
once[2:5](sig1 < 10)
```

### E13 无界未来持续

DSL:

```text
throughout the entire future {
  `sig1` is equal to `sig2`
}
```

STL:

```text
always(sig1 == sig2)
```

### E14 无界未来至少一次

DSL:

```text
at least once in the entire future {
  `sig1` is equal to `sig2`
}
```

STL:

```text
eventually(sig1 == sig2)
```

### E15 无界过去持续

DSL:

```text
throughout the entire past {
  `sig1` is equal to `sig2`
}
```

STL:

```text
historically(sig1 == sig2)
```

### E16 无界过去至少一次

DSL:

```text
at least once in the entire past {
  `sig1` is equal to `sig2`
}
```

STL:

```text
once(sig1 == sig2)
```

### E17 有界直到

DSL:

```text
keep {
  `sig1` is less than 10
} until the next [2, 5] time units {
  `sig2` is equal to 1
}
```

STL:

```text
((sig1 < 10) until[2:5] (sig2 == 1))
```

### E18 有界自从

DSL:

```text
keep {
  `sig1` is less than 10
} since the previous [1, 5] time units {
  `sig2` is equal to 1
}
```

STL:

```text
((sig1 < 10) since[1:5] (sig2 == 1))
```

### E19 无界直到

DSL:

```text
keep {
  `sig1` is less than 10
} until the entire future {
  `sig2` is equal to 1
}
```

STL:

```text
((sig1 < 10) until (sig2 == 1))
```

### E20 无界自从

DSL:

```text
keep {
  `sig1` is less than 10
} since the entire past {
  `sig2` is equal to 1
}
```

STL:

```text
((sig1 < 10) since (sig2 == 1))
```

### E21 共同成立一次

DSL:

```text
at least once in the next [0, 5] time units {
  all of {
    `sig1` is equal to 1;
    `sig2` is equal to 1;
  }
}
```

STL:

```text
eventually[0:5](sig1 == 1 and sig2 == 1)
```

### E22 分别成立一次

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

STL:

```text
(eventually[0:5](sig1 == 1) and eventually[0:5](sig2 == 1))
```

### E23 并非一直成立

DSL:

```text
it is not the case that {
  throughout the next [0, 5] time units {
    `sig1` is greater than 5
  }
}
```

STL:

```text
not(always[0:5](sig1 > 5))
```

### E24 一直不成立

DSL:

```text
throughout the next [0, 5] time units {
  it is not the case that {
    `sig1` is greater than 5
  }
}
```

STL:

```text
always[0:5](not(sig1 > 5))
```

### E25 限时响应

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

STL:

```text
always(sig1 > 20 -> eventually[0:3](sig2 == 1))
```

### E26 达到后保持

DSL:

```text
at least once in the next [0, 5] time units {
  throughout the next [0, 10] time units {
    `sig1` is equal to 1
  }
}
```

STL:

```text
eventually[0:5](always[0:10](sig1 == 1))
```

### E27 持续要求限时达到

DSL:

```text
throughout the next [0, 5] time units {
  at least once in the next [0, 10] time units {
    `sig1` is equal to 1
  }
}
```

STL:

```text
always[0:5](eventually[0:10](sig1 == 1))
```

### E28 过去条件与未来响应

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

STL:

```text
always(once[0:8](sig1 >= 1) -> eventually[2:5](sig2 == sig3))
```
