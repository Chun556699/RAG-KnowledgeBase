/**
 * 前端类型定义。
 *
 * 与后端 Pydantic Schema 对应，保证前后端数据结构一致。
 */

/** 检索命中的文档片段 */
export interface RetrievedChunk {
  text: string
  score: number
  filename: string
}

/** 文档信息 */
export interface DocumentInfo {
  document_id: string
  filename: string
  chunk_count: number
  size_bytes: number
  created_at: number
}

/** 反问澄清（问题模糊时，助手向用户发出的澄清问题与候选方向） */
export interface Clarify {
  question: string
  options: string[]
}

/** RAG 对话响应 */
export interface ChatResponse {
  session_id: string
  answer: string
  sources: RetrievedChunk[]
  provider: string
  model: string
  /** 若本次为反问澄清，则携带澄清问题与候选方向 */
  clarify?: Clarify | null
}

/** 会话信息 */
export interface SessionInfo {
  id: string
  title: string
  created_at: number
  updated_at: number
}

/** 对话消息 */
export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at?: number
  /** 前端专用：该条回答依据的检索来源 */
  sources?: RetrievedChunk[]
  /** 前端专用：若该条为反问澄清，携带候选方向供一键选择 */
  clarify?: Clarify
}

/** LLM 模型信息 */
export interface ModelInfo {
  provider: string
  model: string
  available: boolean
  description: string
}

/** 提示词模板 */
export interface PromptTemplate {
  name: string
  description: string
  template: string
  /** 是否为内置模板（不可删除，仅可覆盖/重置） */
  is_builtin?: boolean
  /** 内置模板是否已被用户覆盖 */
  is_overridden?: boolean
}

/** Agent 子任务（ReAct：含推理依据） */
export interface SubTask {
  step: number
  thought: string
  description: string
  tool: string | null
}

/** Agent 步骤执行结果（ReAct：推理→行动→观察） */
export interface StepResult {
  step: number
  thought: string
  description: string
  tool: string | null
  output: string
}

/** Agent 执行结果 */
export interface AgentResponse {
  query: string
  plan: SubTask[]
  steps: StepResult[]
  answer: string
  reflection: string
  iterations: number
}

/** 长期记忆条目 */
export interface LongTermItem {
  id: number
  key: string
  value: string
  topic: string | null
  importance: number
  created_at: number
}

/** 当前选中的模型（provider + model） */
export interface SelectedModel {
  provider: string
  model: string
}

/** 知识图谱节点（实体） */
export interface GraphNode {
  id: string
  label: string
  weight: number
}

/** 知识图谱边（实体间关系） */
export interface GraphEdge {
  source: string
  target: string
  relation: string
  weight: number
}

/** 知识图谱数据 */
export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  /** 上次构建时间戳，从未构建则为 null */
  built_at?: number | null
}

/** 单个 LLM 提供商的脱敏配置（密钥仅为掩码） */
export interface LLMProviderConfig {
  provider: string
  model: string
  base_url: string
  api_key_masked: string
  has_key: boolean
  available: boolean
  description: string
}

/** 嵌入配置脱敏快照 */
export interface EmbeddingConfig {
  provider: string
  model: string
  base_url: string
  dimension: number
  api_key_masked: string
  has_key: boolean
}

/** 重排序配置脱敏快照 */
export interface RerankerConfig {
  enabled: boolean
  model: string
  base_url: string
  top_n: number
  candidate_k: number
  api_key_masked: string
  has_key: boolean
}

/** 系统设置全量脱敏快照 */
export interface SettingsSnapshot {
  default_provider: string
  llm: LLMProviderConfig[]
  embedding: EmbeddingConfig
  reranker: RerankerConfig
}

/** 连通性测试结果 */
export interface ConnectionTestResult {
  ok: boolean
  message: string
}
