# AI 知识库平台 · 系统全景（求职展示版）

> 一份从 **定位 → 功能 → 技术栈 → 架构 → 设计思想 → 模块深剖 → 技术亮点 → 工程化 → 简历话术** 九个维度撰写的系统全景，既可用于作品集展示，也经得起面试深挖。全部内容以源码为准，不含虚标。

---

## 一、项目定位

**一句话**：独立设计并实现的**生产级 AI 知识库平台**，打通 RAG（真实语义嵌入 + 两阶段重排序）、ReAct 智能体、多模型 LLM、上下文记忆、知识图谱五大能力；支持**在 Web 端完成大模型密钥的接入 / 切换并脱密保护**，前后端分离 + 分层架构，Docker 一键部署。

**解决什么问题**：把「文档摄取 → 向量检索 → 提示工程 → 智能体编排 → 多轮记忆 → 知识图谱 → 前端交互」这条现代 AI 产品的完整链路，收敛到一个可运行、可测试、可扩展的工程实体中。

**关键取舍**：
- **可演示性**：离线确定性 Mock 嵌入让整条 RAG 链路在**零密钥、零外部依赖**下也能真实跑通（利于演示 / CI / 单测）；生产切换为真实语义嵌入。
- **可用性优先**：重排序、澄清、查询改写等增强能力**失败即降级**，绝不阻断主流程。
- **安全**：密钥脱敏、只读 `.env` + 运行时覆盖层，密钥永不出网页。

---

## 二、核心功能

| 模块 | 能力 |
| --- | --- |
| **RAG 检索增强** | 多格式文档（PDF/Word/TXT/Markdown）上传 → 解析 → 递归分块 → 向量化入库；两阶段语义检索（向量召回 + 重排精排）；相关性阈值过滤，无据不编造 |
| **多模型 LLM** | 统一抽象封装 DeepSeek / 小米 MiMo；工厂 + 实例缓存；运行时一键切换；模板化提示工程；SSE 流式输出 |
| **ReAct 智能体** | 复杂任务拆解（规划）→ 工具调用（计算器 / 时间 / 知识库检索）→ 汇总 → 自我反思迭代，全轨迹可视化 |
| **上下文记忆** | 多轮会话上下文维护；长期记忆持久化（主题 + 重要度 + TTL）；跨会话历史检索；过期自动清理 |
| **知识图谱** | LLM 抽取「实体-关系-实体」三元组 → 并发限流 → 聚合去重加权 → cytoscape 可视化 |
| **系统设置** | Web 端配置 / 切换 LLM、嵌入、重排序密钥；脱敏展示；热重载免重启 |
| **前端界面** | 深色主题、响应式；SSE 打字机；检索来源展示；Agent 时间线；实时健康状态 |

---

## 三、技术栈

- **后端**：Python 3.11 · FastAPI · Pydantic v2 · pydantic-settings · asyncio · openai SDK · httpx · numpy · SQLite
- **模型 / 服务**：DeepSeek · 小米 MiMo（OpenAI 兼容）；嵌入 bge-m3；重排序 bge-reranker-v2-m3（OpenAI 兼容 `/rerank`）
- **前端**：React 18 · Vite 5 · TypeScript（strict）· 原生 SSE 流式解析 · cytoscape
- **部署**：Docker · Docker Compose · Nginx（静态托管 + API 反向代理）
- **测试**：pytest · pytest-asyncio（49 例，全离线）

---

## 四、整体架构

**前后端分离 + 后端四层**，依赖方向自上而下，核心能力不感知上层。

```
┌──────────────────────────────────────────────────────────┐
│                    浏览器（React SPA）                     │
│   Chat / Documents / Graph / Agent / Memory / Prompt /     │
│   Settings 面板                                            │
└───────────────────────────┬──────────────────────────────┘
                            │ HTTP / SSE  (开发: Vite Proxy；生产: Nginx)
┌───────────────────────────▼──────────────────────────────┐
│                    FastAPI 应用 (main.py)                  │
│      CORS · 全局异常 · 生命周期(lifespan) · 路由注册         │
├──────────────────────────────────────────────────────────┤
│  API 路由层  documents·chat·agent·memory·models·graph·      │
│             settings                                       │
├──────────────────────────────────────────────────────────┤
│  服务编排层  Container(组合根) · Document/Chat/Agent/Graph   │
│             Service                                        │
├──────────────────────────────────────────────────────────┤
│  核心能力层  LLM · RAG · Agent · Memory · Graph             │
│             + RuntimeConfigStore(运行时配置层)              │
├──────────────────────────────────────────────────────────┤
│  基础设施   numpy 向量库 · SQLite · 文件系统 · 外部 LLM/嵌入 │
└──────────────────────────────────────────────────────────┘
```

