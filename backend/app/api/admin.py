"""
管理端 API 路由（企业化）：知识库管理 + API 密钥管理。

- 知识库：创建/列出（含片段与文档计数）；
- API 密钥：创建（明文仅此一次返回）/ 列出（脱敏）/ 吊销；
- 指标：GET /api/metrics 输出进程内指标快照。

若配置了 ``ADMIN_API_KEY``，本组路由全部要求 ``X-Admin-Key`` 头鉴权；
未配置则为本地/内网开发模式（部署公网务必配置）。
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import get_settings
from app.core.metrics import get_metrics
from app.models.schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeySchema,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseSchema,
    OkResponse,
)
from app.services.container import Container, get_container
from app.utils.exceptions import NotFoundError, ValidationError

router = APIRouter(prefix="/api", tags=["admin"])


def _require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    """管理端鉴权：配置了 ADMIN_API_KEY 时校验 X-Admin-Key 头。"""
    expected = get_settings().admin_api_key
    if expected and x_admin_key != expected:
        raise HTTPException(status_code=401, detail="无效的管理端密钥")


def _kb_schema(container: Container, kb) -> KnowledgeBaseSchema:
    """知识库记录 → 响应 Schema（附统计信息）。"""
    return KnowledgeBaseSchema(
        kb_id=kb.kb_id,
        name=kb.name,
        description=kb.description,
        created_at=kb.created_at,
        chunk_count=container.retriever.count(kb_id=kb.kb_id),
        document_count=container.documents.count_by_kb(kb.kb_id),
    )


def _key_schema(rec) -> ApiKeySchema:
    return ApiKeySchema(
        key_id=rec.key_id,
        name=rec.name,
        key_prefix=rec.key_prefix,
        scopes=rec.scopes,
        kb_id=rec.kb_id,
        created_at=rec.created_at,
        last_used_at=rec.last_used_at,
        revoked=rec.revoked,
    )


# ------------------------------------------------------------------
# 知识库
# ------------------------------------------------------------------
@router.get("/kbs", response_model=List[KnowledgeBaseSchema], summary="列出知识库")
async def list_kbs(
    container: Container = Depends(get_container),
    _: None = Depends(_require_admin),
) -> List[KnowledgeBaseSchema]:
    return [_kb_schema(container, kb) for kb in container.platform.list_kbs()]


@router.post("/kbs", response_model=KnowledgeBaseSchema, summary="创建知识库")
async def create_kb(
    req: KnowledgeBaseCreateRequest,
    container: Container = Depends(get_container),
    _: None = Depends(_require_admin),
) -> KnowledgeBaseSchema:
    kb = container.platform.create_kb(req.name, req.description)
    return _kb_schema(container, kb)


# ------------------------------------------------------------------
# API 密钥
# ------------------------------------------------------------------
@router.get("/keys", response_model=List[ApiKeySchema], summary="列出 API 密钥")
async def list_keys(
    container: Container = Depends(get_container),
    _: None = Depends(_require_admin),
) -> List[ApiKeySchema]:
    return [_key_schema(r) for r in container.platform.list_keys()]


@router.post("/keys", response_model=ApiKeyCreateResponse, summary="创建 API 密钥")
async def create_key(
    req: ApiKeyCreateRequest,
    container: Container = Depends(get_container),
    _: None = Depends(_require_admin),
) -> ApiKeyCreateResponse:
    valid_scopes = {"ask", "ingest", "admin"}
    bad = set(req.scopes) - valid_scopes
    if bad:
        raise ValidationError(f"无效的 scope: {sorted(bad)}，可选 {sorted(valid_scopes)}")
    if req.kb_id and container.platform.get_kb(req.kb_id) is None:
        raise ValidationError(f"知识库不存在: {req.kb_id}")
    record, raw = container.platform.create_key(
        req.name, scopes=req.scopes, kb_id=req.kb_id
    )
    return ApiKeyCreateResponse(key=_key_schema(record), raw_key=raw)


@router.delete("/keys/{key_id}", response_model=OkResponse, summary="吊销 API 密钥")
async def revoke_key(
    key_id: str,
    container: Container = Depends(get_container),
    _: None = Depends(_require_admin),
) -> OkResponse:
    if not container.platform.revoke_key(key_id):
        raise NotFoundError(f"密钥不存在: {key_id}")
    return OkResponse(message="密钥已吊销")


# ------------------------------------------------------------------
# 指标
# ------------------------------------------------------------------
@router.get("/metrics", summary="应用指标快照")
async def metrics() -> dict:
    """返回进程内指标：请求计数、延迟分布、检索/缓存/LLM 统计。"""
    return get_metrics().snapshot()
