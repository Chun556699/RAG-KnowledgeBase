"""
稀疏检索（BM25）模块。

在向量（稠密）检索之外补充基于关键词的稀疏检索，两者融合可显著提升召回：
- 稠密检索擅长语义相近（同义改写、跨语言），但对专有名词、精确术语、
  缩写、编号等「字面匹配」场景容易漏召回；
- 稀疏检索（BM25）擅长精确字面匹配，恰好互补。

本实现为纯 Python 零依赖的内存 BM25 索引，中文采用「单字 + bigram」分词，
英文/数字按连续串切分，无需外部分词器即可获得不错的中文关键词检索效果。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SparseHit:
    """稀疏检索命中片段。"""

    chunk_id: str
    text: str
    score: float
    metadata: Dict[str, str]


class BM25Index:
    """
    内存 BM25 索引。

    维护 chunk 文本及其元数据，支持增量新增、按文档删除与检索。
    与向量库同步更新（由 Retriever 在索引构建 / 删除时调用）。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        """
        Args:
            k1: BM25 词频饱和参数（越大词频影响越大）。
            b: 文档长度归一化参数（0~1，越大越惩罚长文档）。
        """
        self._k1 = k1
        self._b = b
        # chunk_id -> {"text": str, "tokens": List[str], "metadata": dict}
        self._docs: Dict[str, dict] = {}
        # 词 -> 文档频率（出现在多少个文档中）
        self._df: Dict[str, int] = {}
        self._total_len = 0
        self._n = 0
        self._avgdl = 0.0

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """分词：英文/数字按连续串切分，中文按「单字 + bigram」。"""
        text = text.lower()
        tokens: List[str] = re.findall(r"[a-z0-9]+", text)
        chinese = re.findall(r"[\u4e00-\u9fff]", text)
        for i in range(len(chinese) - 1):
            tokens.append(chinese[i] + chinese[i + 1])
        tokens.extend(chinese)
        return tokens

    # ------------------------------------------------------------------
    # 写入 / 删除
    # ------------------------------------------------------------------
    def add(self, chunk_id: str, text: str, metadata: Dict[str, str]) -> None:
        """新增或覆盖一个片段（若 chunk_id 已存在则先移除旧的）。"""
        if chunk_id in self._docs:
            self.remove(chunk_id)
        tokens = self._tokenize(text)
        for tok in set(tokens):
            self._df[tok] = self._df.get(tok, 0) + 1
        self._docs[chunk_id] = {"text": text, "tokens": tokens, "metadata": metadata}
        self._total_len += len(tokens)
        self._n += 1
        self._avgdl = self._total_len / max(self._n, 1)

    def remove(self, chunk_id: str) -> None:
        """移除单个片段，同步维护词频统计。"""
        doc = self._docs.pop(chunk_id, None)
        if doc is None:
            return
        for tok in set(doc["tokens"]):
            self._df[tok] = self._df.get(tok, 0) - 1
            if self._df[tok] <= 0:
                self._df.pop(tok, None)
        self._total_len -= len(doc["tokens"])
        self._n -= 1
        self._avgdl = self._total_len / max(self._n, 1)

    def remove_by_document(self, document_id: str) -> int:
        """删除某文档的全部片段，返回删除数量。"""
        targets = [
            cid
            for cid, d in self._docs.items()
            if d["metadata"].get("document_id") == document_id
        ]
        for cid in targets:
            self.remove(cid)
        return len(targets)

    def count(self) -> int:
        """返回索引中的片段总数。"""
        return self._n

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    def search(self, query: str, top_k: int = 10) -> List[SparseHit]:
        """
        按 BM25 打分检索最相关的片段。

        Args:
            query: 查询文本。
            top_k: 返回条数。

        Returns:
            List[SparseHit]: 按 BM25 分数降序、且分数 > 0 的命中列表。
        """
        if self._n == 0:
            return []
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return []

        scored: List[SparseHit] = []
        for cid, doc in self._docs.items():
            tf: Dict[str, int] = {}
            for t in doc["tokens"]:
                tf[t] = tf.get(t, 0) + 1
            score = 0.0
            for qt in q_tokens:
                if qt not in tf:
                    continue
                df = self._df.get(qt, 0)
                # IDF：少见的词权重更高
                idf = math.log((self._n - df + 0.5) / (df + 0.5) + 1)
                # TF 归一化（含长度惩罚）
                tf_norm = (tf[qt] * (self._k1 + 1)) / (
                    tf[qt]
                    + self._k1
                    * (1 - self._b + self._b * len(doc["tokens"]) / max(self._avgdl, 1))
                )
                score += idf * tf_norm
            if score > 0:
                scored.append(
                    SparseHit(
                        chunk_id=cid,
                        text=doc["text"],
                        score=score,
                        metadata=doc["metadata"],
                    )
                )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]
