"""
系统设置 API 路由。

支撑「在网页端完成大模型 Key 的接入与切换」：读取脱敏配置快照、更新各提供商
密钥/端点/模型、开关与配置重排序、切换默认模型，并提供连通性测试。

安全约定（脱密保护）：
- 所有读取接口只返回掩码后的密钥，真实密钥永不出网页；
- 更新接口对密钥字段做「空值/掩码值即不修改」处理，避免回填掩码时误清空真实密钥。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

from app.core.llm.base import GenerationConfig, Message, Role
from app.core.rag.reranker import create_reranker
from app.models.schemas import (
    ConnectionTestRequest,
    ConnectionTestResult,
    DefaultProviderUpdateRequest,
    EmbeddingConfigUpdateRequest,
    LLMConfigUpdateRequest,
    RerankerConfigUpdateRequest,
    SettingsSnapshot,
)
from app.services.container import Container, get_container
from app.utils.exceptions import ValidationError
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _clean(value: Optional[str]) -> Optional[str]:
    """将空字符串归一化为 None（视为「不修改」），避免误清空已有配置。"""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _snapshot(container: Container) -> SettingsSnapshot:
    """从运行时配置存储构造脱敏快照。"""
    return SettingsSnapshot(**container.config_store.snapshot())


@router.get("", response_model=SettingsSnapshot, summary="获取系统设置（脱敏）")
async def get_settings_snapshot(
    container: Container = Depends(get_container),
) -> SettingsSnapshot:
    """返回 LLM / 嵌入 / 重排序的当前配置快照，密钥均为掩码。"""
    return _snapshot(container)


@router.put(
    "/llm/{provider}", response_model=SettingsSnapshot, summary="更新 LLM 提供商配置"
)
async def update_llm_config(
    provider: str,
    req: LLMConfigUpdateRequest,
    container: Container = Depends(get_container),
) -> SettingsSnapshot:
    """更新指定提供商的密钥/端点/模型，并使新凭据立即生效。"""
    try:
        container.config_store.set_llm(
            provider,
            api_key=_clean(req.api_key),
            base_url=_clean(req.base_url),
            model=_clean(req.model),
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    container.reload_llm()
    logger.info("已更新 LLM 提供商配置: %s", provider)
    return _snapshot(container)


@router.put("/reranker", response_model=SettingsSnapshot, summary="更新重排序配置")
async def update_reranker_config(
    req: RerankerConfigUpdateRequest,
    container: Container = Depends(get_container),
) -> SettingsSnapshot:
    """开关并配置两阶段重排序，变更后热替换重排序器。"""
    container.config_store.set_reranker(
        enabled=req.enabled,
        api_key=_clean(req.api_key),
        base_url=_clean(req.base_url),
        model=_clean(req.model),
        top_n=req.top_n,
        candidate_k=req.candidate_k,
    )
    container.reload_reranker()
    logger.info("已更新重排序配置: enabled=%s", req.enabled)
    return _snapshot(container)


@router.put("/embedding", response_model=SettingsSnapshot, summary="更新嵌入配置")
async def update_embedding_config(
    req: EmbeddingConfigUpdateRequest,
    container: Container = Depends(get_container),
) -> SettingsSnapshot:
    """
    更新嵌入提供商/密钥/端点/模型/维度，变更后热替换嵌入器。

    注意：切换嵌入模型可能改变向量维度，与库内已有向量不一致时检索会返回空，
    需重新上传文档重建索引。
    """
    container.config_store.set_embedding(
        provider=_clean(req.provider),
        api_key=_clean(req.api_key),
        base_url=_clean(req.base_url),
        model=_clean(req.model),
        dimension=req.dimension,
    )
    container.reload_embedding()
    logger.info("已更新嵌入配置: provider=%s", req.provider)
    return _snapshot(container)


@router.put(
    "/default-provider", response_model=SettingsSnapshot, summary="设置默认模型"
)
async def update_default_provider(
    req: DefaultProviderUpdateRequest,
    container: Container = Depends(get_container),
) -> SettingsSnapshot:
    """切换默认 LLM 提供商。"""
    try:
        container.config_store.set_default_provider(req.provider)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return _snapshot(container)


@router.post("/test", response_model=ConnectionTestResult, summary="测试连通性")
async def test_connection(
    req: ConnectionTestRequest,
    container: Container = Depends(get_container),
) -> ConnectionTestResult:
    """
    对 LLM 或重排序服务做一次最小化真实调用，验证密钥与端点是否可用。

    该接口会发起真实网络请求，失败时返回 ok=False 及错误原因，不抛异常。
    """
    section = (req.section or "").lower().strip()
    try:
        if section == "llm":
            provider = (req.provider or container.config_store.default_provider()).lower()
            llm = container.llm_factory.get_provider(provider)
            resp = await llm.generate(
                [Message(Role.USER, "ping")],
                GenerationConfig(temperature=0.0, max_tokens=1),
            )
            _ = resp.content
            return ConnectionTestResult(ok=True, message=f"{provider} 连通正常")

        if section == "reranker":
            cfg = container.config_store.effective_reranker()
            if not cfg.get("api_key"):
                return ConnectionTestResult(ok=False, message="重排序未配置密钥")
            reranker = create_reranker({**cfg, "enabled": True})
            from app.core.rag.vectorstore import RetrievedChunk

            out = reranker.rerank(
                "测试查询",
                [
                    RetrievedChunk(chunk_id="t1", text="这是一段测试文本", score=0.0, metadata={}),
                    RetrievedChunk(chunk_id="t2", text="另一段无关内容", score=0.0, metadata={}),
                ],
                top_n=1,
            )
            if out:
                return ConnectionTestResult(ok=True, message="重排序服务连通正常")
            return ConnectionTestResult(ok=False, message="重排序服务无有效返回")

        raise ValidationError(f"不支持的测试对象: {section}（可选: llm / reranker）")
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001  测试失败如实返回原因，不抛 500
        logger.warning("连通性测试失败 section=%s: %s", section, exc)
        return ConnectionTestResult(ok=False, message=f"连接失败: {exc}")