| 层 | 目录 | 职责 |
| --- | --- | --- |
| 路由层 | `app/api/` | HTTP 端点、参数校验、序列化；不含业务逻辑 |
| 服务编排层 | `app/services/` | 编排核心能力完成业务用例；组合根统一装配 |
| 核心能力层 | `app/core/` | 领域纯逻辑：LLM / RAG / Agent / Memory / Graph；可独立测试 |
| 基础设施 | 第三方 / 标准库 | numpy 向量库、SQLite、文件系统 |
| 横切工具 | `app/utils/` | 日志、异常、LLM 输出解析 |

---

## 五、设计思想

- **依赖倒置（DIP）**：上层只依赖抽象（`BaseLLMProvider` / `BaseEmbedder` / `BaseReranker` / `BaseTool` / `VectorStore` 接口），实现可插拔替换。
- **组合根（Composition Root）**：`services/container.py` 是唯一装配点，在 `lifespan` 中一次性构建并连接所有子系统，路由通过 `Depends(get_container)` 获取，杜绝散落单例与隐式依赖。
- **工厂模式**：LLM / 嵌入 / 重排序均以工厂创建，按配置产出对应实现，新增厂商符合开闭原则。
- **单一事实来源**：凭据统一由 `RuntimeConfigStore` 提供（运行时覆盖层叠加只读 `.env`），LLM 工厂 / 嵌入 / 重排序全部从它读取「有效配置」。
- **优雅降级**：重排序、澄清、查询改写、Agent 规划均有失败兜底，保障可用性。
- **可测试性**：核心层不依赖 Web 框架，离线 Mock 让 49 例单测无需密钥 / 网络。

---

## 六、模块深剖

### 6.1 RAG 检索增强（`core/rag`）

**数据流**
```
文档 → loader(多格式解析) → splitter(递归分块) → embedder → VectorStore(numpy) + BM25Index
查询 → 向量召回 + BM25 稀疏召回 → RRF 融合 → Reranker 精排 top_n → build_context → LLM
```

- **嵌入-存储解耦**：`BaseEmbedder` 抽象 + `create_embedder` 工厂；`MockEmbedder`（哈希词袋 + L2 归一化，离线兜底，384 维）与 `OpenAICompatibleEmbedder`（真实语义，bge-m3，1024 维，服务端返回维度后回写）可插拔。
- **混合检索**：`BM25Index`（中文单字 + bigram 分词，零依赖）与向量检索并行召回，`Retriever._rrf_fuse` 做加权 RRF（Reciprocal Rank Fusion）融合，两路权重可配置（`hybrid_dense_weight` / `hybrid_sparse_weight`），专有名词 / 精确匹配召回显著提升。
- **两阶段检索**：`enabled` 为真时先向量召回 `candidate_k`（默认 20）候选，再由 `SiliconFlowReranker` 调用 OpenAI 兼容 `/rerank` 精排至 `top_n`，最后按 `min_score` 过滤；重排 `try/except` **失败自动降级**为向量结果。
- **本地向量库**：numpy 计算 cosine 相似度，支持元数据（`document_id` 等）过滤、按文档删除、JSON 单文件持久化；嵌入与存储解耦（写入预计算向量）。
- **递归分块**：按 `\n\n → \n → 句号 …` 逐级切分，`chunk_size=500 / overlap=50`，避免语义断裂。
- **健壮性**：`retrieval_min_score` 过滤噪音、命中为空如实回退不编造；支持多轮追问的**查询改写**与问题模糊时的**反问澄清**（均可降级）。

### 6.2 LLM 抽象层（`core/llm`）

```
BaseLLMProvider (抽象: generate / stream)
   └─ OpenAICompatibleProvider (统一封装 DeepSeek / 小米 MiMo)
LLMFactory (按 provider:model 缓存 + 运行时切换 + 可用性标记 + invalidate 热重载)
prompt.py (模板化提示，{变量} 运行时渲染)
```

