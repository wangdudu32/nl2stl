# NL2STL

基于 LangChain 和 LangGraph 的人机协同自然语言到 STL 翻译器。

## 运行

`src/.env` 需要包含：

```dotenv
OPENAI_API_KEY=...
OPENAI_BASE_URL=...
TAVILY_API_KEY=...
# 可选，默认 gpt-4.1-mini
OPENAI_MODEL=gpt-4.1-mini
```

启动交互：

```bash
.venv/bin/python src/main.py
```

也可直接提供需求：

```bash
.venv/bin/python src/main.py "在整个停车期间，车辆应该始终保持低速"
```

页面每次只显示当前阶段，并实时显示当前执行步骤和耗时。存在歧义时，每轮显示一个优先问题和 2～3 个经过来源核验、去重的简洁候选；自定义输入可以是自然语言、数值、单位、区间或公式，也可以修改当前全局语义中的其它内容。

## 工作流

```text
信号索引选择
→ 详细知识检索
→ 建立并复核统一全局语义
→ 候选生成与来源/重复验证
→ 自由格式澄清（LangGraph interrupt）
→ 完整全局语义修订与独立一致性验证
→ 重新计算全部模糊点（可反复修订或推翻旧结论）
→ AST 生成
→ JSON Schema/知识库信号/全局语义边界/区间验证
→ 有限次数修复
→ validate_ast.py 与 ast2stl.py 最终验证和紧凑输出
```

所有 Agent 提示词位于 `knowledge_base/prompt.json`，中间数据格式位于 `knowledge_base/data_formats.json`。信号先从 `signals_index.json` 选择，再按需读取 `signals_explain.txt` 的详细定义。

每次会话的 AST 写入 `tmp/<session_id>/ast.json`。

## 测试

```bash
.venv/bin/python -m pytest -q
```
