# 架构设计文档

本文档描述 AI 知识库平台的整体架构、分层设计、核心数据流与关键设计决策。

---

## 1. 总体架构

系统采用**前后端分离 + 分层架构**，后端进一步按「路由 → 服务编排 → 核心能力 → 基础设施」分层，依赖方向自上而下，核心能力不感知上层。

```
┌──────────────────────────────────────────────────────────┐
│                      浏览器（React SPA）                    │
│   Chat / Documents / Agent / Memory / Prompt 面板           │
└───────────────────────────┬──────────────────────────────┘
                            │ HTTP / SSE (/api/*)
                            │ (开发: Vite Proxy；生产: Nginx 反向代理)
┌───────────────────────────▼──────────────────────────────┐
│                      FastAPI 应用 (main.py)                │
│   CORS · 全局异常处理 · 生命周期(lifespan) · 路由注册         │
├──────────────────────────────────────────────────────────┤
│  API 路由层  documents · chat · agent · memory · models     │
├──────────────────────────────────────────────────────────┤
│  服务编排层  Container(组合根) · DocumentService             │
│             · ChatService · AgentService                    │
├──────────────────────────────────────────────────────────┤
│  核心能力层                                                  │
│   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐              │
│   │  LLM   │ │  RAG   │ │ Agent  │ │ Memory │              │
│   │ 抽象/工厂│ │ 检索器  │ │规划/执行│ │会话/长期│              │
│   └────────┘ └────────┘ └────────┘ └────────┘              │
├──────────────────────────────────────────────────────────┤
│  基础设施   本地向量库(numpy) · SQLite(记忆) · 文件系统(文档)    │
└──────────────────────────────────────────────────────────┘
```

---

## 2. 分层职责

| 层 | 目录 | 职责 |
| --- | --- | --- |
| 路由层 | `app/api/` | 定义 HTTP 端点、参数校验（Pydantic）、序列化；不含业务逻辑 |
| 服务编排层 | `app/services/` | 编排多个核心能力完成一个业务用例；依赖容器统一装配 |
| 核心能力层 | `app/core/` | 领域纯逻辑：LLM 抽象、RAG、Agent、记忆；可独立测试 |
| 基础设施 | 第三方/标准库 | 本地向量库(numpy)、SQLite、文件系统 |
| 横切工具 | `app/utils/` | 日志、异常、LLM 输出解析 |

---

## 3. 核心模块设计

### 3.1 LLM 抽象层（`core/llm`）

- **`BaseLLMProvider`**：抽象基类，定义 `generate()`（一次性）与 `stream()`（异步流式）两个接口。
- **具体提供商**：`OpenAICompatibleProvider` 统一封装 DeepSeek 与小米 MiMo（二者均兼容 OpenAI 协议）。
- **`LLMFactory`**：工厂模式，按 `provider:model` 缓存实例，支持**运行时切换**；`available_models()` 依据密钥配置动态标记可用性。
- **`prompt.py`**：模板化提示工程，将提示与业务逻辑解耦；模板含 `{变量}` 占位符，运行时渲染。

> **设计意图**：上层只依赖 `BaseLLMProvider` 抽象，新增一个模型厂商只需实现接口并在工厂注册，符合开闭原则。

### 3.2 RAG 系统（`core/rag`）

数据摄取与检索流水线：

```
文档 → loader(解析) → splitter(递归分块) → embedder(向量化) → VectorStore(本地向量库)
查询 → embedder(向量化) → VectorStore.query(相似度检索) → build_context(拼接) → LLM
```

- **`loader.py`**：多格式解析（PDF/Word/TXT/Markdown），兼容 GBK/UTF-8。
- **`splitter.py`**：递归字符分块，按 `\n\n → \n → 句号 → …` 逐级切分，带重叠避免语义断裂。
- **`embeddings.py`**：`MockEmbedder`（哈希词袋 + L2 归一化，离线确定性），无需密钥即可使用。
- **`vectorstore.py`**：基于 numpy 的本地轻量向量库，**自行计算嵌入并写入预计算向量**，与嵌入实现解耦；cosine 相似度，JSON 单文件持久化。
- **`retriever.py`**：对外主入口，编排 index / retrieve / delete / build_context。

