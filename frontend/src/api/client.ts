/**
 * API 客户端。
 *
 * 封装对后端 REST API 的调用，统一处理错误与 JSON 解析。
 * 所有请求走相对路径 /api，由 Vite 开发代理或生产反向代理转发到后端。
 */

import type {
  AgentResponse,
  ChatResponse,
  Clarify,
  ConnectionTestResult,
  DocumentInfo,
  EvaluationResponse,
  GraphData,
  GraphTriple,
  LongTermItem,
  ModelInfo,
  PromptTemplate,
  RetrievedChunk,
  SessionInfo,
  SettingsSnapshot,
  ChatMessage,
} from '../types'

/** 统一的请求错误 */
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

/** 通用 JSON 请求封装 */
async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    // 尝试解析后端标准错误体 { error, message }
    let message = `请求失败 (${resp.status})`
    try {
      const body = await resp.json()
      message = body.message || message
    } catch {
      /* 忽略解析错误 */
    }
    throw new ApiError(resp.status, message)
  }
  return resp.json() as Promise<T>
}

export const api = {
  // -------- 系统 --------
  health: () => request<Record<string, unknown>>('/api/health'),

  // -------- 模型 / 提示词 --------
  listModels: () => request<ModelInfo[]>('/api/models'),
  listPrompts: () => request<PromptTemplate[]>('/api/models/prompts'),
  /** 新建自定义提示词模板 */
  createPrompt: (payload: { name: string; description: string; template: string }) =>
    request<PromptTemplate>('/api/models/prompts', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  /** 更新/覆盖提示词模板 */
  updatePrompt: (name: string, payload: { description: string; template: string }) =>
    request<PromptTemplate>(`/api/models/prompts/${encodeURIComponent(name)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  /** 删除自定义模板（或重置被覆盖的内置模板） */
  deletePrompt: (name: string) =>
    request<{ success: boolean }>(`/api/models/prompts/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    }),

  // -------- 文档 / RAG --------
  listDocuments: () => request<DocumentInfo[]>('/api/documents'),
  deleteDocument: (id: string) =>
    request<{ success: boolean }>(`/api/documents/${id}`, { method: 'DELETE' }),
  search: (query: string, topK = 4) =>
    request<{ query: string; chunks: RetrievedChunk[] }>('/api/documents/search', {
      method: 'POST',
      body: JSON.stringify({ query, top_k: topK }),
    }),
  /** 上传文档（multipart，不设置 Content-Type，交由浏览器自动生成 boundary） */
  uploadDocument: async (file: File): Promise<DocumentInfo> => {
    const form = new FormData()
    form.append('file', file)
    const resp = await fetch('/api/documents/upload', { method: 'POST', body: form })
    if (!resp.ok) {
      let message = `上传失败 (${resp.status})`
      try {
        message = (await resp.json()).message || message
      } catch {
        /* ignore */
      }
      throw new ApiError(resp.status, message)
    }
    const data = await resp.json()
    return data.document as DocumentInfo
  },

  // -------- 对话 --------
  chat: (payload: {
    message: string
    session_id?: string
    provider?: string
    model?: string
    use_rag: boolean
    top_k?: number
    allow_clarify?: boolean
  }) =>
    request<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // -------- Agent --------
  runAgent: (query: string, provider?: string, model?: string) =>
    request<AgentResponse>('/api/agent', {
      method: 'POST',
      body: JSON.stringify({ query, provider, model }),
    }),
  listTools: () =>
    request<{ name: string; description: string }[]>('/api/agent/tools'),

  // -------- 记忆 --------
  listSessions: () => request<SessionInfo[]>('/api/memory/sessions'),
  getMessages: (sessionId: string) =>
    request<ChatMessage[]>(`/api/memory/sessions/${sessionId}/messages`),
  deleteSession: (sessionId: string) =>
    request<{ success: boolean }>(`/api/memory/sessions/${sessionId}`, {
      method: 'DELETE',
    }),
  searchHistory: (keyword: string) =>
    request<ChatMessage[]>(`/api/memory/search?keyword=${encodeURIComponent(keyword)}`),
  listLongTerm: (topic?: string) =>
    request<LongTermItem[]>(
      `/api/memory/long-term${topic ? `?topic=${encodeURIComponent(topic)}` : ''}`,
    ),
  remember: (payload: { key: string; value: string; topic?: string; importance: number }) =>
    request<{ success: boolean }>('/api/memory/long-term', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  cleanupMemory: () =>
    request<{ success: boolean; message: string }>('/api/memory/cleanup', {
      method: 'POST',
    }),

  // -------- 知识图谱 --------
  /** 获取当前已构建的知识图谱 */
  getGraph: () => request<GraphData>('/api/graph'),
  /** 从知识库语料重建知识图谱（调用 LLM 抽取实体关系，耗时较长） */
  buildGraph: (payload?: { provider?: string; model?: string; max_chunks?: number }) =>
    request<GraphData>('/api/graph/build', {
      method: 'POST',
      body: JSON.stringify(payload ?? {}),
    }),

  // -------- 系统设置 --------
  /** 获取系统设置脱敏快照（LLM / 嵌入 / 重排序） */
  getSettings: () => request<SettingsSnapshot>('/api/settings'),
  /** 更新某 LLM 提供商配置（密钥留空/掩码则不修改） */
  updateLLMConfig: (
    provider: string,
    payload: { api_key?: string; base_url?: string; model?: string },
  ) =>
    request<SettingsSnapshot>(`/api/settings/llm/${encodeURIComponent(provider)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  /** 更新重排序配置 */
  updateRerankerConfig: (payload: {
    enabled?: boolean
    api_key?: string
    base_url?: string
    model?: string
    top_n?: number
    candidate_k?: number
  }) =>
    request<SettingsSnapshot>('/api/settings/reranker', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  /** 更新嵌入配置（切换后可能需重建索引） */
  updateEmbeddingConfig: (payload: {
    provider?: string
    api_key?: string
    base_url?: string
    model?: string
    dimension?: number
  }) =>
    request<SettingsSnapshot>('/api/settings/embedding', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  /** 切换默认 LLM 提供商 */
  updateDefaultProvider: (provider: string) =>
    request<SettingsSnapshot>('/api/settings/default-provider', {
      method: 'PUT',
      body: JSON.stringify({ provider }),
    }),
  /** 测试 LLM / 重排序 服务连通性 */
  testConnection: (payload: { section: 'llm' | 'reranker'; provider?: string }) =>
    request<ConnectionTestResult>('/api/settings/test', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // -------- 评估 --------
  /** 评估 RAG 回答质量（faithfulness + answer_relevancy） */
  evaluate: (payload: { question: string; answer: string; context?: string; provider?: string }) =>
    request<EvaluationResponse>('/api/evaluation', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}

/**
 * 流式对话（SSE）。
 *
 * 通过 fetch + ReadableStream 逐块解析后端返回的 SSE 事件，
 * 分别回调元信息（会话/来源）、文本增量与结束事件。
 *
 * @param payload 对话参数
 * @param handlers 事件回调
 */
export async function chatStream(
  payload: {
    message: string
    session_id?: string
    provider?: string
    model?: string
    use_rag: boolean
    top_k?: number
    allow_clarify?: boolean
  },
  handlers: {
    onMeta?: (meta: { session_id: string; sources: RetrievedChunk[]; graph_triples: GraphTriple[]; provider: string; model: string }) => void
    onClarify?: (clarify: Clarify) => void
    onDelta?: (text: string) => void
    onDone?: () => void
    onError?: (err: Error) => void
  },
): Promise<void> {
  try {
    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!resp.ok || !resp.body) {
      throw new ApiError(resp.status, `流式请求失败 (${resp.status})`)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finished = false // 防止 onDone 被重复触发

    // 逐块读取并按 SSE 事件（以空行分隔）解析
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop() || '' // 最后一段可能不完整，留到下轮

      for (const evt of events) {
        const line = evt.trim()
        if (!line.startsWith('data:')) continue
        try {
          const json = JSON.parse(line.slice(5).trim())
          if (json.type === 'meta') handlers.onMeta?.(json)
          else if (json.type === 'clarify') handlers.onClarify?.(json)
          else if (json.type === 'delta') handlers.onDelta?.(json.content)
          else if (json.type === 'done') {
            finished = true
            handlers.onDone?.()
          }
        } catch {
          // 忽略无法解析的事件行，避免单行坏数据中断整个流
        }
      }
    }
    if (!finished) handlers.onDone?.()
  } catch (err) {
    handlers.onError?.(err as Error)
  }
}
