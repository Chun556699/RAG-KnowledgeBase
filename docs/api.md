# API 文档

所有接口以 `/api` 为前缀。开发环境经 Vite 代理、生产环境经 Nginx 反向代理转发到后端。

- **交互式文档（Swagger UI）**：<http://localhost:8000/docs>
- **OpenAPI Schema**：<http://localhost:8000/openapi.json>

统一错误响应体：

```json
{ "error": "ValidationError", "message": "错误描述" }
```

---

## 系统

### `GET /api/health`
健康检查，返回服务状态与已索引片段数。

```json
{
  "status": "ok",
  "app": "AI Knowledge Base",
  "env": "development",
  "default_provider": "deepseek",
  "indexed_chunks": 12
}
```

---

## 模型 / 提示词

### `GET /api/models`
列出全部 LLM 提供商及可用状态（真实厂商需配置密钥）。

```json
[
  { "provider": "deepseek", "model": "deepseek-chat", "available": true, "description": "DeepSeek 深度求索（OpenAI 兼容）" },
  { "provider": "mimo", "model": "mimo-7b-rl", "available": false, "description": "小米 MiMo（OpenAI 兼容）" }
]
```

### `GET /api/models/prompts`
列出全部内置提示词模板（提示工程展示）。

```json
[
  { "name": "rag_system", "description": "RAG 系统提示", "template": "……参考资料：{context}" }
]
```

---

## 文档 / RAG

### `POST /api/documents/upload`
上传并索引文档。`multipart/form-data`，字段名 `file`。支持 PDF / Word(.docx) / TXT / Markdown。

**响应**

```json
{
  "document": {
    "document_id": "a1b2c3",
    "filename": "guide.pdf",
    "chunk_count": 8,
    "size_bytes": 20480,
    "created_at": 1721520000.0
  },
  "message": "文档上传并索引成功"
}
```

### `GET /api/documents`
列出已索引文档（按上传时间降序）。

### `DELETE /api/documents/{document_id}`
删除文档及其向量索引与磁盘文件。返回 `{ "success": true, "message": "文档已删除" }`。

### `POST /api/documents/search`
纯语义检索（不经 LLM 生成）。

**请求**

```json
{ "query": "什么是向量检索", "top_k": 5 }
```

**响应**

```json
{
  "query": "什么是向量检索",
  "chunks": [
    { "text": "向量检索是……", "score": 0.87, "filename": "guide.pdf" }
  ]
}
```

---

## 对话（RAG）

### `POST /api/chat`
一次性返回完整回答。

**请求**

```json
{
  "message": "介绍一下这份文档的主题",
  "session_id": null,
  "provider": "deepseek",
  "model": "deepseek-chat",
  "use_rag": true,
  "top_k": 4
}
```

**响应**

```json
{
  "session_id": "f7e6d5",
  "answer": "根据知识库检索到的资料……",
  "sources": [ { "text": "……", "score": 0.83, "filename": "guide.pdf" } ],
  "provider": "deepseek",
  "model": "deepseek-chat"
}
```

### `POST /api/chat/stream`
SSE 流式对话。请求体同上，响应 `Content-Type: text/event-stream`。

每个事件为一行 `data: {json}\n\n`，类型如下：

| 事件 | 载荷 | 说明 |
| --- | --- | --- |
| `meta` | `{ type, session_id, provider, model, sources }` | 首个事件，携带会话与检索来源 |
| `delta` | `{ type, content }` | 文本增量（打字机效果） |
| `done` | `{ type }` | 结束标记 |

> 提示：为支持流式实时下发，Nginx 侧已关闭 `proxy_buffering`。

---

## Agent 智能体

### `POST /api/agent`
运行智能体任务，返回完整执行轨迹。

**请求**

```json
{ "query": "帮我计算 (128 + 56) * 3", "provider": "deepseek", "model": "deepseek-chat" }
```

**响应**

```json
{
  "query": "帮我计算 (128 + 56) * 3",
  "plan": [ { "step": 1, "description": "计算表达式", "tool": "calculator" } ],
  "steps": [ { "step": 1, "description": "计算表达式", "tool": "calculator", "output": "计算结果：(128 + 56) * 3 = 552" } ],
  "answer": "最终答案……",
  "reflection": "回答已满足需求。",
  "iterations": 1
}
```

### `GET /api/agent/tools`
列出可用工具。

```json
[ { "name": "calculator", "description": "计算数学算术表达式……" } ]
```

---

## 记忆管理

### 会话

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/memory/sessions` | 创建会话，body `{ "title": "新会话" }` |
| `GET` | `/api/memory/sessions` | 列出会话（按最近更新） |
| `GET` | `/api/memory/sessions/{id}/messages` | 获取会话历史消息 |
| `DELETE` | `/api/memory/sessions/{id}` | 删除会话及其消息 |

### 历史检索

### `GET /api/memory/search?keyword=xxx&limit=20`
跨会话按关键词检索历史消息。

### 长期记忆

### `POST /api/memory/long-term`
写入长期记忆。

```json
{ "key": "用户偏好语言", "value": "中文", "topic": "偏好", "importance": 5 }
```

### `GET /api/memory/long-term?topic=偏好&limit=20`
检索长期记忆（自动过滤已过期项，按重要度与时间排序）。

### `POST /api/memory/cleanup`
手动触发过期长期记忆清理，返回 `{ "success": true, "message": "已清理 N 条过期记忆" }`。

---

## 使用示例（curl）

```bash
# 健康检查
curl http://localhost:8000/api/health

# 上传文档
curl -F "file=@./guide.pdf" http://localhost:8000/api/documents/upload

# 语义检索
curl -X POST http://localhost:8000/api/documents/search \
  -H "Content-Type: application/json" \
  -d '{"query":"向量检索","top_k":3}'

# 一次性对话
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"总结这份文档","use_rag":true}'

# 运行 Agent
curl -X POST http://localhost:8000/api/agent \
  -H "Content-Type: application/json" \
  -d '{"query":"帮我计算 (128 + 56) * 3"}'
```
