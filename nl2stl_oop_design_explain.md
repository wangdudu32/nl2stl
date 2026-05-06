# NL2STL 脚本系统：面向对象设计说明

## 1. 是否应该使用面向对象？

**建议使用面向对象，但不要过度设计。**

你的目标不是写一个简单的“一次输入 -> 一次输出”的脚本，而是实现一个类似 Kimi Code Skill 的脚本版运行时。它需要支持：

- 多轮对话；
- 判断用户输入意图；
- 保存当前任务状态；
- 识别场景补充信息；
- 处理用户对候选项的选择；
- 根据修改指令更新 AST / STL；
- 调用校验脚本；
- 调用 AST 转 STL 脚本；
- 支持后续批量实验。

这些功能都有比较清晰的职责边界，因此适合采用：

```text
轻量面向对象 + 状态驱动 + LangGraph 工作流
```

也就是说：

- 核心实体用类封装；
- 工作流分支交给 LangGraph 管理；
- AST 校验、AST 转 STL 等确定性逻辑继续用普通 Python 脚本或工具函数实现。

---

## 2. 为什么不能只用简单脚本？

简单脚本通常是这样的：

```text
用户输入 -> LLM -> 输出 STL
```

这种方式的问题是：

1. **没有状态**  
   用户上一轮说了什么、当前有哪些候选项、哪个 ambiguity 已经解决，都不好保存。

2. **无法稳定处理多轮交互**  
   用户说“选第二个”“把时间改成 5 秒内”“这是高速场景”，脚本很难知道该如何接续上一轮任务。

3. **难以区分输入类型**  
   用户输入可能是：
   - 新的 NL2STL 需求；
   - 场景补充；
   - 修改指令；
   - 候选项选择；
   - 闲聊；
   - 无关内容。

4. **不好测试和维护**  
   所有逻辑混在一个 `main.py` 里，后面会越来越乱。

所以需要把系统拆成多个职责清晰的类。

---

## 3. 总体设计思想

推荐架构是：

```text
用户输入
  ↓
NL2STLRuntime
  ↓
IntentRouter：判断输入类型
  ↓
SessionState：读取 / 更新当前会话状态
  ↓
ASTService / LLMService：生成或修改 AST
  ↓
ValidationTool：校验 AST
  ↓
ConversionTool：AST 转 STL
  ↓
返回结果
```

核心原则：

```text
LLM 负责语义理解；
Python 类负责状态管理和流程控制；
确定性脚本负责 AST 校验和 STL 生成。
```

---

## 4. 核心类说明

## 4.1 NL2STLRuntime

`NL2STLRuntime` 是系统总控类。

它负责接收用户输入，并组织整个处理流程。

### 主要属性

```python
router: IntentRouter
prompt_loader: SkillPromptLoader
llm_service: LLMService
ast_service: ASTService
validator: ValidationTool
converter: ConversionTool
repository: SessionRepository
```

### 主要方法

```python
handle_input(user_input)
dispatch(intent, state)
build_response(state)
```

### 职责

- 接收用户输入；
- 加载当前会话状态；
- 调用 `IntentRouter` 判断输入类型；
- 根据输入类型分派到不同处理流程；
- 调用 AST 生成、校验、转换工具；
- 保存最新状态；
- 返回用户可读结果。

它类似整个系统的“大脑”或“调度器”。

---

## 4.2 SessionState

`SessionState` 是整个系统中最重要的数据类。

它保存当前会话的全部上下文。

### 推荐字段

```python
session_id: str
current_intent: IntentType
base_requirement: str
scenario_context: list[str]
draft_ast: dict
ambiguities: list[AmbiguityRecord]
candidate_options: dict
resolved_choices: dict
final_ast: dict
stl_formula: str
history: list[Message]
```

### 推荐方法

```python
update_intent(intent)
merge_context(info)
apply_selection(selection)
reset_task()
```

### 职责

- 保存原始自然语言需求；
- 保存场景补充信息；
- 保存当前 Draft AST；
- 保存 ambiguity records；
- 保存候选项；
- 保存用户已选择的候选项；
- 保存最终 AST；
- 保存最终 STL 公式；
- 保存历史消息。

多轮交互的关键就在这个类。

---

## 4.3 IntentRouter

`IntentRouter` 用来判断用户当前输入属于哪种类型。

### 推荐识别的意图类型

```python
NEW_REQUIREMENT
SCENARIO_INFO
MODIFICATION
CANDIDATE_SELECTION
SMALL_TALK
IRRELEVANT
```

### 主要方法

```python
route(user_input, state)
classify(user_input)
extract_payload(user_input)
```

### 例子

用户输入：

```text
自车应在前车急刹时 2 秒内减速
```

应识别为：

```text
NEW_REQUIREMENT
```

用户输入：

```text
这是高速场景，天气是雨天
```

应识别为：

```text
SCENARIO_INFO
```

用户输入：

```text
选第二个候选项
```

应识别为：

```text
CANDIDATE_SELECTION
```

用户输入：

```text
把时间从 2 秒改成 3 秒
```

应识别为：

```text
MODIFICATION
```

---

## 4.4 SkillPromptLoader

