"""
HTTP 中间件集合（企业化横切关注点）。

1. ``RequestContextMiddleware``：为每个请求生成/透传 X-Request-ID，
   记录访问日志与延迟指标，响应头回传 Request-ID。
2. ``PublicCORSMiddleware``：公共面（/api/v1、/embed）宽松 CORS，
   管理面仍由主 CORS 中间件按白名单控制。
3. ``SecurityHeadersMiddleware``：常规安全响应头（跳过 /embed 以便嵌入）。
4. ``RateLimitMiddleware``：公共端点令牌桶限流（按 API Key 或 IP）。
"""

from __future__ import annotations

import time
import uuid
from typing import Dict

from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.metrics import get_metrics
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 公共面路径前缀（嵌入产品可达，需宽松跨域）
PUBLIC_PREFIXES = ("/api/v1", "/embed")


def _is_public(path: str) -> bool:
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Request-ID 生成/透传 + 访问日志 + 指标采集。"""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            latency = time.perf_counter() - start
            get_metrics().record_request(request.url.path, 500, latency)
            logger.exception(
                "请求异常 %s %s (rid=%s, %.0fms)",
                request.method,
                request.url.path,
                request_id,
                latency * 1000,
            )
            raise
        latency = time.perf_counter() - start
        get_metrics().record_request(request.url.path, response.status_code, latency)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %d (%.0fms, rid=%s)",
            request.method,
            request.url.path,
            response.status_code,
            latency * 1000,
            request_id,
        )
        return response


class PublicCORSMiddleware:
    """
    公共面 CORS：对 /api/v1 与 /embed 的请求回 ``Access-Control-Allow-Origin: *``
    （含预检），使任何产品网页都可调用公共问答 API 或加载挂件。

    实现为纯 ASGI 中间件，置于管理面 CORSMiddleware 之外：
    命中公共路径时直接重写响应头（移除内层可能写入的受限 ACAO），
    否则原样透传。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not _is_public(path):
            await self.app(scope, receive, send)
            return

        async def send_with_public_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=list(message["headers"]))
                for name in (
                    "access-control-allow-origin",
                    "access-control-allow-credentials",
                    "access-control-allow-methods",
                    "access-control-allow-headers",
                    "vary",
                ):
                    del headers[name]
                headers["Access-Control-Allow-Origin"] = "*"
                headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
                headers["Access-Control-Max-Age"] = "600"
                message["headers"] = headers.raw
            await send(message)

        # 公共路径的预检直接放行
        if scope.get("method") == "OPTIONS":
            response = JSONResponse({"ok": True})
            await response(scope, receive, send_with_public_cors)
            return

        await self.app(scope, receive, send_with_public_cors)


class SecurityHeadersMiddleware:
    """常规安全响应头；公共嵌入面跳过 X-Frame-Options（允许被 iframe 引用）。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=list(message["headers"]))
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                if not _is_public(path):
                    headers.setdefault("X-Frame-Options", "DENY")
                message["headers"] = headers.raw
            await send(message)

        await self.app(scope, receive, send_with_headers)


class _TokenBucket:
    """单键令牌桶（线程安全的近似实现，进程内限流用）。"""

    __slots__ = ("rate", "capacity", "tokens", "updated")

    def __init__(self, rate_per_minute: int) -> None:
        self.rate = rate_per_minute / 60.0      # 每秒补充速率
        self.capacity = float(max(rate_per_minute, 1))
        self.tokens = self.capacity
        self.updated = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    公共问答端点限流：按 API Key（X-API-Key / Bearer）或客户端 IP 分桶。
    超限返回 429 与 Retry-After 提示。
    """

    def __init__(self, app: ASGIApp, per_minute: int) -> None:
        super().__init__(app)
        self._per_minute = max(per_minute, 1)
        self._buckets: Dict[str, _TokenBucket] = {}

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/v1"):
            return await call_next(request)

        key = (
            request.headers.get("x-api-key")
            or request.headers.get("authorization")
            or (request.client.host if request.client else "anon")
        )
        bucket = self._buckets.setdefault(key, _TokenBucket(self._per_minute))
        # 简单清理：桶数量过大时重建（防内存膨胀）
        if len(self._buckets) > 10000:
            self._buckets.clear()
            self._buckets[key] = bucket
        if not bucket.allow():
            get_metrics().incr("ask_denied_total")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "RateLimitExceeded",
                    "message": "请求过于频繁，请稍后再试",
                },
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
