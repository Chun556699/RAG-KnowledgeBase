"""
文本分块（Chunking）模块。

将长文本切分为带重叠的语义片段，是 RAG 索引质量的关键环节。
本实现采用「递归分隔符」策略：优先按段落/句子等自然边界切分，
在保证块大小可控的同时，尽量维持语义完整。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from app.utils.logger import get_logger

logger = get_logger(__name__)

# 递归切分使用的分隔符，按语义粒度从大到小排列
_SEPARATORS = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]

# Markdown 标题行（# ~ ######），总是视为章节边界
_MD_HEADING_RE = re.compile(r"^\s*#{1,6}\s+\S")
# 中文章节 / 编号标题（如「第一章」「一、」「1.」「1.2 」），仅当行较短时视为标题
_NUM_HEADING_RE = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百零\d]+[章节部分篇回]"
    r"|[一二三四五六七八九十]+[、.．]"
    r"|\d+(?:\.\d+)*[、.．]?\s+)"
)
# 标题行的长度上限（超过则视为普通正文，避免误判以数字开头的长句）
_HEADING_MAX_LEN = 60


@dataclass
class Chunk:
    """
    文本块。

    Attributes:
        text: 块文本内容。
        index: 块在原文中的序号（从 0 开始）。
    """

    text: str
    index: int


class TextSplitter:
    """
    递归字符文本分割器。

    通过递归尝试不同粒度的分隔符，将文本切分为不超过 chunk_size 的块，
    相邻块之间保留 chunk_overlap 个字符的重叠，以避免语义在边界处断裂。
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        """
        Args:
            chunk_size: 单块最大字符数。
            chunk_overlap: 相邻块的重叠字符数，必须小于 chunk_size。

        Raises:
            ValueError: 当 chunk_overlap >= chunk_size 时。
        """
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, text: str) -> List[Chunk]:
        """
        将文本切分为块列表。

        先按标题行将全文切为若干语义章节，再在每个章节内递归分块并加重叠，
        从而避免一个块跨越两个不相关的标题，提升块的语义内聚性。

        Args:
            text: 待切分的完整文本。

        Returns:
            List[Chunk]: 有序的文本块列表。
        """
        text = text.strip()
        if not text:
            return []

        # 第一步：按标题切为语义章节（标题与其正文留在同一章节）
        sections = self._split_by_headings(text)

        # 第二步：章节内递归切为原子片段，再合并加重叠（重叠不跨章节）
        merged: List[str] = []
        for section in sections:
            pieces = self._recursive_split(section, _SEPARATORS)
            merged.extend(self._merge_with_overlap(pieces))

        chunks = [
            Chunk(text=t, index=i)
            for i, t in enumerate(c for c in merged if c.strip())
        ]
        logger.info(
            "文本分块完成：原文 %d 字 -> %d 章节 -> %d 块",
            len(text),
            len(sections),
            len(chunks),
        )
        return chunks

    def _split_by_headings(self, text: str) -> List[str]:
        """按标题行将文本切分为若干章节；无标题时整体作为单个章节。"""
        lines = text.split("\n")
        sections: List[str] = []
        current: List[str] = []
        for line in lines:
            if self._is_heading(line) and current:
                sections.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append("\n".join(current))
        return [s for s in sections if s.strip()]

    @staticmethod
    def _is_heading(line: str) -> bool:
        """判断一行是否为标题（Markdown 标题直接命中；编号/中文章节需较短）。"""
        stripped = line.strip()
        if not stripped:
            return False
        if _MD_HEADING_RE.match(line):
            return True
        if len(stripped) <= _HEADING_MAX_LEN and _NUM_HEADING_RE.match(line):
            return True
        return False

    def _recursive_split(self, text: str, separators: List[str]) -> List[str]:
        """按分隔符递归切分，直到每段不超过 chunk_size。"""
        if len(text) <= self.chunk_size:
            return [text] if text else []

        # 取当前粒度最大的分隔符
        sep = separators[0]
        rest = separators[1:]

        if sep == "":
            # 已无分隔符可用，强制按长度硬切
            return [
                text[i : i + self.chunk_size]
                for i in range(0, len(text), self.chunk_size)
            ]

        parts = text.split(sep)
        result: List[str] = []
        for part in parts:
            # 切分后保留分隔符，避免语义丢失
            segment = part + sep if sep else part
            if len(segment) <= self.chunk_size:
                if segment.strip():
                    result.append(segment)
            else:
                # 仍过长，用更细粒度的分隔符继续递归
                result.extend(self._recursive_split(segment, rest))
        return result

    def _merge_with_overlap(self, pieces: List[str]) -> List[str]:
        """将原子片段贪心合并为接近 chunk_size 的块，并添加重叠。"""
        chunks: List[str] = []
        current = ""

        for piece in pieces:
            if len(current) + len(piece) <= self.chunk_size:
                current += piece
            else:
                if current:
                    chunks.append(current.strip())
                # 用上一块的尾部作为下一块的开头，实现重叠
                overlap = current[-self.chunk_overlap :] if self.chunk_overlap else ""
                current = overlap + piece

        if current.strip():
            chunks.append(current.strip())
        return [c for c in chunks if c]
