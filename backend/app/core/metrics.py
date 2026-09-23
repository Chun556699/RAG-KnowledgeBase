"""
轻量应用指标（Metrics）模块。

进程内指标采集（无外部依赖、零序列化开销）：
- 请求计数 / 按状态码 / 按路径；
- 延迟直方图（固定桶）与均值；
- 领域指标：检索次数、检索缓存命中、LLM 调用次数与 tokens。

通过 ``GET /api/metrics`` 暴露 JSON 快照，供监控看板或排查使用。
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict

# 延迟直方图桶边界（秒）
_LATENCY_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class Metrics:
    """进程内指标收集器（线程安全）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.requests_total = 0
        self.errors_total = 0
        self._by_status: Dict[int, int] = defaultdict(int)
        self._by_path: Dict[str, int] = defaultdict(int)
        self._latency_hist: Dict[float, int] = {b: 0 for b in _LATENCY_BUCKETS}
        self._latency_sum = 0.0
        self._latency_count = 0
        # 领域指标
        self.retrievals_total = 0
        self.retrieval_cache_hits = 0
        self.llm_calls_total = 0
        self.llm_tokens_total = 0
        self.ask_total = 0          # 公开 API 问答次数
        self.ask_denied_total = 0   # 鉴权/限流拒绝次数

    def record_request(self, path: str, status: int, latency: float) -> None:
        """记录一次 HTTP 请求。"""
        with self._lock:
            self.requests_total += 1
            self._by_status[status] += 1
            # 路径归一化：去掉路径参数尾部差异，聚合到路由粒度
            norm = self._normalize_path(path)
            self._by_path[norm] += 1
            self._latency_sum += latency
            self._latency_count += 1
            for b in _LATENCY_BUCKETS:
                if latency <= b:
                    self._latency_hist[b] += 1
                    break
            if status >= 500:
                self.errors_total += 1

    @staticmethod
    def _normalize_path(path: str) -> str:
        """把携带 ID 的路径归一化为路由模板（粗略，防基数爆炸）。"""
        parts = path.strip("/").split("/")
        out = []
        for p in parts:
            # 长随机串/UUID/数字 视为路径参数
            if len(p) >= 16 and all(c in "0123456789abcdefABCDEF-_=" for c in p):
                out.append("{id}")
            elif p.isdigit():
                out.append("{id}")
            else:
                out.append(p)
        return "/" + "/".join(out) if out else "/"

    def incr(self, name: str, value: int = 1) -> None:
        """领域计数器递增。"""
        with self._lock:
            current = getattr(self, name, 0)
            setattr(self, name, current + value)

    def snapshot(self) -> dict:
        """导出当前指标快照。"""
        with self._lock:
            avg = self._latency_sum / self._latency_count if self._latency_count else 0.0
            hit_rate = (
                self.retrieval_cache_hits / self.retrievals_total
                if self.retrievals_total
                else 0.0
            )
            return {
                "uptime_seconds": round(time.time() - self.started_at, 1),
                "requests_total": self.requests_total,
                "errors_total": self.errors_total,
                "by_status": dict(self._by_status),
                "by_path": dict(sorted(self._by_path.items(), key=lambda x: -x[1])[:30]),
                "latency": {
                    "avg_seconds": round(avg, 4),
                    "buckets": {str(k): v for k, v in self._latency_hist.items()},
                },
                "retrievals_total": self.retrievals_total,
                "retrieval_cache_hit_rate": round(hit_rate, 4),
                "llm_calls_total": self.llm_calls_total,
                "llm_tokens_total": self.llm_tokens_total,
                "ask_total": self.ask_total,
                "ask_denied_total": self.ask_denied_total,
            }


# 全局单例
_metrics = Metrics()


def get_metrics() -> Metrics:
    """获取全局指标收集器。"""
    return _metrics
