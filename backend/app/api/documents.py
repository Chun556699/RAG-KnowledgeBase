"""
文档管理 API 路由（RAG）。

提供文档上传、列表、删除，以及独立的语义检索接口。
"""

from __future__ import annotations

import asyncio
from typing import List

from fastapi import APIRouter, Depends, File, UploadFile

from app.models.schemas import (
    DocumentInfo,
    OkResponse,
    RetrievedChunkSchema,
    SearchRequest,
    SearchResponse,
    UploadResponse,
)
from app.services.container import Container, get_container

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse, summary="上传并索引文档")
async def upload_document(
    file: UploadFile = File(..., description="待上传的文档文件"),
    container: Container = Depends(get_container),
) -> UploadResponse:
    """
    上传文档，服务端将自动解析、分块、向量化并写入知识库。

    支持格式：PDF / Word(.docx) / TXT / Markdown。
    """
    content = await file.read()
    # 解析/分块/嵌入/落盘均为同步 CPU/IO 密集型操作，放入线程池避免阻塞事件循环
    record = await asyncio.to_thread(
        container.documents.add_document, file.filename or "unknown", content
    )
    return UploadResponse(
        document=DocumentInfo(
            document_id=record.document_id,
            filename=record.filename,
            chunk_count=record.chunk_count,
            size_bytes=record.size_bytes,
            created_at=record.created_at,
        )
    )


@router.get("", response_model=List[DocumentInfo], summary="列出全部文档")
async def list_documents(
    container: Container = Depends(get_container),
) -> List[DocumentInfo]:
    """返回知识库中已索引的全部文档。"""
    return [
        DocumentInfo(
            document_id=r.document_id,
            filename=r.filename,
            chunk_count=r.chunk_count,
            size_bytes=r.size_bytes,
            created_at=r.created_at,
        )
        for r in container.documents.list_documents()
    ]


@router.delete("/{document_id}", response_model=OkResponse, summary="删除文档")
async def delete_document(
    document_id: str,
    container: Container = Depends(get_container),
) -> OkResponse:
    """删除指定文档及其向量索引。"""
    container.documents.delete_document(document_id)
    return OkResponse(message="文档已删除")


@router.post("/search", response_model=SearchResponse, summary="语义检索")
async def search(
    req: SearchRequest,
    container: Container = Depends(get_container),
) -> SearchResponse:
    """在知识库中执行向量语义检索，返回最相关的片段（不经过 LLM 生成）。"""
    chunks = container.retriever.retrieve(req.query, top_k=req.top_k)
    return SearchResponse(
        query=req.query,
        chunks=[
            RetrievedChunkSchema(
                text=c.text,
                score=c.score,
                filename=c.metadata.get("filename", "未知"),
            )
            for c in chunks
        ],
    )
