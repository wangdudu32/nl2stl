## STL 部分

### 1、原子谓词

#### 定义

<img src="./assets/image-20251203151553442.png" alt="image-20251203151553442" style="zoom:50%;" />

#### 关键特性

1. **输入是实值信号**：处理的是连续或离散的数值数据
2. **输出是布尔信号**：在每一个时间点 t*t*，原子谓词评估为 `True` 或 `False`

3. **无时序成分**：只关心当前时刻的信号值，不涉及时间关系



### 2、布尔连接词

| 连接词 | 符号   | 名称    | 含义           |
| :----- | :----- | :------ | :------------- |
| 否定   | ¬, !   | NOT     | 逻辑非         |
| 合取   | ∧, &   | AND     | 逻辑与         |
| 析取   | ∨, \|  | OR      | 逻辑或         |
| 蕴含   | →, ->  | IMPLIES | 如果...那么... |
| 等价   | ↔, <-> | IFF     | 当且仅当       |





### 3、带时间区间的时序算子

#### 时序算子

##### a、基础 STL 算子

###### 1. always

```
always（始终/全局） 
```

- **符号**: `always[a,b]φ 或者 always(φ)`
- **含义**: always[a,b]`φ`表示“在**整个时间区间 [a,b] 内**，**所有时刻** `φ` 都为真。” ； always(`φ`)表示“对于所有时刻，`φ`始终为真”
- **例子**: `G[0,30](speed < 60)`
  “在30秒内，速度始终低于60”



###### 2. eventually

```
eventually（最终/未来某刻）
```

- **符号**: `eventually[a,b]φ 或者 eventually(φ)`
- **含义**: `eventually[a,b]φ表示"在时间区间 I 内，φ 至少成立一次"; eventually(φ)表示"在未来的时间里,φ至少会成立一次"`
- **例子**: `eventually[5,15](arrive_destination == true)`
  “在未来的5到15秒之间的某个时刻，(arrive_destination == true)会成立”



###### 3. until

```
 until（直到）
```

- **符号**: `φ₁ until[a,b] φ₂ 或者 φ₁ until φ₂ `
- **含义**:  `φ₁ until[a,b] φ₂表示"在时间区间[a,b]内，∃c∈[a,b]，使得在[a,c) φ₁ 一直为真，在时刻 c 时 φ₂ 变为真。"; φ₁ until φ₂ 表示"在未来的时间里 ∃c ∈[0,+∞)，使得在[0,c) φ₁ 一直为真，在时刻 c 时 φ₂ 变为真"`
- **例子**: `(temperature > 20) until[0,10] (alarm == true)`
  “∃c ∈[0,10]，使得在[0,c) `(temperature > 20)` 一直为真，在时刻 c 时 `(alarm == true)` 变为真”



###### 4. weak_until

**符号**: `ϕ weak_until[a,b] ψ 或者 ϕ weak_until ψ `

**含义**: `ϕ  weak_until[a,b]  ψ表示"在时间区间[a,b]内，要么 ϕ 一直为真直到 ψ 为真，要么 ψ 在整个区间内从未为真而 ϕ 始终为真。"; ϕ weak_until ψ 表示"在未来时间里，要么 ϕ 一直为真直到 ψ 为真，要么 ψ 从未为真而 ϕ 始终为真"`

例子：`(send_heartbeat == true)  weak_until[0,10]  (ack_received == true)`

"系统将持续发送心跳信号，直到收到确认信号或时间超过10秒（即使未收到确认）"



###### 5. release

```
release（释放） （until的对偶）
```

- **符号**: `φ₁ release[a,b] φ₂`
- **定义**: `¬(¬φ₁ until[a,b] ¬φ₂)`
  （until的对偶算子）
- **含义**: 它是 Until 的对偶 (Dual)。意思是: *ψ* 必须一直为真，除非 ϕ 发生（*ϕ* 发生时刻及之后，*ψ* 不再强制为真）；如果 *ϕ* 从未发生，那么 *ψ* 必须在整个区间内为真。
- **例子**: `(system_state == normal) R [0,∞] (mode == safe_mode)`
  “安全模式必须一直保持，直到系统正常运行为止”

### 4、扩展STL算子

##### a、过去时态算子

```
经典STL通常只面向未来，但扩展后会加入过去算子。
```

###### 6. Once

```
Once（过去某刻） O I
```

- **符号**:  O[*a*,*b*]*ϕ*
- **含义**（在**过去时间逻辑**中）: 在**过去的**时间区间 I 内，**存在某个时刻** `φ` 为真
- **例子**: `O[0,5](button_pressed == true)`
  “在过去的5秒内，按键曾被按下过”



###### 7. Historically

```
Historically（过去始终） H[a,b]
```

- **符号**: `H[a,b] φ`
- **含义**: 在**整个过去的**时间区间 [a,b] 内，**所有时刻** `φ` 都为真。
- **例子**: `H[0,10] (door_closed == true)`
  “在过去的10秒内，门一直关着”



###### 8、 Since 