- **工厂 + 实例缓存**：按 `provider:model` 复用实例；`available_models()` 依据密钥配置动态标记可用性；凭据来自运行时配置层，网页改密钥后 `invalidate()` 清缓存即时生效。
- **全异步 + SSE**：`stream()` 异步产出，`meta → delta* → done` 三段式；前端手写 SSE 解析实现打字机效果。
- **提示工程**：模板与业务解耦，前端「提示工程」面板可增删改查，内置模板作只读基线可覆盖 / 重置。

### 6.3 ReAct 智能体（`core/agent`）

```
query → Planner(拆解为带工具标注的子任务)
      → AgentExecutor 逐步执行(有工具调工具, 否则 LLM 作答)
      → Synthesize 汇总答案
      → Reflector 反思(满意则止, 否则携建议在 max_iterations 内再迭代)
```

- **工具注册中心**：`BaseTool` 抽象 + `ToolRegistry`；内置 `CalculatorTool`（字符白名单**防注入**）、`DateTimeTool`、`KnowledgeSearchTool`（注入检索回调，Agent 不直接耦合 RAG）。
- **健壮解析**：Planner / Reflector 的 LLM 输出经 `utils/parsing.extract_json` 容错抽取；**规划失败退化为单步计划**。
- **可视化轨迹**：产出 `plan / steps(thought,tool,output) / answer / reflection / iterations`，前端渲染思考时间线。

### 6.4 上下文记忆（`core/memory`）

**存储设计（SQLite / 线程安全）**
```
sessions   会话元数据(id, title, 时间戳)
messages   多轮消息(session_id 外键, role, content) + idx_messages_session
long_term  长期记忆(key, value, topic, importance, expires_at) + idx_long_term_topic
```

- **统一门面** `MemoryManager`：会话管理、短期历史、长期记忆、历史检索与清理。
- **短期记忆**：按 `max_history_turns`（默认 20）截断最近 N 轮注入上下文；取出降序再反转保证时间升序。
- **长期记忆**：`importance` 重要度 + `topic` 主题 + **TTL 过期**；`recall()` 按「重要度 → 时间」排序并自动过滤过期项；`cleanup_expired()` 主动清理。
- **并发正确性**：`sqlite3` 连接非线程安全，用 `threading.Lock` 保护跨线程访问（FastAPI 线程池），`check_same_thread=False` 配合锁复用连接。

### 6.5 知识图谱（`core/graph`）

```
全量片段 → round-robin 均衡采样 → asyncio 并发 LLM 抽取三元组
        → 聚合去重(节点/边加权) → 持久化 → cytoscape 可视化 + 图增强检索(GraphRAG)
```

- **并发限流**：`asyncio.Semaphore(graph_extract_concurrency)`（默认 4）限制 LLM 并发，`asyncio.gather` 批量抽取「实体-关系-实体」；**单片段失败不阻断**整体。
- **均衡采样**：按 `document_id` 分桶后 round-robin 轮流取片段，避免大文档垄断，`graph_max_chunks` 控成本（默认 40）。
- **聚合去重加权**：实体归一化为 key 去重、重复累加节点 `weight`（热度）；`(source, target, relation)` 唯一化边并累加权重（关系强度）。
- **图增强检索（GraphRAG）**：`GraphSearcher` 将图谱纳入问答检索——查询匹配实体 → 沿边邻居扩展（1 跳）→ 返回相关三元组；ChatService 将图谱三元组与文档片段合并注入提示词，捕捉间接关联与多跳语义。
- **稳定输出**：抽取 `temperature=0.0`，`extract_json` 容错，非法项跳过。

### 6.6 运行时配置层与脱密（`core/config_store`）

- **分层配置**：`data/runtime_config.json`（网页可改覆盖层）叠加只读 `.env`（基线），覆盖层非空字段生效，作凭据**单一事实来源**。
- **脱密保护**：对外快照只返回掩码密钥（`sk-a****wxyz`）；更新时「空值 / 掩码值视为不修改」，避免回填掩码误清真实密钥；密钥永不出网页。
- **热重载**：`RLock` + 原子落盘（临时文件替换）+ `revision` 自增；`reload_llm / reload_reranker / reload_embedding` 热替换实现，**无需重启**。

---

## 七、技术亮点（面试可深挖）

