"""
公开问答 API（企业版对外面）。

供「嵌入任意产品」的只读问答接口：
- ``POST /api/v1/ask``：一次性问答（JSON）；
- ``POST /api/v1/ask/stream``：SSE 流式问答；
- ``GET  /api/v1/kb``：当前密钥可见的知识库信息。

鉴权：``X-API-Key`` 或 ``Authorization: Bearer <key>``，密钥需含 ``ask`` scope；
密钥绑定知识库时强制该库（租户隔离，请求不可越界），未绑定则取请求 kb 或 default。
限流：由 RateLimitMiddleware 按密钥/IP 分桶执行。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.metrics import get_metrics
from app.core.platform_db import ApiKeyInfo
from app.models.schemas import (
    PublicAskRequest,
    PublicAskResponse,
    RetrievedChunkSchema,
)
from app.services.container import Container, get_container

router = APIRouter(prefix="/api/v1", tags=["public"])


def _extract_key(request: Request) -> str:
    """从 X-API-Key 或 Authorization: Bearer 提取明文密钥。"""
    raw = request.headers.get("x-api-key")
    if raw:
        return raw.strip()
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


async def _auth(request: Request, container: Container = Depends(get_container)) -> ApiKeyInfo:
    """公共端点鉴权：校验密钥并检查 ask scope。"""
    settings = container.settings
    if not settings.public_api_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    info = container.platform.verify_key(_extract_key(request))
    if info is None or "ask" not in info.scopes:
        get_metrics().incr("ask_denied_total")
        raise HTTPException(status_code=401, detail="无效或已吊销的 API Key")
    return info


def _resolve_kb(req: PublicAskRequest, key: ApiKeyInfo) -> str:
    """解析本次问答的知识库：密钥绑定库优先（强隔离），否则取请求值或 default。"""
    if key.kb_id:
        return key.kb_id
    return req.kb or "default"


def _sources_schema(sources) -> list[RetrievedChunkSchema]:
    return [
        RetrievedChunkSchema(
            text=c.text, score=c.score, filename=c.metadata.get("filename", "未知")
        )
        for c in sources
    ]


@router.post("/ask", response_model=PublicAskResponse, summary="公开问答（一次性）")
async def ask(
    req: PublicAskRequest,
    key: ApiKeyInfo = Depends(_auth),
    container: Container = Depends(get_container),
) -> PublicAskResponse:
    """
    面向嵌入产品的问答接口：检索指定知识库并由 LLM 生成带来源的回答。

    - 密钥绑定知识库时强制只查该库（多租户隔离）；
    - session_id 透传实现多轮上下文（由调用方保存）。
    """
    kb_id = _resolve_kb(req, key)
    answer, ctx = await container.chat.chat(
        message=req.question,
        session_id=req.session_id,
        use_rag=True,
        top_k=req.top_k,
        allow_clarify=False,
        kb_id=kb_id,
    )
    get_metrics().incr("ask_total")
    return PublicAskResponse(
        session_id=ctx.session_id,
        answer=answer,
        sources=_sources_schema(ctx.sources),
        kb_id=kb_id,
    )


@router.post("/ask/stream", summary="公开问答（SSE 流式）")
async def ask_stream(
    req: PublicAskRequest,
    key: ApiKeyInfo = Depends(_auth),
    container: Container = Depends(get_container),
) -> StreamingResponse:
    """
    SSE 流式问答。事件格式（每行 ``data: {json}\\n\\n``）：
    ``meta``（session_id/sources/kb）→ ``delta``（文本增量）→ ``done``。
    """
    kb_id = _resolve_kb(req, key)
    generator, ctx = await container.chat.chat_stream(
        message=req.question,
        session_id=req.session_id,
        use_rag=True,
        top_k=req.top_k,
        allow_clarify=False,
        kb_id=kb_id,
    )
    get_metrics().incr("ask_total")

    async def event_stream():
        meta = {
            "type": "meta",
            "session_id": ctx.session_id,
            "kb_id": kb_id,
            "sources": [s.model_dump() for s in _sources_schema(ctx.sources)],
        }
        yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
        async for delta in generator:
            payload = {"type": "delta", "content": delta}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/kb", summary="当前密钥可见的知识库信息")
async def kb_info(
    key: ApiKeyInfo = Depends(_auth),
    container: Container = Depends(get_container),
) -> dict:
    """返回密钥可见的知识库列表（绑定密钥仅见其绑定库）。"""
    kbs = container.platform.list_kbs()
    if key.kb_id:
        kbs = [k for k in kbs if k.kb_id == key.kb_id]
    return {
        "kbs": [
            {
                "kb_id": k.kb_id,
                "name": k.name,
                "chunk_count": container.retriever.count(kb_id=k.kb_id),
            }
            for k in kbs
        ]
    }
