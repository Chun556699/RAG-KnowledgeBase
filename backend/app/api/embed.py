"""
嵌入产物路由：对外提供可嵌入任意网页的聊天挂件与演示页。

- ``GET /embed/widget.js``：自包含挂件脚本（Vanilla JS + Shadow DOM，零依赖），
  任意页面一行 ``<script>`` 即可集成；
- ``GET /embed/demo``：演示页，展示挂件的实际运行效果；
- ``GET /embed/config``：公开嵌入配置（公共 API 开关等），
  供挂件自动探测可用性。

这些路径属于公共面（宽松 CORS、不设置 X-Frame-Options），由
PublicCORSMiddleware / SecurityHeadersMiddleware 按前缀放行。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.config import get_settings

router = APIRouter(prefix="/embed", tags=["embed"])

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_NO_CACHE = {"Cache-Control": "no-cache"}


@router.get("/widget.js", include_in_schema=False)
async def widget_js() -> FileResponse:
    """挂件脚本（强缓存 + 重新校验；文件名含版本参数即可缓存刷新）。"""
    return FileResponse(
        _STATIC_DIR / "widget.js",
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/demo", include_in_schema=False)
async def widget_demo() -> FileResponse:
    """挂件演示页：加载 widget.js 并附带示例密钥说明。"""
    return FileResponse(
        _STATIC_DIR / "demo.html",
        media_type="text/html",
        headers=_NO_CACHE,
    )


@router.get("/config", summary="公开嵌入配置")
async def embed_config() -> dict:
    """返回公共 API 是否启用及限速，供挂件与集成方探测。"""
    s = get_settings()
    return {
        "public_api_enabled": s.public_api_enabled,
        "rate_limit_per_minute": s.public_rate_limit_per_minute,
    }