### 3.3 Agent 系统（`core/agent`）

「**规划 → 执行 → 反思**」闭环（ReAct 思想）：

```
query → Planner(拆解为带工具标注的子任务)
      → AgentExecutor(逐步执行, 调用 ToolRegistry 中的工具)
      → 汇总答案
      → Reflector(自我评估; 不满意则在 max_iterations 内迭代)
```

- **`tools.py`**：`BaseTool` 抽象 + `CalculatorTool`（字符白名单防注入）、`DateTimeTool`、`KnowledgeSearchTool`（依赖注入检索回调）；`ToolRegistry` 注册中心。
- **`planner.py` / `reflection.py`**：调用 LLM 产出 JSON，经 `utils/parsing.extract_json` 容错解析；解析失败有兜底计划。
- **`executor.py`**：驱动整个闭环，产出含 `plan / steps / answer / reflection / iterations` 的完整轨迹供前端可视化。

### 3.4 记忆管理（`core/memory`）

- **`store.py`**：SQLite 存储层，`threading.Lock` 保护跨线程访问（FastAPI 线程池场景），三张表 `sessions / messages / long_term`。
- **`manager.py`**：统一门面，提供会话管理、短期历史、长期记忆（含 TTL）、历史检索、过期清理。

---

## 4. 关键数据流

### 4.1 RAG 流式对话

```
前端 POST /api/chat/stream
  → ChatService._prepare_context()
      · use_rag 时：retriever.retrieve() → build_context() → 注入 rag_system 模板
      · 加载会话历史 → 组装 messages
  → provider.stream() 逐块产出
  → SSE: meta(会话/来源/模型) → delta(文本增量)* → done
  → 生成器耗尽后将完整回答写回记忆
```

### 4.2 Agent 任务

```
前端 POST /api/agent
  → AgentExecutor.run()
      → Planner.plan()      (LLM → JSON 子任务)
      → 逐步执行            (按需 ToolRegistry.get(tool).run())
      → LLM 汇总答案
      → Reflector.reflect() (满意则结束，否则迭代)
  → 返回完整轨迹
```

---

## 5. 依赖注入与组合根

`services/container.py` 是唯一的**组合根（Composition Root）**：在应用启动的 `lifespan` 中 `init_container()`，一次性构建并连接所有子系统（LLM 工厂、检索器、记忆、工具、各业务服务）。路由通过 `Depends(get_container)` 获取，避免全局散落的单例与隐式依赖，也便于在测试中替换实现。

`KnowledgeSearchTool` 通过注入 `_knowledge_search` 回调获得检索能力，使 Agent 层不直接耦合 RAG 实现——体现依赖倒置。

---

## 6. 错误处理策略

- **业务异常**：`utils/exceptions.py` 定义 `AppException` 体系（`ValidationError` / `NotFoundError` / `ProviderError` 等），由 `main.py` 的全局处理器统一转为 `{error, message}` 标准响应。
- **兜底**：未预期异常返回 500 且不泄露堆栈。
- **健壮解析**：LLM 输出 JSON 容错；Agent 规划失败退化为单步计划；计算器字符白名单。

---

## 7. 可扩展性

| 需求 | 扩展点 |
| --- | --- |
| 新增 LLM 厂商 | 实现 `BaseLLMProvider` 并在 `LLMFactory` 注册 |
| 新增 Agent 工具 | 实现 `BaseTool` 并 `ToolRegistry.register()` |
| 更换向量库 | 实现与 `VectorStore` 一致的接口（鸭子类型），替换注入即可 |
| 更换嵌入模型 | 实现 `BaseEmbedder` 并在 `create_embedder` 注册 |
| 新增提示模板 | 在 `prompt.py` 注册模板，前端「提示工程」面板自动展示 |