- **为什么加重排序？** 单阶段向量召回受 bi-encoder 表达力限制，长尾 / 近义 query 排序不稳；引入 cross-encoder 对 query-doc 逐对精排，用「召回宽 + 精排准」换质量，并做失败降级守住可用性——体现对检索质量与稳定性的权衡。
- **密钥脱密怎么做的？** 读接口只出掩码；写接口把「空值 / 掩码值」判定为「不修改」，避免误清真实密钥；`.env` 只读、覆盖层落盘、`RLock` + 原子写——体现安全意识与并发正确性。
- **为什么保留 Mock 嵌入？** 保证零密钥跑通整条链路 → 演示、CI、单测全离线（49 例）；生产切真实语义嵌入——体现可测试性与工程化取舍。
- **知识图谱如何兼顾速度 / 成本 / 稳定？** 信号量限流 + gather 并发 + round-robin 采样 + 单片段失败隔离。
- **Agent 如何避免脆弱？** 规划失败兜底单步、工具白名单防注入、JSON 容错解析、反思迭代上限。

---

## 八、工程化

- **测试**：49 例 pytest 单测，覆盖嵌入 / 分块 / 解析 / 记忆 / 工具 / LLM 工厂 / 检索 / 向量库，**全离线无需密钥**。
- **配置**：pydantic-settings 类型校验 + 默认值，`ensure_directories()` 首启自动建目录，默认零密钥可跑。
- **错误处理**：`AppException` 体系（`ValidationError / NotFoundError / ProviderError`）→ 全局处理器统一 `{error, message}`；未预期异常返回 500 不泄露堆栈。
- **可观测**：统一 logger，关键路径（向量库就绪、记忆连接、工具注册、图谱构建、配置变更）均有日志。
- **部署**：多阶段 Dockerfile + docker-compose 一键编排；Nginx 静态托管 + `/api` 反向代理。
- **可扩展点**：新增 LLM 厂商 / Agent 工具 / 向量库 / 嵌入模型 / 提示模板均有明确扩展位，符合开闭原则。

---

## 九、简历话术

**一句话项目描述**
> 独立设计并实现生产级 AI 知识库平台，集成 RAG（真实语义嵌入 + 两阶段重排序）、ReAct 智能体、多模型 LLM、上下文记忆与知识图谱五大能力，支持 Web 端大模型密钥热切换与脱密保护，前后端分离 + 分层架构，Docker 一键部署。

**核心 bullet（4 条精简版）**
- **RAG 两阶段检索**：bge-m3（1024 维语义嵌入）向量召回 + bge-reranker-v2-m3 精排，重排失败自动降级；`BaseEmbedder` 抽象让真实语义 / 离线 Mock 可插拔，自研 numpy 向量库支持 cosine + 元数据过滤 + 持久化。
- **LLM 抽象层 + 工厂**：统一封装 OpenAI 兼容厂商（DeepSeek / MiMo），按 `provider:model` 缓存实例、依据密钥标记可用性、运行时热切换；全异步 `meta→delta*→done` SSE 流式对话。
- **上下文记忆管理**：SQLite 三表（会话 / 消息 / 长期记忆）+ 索引，`threading.Lock` 保障线程池并发安全；长期记忆按重要度 + 主题 + TTL「新陈代谢」，支持跨会话历史检索与自动清理。
- **知识图谱**：`asyncio.Semaphore` 限流 + `gather` 并发调 LLM 抽取「实体-关系-实体」三元组，单片段失败不阻断；round-robin 均衡采样、实体归一化去重加权，cytoscape 可视化。

**加分 bullet（可替换 / 追加）**
- **Web 端密钥热切换 + 脱密**：运行时配置层叠加只读 `.env`，网页即可切换多模型 / 嵌入 / 重排序密钥且免重启；对外仅返回掩码，密钥不出网页。
- **架构工程化**：分层 + 组合根 + 依赖倒置，核心层可独立单测（49 例全离线通过）。

**ATS 关键词**
> `Python · FastAPI · asyncio · Pydantic v2 · RAG · 向量检索 · Embedding(bge-m3) · Reranker(cross-encoder) · 两阶段检索 · LLM · Agent · ReAct · Prompt Engineering · SSE 流式 · 密钥脱敏 · 热重载 · React 18 · TypeScript · Vite · cytoscape · Docker · Nginx · SQLite · numpy · 工厂模式 · 依赖倒置 · 组合根 · 单元测试`
