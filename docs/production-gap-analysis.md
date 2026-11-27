# 当前仓库生产级差距审计

> 审计日期：2026-11-28  
> 基线：`main` 分支当前实现；后端 `pytest` 74 例全部通过，前端可构建（存在单 bundle 超 500 kB 警告）。  
> 结论：当前项目是一个**结构清晰、可离线演示、适合作为作品集/单机原型的 RAG Demo**；但按真实企业生产标准，它还不具备多租户、权限、安全、异步摄取、可扩展检索、评估门禁和可观测性。

---

## 1. 现状优点

1. 分层清晰：`api → services → core` 的责任边界较好，`services/container.py` 具备组合根思想。
2. 离线可跑：Mock 嵌入、numpy 向量库、SQLite 让演示与单元测试无需外部服务。
3. 已有先进概念雏形：混合检索、RRF、Cross-Encoder rerank、CRAG、GraphRAG、RAGAS 风格评估、SSE。
4. 可插拔意识好：LLM、Embedder、Reranker 均有抽象或工厂。
5. 测试基础可用：审计基线 74 个离线单元测试全部通过；本分支新增 BM25 重启回归测试后为 78 个，适合继续扩展为核心逻辑回归网。

这些优点应该保留，不应推倒重写。

---

## 2. 关键生产差距

### 2.1 认证、授权与多租户（最高优先级）

| 现状 | 生产风险 | 目标 |
|---|---|---|
| 所有 API 无认证 | 任何人可上传/删除文档、改密钥、读取会话 | OIDC/API key/OAuth2 认证 |
| 无 tenant/user/kb 概念 | 无法做企业隔离、配额、审计 | PostgreSQL 控制面，租户/用户/组/知识库模型 |
| 无文档级 ACL | 一旦索引，所有用户可检索全部内容 | ACL 随 chunk 进入 payload，检索前强制过滤 |
| 无审计日志 | 无法满足合规与事故追踪 | 所有管理/删除/查询敏感操作写 audit_events |

### 2.2 摄取管道

| 现状 | 生产风险 | 目标 |
|---|---|---|
| 上传请求内同步解析/嵌入/索引 | 大文件阻塞请求；失败不可恢复；无法横向扩展 | 上传返回 202，RabbitMQ/Celery 后台任务 |
| 无任务状态、重试、幂等、DLQ | worker/网络失败后重复或丢失索引 | job 状态机 + 幂等键 + 重试 + 死信 |
| 原始文件直接写本地磁盘 | 多副本不可共享；备份/版本化困难 | S3/MinIO 不可变对象存储 |
| 文档无 hash/version/pipeline_version | 无法增量同步、去重、重建与审计 | document/document_version/pipeline 元数据 |
| 无删除/权限撤销传播机制 | 撤权后仍可能被旧索引检索 | tombstone + 版本化删除 + 对账任务 |

### 2.3 文档解析与分块

| 现状 | 生产风险 | 目标 |
|---|---|---|
| 仅 PDF/DOCX/TXT/Markdown | 企业常见扫描件、PPT、Excel、图片、HTML、音频不可用 | Docling/MinerU 分层解析 + 连接器 |
| PDF 只 `extract_text()` | 扫描件、双栏、页眉页脚、表格、公式、图片文字质量差 | 版面/OCR/表格结构解析，保留页码和 bbox |
| 固定字符递归分块 | 中文 token 不准，表格/代码/标题易被切坏 | 结构感知 + token 感知 + parent-child |
| chunk 元数据过少 | 无法精确引用页码/章节，无法做 ACL/版本过滤 | chunk 级完整 metadata 与引用 ID |

### 2.4 检索与向量底座

| 现状 | 生产风险 | 目标 |
|---|---|---|
| numpy 全量扫描 + JSON 单文件 | O(N) 扫描，内存/磁盘/并发都不可扩展 | Qdrant/pgvector/Milvus 等生产检索引擎 |
| BM25Index 只存在内存且启动时为空 | **重启后混合检索退化为单向量路**，且无法持久化/共享 | BM25/sparse 与 dense 一并进检索引擎 |
| 无 ANN/量化/索引容量管理 | 大规模延迟和内存不可控 | HNSW、量化、分片、副本、容量监控 |
| 无 tenant/ACL payload pre-filter | 多租户不可用 | 检索前强制 payload filter |
| 阈值/RRF/rerank 分数混用 | 不同分数尺度不可直接比较，容易误过滤 | 分数语义统一，阈值按路径标定并评估 |

### 2.5 查询编排与生成

| 现状 | 生产风险 | 目标 |
|---|---|---|
| 所有问题走同一条 RAG 流水线 | 简单问题浪费成本，复杂问题质量不足 | Query Router 分流 fast/agentic/graph/table |
| 查询改写、澄清、CRAG 串行叠加 | 延迟和 token 成本上升 | 按复杂度和置信度按需触发 |
| GraphRAG 只有简单实体 1 跳扩展 | 难支撑真正多跳/全局总结 | 增量图谱 + 社区摘要 + 查询路由按需启用 |
| 无引用 ID/claim 校验 | 引用可能看似专业但不支持答案 | evidence snapshot + citation validation |
| 无上下文 token 预算/压缩策略 | 上下文膨胀、成本高、关键证据被截断 | parent expansion + dedupe/MMR + token budget |

### 2.6 模型与密钥

