"""
对话 API 路由。

提供 RAG 对话接口，支持一次性 JSON 响应与 SSE 流式响应两种模式。
流式模式便于前端呈现「打字机」实时反馈效果。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ClarifySchema,
    RetrievedChunkSchema,
)
from app.services.container import Container, get_container

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sources_schema(sources) -> list[RetrievedChunkSchema]:
    """将检索来源转换为响应 Schema。"""
    return [
        RetrievedChunkSchema(
            text=c.text, score=c.score, filename=c.metadata.get("filename", "未知")
        )
        for c in sources
    ]


@router.post("", response_model=ChatResponse, summary="RAG 对话（一次性）")
async def chat(
    req: ChatRequest,
    container: Container = Depends(get_container),
) -> ChatResponse:
    """
    发送一条消息并获取完整回答。

    - 当 use_rag=True 时，会先检索知识库并将上下文注入提示词；
    - 自动维护多轮会话上下文（通过 session_id）。
    """
    answer, ctx = await container.chat.chat(
        message=req.message,
        session_id=req.session_id,
        provider=req.provider,
        model=req.model,
        use_rag=req.use_rag,
        top_k=req.top_k,
        allow_clarify=req.allow_clarify,
    )
    return ChatResponse(
        session_id=ctx.session_id,
        answer=answer,
        sources=_sources_schema(ctx.sources),
        provider=ctx.provider_name,
        model=ctx.model_name,
        clarify=ClarifySchema(**ctx.clarify) if ctx.clarify else None,
    )


@router.post("/stream", summary="RAG 对话（SSE 流式）")
async def chat_stream(
    req: ChatRequest,
    container: Container = Depends(get_container),
) -> StreamingResponse:
    """
    流式对话接口，采用 Server-Sent Events (SSE)。

    事件格式（每行 `data: {json}\\n\\n`）：
    - {"type": "meta", "session_id", "sources", "provider", "model"} 首个元信息事件
    - {"type": "clarify", "question", "options"} 反问澄清（若本次需澄清，不再产出 delta）
    - {"type": "delta", "content"} 文本增量
    - {"type": "done"} 结束标记
    """
    generator, ctx = await container.chat.chat_stream(
        message=req.message,
        session_id=req.session_id,
        provider=req.provider,
        model=req.model,
        use_rag=req.use_rag,
        top_k=req.top_k,
        allow_clarify=req.allow_clarify,
    )

    async def event_stream():
        """将业务生成器包装为 SSE 事件流。"""
        # 1) 先发送元信息（会话 ID、检索来源、模型）
        meta = {
            "type": "meta",
            "session_id": ctx.session_id,
            "provider": ctx.provider_name,
            "model": ctx.model_name,
            "sources": [s.model_dump() for s in _sources_schema(ctx.sources)],
        }
        yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"

        # 2) 反问澄清：推送澄清事件，并消费生成器以触发记忆写入（不产出正文）
        if ctx.clarify is not None:
            clarify_evt = {
                "type": "clarify",
                "question": ctx.clarify["question"],
                "options": ctx.clarify["options"],
            }
            yield f"data: {json.dumps(clarify_evt, ensure_ascii=False)}\n\n"
            async for _ in generator:
                pass
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            return

        # 3) 逐块推送文本增量
        async for delta in generator:
            payload = {"type": "delta", "content": delta}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        # 4) 结束标记
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
