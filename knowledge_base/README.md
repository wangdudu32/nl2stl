# STL Clarifier

基于 LangChain 和 LangGraph 的人机协同自然语言转 STL 原型。系统分别识别模糊点（程度、边界、时限不明确）和歧义点（存在多个离散解释或信号映射），每次只询问一个问题。所有问题解决后生成并校验 STL 公式。

针对 ChatAnywhere 兼容端点，网络调用由显式顺序控制器执行；LangGraph 只负责纯状态转换，不在节点中执行网络请求。

## 工作流

```text
ChatAnywhere 分析歧义
  -> 识别领域、场景、主体、物理量和预期单位
  -> LangGraph 选择下一个歧义（无网络）
  -> 本地知识检索
  -> 本地候选，或 Tavily + ChatAnywhere 候选
  -> 用户回答并推进状态
  -> 全部澄清后生成类型化语义 AST
  -> 来源、类型和量纲校验
  -> 本地确定性编译 STL、清晰 NL 和片段映射
```

候选项来源只允许以下类型：

- `signal_knowledge`：`signals_kb.txt` 中的实际条目。领域和场景路径仅用于检索消歧，STL 公式始终使用 `ego_speed`、`parking_mode` 这类原始叶子信号名。
- `stl_knowledge`：`stl_operators.md` 中的实际章节。
- `tavily`：本轮 Tavily 返回的真实 URL。
- `llm_inference`：知识不足时的工程推断。
- `user_input`：用户没有采用候选项，直接输入的澄清。

程序会校验本地 source id 和 Tavily URL。无法对应实际证据的引用会降级为 `llm_inference`。

候选来源按固定优先级生成：`本地知识库 > Tavily 搜索 > LLM 推断`。只要本地知识能形成至少两个有效建模候选，就不会调用 Tavily。领域和场景唯一确定后，底层信号会自动绑定到该场景，不再要求用户选择同名信号；用户确认的是安全距离、触发条件、响应时限等建模决策。

候选项必须具备可执行形式：具体数值及单位、明确计算/比较公式，或信号与命名参数阈值的完整比较。程序会拒绝“固定数值”“动态模型”“适当阈值”等没有数值、公式或参数定义的空泛候选。本地知识未提供候选中的数值时，也不能标注为知识库来源。

当搜索和模型仍无法给出两个合格候选时，程序会基于当前场景中已绑定的真实信号补充参数化候选，例如 `front_vehicle_distance >= d_safe` 或 `eventually[0,t_brake](brake_active == 1)`，不会因候选不足直接抛出异常终止。

用户直接输入自定义澄清时，ChatAnywhere 会判断该回答是否真正消除了当前歧义。仍然模糊、无关或缺少数值/单位/范围的回答不会写入状态，程序会说明原因并继续询问同一个问题；有效回答会先规范化为明确约束。

最终公式不再由 LLM 直接拼接。LLM 只生成由原子比较、布尔组合、不变约束、作用域和限时响应组成的类型化语义 AST；本地编译器解析知识库信号单位，执行量纲检查并确定性生成 STL。响应语义固定编译为 `always(trigger -> eventually[0,T](target))`，不会被模型改写为含义不同的 `always[0,T](target)`。

AST 中每个非布尔常量和参数必须追踪到原始需求或具体澄清答案。程序会检查数值、单位和参数名是否真实存在于来源文本，并确认每条澄清都进入正确语义位置。速度乘普通无量纲常数仍被识别为速度，不能与距离比较；用户明确采用“N 倍时速距离”这一数值映射时，N 会建模为 `m/(km/h)` 比例系数，使结果具有距离量纲，同时不会被擅自改写成“N 秒时间头距”。语义计划校验失败时会携带具体错误重新生成，最多尝试 3 次，始终失败则终止而不是输出未通过检查的公式。

候选或模型计划中的标准换算写法会在来源审核前规范化，例如 `ego_speed / 3.6` 会转换为 `convert(ego_speed, m/s)`。换算系数属于本地单位系统，不要求出现在原始需求中；用户阈值和参数仍必须追踪到对应澄清。

对于“车辆不得超过限速”这类表达，系统会优先使用知识库中的动态信号关系 `ego_speed <= speed_limit`，不会把“限速”误当成缺少固定数值，也不会搜索网络带宽或报文速率。

外部检索没有固定领域黑名单。系统先识别当前需求的领域和场景，再生成包含领域、主体、物理量及单位的 Tavily 查询，并由 LLM 对搜索结果做上下文相关性判定。因此报文速率资料在车辆限速场景中会被排除，但在网络设备流量控制场景中可以作为有效证据。

## 安装

建议使用 Python 3.11 或更高版本：

```bash
python -m venv .venv
source .venv/bin/activate
uv pip install --python .venv/bin/python -e '.[dev]'
```

复制 `.env.example` 中缺少的配置到 `.env`。当前目录已有 `.env` 时，只需按需增加：

```dotenv
OPENAI_MODEL=gpt-4.1-mini
REQUEST_TIMEOUT_SECONDS=30
```

`OPENAI_BASE_URL` 可选。没有 `TAVILY_API_KEY` 时，外部搜索返回空结果，系统会使用明确标记的 LLM 推断候选项。

CLI 仅在当前步骤执行期间显示单行状态，例如“正在分析需求”或“正在搜索相关资料”。状态会被下一步骤覆盖，并在提问或输出最终结果前自动清除，不保留模型地址、耗时和内部筛选细节。

## 运行

推荐直接运行根目录入口：

```bash
python main.py "整个泊车过程中，车辆应始终保持低速"
```

不传参数时，程序会提示输入需求：

```bash
python main.py
```

运行前需要激活项目虚拟环境：`source .venv/bin/activate`。

## 结构

```text
stl_clarifier/
├── cli.py          # 命令行交互
├── config.py       # 环境变量与路径
├── graph.py        # 无网络的 LangGraph 状态转换及校验
├── knowledge.py    # JSON/Markdown 本地检索
├── prompts.py      # 结构化任务提示词
├── schemas.py      # Pydantic 模型和 GraphState
├── services.py     # ChatAnywhere 与 Tavily HTTP 客户端
├── semantics.py    # 类型/量纲检查、语义 AST 与确定性 STL 编译
└── workflow.py     # 显式顺序澄清控制器
```

## 第一版边界

- STL 由本地语义编译器生成；末端校验仍覆盖括号、信号白名单及 `signals_used` 一致性。
- 当前语义 AST 覆盖原子比较、布尔组合、不变约束、作用域和触发后限时响应；更多 STL 算子需要继续扩展 AST 和编译器，不能退回自由字符串生成。
- Markdown 检索采用轻量关键词匹配，106 个信号规模下足够直接，后续数据量扩大再引入 BM25 或向量检索。
- 数值单位由模型结合知识说明检查，尚未建立独立的量纲 AST。
- 模型通过普通 Chat Completions 返回 JSON，再由 Pydantic 本地校验；不依赖兼容端点实现 OpenAI 原生结构化输出。
- 外部请求使用 `httpx` 严格超时，不经过 OpenAI SDK 的隐式重试。

## 测试

```bash
pytest
```
