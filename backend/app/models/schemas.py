"""
API 请求 / 响应数据模型（Pydantic Schema）。

集中定义对外接口的输入输出结构，提供自动校验与 OpenAPI 文档生成。
按业务模块分组：通用、文档、对话、Agent、记忆、模型。
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ======================== 通用 ========================
class ErrorResponse(BaseModel):
    """统一错误响应体。"""

    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误描述")


class OkResponse(BaseModel):
    """通用成功响应体。"""

    success: bool = True
    message: str = "操作成功"


# ======================== 文档 / RAG ========================
class DocumentInfo(BaseModel):
    """文档信息。"""

    document_id: str = Field(..., description="文档唯一 ID")
    filename: str = Field(..., description="原始文件名")
    chunk_count: int = Field(..., description="切分后的片段数")
    size_bytes: int = Field(..., description="文件大小（字节）")
    created_at: float = Field(..., description="上传时间戳")


class UploadResponse(BaseModel):
    """文档上传响应。"""

    document: DocumentInfo
    message: str = "文档上传并索引成功"


class RetrievedChunkSchema(BaseModel):
    """检索片段。"""

    text: str = Field(..., description="片段文本")
    score: float = Field(..., description="相似度分数 0~1")
    filename: str = Field(..., description="来源文件名")


class GraphTripleSchema(BaseModel):
    """知识图谱检索命中的实体关系三元组。"""

    source: str = Field(..., description="起始实体")
    relation: str = Field(..., description="关系描述")
    target: str = Field(..., description="目标实体")


class SearchRequest(BaseModel):
    """语义检索请求。"""

    query: str = Field(..., min_length=1, description="检索查询文本")
    top_k: int = Field(4, ge=1, le=20, description="返回片段数")


class SearchResponse(BaseModel):
    """语义检索响应。"""

    query: str
    chunks: List[RetrievedChunkSchema]


# ======================== 对话 / Chat ========================
class ChatRequest(BaseModel):
    """RAG 对话请求。"""

    message: str = Field(..., min_length=1, description="用户消息")
    session_id: Optional[str] = Field(None, description="会话 ID，为空则新建会话")
    provider: Optional[str] = Field(None, description="LLM 提供商，覆盖默认值")
    model: Optional[str] = Field(None, description="模型名，覆盖默认值")
    use_rag: bool = Field(True, description="是否启用知识库检索增强")
    top_k: int = Field(4, ge=1, le=20, description="RAG 检索片段数")
    allow_clarify: bool = Field(
        True,
        description="是否允许本轮反问澄清（用户回应澄清后应置为 false，直接作答）",
    )


class ClarifySchema(BaseModel):
    """反问澄清结果（问题模糊时，助手向用户发出的澄清问题）。"""

    question: str = Field(..., description="向用户反问的澄清问题")
    options: List[str] = Field(
        default_factory=list, description="候选澄清方向，供用户一键选择"
    )


class ChatResponse(BaseModel):
    """RAG 对话响应（非流式）。"""

    session_id: str
    answer: str
    sources: List[RetrievedChunkSchema] = Field(
        default_factory=list, description="回答所依据的检索来源"
    )
    graph_triples: List[GraphTripleSchema] = Field(
        default_factory=list, description="图谱增强检索命中的实体关系三元组"
    )
    provider: str
    model: str
    clarify: Optional[ClarifySchema] = Field(
        None, description="若本次为反问澄清，则携带澄清问题与候选方向；否则为空"
    )


# ======================== Agent ========================
class AgentRequest(BaseModel):
    """Agent 任务请求。"""

    query: str = Field(..., min_length=1, description="复杂查询/任务")
    provider: Optional[str] = Field(None, description="LLM 提供商")
    model: Optional[str] = Field(None, description="模型名")


class SubTaskSchema(BaseModel):
    """子任务（ReAct 风格，含推理依据）。"""

    step: int
    thought: str = Field("", description="规划该步时的推理依据")
    description: str
    tool: Optional[str] = None


class StepResultSchema(BaseModel):
    """子任务执行结果（ReAct：推理→行动→观察）。"""

    step: int
    thought: str = Field("", description="该步的推理依据")
    description: str
    tool: Optional[str]
    output: str


class AgentResponse(BaseModel):
    """Agent 执行结果。"""

    query: str
    plan: List[SubTaskSchema]
    steps: List[StepResultSchema]
    answer: str
    reflection: str
    iterations: int


# ======================== 记忆 ========================
class SessionSchema(BaseModel):
    """会话信息。"""

    id: str
    title: str
    created_at: float
    updated_at: float


class MessageSchema(BaseModel):
    """对话消息。"""

    role: str
    content: str
    created_at: float


class CreateSessionRequest(BaseModel):
    """创建会话请求。"""

    title: str = Field("新会话", description="会话标题")


class RememberRequest(BaseModel):
    """写入长期记忆请求。"""

    key: str = Field(..., description="记忆键")
    value: str = Field(..., description="记忆值")
    topic: Optional[str] = Field(None, description="主题标签")
    importance: int = Field(1, ge=1, le=5, description="重要度 1~5")


class LongTermItemSchema(BaseModel):
    """长期记忆条目。"""

    id: int
    key: str
    value: str
    topic: Optional[str]
    importance: int
    created_at: float


# ======================== 模型 ========================
class ModelInfo(BaseModel):
    """LLM 模型信息。"""

    provider: str
    model: str
    available: bool
    description: str


class PromptTemplateSchema(BaseModel):
    """提示词模板。"""

    name: str
    description: str
    template: str
    is_builtin: bool = Field(False, description="是否为内置模板（不可删除）")
    is_overridden: bool = Field(False, description="内置模板是否已被用户覆盖")


class PromptCreateRequest(BaseModel):
    """新建提示词模板请求。"""

    name: str = Field(..., min_length=1, description="模板唯一标识")
    description: str = Field("", description="模板用途说明")
    template: str = Field(..., min_length=1, description="含占位符的模板内容")


class PromptUpdateRequest(BaseModel):
    """更新（含覆盖内置）提示词模板请求。"""

    description: str = Field("", description="模板用途说明")
    template: str = Field(..., min_length=1, description="含占位符的模板内容")


# ======================== 知识图谱 ========================
class GraphNodeSchema(BaseModel):
    """知识图谱节点（实体）。"""

    id: str = Field(..., description="节点唯一标识（实体归一化后的键）")
    label: str = Field(..., description="节点显示名称（实体原文）")
    weight: int = Field(1, description="节点权重（关联度/出现频次，越大越重要）")


class GraphEdgeSchema(BaseModel):
    """知识图谱边（实体间关系）。"""

    source: str = Field(..., description="起始节点 id")
    target: str = Field(..., description="目标节点 id")
    relation: str = Field(..., description="关系描述")
    weight: int = Field(1, description="边权重（同一关系出现次数）")


class GraphResponse(BaseModel):
    """知识图谱数据响应。"""

    nodes: List[GraphNodeSchema] = Field(default_factory=list, description="节点列表")
    edges: List[GraphEdgeSchema] = Field(default_factory=list, description="边列表")
    built_at: Optional[float] = Field(None, description="上次构建时间戳，从未构建则为空")


class GraphBuildRequest(BaseModel):
    """知识图谱构建请求。"""

    provider: Optional[str] = Field(None, description="LLM 提供商，覆盖默认值")
    model: Optional[str] = Field(None, description="模型名，覆盖默认值")
    max_chunks: Optional[int] = Field(
        None, ge=1, le=200, description="本次最多参与抽取的片段数，缺省用配置值"
    )


# ======================== 系统设置 ========================
class LLMProviderConfigSchema(BaseModel):
    """单个 LLM 提供商的脱敏配置（密钥仅返回掩码）。"""

    provider: str = Field(..., description="提供商标识（deepseek / mimo）")
    model: str = Field(..., description="模型名")
    base_url: str = Field(..., description="OpenAI 兼容端点地址")
    api_key_masked: str = Field("", description="脱敏后的密钥（如 sk-a****wxyz）")
    has_key: bool = Field(False, description="是否已配置密钥")
    available: bool = Field(False, description="是否可用（已配置密钥）")
    description: str = Field("", description="提供商描述")


class EmbeddingConfigSchema(BaseModel):
    """嵌入配置脱敏快照。"""

    provider: str = Field(..., description="嵌入提供商（mock / openai）")
    model: str = Field(..., description="嵌入模型名")
    base_url: str = Field(..., description="OpenAI 兼容嵌入端点")
    dimension: int = Field(..., description="向量维度（mock 生效）")
    api_key_masked: str = Field("", description="脱敏后的密钥")
    has_key: bool = Field(False, description="是否已配置密钥")


class RerankerConfigSchema(BaseModel):
    """重排序配置脱敏快照。"""

    enabled: bool = Field(False, description="是否启用两阶段重排序")
    model: str = Field(..., description="重排序模型名")
    base_url: str = Field(..., description="OpenAI 兼容 /rerank 端点")
    top_n: int = Field(..., description="精排后保留条数")
    candidate_k: int = Field(..., description="第一阶段向量召回的候选数")
    api_key_masked: str = Field("", description="脱敏后的密钥")
    has_key: bool = Field(False, description="是否已配置密钥")


class SettingsSnapshot(BaseModel):
    """系统设置全量脱敏快照（供 Web 设置面板展示）。"""

    default_provider: str = Field(..., description="默认 LLM 提供商")
    llm: List[LLMProviderConfigSchema] = Field(default_factory=list)
    embedding: EmbeddingConfigSchema
    reranker: RerankerConfigSchema


class LLMConfigUpdateRequest(BaseModel):
    """更新某 LLM 提供商配置请求（字段省略则不变）。"""

    api_key: Optional[str] = Field(
        None, description="新密钥；省略/空/含掩码字符则不修改现有密钥"
    )
    base_url: Optional[str] = Field(None, description="新端点地址")
    model: Optional[str] = Field(None, description="新模型名")


class RerankerConfigUpdateRequest(BaseModel):
    """更新重排序配置请求（字段省略则不变）。"""

    enabled: Optional[bool] = Field(None, description="是否启用")
    api_key: Optional[str] = Field(None, description="新密钥（含掩码则忽略）")
    base_url: Optional[str] = Field(None, description="新端点地址")
    model: Optional[str] = Field(None, description="新模型名")
    top_n: Optional[int] = Field(None, ge=1, le=50, description="精排后保留条数")
    candidate_k: Optional[int] = Field(None, ge=1, le=200, description="候选召回数")


class EmbeddingConfigUpdateRequest(BaseModel):
    """更新嵌入配置请求（字段省略则不变；切换后可能需重建索引）。"""

    provider: Optional[str] = Field(None, description="嵌入提供商（mock / openai）")
    api_key: Optional[str] = Field(None, description="新密钥（含掩码则忽略）")
    base_url: Optional[str] = Field(None, description="新端点地址")
    model: Optional[str] = Field(None, description="新模型名")
    dimension: Optional[int] = Field(None, ge=1, le=8192, description="mock 嵌入维度")


class DefaultProviderUpdateRequest(BaseModel):
    """设置默认 LLM 提供商请求。"""

    provider: str = Field(..., description="提供商标识（deepseek / mimo）")


class ConnectionTestRequest(BaseModel):
    """连通性测试请求。"""

    section: str = Field(..., description="测试对象：llm / reranker")
    provider: Optional[str] = Field(None, description="section=llm 时的提供商标识")


class ConnectionTestResult(BaseModel):
    """连通性测试结果。"""

    ok: bool = Field(..., description="是否连通")
    message: str = Field(..., description="结果描述（成功提示或错误原因）")
