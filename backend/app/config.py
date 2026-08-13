"""
应用配置模块。

使用 pydantic-settings 从环境变量 / .env 文件加载配置，提供类型校验与默认值。
所有默认值均保证项目在 **无任何真实 API Key** 的情况下（Mock 模式）可直接运行。
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置项。字段名与 .env 中的变量名（大小写不敏感）一一对应。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- 应用基础 ----------
    app_name: str = "AI Knowledge Base"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ---------- LLM ----------
    # 仅保留 DeepSeek 与小米 MiMo 两个提供商，二者均兼容 OpenAI Chat Completions 协议。
    default_llm_provider: str = "deepseek"

    # DeepSeek（https://platform.deepseek.com，OpenAI 兼容）
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # 小米 MiMo（OpenAI 兼容端点）
    mimo_api_key: str = ""
    mimo_base_url: str = "https://api.mimo.chat/v1"
    mimo_model: str = "mimo-7b-rl"

    # ---------- Embedding ----------
    # 嵌入默认使用离线确定性 Mock（无需任何密钥即可完成 RAG 检索）；
    # 若需真实语义检索，将 embedding_provider 设为 "openai" 并配置下方 OpenAI 兼容嵌入端点
    # （例如硅基流动 SiliconFlow：base_url=https://api.siliconflow.cn/v1，model=BAAI/bge-m3；
    #   或 OpenAI：model=text-embedding-3-small）。切换嵌入后需重建索引（重新上传文档）。
    embedding_provider: str = "mock"
    embedding_dimension: int = 384
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_api_key: str = ""
    embedding_model: str = "BAAI/bge-m3"

    # ---------- 向量库 ----------
    # 本地轻量向量库（numpy 实现），单文件持久化，无需外部服务。
    vector_store_path: str = "./data/vectorstore.json"

    # ---------- 运行时配置 ----------
    # Web 界面修改的运行时覆盖配置（LLM 密钥/端点、嵌入、重排序）的持久化文件。
    # 该层叠加在只读的 .env 基线之上，作为凭据的单一事实来源；.env 本身不会被修改。
    runtime_config_path: str = "./data/runtime_config.json"

    # ---------- 重排序（Rerank） ----------
    # 两阶段检索：向量召回后用 Cross-Encoder 重排序模型精排，提升相关性。
    # 默认关闭（不影响既有行为）；开启需配置 rerank_api_key（OpenAI 兼容 /rerank 端点）。
    rerank_enabled: bool = False
    rerank_base_url: str = "https://api.siliconflow.cn/v1"
    rerank_api_key: str = ""
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    # 重排序前，先从向量库召回的候选片段数（应 >= retrieval_top_k）。
    rerank_candidate_k: int = 20
    # 调用重排序 API 的超时时间（秒）。
    rerank_timeout: float = 20.0

    # ---------- 提示词 ----------
    # 用户自定义 / 覆盖内置提示词模板的持久化文件（内置模板作为只读基线）。
    prompt_store_path: str = "./data/prompts.json"

    # ---------- 知识图谱 ----------
    # 图谱数据（节点/边）的持久化文件，由 LLM 从文档抽取实体关系后聚合而成。
    graph_store_path: str = "./data/graph.json"
    # 单次构建最多参与抽取的片段数（控制 LLM 调用成本与时长）。
    graph_max_chunks: int = 40
    # 实体关系抽取的 LLM 并发度（asyncio 信号量上限）。
    graph_extract_concurrency: int = 4

    # ---------- RAG ----------
    chunk_size: int = 500
    chunk_overlap: int = 50
    retrieval_top_k: int = 4
    # 是否启用混合检索（向量稠密 + BM25 稀疏 + RRF 融合），提升专有名词/精确匹配的召回
    hybrid_search_enabled: bool = True
    # RRF 倒数排名融合的平滑参数（越小排名影响越显著）
    rrf_k: int = 60
    # RRF 融合两路权重（精确匹配/专有名词场景可调高 sparse_weight；语义场景可调高 dense_weight）
    hybrid_dense_weight: float = 1.0
    hybrid_sparse_weight: float = 1.0
    # 检索相关性阈值：低于该余弦相似度的片段视为噪音被过滤，命中为空时如实回退不编造。
    # 说明：Mock 词袋嵌入分数偏低（建议 0.05 左右）；真实语义嵌入分数偏高（建议 0.3 左右）。
    retrieval_min_score: float = 0.05
    # RAG 问答生成温度：事实型问答宜低，减少发挥、提高对资料的忠实度。
    rag_temperature: float = 0.2
    # 是否启用多轮追问的查询改写（用 LLM 将含指代的追问改写为独立检索查询）。
    query_rewrite_enabled: bool = True
    # 是否启用「反问澄清」：问题模糊时先反问用户再作答（需 LLM 可用，失败自动降级）。
    clarify_enabled: bool = True
    # 是否启用 CRAG（纠正性 RAG）：检索后评估质量，不足则改写查询重新检索（失败自动降级）。
    crag_enabled: bool = True
    # CRAG 触发阈值：仅当检索最高分低于此值时评估（高分说明检索可靠，跳过评估以提速）。
    crag_trigger_threshold: float = 0.4

    # ---------- 记忆 ----------
    memory_db_path: str = "./data/memory.db"
    memory_ttl_days: int = 30
    max_history_turns: int = 20

    # ---------- 上传 ----------
    # 上传文件保存目录。不限制单文件大小（如需限制可在此新增配置并在
    # DocumentService 中启用校验，生产环境还需相应调整 Nginx client_max_body_size）。
    upload_dir: str = "./data/uploads"

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        """去除跨域配置中的多余空白。"""
        return v.strip()

    @property
    def cors_origin_list(self) -> List[str]:
        """将逗号分隔的跨域字符串解析为列表。"""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_directories(self) -> None:
        """确保所有持久化目录存在（首次启动时自动创建）。"""
        for path in (
            str(Path(self.vector_store_path).parent),
            self.upload_dir,
            str(Path(self.memory_db_path).parent),
            str(Path(self.graph_store_path).parent),
            str(Path(self.runtime_config_path).parent),
        ):
            Path(path).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """
    获取全局配置单例。

    使用 lru_cache 确保配置只加载一次，避免重复解析 .env 文件。

    Returns:
        Settings: 全局配置对象。
    """
    return Settings()
