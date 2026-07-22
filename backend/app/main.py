"""
FastAPI 应用入口。

职责：
1. 应用生命周期管理（启动时初始化依赖容器，关闭时释放资源）；
2. 注册跨域（CORS）中间件，供前端访问；
3. 注册全局异常处理器，统一错误响应格式；
4. 挂载各业务路由；
5. 提供健康检查端点。

启动命令：uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import agent, chat, documents, graph, memory, models, settings as settings_api
from app.config import get_settings
from app.services.container import get_container, init_container, reset_container
from app.utils.exceptions import AppException
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期钩子。

    启动阶段初始化依赖容器（构建 RAG/记忆/Agent 等子系统），
    关闭阶段释放数据库连接等资源。
    """
    logger.info("应用启动中：初始化依赖容器…")
    init_container()
    logger.info("=== %s 已就绪 (env=%s) ===", settings.app_name, settings.app_env)
    yield
    logger.info("应用关闭中：释放资源…")
    reset_container()


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    description=(
        "综合性 AI 知识库产品后端 API。集成 RAG 检索增强、Agent 智能体、"
        "多模型 LLM、上下文记忆四大能力。"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ---------- 跨域中间件 ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 全局异常处理 ----------
@app.exception_handler(AppException)
async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
    """将业务异常转换为标准 JSON 错误响应。"""
    logger.warning("业务异常: %s (%d)", exc.message, exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.__class__.__name__, "message": exc.message},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """兜底处理未预期异常，避免泄露堆栈细节。"""
    logger.exception("未处理异常: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "InternalServerError", "message": "服务器内部错误"},
    )


# ---------- 路由注册 ----------
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(agent.router)
app.include_router(memory.router)
app.include_router(models.router)
app.include_router(graph.router)
app.include_router(settings_api.router)


# ---------- 健康检查 ----------
@app.get("/api/health", tags=["system"], summary="健康检查")
async def health() -> dict:
    """返回服务健康状态与关键运行指标。"""
    container = get_container()
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "default_provider": settings.default_llm_provider,
        "indexed_chunks": container.retriever.count(),
    }


@app.get("/", tags=["system"], summary="根路径")
async def root() -> dict:
    """根路径，返回 API 文档入口提示。"""
    return {
        "message": f"{settings.app_name} API 正在运行",
        "docs": "/docs",
        "health": "/api/health",
    }
