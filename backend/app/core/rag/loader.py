"""
文档加载器模块。

负责将多种格式的原始文档（PDF / Word / TXT / Markdown）解析为纯文本。
采用「注册表 + 扩展名分发」的策略，便于后续扩展新格式。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict

from app.utils.exceptions import DocumentParseError
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _load_txt(path: Path) -> str:
    """加载纯文本 / Markdown 文件。"""
    # 尝试 UTF-8，失败则退回 GBK（兼容中文 Windows 环境导出的文本）
    for encoding in ("utf-8", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentParseError(f"无法解码文本文件（编码不支持）: {path.name}")


def _load_pdf(path: Path) -> str:
    """加载 PDF 文件，逐页提取文本。"""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise DocumentParseError("未安装 pypdf，无法解析 PDF") from exc

    try:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001
        raise DocumentParseError(f"PDF 解析失败: {path.name} ({exc})") from exc

    text = "\n".join(pages).strip()
    if not text:
        raise DocumentParseError(
            f"PDF 未提取到文本（可能为扫描件，需 OCR）: {path.name}"
        )
    return text


def _load_docx(path: Path) -> str:
    """加载 Word (.docx) 文件，提取所有段落文本。"""
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover
        raise DocumentParseError("未安装 python-docx，无法解析 Word") from exc

    try:
        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    except Exception as exc:  # noqa: BLE001
        raise DocumentParseError(f"Word 解析失败: {path.name} ({exc})") from exc

    return "\n".join(paragraphs).strip()


# 扩展名 -> 加载函数 的分发表
_LOADERS: Dict[str, Callable[[Path], str]] = {
    ".txt": _load_txt,
    ".md": _load_txt,
    ".markdown": _load_txt,
    ".pdf": _load_pdf,
    ".docx": _load_docx,
}

# 对外暴露的支持格式集合（供上传校验使用）
SUPPORTED_EXTENSIONS = frozenset(_LOADERS.keys())


def load_document(path: str | Path) -> str:
    """
    将文档文件解析为纯文本。

    Args:
        path: 文档文件路径。

    Returns:
        str: 解析出的纯文本内容。

    Raises:
        DocumentParseError: 当格式不支持或解析失败时。
    """
    p = Path(path)
    if not p.exists():
        raise DocumentParseError(f"文件不存在: {p}")

    ext = p.suffix.lower()
    loader = _LOADERS.get(ext)
    if loader is None:
        raise DocumentParseError(
            f"不支持的文件格式: {ext}，支持: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    logger.info("解析文档: %s (格式=%s)", p.name, ext)
    text = loader(p)
    if not text.strip():
        raise DocumentParseError(f"文档内容为空: {p.name}")
    return text
