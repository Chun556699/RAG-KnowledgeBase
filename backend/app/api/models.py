"""
模型与提示词 API 路由。

暴露「可用 LLM 模型清单」与「提示词模板清单」，
支撑前端的模型切换下拉框与提示工程展示面板。
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from app.core.llm.prompt import get_prompt_store, list_templates
from app.models.schemas import (
    ModelInfo,
    OkResponse,
    PromptCreateRequest,
    PromptTemplateSchema,
    PromptUpdateRequest,
)
from app.services.container import Container, get_container
from app.utils.exceptions import NotFoundError, ValidationError

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=List[ModelInfo], summary="列出可用模型")
async def list_models(
    container: Container = Depends(get_container),
) -> List[ModelInfo]:
    """
    返回全部 LLM 提供商及其可用状态。

    DeepSeek / 小米 MiMo 仅在配置了对应 API Key 时标记为可用。
    """
    return [ModelInfo(**m) for m in container.llm_factory.available_models()]


@router.get("/prompts", response_model=List[PromptTemplateSchema], summary="列出提示词模板")
async def list_prompt_templates() -> List[PromptTemplateSchema]:
    """返回全部提示词模板（内置 + 用户自定义）。"""
    return [PromptTemplateSchema(**t) for t in list_templates()]


@router.post("/prompts", response_model=PromptTemplateSchema, summary="新建提示词模板")
async def create_prompt_template(req: PromptCreateRequest) -> PromptTemplateSchema:
    """新增一个自定义提示词模板（名称不得与已有模板冲突）。"""
    store = get_prompt_store()
    try:
        store.create(req.name, req.template, req.description)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return PromptTemplateSchema(
        name=req.name.strip(),
        description=req.description,
        template=req.template,
        is_builtin=False,
        is_overridden=False,
    )


@router.put(
    "/prompts/{name}", response_model=PromptTemplateSchema, summary="更新/覆盖提示词模板"
)
async def update_prompt_template(
    name: str, req: PromptUpdateRequest
) -> PromptTemplateSchema:
    """更新自定义模板，或覆盖内置模板的内容。"""
    store = get_prompt_store()
    try:
        store.update(name, req.template, req.description)
    except KeyError as exc:
        raise NotFoundError(f"提示词模板不存在: {name}") from exc
    # 重新取回以带上准确的来源标记
    item = next((t for t in list_templates() if t["name"] == name), None)
    return PromptTemplateSchema(**item) if item else PromptTemplateSchema(
        name=name, description=req.description, template=req.template
    )


@router.delete("/prompts/{name}", response_model=OkResponse, summary="删除/重置提示词模板")
async def delete_prompt_template(name: str) -> OkResponse:
    """删除自定义模板；若为被覆盖的内置模板则重置为默认。"""
    store = get_prompt_store()
    try:
        store.delete(name)
    except KeyError as exc:
        raise NotFoundError(f"提示词模板不存在: {name}") from exc
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return OkResponse(message="删除成功")
