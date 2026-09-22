"""
文档服务。

编排 RAG 的文档摄取流程：保存上传文件 → 解析文本 → 构建索引 → 记录元数据。
文档元数据以 JSON 文件持久化（轻量、无需额外数据库），支持列出与删除。

v2 升级点：
- 知识库（kb_id）归属：上传/列表/删除均按知识库隔离；
- Contextual Retrieval：可选在索引期为每块生成 LLM 上下文前缀；
- 文件大小限制（upload_max_mb）与更严格的校验；
- 摄取主流程异步化（解析/嵌入在线程池，LLM 前缀生成在事件循环并发）。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

from app.core.rag.loader import SUPPORTED_EXTENSIONS, load_document
from app.core.rag.retriever import DEFAULT_KB, Retriever
from app.utils.exceptions import NotFoundError, ValidationError
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DocumentRecord:
    """文档元数据记录。"""

    document_id: str
    filename: str
    chunk_count: int
    size_bytes: int
    created_at: float
    kb_id: str = DEFAULT_KB


class DocumentService:
    """管理文档的上传、索引、查询与删除。"""

    def __init__(
        self,
        retriever: Retriever,
        upload_dir: str,
        max_bytes: int = 50 * 1024 * 1024,
        contextualizer=None,
    ) -> None:
        """
        Args:
            retriever: RAG 检索器（用于建索引）。
            upload_dir: 上传文件保存目录。
            max_bytes: 单文件大小上限（字节）。
            contextualizer: 可选 Contextualizer（Contextual Retrieval 开启时由容器注入）。
        """
        self._retriever = retriever
        self._upload_dir = Path(upload_dir)
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        self._contextualizer = contextualizer
        # 元数据索引文件
        self._meta_path = self._upload_dir / "_documents.json"
        self._lock = Lock()
        self._records: Dict[str, DocumentRecord] = self._load_meta()

    def _load_meta(self) -> Dict[str, DocumentRecord]:
        """从磁盘加载文档元数据索引（兼容无 kb_id 的旧记录）。"""
        if not self._meta_path.exists():
            return {}
        try:
            data = json.loads(self._meta_path.read_text(encoding="utf-8"))
            out: Dict[str, DocumentRecord] = {}
            for k, v in data.items():
                v.setdefault("kb_id", DEFAULT_KB)
                out[k] = DocumentRecord(**v)
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("文档元数据加载失败，将重建: %s", exc)
            return {}

    def _save_meta(self) -> None:
        """将文档元数据索引写回磁盘。"""
        data = {k: asdict(v) for k, v in self._records.items()}
        self._meta_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _validate_and_save(self, filename: str, content: bytes, document_id: str) -> Path:
        """校验文件并落盘（上传目录内以文档 ID 为前缀，避免同名覆盖）。"""
        if len(content) == 0:
            raise ValidationError("上传文件为空")
        if len(content) > self._max_bytes:
            raise ValidationError(
                f"文件过大：{len(content) / 1024 / 1024:.1f}MB，"
                f"上限 {self._max_bytes / 1024 / 1024:.0f}MB"
            )
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValidationError(
                f"不支持的文件格式: {ext}，支持: {sorted(SUPPORTED_EXTENSIONS)}"
            )
        saved_path = self._upload_dir / f"{document_id}{ext}"
        saved_path.write_bytes(content)
        return saved_path

    async def add_document(
        self,
        filename: str,
        content: bytes,
        kb_id: str = DEFAULT_KB,
    ) -> DocumentRecord:
        """
        保存并索引一个上传文档（异步编排：解析/嵌入在线程池，上下文前缀并发生成）。

        Args:
            filename: 原始文件名。
            content: 文件二进制内容。
            kb_id: 目标知识库 ID。

        Returns:
            DocumentRecord: 生成的文档记录。

        Raises:
            ValidationError: 文件为空、超限或格式不支持时。
        """
        document_id = uuid.uuid4().hex
        saved_path = await asyncio.to_thread(
            self._validate_and_save, filename, content, document_id
        )

        # 解析纯文本（CPU/IO，线程池）
        text = await asyncio.to_thread(load_document, saved_path)

        # 可选 Contextual Retrieval：为每个块生成语境前缀
        embed_contexts: Optional[List[str]] = None
        if self._contextualizer is not None:
            try:
                chunk_texts = await asyncio.to_thread(
                    lambda: [c.text for c in self._retriever.split_text(text)]
                )
                contexts = await self._contextualizer.build_contexts(
                    text[:2000], chunk_texts
                )
                if any(contexts):
                    embed_contexts = [(c or "") for c in contexts]
            except Exception as exc:  # noqa: BLE001 失败不阻断索引
                logger.warning("上下文前缀生成失败，按普通索引继续: %s", exc)

        chunk_count = await asyncio.to_thread(
            self._retriever.index_document,
            document_id,
            filename,
            text,
            kb_id,
            embed_contexts,
        )

        record = DocumentRecord(
            document_id=document_id,
            filename=filename,
            chunk_count=chunk_count,
            size_bytes=len(content),
            created_at=time.time(),
            kb_id=kb_id,
        )
        with self._lock:
            self._records[document_id] = record
            self._save_meta()
        logger.info("文档已入库: %s (%d 片段, kb=%s)", filename, chunk_count, kb_id)
        return record

    def list_documents(self, kb_id: Optional[str] = None) -> List[DocumentRecord]:
        """列出文档，按上传时间降序；可选按知识库过滤。"""
        records = self._records.values()
        if kb_id:
            records = [r for r in records if r.kb_id == kb_id]
        return sorted(records, key=lambda r: r.created_at, reverse=True)

    def count_by_kb(self, kb_id: str) -> int:
        """统计某知识库的文档数。"""
        return sum(1 for r in self._records.values() if r.kb_id == kb_id)

    def delete_document(self, document_id: str) -> None:
        """
        删除文档：移除向量索引、磁盘文件与元数据。

        Args:
            document_id: 文档 ID。

        Raises:
            NotFoundError: 文档不存在时。
        """
        with self._lock:
            record = self._records.get(document_id)
            if record is None:
                raise NotFoundError(f"文档不存在: {document_id}")

            # 删除向量库中的片段
            self._retriever.delete_document(document_id)

            # 删除磁盘文件
            ext = Path(record.filename).suffix.lower()
            file_path = self._upload_dir / f"{document_id}{ext}"
            file_path.unlink(missing_ok=True)

            del self._records[document_id]
            self._save_meta()
        logger.info("文档已删除: %s", record.filename)