`SkillPromptLoader` 负责加载你的 skill 规则。

### 推荐字段

```python
skill_path: str
references_dir: str
```

### 推荐方法

```python
load_skill_prompt()
load_references()
build_system_prompt()
```

### 职责

- 读取 `SKILL.md`；
- 读取 `references/` 目录下的参考规则；
- 拼接成系统提示词；
- 提供给 `LLMService` 使用。

这样做的好处是：

- 你不用把 skill 规则写死在代码里；
- 后面修改 `SKILL.md` 后，脚本可以直接复用；
- 更接近 Kimi Code 读取 skill 的效果。

---

## 4.5 LLMService

`LLMService` 是大模型调用封装层。

### 推荐字段

```python
model_name: str
base_url: str
```

### 推荐方法

```python
classify_intent(...)
validate_semantics(...)
detect_ambiguities(...)
generate_candidates(...)
chat_reply(...)
```

### 职责

- 调用 ChatAnywhere / DeepSeek / OpenAI 风格接口；
- 完成意图识别；
- 完成语义可翻译性判断；
- 检测模糊项；
- 生成候选项；
- 生成普通闲聊回复。

建议所有 LLM 调用都集中在这个类中，不要散落在各个文件里。

好处：

- 后面换模型，只改这一层；
- 后面做实验，可以统一记录 token、耗时、输入输出；
- 后面做 mock 测试，也更方便。

---

## 4.6 ASTService

`ASTService` 负责 AST 相关业务逻辑。

### 推荐方法

```python
build_draft_ast(...)
revise_ast(...)
apply_clarification(...)
finalize_ast(...)
```

### 职责

- 根据自然语言生成 Draft AST；
- 根据用户补充场景修改 AST；
- 根据用户选择的候选项解决 ambiguity；
- 根据修改指令修正已有 AST；
- 生成 Final AST。

注意：

`ASTService` 可以调用 `LLMService`，但不要直接负责底层模型 API 请求。

也就是说：

```text
ASTService 负责“要生成什么”；
LLMService 负责“怎么调用模型生成”。
```

---

## 4.7 ValidationTool

`ValidationTool` 负责调用你的 AST 校验逻辑。

### 推荐方法

```python
validate(ast)
```

### 职责

- 调用 `validate_ast.py`；
- 判断 AST 是否符合 schema；
- 返回校验成功 / 失败；
- 如果失败，返回错误位置和错误原因。

这个类应该是确定性的，不应该依赖 LLM。

---

## 4.8 ConversionTool

`ConversionTool` 负责把 AST 转成 STL 字符串。

### 推荐方法

```python
ast_to_stl(ast)
```

### 职责

- 调用 `ast2stl.py`；
- 输入 Final AST；
- 输出 STL 公式。

这个类也应该是确定性的，不应该依赖 LLM。

---

## 4.9 SessionRepository

`SessionRepository` 负责状态持久化。

### 推荐方法

```python
load(session_id)
save(state)
delete(session_id)
```

### 第一版建议

用 JSON 文件保存即可：

```text
memory/sessions.json
```

### 后续可升级

如果会话变多，可以换成：

```text
SQLite
```

职责很简单：

- 读取会话；
- 保存会话；
- 删除会话。

---

## 4.10 AmbiguityRecord

`AmbiguityRecord` 表示一个模糊项。

### 推荐字段

```python
id: str
category: str
original_text: str
question: str
candidates: list[dict]
resolved_value: Any
```

### 例子

```json
{
  "id": "A1",
  "category": "threshold_ambiguous",
  "original_text": "速度过快",
  "question": "速度超过多少 km/h 算作过快？",
  "candidates": [
    {"value": 80, "unit": "km/h", "reason": "城市快速路候选"},
    {"value": 120, "unit": "km/h", "reason": "高速道路候选"}
  ],
  "resolved_value": null
}
```

---

## 4.11 Message

`Message` 表示一条历史消息。

### 推荐字段

```python
role: str
content: str
timestamp: str
```

用于保存用户和系统之间的多轮交互记录。

---

## 4.12 IntentType

`IntentType` 是枚举类。

推荐值：

```python
NEW_REQUIREMENT
SCENARIO_INFO
MODIFICATION
CANDIDATE_SELECTION
SMALL_TALK
IRRELEVANT
```

它的作用是让代码不要到处写字符串，减少拼写错误。

---

# 5. 类之间的关系

## 5.1 NL2STLRuntime uses 其他服务类

`NL2STLRuntime` 依赖：

```text
IntentRouter
SkillPromptLoader
LLMService
ASTService
ValidationTool
ConversionTool
SessionRepository
```

因为它是总控类，需要调用这些组件完成完整流程。

---

## 5.2 SessionState contains AmbiguityRecord

一个会话中可能有多个模糊项。

所以关系是：

```text
SessionState 1 -> 0..* AmbiguityRecord
```

---

## 5.3 SessionState contains Message

一个会话中会有多条历史消息。

所以关系是：

```text
SessionState 1 -> 0..* Message
```

---

## 5.4 SessionState references IntentType

一个会话当前只对应一个当前意图。

所以关系是：

