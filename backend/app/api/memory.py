"""
记忆管理 API 路由。

暴露会话管理、历史检索、长期记忆读写与过期清理等接口，
对应产品的「上下文记忆管理」模块。
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.models.schemas import (
    CreateSessionRequest,
    LongTermItemSchema,
    MessageSchema,
    OkResponse,
    RememberRequest,
    SessionSchema,
)
from app.services.container import Container, get_container
from app.utils.exceptions import NotFoundError

router = APIRouter(prefix="/api/memory", tags=["memory"])


# ======================== 会话 ========================
@router.post("/sessions", response_model=SessionSchema, summary="创建会话")
async def create_session(
    req: CreateSessionRequest,
    container: Container = Depends(get_container),
) -> SessionSchema:
    """创建一个新会话。"""
    s = container.memory.create_session(req.title)
    return SessionSchema(id=s.id, title=s.title, created_at=s.created_at, updated_at=s.updated_at)


@router.get("/sessions", response_model=List[SessionSchema], summary="列出会话")
async def list_sessions(
    container: Container = Depends(get_container),
) -> List[SessionSchema]:
    """列出全部会话（按最近更新排序）。"""
    return [
        SessionSchema(id=s.id, title=s.title, created_at=s.created_at, updated_at=s.updated_at)
        for s in container.memory.list_sessions()
    ]


@router.get(
    "/sessions/{session_id}/messages",
    response_model=List[MessageSchema],
    summary="获取会话历史",
)
async def get_messages(
    session_id: str,
    container: Container = Depends(get_container),
) -> List[MessageSchema]:
    """获取指定会话的全部历史消息。"""
    if container.memory.get_session(session_id) is None:
        raise NotFoundError(f"会话不存在: {session_id}")
    return [
        MessageSchema(role=m.role, content=m.content, created_at=m.created_at)
        for m in container.memory.get_history(session_id, limit=1000)
    ]


@router.delete("/sessions/{session_id}", response_model=OkResponse, summary="删除会话")
async def delete_session(
    session_id: str,
    container: Container = Depends(get_container),
) -> OkResponse:
    """删除会话及其全部消息。"""
    container.memory.delete_session(session_id)
    return OkResponse(message="会话已删除")


# ======================== 历史检索 ========================
@router.get("/search", response_model=List[MessageSchema], summary="跨会话历史检索")
async def search_history(
    keyword: str = Query(..., min_length=1, description="检索关键词"),
    limit: int = Query(20, ge=1, le=100),
    container: Container = Depends(get_container),
) -> List[MessageSchema]:
    """按关键词跨会话检索历史消息。"""
    return [
        MessageSchema(role=m.role, content=m.content, created_at=m.created_at)
        for m in container.memory.search_history(keyword, limit=limit)
    ]


# ======================== 长期记忆 ========================
@router.post("/long-term", response_model=OkResponse, summary="写入长期记忆")
async def remember(
    req: RememberRequest,
    container: Container = Depends(get_container),
) -> OkResponse:
    """写入一条长期记忆（如用户偏好、重要事实）。"""
    container.memory.remember(
        key=req.key, value=req.value, topic=req.topic, importance=req.importance
    )
    return OkResponse(message="长期记忆已保存")


@router.get("/long-term", response_model=List[LongTermItemSchema], summary="检索长期记忆")
async def recall(
    topic: Optional[str] = Query(None, description="按主题过滤"),
    limit: int = Query(20, ge=1, le=100),
    container: Container = Depends(get_container),
) -> List[LongTermItemSchema]:
    """检索长期记忆（自动过滤已过期项）。"""
    return [
        LongTermItemSchema(
            id=i.id, key=i.key, value=i.value, topic=i.topic,
            importance=i.importance, created_at=i.created_at,
        )
        for i in container.memory.recall(topic=topic, limit=limit)
    ]


@router.post("/cleanup", response_model=OkResponse, summary="清理过期记忆")
async def cleanup(
    container: Container = Depends(get_container),
) -> OkResponse:
    """手动触发过期长期记忆清理。"""
    deleted = container.memory.cleanup_expired()
    return OkResponse(message=f"已清理 {deleted} 条过期记忆")
