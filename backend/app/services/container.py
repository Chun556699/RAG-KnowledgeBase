"""
依赖容器（Composition Root）。

在应用启动时集中构建各核心子系统的单例，并处理它们之间的依赖装配。
这是整个后端的「组合根」：所有对象图在此处一次性组装，
FastAPI 路由通过依赖注入从此容器获取服务，实现清晰的分层与可测试性。
"""

from __future__ import annotations

from typing import Optional

from app.config import Settings, get_settings
from app.core.agent.tools import (
    CalculatorTool,
    DateTimeTool,
    KnowledgeSearchTool,
    ToolRegistry,
)
from app.core.config_store import RuntimeConfigStore, get_config_store
from app.core.llm.factory import LLMFactory, get_llm_factory
from app.core.memory.manager import MemoryManager
from app.core.memory.store import MemoryStore
from app.core.rag.embeddings import create_embedder
from app.core.rag.reranker import create_reranker
from app.core.rag.retriever import Retriever
from app.core.rag.sparse import BM25Index
from app.core.rag.splitter import TextSplitter
from app.core.rag.vectorstore import VectorStore
from app.services.agent_service import AgentService
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
from app.services.graph_service import GraphService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Container:
    """应用级依赖容器，持有所有子系统单例。"""

    def __init__(self, settings: Settings) -> None:
        """
        构建并装配所有核心子系统。

        Args:
            settings: 全局配置。
        """
        self.settings = settings
        settings.ensure_directories()

        # ---------- 运行时配置（.env 基线 + 网页端可改覆盖层） ----------
        self.config_store: RuntimeConfigStore = get_config_store()

        # ---------- LLM 工厂（从运行时配置读取凭据） ----------
        self.llm_factory: LLMFactory = get_llm_factory()

        # ---------- RAG ----------
        emb_cfg = self.config_store.effective_embedding()
        embedder = create_embedder(
            str(emb_cfg["provider"]),
            dimension=int(emb_cfg["dimension"]),
            api_key=str(emb_cfg["api_key"]),
            base_url=str(emb_cfg["base_url"]),
            model=str(emb_cfg["model"]),
        )
        vector_store = VectorStore(
            persist_path=settings.vector_store_path,
            embedder=embedder,
        )
        splitter = TextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        # 重排序（两阶段检索）：未启用/未配置密钥时为 NoOp，零副作用
        rr_cfg = self.config_store.effective_reranker()
        reranker = create_reranker(rr_cfg)
        # 稀疏索引（BM25）：与向量索引同步维护，用于混合检索
        sparse_index = BM25Index() if settings.hybrid_search_enabled else None
        self.retriever = Retriever(
            vector_store,
            splitter,
            reranker=reranker,
            candidate_k=int(rr_cfg["candidate_k"]),
            sparse_index=sparse_index,
            hybrid_enabled=settings.hybrid_search_enabled,
            rrf_k=settings.rrf_k,
            dense_weight=settings.hybrid_dense_weight,
            sparse_weight=settings.hybrid_sparse_weight,
        )

        # 文档服务：编排上传 → 解析 → 索引 → 元数据管理
        self.documents = DocumentService(
            retriever=self.retriever,
            upload_dir=settings.upload_dir,
        )

        # ---------- 记忆 ----------
        self.memory_store = MemoryStore(settings.memory_db_path)
        self.memory = MemoryManager(
            store=self.memory_store,
            max_history_turns=settings.max_history_turns,
            ttl_days=settings.memory_ttl_days,
        )

        # ---------- Agent 工具 ----------
        self.tools = ToolRegistry()
        self.tools.register(CalculatorTool())
        self.tools.register(DateTimeTool())
        # 知识库检索工具注入 RAG 检索能力（依赖倒置）
        self.tools.register(
            KnowledgeSearchTool(search_fn=self._knowledge_search)
        )

        # ---------- 高层业务服务 ----------
        self.chat = ChatService(
            llm_factory=self.llm_factory,
            retriever=self.retriever,
            memory=self.memory,
            settings=settings,
        )
        self.agent = AgentService(
            llm_factory=self.llm_factory,
            tools=self.tools,
            settings=settings,
        )

        # 知识图谱：从全量语料抽取实体关系并构建可视化图谱
        self.graph = GraphService(
            llm_factory=self.llm_factory,
            retriever=self.retriever,
            settings=settings,
        )

        logger.info("依赖容器初始化完成")

    def _knowledge_search(self, query: str) -> str:
        """供 Agent 工具调用的知识库检索回调。"""
        chunks = self.retriever.retrieve(
            query,
            top_k=self.settings.retrieval_top_k,
            min_score=self.settings.retrieval_min_score,
        )
        return self.retriever.build_context(chunks)

    # ------------------------------------------------------------------
    # 运行时重载（网页端修改配置后由设置 API 调用）
    # ------------------------------------------------------------------
    def reload_llm(self) -> None:
        """LLM 凭据变更后清空工厂缓存，使新密钥/端点/模型下次生效。"""
        self.llm_factory.invalidate()

    def reload_reranker(self) -> None:
        """重排序配置变更后重建重排序器并热替换到检索器。"""
        rr_cfg = self.config_store.effective_reranker()
        self.retriever.set_reranker(
            create_reranker(rr_cfg), candidate_k=int(rr_cfg["candidate_k"])
        )

    def reload_embedding(self) -> None:
        """嵌入配置变更后重建嵌入器并热替换（若维度变化需重建索引）。"""
        emb_cfg = self.config_store.effective_embedding()
        embedder = create_embedder(
            str(emb_cfg["provider"]),
            dimension=int(emb_cfg["dimension"]),
            api_key=str(emb_cfg["api_key"]),
            base_url=str(emb_cfg["base_url"]),
            model=str(emb_cfg["model"]),
        )
        self.retriever.set_embedder(embedder)

    def shutdown(self) -> None:
        """释放资源（关闭数据库连接等）。"""
        self.memory_store.close()
        logger.info("依赖容器已释放资源")


# 全局容器实例（在 FastAPI lifespan 中初始化）
_container: Optional[Container] = None


def init_container() -> Container:
    """初始化全局容器（应用启动时调用）。"""
    global _container
    if _container is None:
        _container = Container(get_settings())
    return _container


def get_container() -> Container:
    """
    获取全局容器（FastAPI 依赖注入入口）。

    Returns:
        Container: 已初始化的容器。

    Raises:
        RuntimeError: 容器尚未初始化时。
    """
    if _container is None:
        raise RuntimeError("依赖容器尚未初始化")
    return _container


def reset_container() -> None:
    """重置容器（主要用于测试隔离）。"""
    global _container
    if _container is not None:
        _container.shutdown()
    _container = None
    # 一并重置与容器共生命的全局单例，避免跨测试/重启残留旧凭据
    from app.core.config_store import reset_config_store
    from app.core.llm.factory import reset_llm_factory

    reset_llm_factory()
    reset_config_store()