| 现状 | 生产风险 | 目标 |
|---|---|---|
| 密钥保存在本地 JSON 配置文件 | 文件泄漏即密钥泄漏；无 KMS/轮换 | Secret Manager/Vault/KMS，密钥引用而非明文 |
| 仅 DeepSeek/MiMo 两个提供商硬编码 | 无法快速接入企业批准模型/私有模型 | LiteLLM Gateway + 模型别名 + provider adapter |
| 无 fallback/budget/rate limit/cost accounting | 单 provider 故障或成本失控 | 网关级 failover、配额、成本日志 |
| 嵌入切换后仅提示“重建索引” | 新旧向量空间混用导致质量不可控 | 模型版本化 + blue/green reindex |

### 2.7 记忆与安全

| 现状 | 生产风险 | 目标 |
|---|---|---|
| 会话/长期记忆无用户绑定 | 无法隔离个人记忆，可能跨用户泄漏 | user/tenant scoped memory |
| 长期记忆无显式同意/写入审核 | 记忆投毒会污染后续所有会话 | memory write guard + 用户可见/可删 |
| 文档内容直接进 prompt | 间接 prompt injection | 数据/指令分层、内容消毒、工具白名单 |
| 上传无大小、页数、病毒扫描 | zip bomb/恶意文件/资源耗尽 | 文件安全管道与隔离区 |

### 2.8 评估、观测与运维

| 现状 | 生产风险 | 目标 |
|---|---|---|
| 评估只有单次 faithfulness/relevancy | 无法量化检索质量、引用质量、拒绝正确性 | golden dataset + retrieval/generation/security metrics |
| 无 CI 质量门禁 | prompt/模型/chunk 改动可能静默退化 | 每次变更跑 golden set，指标回归阻断发布 |
| 只有普通日志 | 无法定位慢在检索、重排还是 LLM | OpenTelemetry traces + metrics + Langfuse |
| 无 token/成本/租户维度报表 | 无法控费、计费、容量规划 | cost per tenant/query/model dashboard |
| Docker compose 只有 frontend/backend | 不是生产拓扑 | PostgreSQL/Qdrant/MinIO/RabbitMQ/Redis/OTel 完整编排或 Helm |

---

## 3. 需要立即修正的具体实现问题

已在本次分支顺手修复两项低风险问题：

- **BM25 重启丢失（已修复）**：`Retriever.rebuild_sparse_index()` 会在启动时从 `VectorStore.all_chunks()` 回填内存 BM25，并新增回归测试。
- **文档测试数量过期（已修复）**：README/系统文档已从 49 例更新为当前 78 例。

仍需立即修正：

1. **上传完全不限制大小**：注释明确“不限制单文件大小”，生产环境会导致内存和磁盘 DoS。
2. **同步上传路径过重**：即使使用 `asyncio.to_thread`，也只是避免阻塞 event loop，不能解决失败恢复、横向扩展与任务可观测。
3. **runtime_config.json 明文密钥**：虽然有掩码展示，但磁盘文件仍是明文，且没有文件权限/KMS/审计保护。
4. **检索分数语义混乱**：dense cosine、BM25 原始分、RRF 归一化分、reranker relevance score 都进入同一个 `score` 字段和阈值逻辑，过滤结果不可解释。
5. **无并发安全边界**：本地 JSON/SQLite/numpy 组合适合单进程，无法在多副本 API 下保持一致。
6. **GraphRAG 名称过度使用**：当前是实体三元组 + 1 跳邻居扩展，不是完整 Microsoft GraphRAG 风格的社区检测/全局摘要体系。

---

## 4. 迁移优先级 backlog

### P0：不解决就不能上生产

- [ ] 认证、租户、用户、角色、知识库权限。
- [ ] 文档 ACL 元数据与检索前强制过滤。
- [ ] 上传安全限制、病毒扫描、文件隔离。
- [ ] 异步摄取任务、幂等、重试、状态查询。
- [ ] PostgreSQL 控制面 + S3/MinIO 原始文件。
- [ ] 生产向量/稀疏索引底座（默认 Qdrant）。
- [ ] Secret Manager/KMS，移除明文密钥文件。
- [ ] 审计日志与删除传播。

### P1：决定问答质量

- [ ] Docling/MinerU 复杂文档解析。
- [ ] 结构感知 parent-child chunking。
- [ ] Qdrant dense + BM25/sparse hybrid + payload filter。
- [ ] Qwen3/bge reranker 两阶段检索。
- [ ] evidence snapshot、citation ID、引用校验。
- [ ] Query Router 与 fast path/agentic path 分离。
- [ ] golden dataset + CI 质量门禁。

### P2：决定企业可运营性

- [ ] LiteLLM gateway、fallback、预算、限流、成本报表。
- [ ] OpenTelemetry + Langfuse + Grafana dashboard。
- [ ] 租户配额、模型别名、成本归因。
- [ ] 反馈闭环、badcase 回填、在线抽样评估。
- [ ] 连接器框架与增量同步。

### P3：高级场景

- [ ] LangGraph 多步检索与工具预算。
- [ ] MCP 工具代理与审批。
- [ ] Graph-assisted retrieval。
- [ ] 表格结构化查询。
- [ ] 多模态图片/音频/视频索引。

---

## 5. 验证基线

本次审计在干净克隆后执行：

```bash
cd backend
python -m venv .venv
pip install -r requirements.txt
pytest -q
# 审计基线结果：74 passed；本分支新增回归测试后：78 passed

cd frontend
npm ci
npm run build
# 结果：构建成功；Vite 提示 bundle 超 500 kB
```

这些结果说明当前代码是一个健康原型，但不能把“测试通过”误解为“生产可上线”。生产级还需要权限、数据一致性、运维、质量和安全的系统性验证。
