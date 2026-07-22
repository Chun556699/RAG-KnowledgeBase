"""
文档服务。

编排 RAG 的文档摄取流程：保存上传文件 → 解析文本 → 构建索引 → 记录元数据。
文档元数据以 JSON 文件持久化（轻量、无需额外数据库），支持列出与删除。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Dict, List

from app.core.rag.loader import SUPPORTED_EXTENSIONS, load_document
from app.core.rag.retriever import Retriever
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


class DocumentService:
    """管理文档的上传、索引、查询与删除。"""

    def __init__(
        self,
        retriever: Retriever,
        upload_dir: str,
    ) -> None:
        """
        Args:
            retriever: RAG 检索器（用于建索引）。
            upload_dir: 上传文件保存目录。
        """
        self._retriever = retriever
        self._upload_dir = Path(upload_dir)
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        # 元数据索引文件
        self._meta_path = self._upload_dir / "_documents.json"
        self._lock = Lock()
        self._records: Dict[str, DocumentRecord] = self._load_meta()

    def _load_meta(self) -> Dict[str, DocumentRecord]:
        """从磁盘加载文档元数据索引。"""
        if not self._meta_path.exists():
            return {}
        try:
            data = json.loads(self._meta_path.read_text(encoding="utf-8"))
            return {k: DocumentRecord(**v) for k, v in data.items()}
        except Exception as exc:  # noqa: BLE001
            logger.warning("文档元数据加载失败，将重建: %s", exc)
            return {}

    def _save_meta(self) -> None:
        """将文档元数据索引写回磁盘。"""
        data = {k: asdict(v) for k, v in self._records.items()}
        self._meta_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add_document(self, filename: str, content: bytes) -> DocumentRecord:
        """
        保存并索引一个上传文档。

        Args:
            filename: 原始文件名。
            content: 文件二进制内容。

        Returns:
            DocumentRecord: 生成的文档记录。

        Raises:
            ValidationError: 文件为空或格式不支持时。
        """
        # 校验非空（不限制文件大小）
        if len(content) == 0:
            raise ValidationError("上传文件为空")
        # 校验扩展名
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValidationError(
                f"不支持的文件格式: {ext}，支持: {sorted(SUPPORTED_EXTENSIONS)}"
            )

        document_id = uuid.uuid4().hex
        # 以文档 ID 为前缀落盘，避免同名覆盖
        saved_path = self._upload_dir / f"{document_id}{ext}"
        saved_path.write_bytes(content)

        # 解析 -> 索引
        text = load_document(saved_path)
        chunk_count = self._retriever.index_document(document_id, filename, text)

        record = DocumentRecord(
            document_id=document_id,
            filename=filename,
            chunk_count=chunk_count,
            size_bytes=len(content),
            created_at=time.time(),
        )
        with self._lock:
            self._records[document_id] = record
            self._save_meta()
        logger.info("文档已入库: %s (%d 片段)", filename, chunk_count)
        return record

    def list_documents(self) -> List[DocumentRecord]:
        """列出全部文档，按上传时间降序。"""
        return sorted(
            self._records.values(), key=lambda r: r.created_at, reverse=True
        )

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