- **符号**: ϕ S_[a,b] ψ 
- **含义**: 在过去的某个区间[ t−b,t−a] 内，存在一个时刻 t′，使得 ψ 在  t′ 处成立，并且从  t′ 开始一直到当前时刻  t ，ϕ 都一直成立。
- **直观理解**: Since 是 Until 在时间上的“过去版本”。



##### b. 边缘算子

###### 9. Rise 

`rise` 通常指一个布尔谓词（Predicate）从**假（False）变为真（True）\**的瞬间，或者一个实值信号\**从下方穿过**某个阈值的瞬间。

语义解释：

<img src="./assets/image-20251203151624837.png" alt="image-20251203151624837" style="zoom:50%;" />



常见用法与示例

<img src="./assets/image-20251203151639328.png" alt="image-20251203151639328" style="zoom:50%;" />

###### 10. Fall 

`fall` 是 `rise` 的对偶概念，指布尔谓词从**真（True）变为假（False）**，或信号**从上方穿过**某个阈值。



语义定义

<img src="./assets/image-20251203151054667.png" alt="image-20251203151054667" style="zoom:50%;" />



 常见用法与示例

<img src="./assets/image-20251203151112506.png" alt="image-20251203151112506" style="zoom:50%;" />



###### 11. Peak

`peak` 用于检测信号的**局部最大值**。这在 STL 中比 rise/fall 更复杂，因为它涉及导数的变化或与邻域的比较。



语义定义

<img src="./assets/image-20251203151127889.png" alt="image-20251203151127889" style="zoom:50%;" />



常见用法与示例

<img src="./assets/image-20251203151149365.png" alt="image-20251203151149365" style="zoom:50%;" />

###### 注意

```
这些扩展算子在rtamt中不被支持
```

##### c.统计类算子

###### 12.Cumulative time

论文出处

```
https://arxiv.org/abs/2504.10325
```

算子形式

<img src="./assets/image-20260406212119633.png" alt="image-20260406212119633" style="zoom: 50%;" />

含义

```
统计在时间窗口 I 内 𝜙 成立的累计持续时间
```

例如：“10秒内危险状态累计不能超过2秒”

可写成：

<img src="./assets/image-20260406212324444.png" alt="image-20260406212324444" style="zoom:50%;" />

###### 13.Count 

论文出处

```
Count operator 目前没有统一标准写法，很多论文是作者自定义扩展，所以也没有较为权威的出处
```

算子形式

<img src="./assets/image-20260406212556786.png" alt="image-20260406212556786" style="zoom: 50%;" />

含义

> 谓词 𝜙 在时间区间 I 内成立的次数

例如：

> 10 秒内刹车至少发生 3 次

<img src="./assets/image-20260406212625070.png" alt="image-20260406212625070" style="zoom:50%;" />

注意：

```
注意这里要严谨：
Count operator 目前没有统一标准写法
很多论文是作者自定义扩展。
它不是像 freeze 那样有经典统一出处。
```



##### d.值引用类

###### 14.freeze

论文

```
STL⁎: Extending signal temporal logic with signal-value freezing operator
```



```
传统STL只能描述信号在当前时间的性质，无法直接比较不同时间点的信号值。例如：
阻尼振荡（振幅逐渐减小）：需要比较当前峰值与之前峰值的大小关系
信号延迟：需要比较当前值与几秒前的值
局部极值：需要判断当前点是否比周围区间都大或小
Freeze算子通过"冻结"当前时间点的信号值，使其在子公式中可被引用，解决了这一问题。
```

<img src="./assets/image-20260406214040315.png" alt="image-20260406214040315" style="zoom:50%;" />

<img src="./assets/image-20260406214112708.png" alt="image-20260406214112708" style="zoom:50%;" />



示例

<img src="./assets/image-20260406214151798.png" alt="image-20260406214151798" style="zoom:50%;" />

<img src="./assets/image-20260406214216192.png" alt="image-20260406214216192" style="zoom:50%;" />

<img src="./assets/image-20260406214230542.png" alt="image-20260406214230542" style="zoom:50%;" />

<img src="./assets/image-20260406214243778.png" alt="image-20260406214243778" style="zoom:50%;" />

<img src="./assets/image-20260406214305159.png" alt="image-20260406214305159" style="zoom:50%;" />

注意

```
论文指出freeze算子可以嵌套，但遵循最近作用域原则
```



##### e.模式类

###### 15.Weighted

论文出处

```
https://arxiv.org/abs/2010.00752
```



```
适合偏好性表述
```

<img src="./assets/image-20260406213018487.png" alt="image-20260406213018487" style="zoom:50%;" />

含义

> 给不同子公式赋予不同优先级

例如：

- 安全 > 舒适
- 刹车 > 加速平顺性

<img src="./assets/image-20260406213042226.png" alt="image-20260406213042226" style="zoom:50%;" />

























### 5、语义解释

STL 有两类常见语义描述：**布尔语义**（是否满足）和**定量/鲁棒度语义**（degree of satisfaction）。

#### a. 布尔语义（经典）

<img src="./assets/image-20251203151206775.png" alt="image-20251203151206775" style="zoom:50%;" />



#### b. 定量语义

（Robustness / quantitative semantics）

<img src="./assets/image-20251203151221601.png" alt="image-20251203151221601" style="zoom:50%;" />