```text
SessionState 1 -> 1 IntentType
```

---

## 5.5 SessionRepository stores / loads SessionState

`SessionRepository` 负责保存和加载 `SessionState`。

关系是：

```text
SessionRepository -> SessionState
```

---

## 5.6 IntentRouter uses LLMService

意图识别可以用规则，也可以用 LLM。

你的场景中，因为要识别复杂输入，例如：

- 场景补充；
- 修改指令；
- 候选项选择；
- 闲聊；
- 无关输入；

所以建议 `IntentRouter` 可以调用 `LLMService` 做结构化分类。

---

## 5.7 ASTService uses LLMService

AST 的生成、修改、补全很多时候需要 LLM。

因此：

```text
ASTService -> LLMService
```

---

# 6. 推荐运行流程

## 6.1 新需求输入

用户输入：

```text
当前车距离前车过近时，应在 2 秒内刹车
```

流程：

```text
NL2STLRuntime.handle_input()
  ↓
SessionRepository.load()
  ↓
IntentRouter.route() -> NEW_REQUIREMENT
  ↓
LLMService.validate_semantics()
  ↓
ASTService.build_draft_ast()
  ↓
LLMService.detect_ambiguities()
  ↓
如果没有模糊项：
    ASTService.finalize_ast()
    ValidationTool.validate()
    ConversionTool.ast_to_stl()
  ↓
SessionRepository.save()
  ↓
返回 STL
```

---

## 6.2 场景补充输入

用户输入：

```text
这是高速雨天场景
```

流程：

```text
IntentRouter.route() -> SCENARIO_INFO
  ↓
SessionState.merge_context()
  ↓
ASTService.apply_clarification() 或重新生成候选项
  ↓
更新当前状态
```

---

## 6.3 候选项选择输入

用户输入：

```text
选第二个
```

流程：

```text
IntentRouter.route() -> CANDIDATE_SELECTION
  ↓
SessionState.apply_selection()
  ↓
ASTService.apply_clarification()
  ↓
如果所有 ambiguity 已解决：
    ASTService.finalize_ast()
    ValidationTool.validate()
    ConversionTool.ast_to_stl()
```

---

## 6.4 修改指令输入

用户输入：

```text
把 2 秒内改成 3 秒内
```

流程：

```text
IntentRouter.route() -> MODIFICATION
  ↓
ASTService.revise_ast()
  ↓
ValidationTool.validate()
  ↓
ConversionTool.ast_to_stl()
  ↓
返回修改后的 STL
```

---

## 6.5 闲聊输入

用户输入：

```text
你觉得这个方向能发论文吗？
```

流程：

```text
IntentRouter.route() -> SMALL_TALK
  ↓
LLMService.chat_reply()
  ↓
返回普通回答，不修改当前 AST 状态
```

---

# 7. 和 LangGraph 的关系

面向对象不是替代 LangGraph。

推荐关系是：

```text
类负责封装能力；
LangGraph 负责组织流程。
```

例如：

```text
intent_router_node 调用 IntentRouter.route()
semantic_validator_node 调用 LLMService.validate_semantics()
ast_generator_node 调用 ASTService.build_draft_ast()
validation_node 调用 ValidationTool.validate()
conversion_node 调用 ConversionTool.ast_to_stl()
```

所以你的系统可以写成：

```text
LangGraph Node = 对某个类方法的包装
```

---

# 8. 第一版工程结构建议

```text
nl2stl_runtime/
├── main.py
├── graph.py
├── enums.py
├── schemas.py
├── state.py
├── runtime.py
├── prompts/
│   └── skill_prompt_loader.py
├── services/
│   ├── llm_service.py
│   ├── ast_service.py
│   └── response_service.py
├── routing/
│   └── intent_router.py
├── tools/
│   ├── validation_tool.py
│   └── conversion_tool.py
├── repository/
│   └── session_repository.py
└── memory/
    └── sessions.json
```

---

# 9. 哪些类第一版必须实现？

第一版建议最少实现这些：

```text
SessionState
IntentRouter
LLMService
ASTService
ValidationTool
ConversionTool
SessionRepository
NL2STLRuntime
```

暂时可以不做复杂继承和抽象基类。

---

# 10. 不建议第一版做什么？

第一版不要做太复杂：

- 不要设计一堆父类、子类；
- 不要搞复杂的插件系统；
- 不要过早上数据库；
- 不要把所有 LangGraph 节点都封装成类；
- 不要让 LLM 直接输出最终 STL 而跳过 AST 校验。

重点是先跑通：

```text
意图识别 -> 状态更新 -> AST 生成 -> AST 校验 -> STL 输出
```

---

# 11. 最终建议

## 推荐实现方式

```text
LangGraph 做工作流；
Python 类做组件封装；
Pydantic 做结构化数据；
JSON / SQLite 做状态保存；
validate_ast.py 和 ast2stl.py 做确定性工具。
```

## 一句话总结

**你的系统应该使用轻量面向对象。核心类负责封装稳定职责，LangGraph 负责流程分支，SessionState 负责多轮状态，LLM 只负责语义理解，最终结果必须经过 AST 校验和 AST 转 STL 脚本。**
