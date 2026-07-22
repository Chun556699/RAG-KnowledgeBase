"""
对话服务（RAG + 记忆编排）。

将 LLM、RAG 检索、会话记忆三者编排为完整的对话能力：
1. 载入/创建会话，读取历史消息维持多轮上下文；
2. 可选进行知识库检索，将上下文注入 system 提示词（RAG）；
3. 调用 LLM 生成回答（支持一次性与流式）；
4. 将用户消息与回答写回会话记忆。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Dict, List, Optional, Tuple

from app.core.llm.base import GenerationConfig, Message, Role
from app.core.llm.factory import LLMFactory
from app.core.llm.prompt import get_template
from app.core.memory.manager import MemoryManager
from app.core.rag.retriever import Retriever
from app.core.rag.vectorstore import RetrievedChunk
from app.config import Settings
from app.utils.logger import get_logger
from app.utils.parsing import extract_json

logger = get_logger(__name__)


@dataclass
class ChatContext:
    """构造好的一次对话请求上下文。"""

    session_id: str
    messages: List[Message]
    sources: List[RetrievedChunk]
    provider_name: str
    model_name: str
    used_rag_context: bool = False
    # 若本次判定为反问澄清，则为 {"question": str, "options": List[str]}；否则 None
    clarify: Optional[Dict] = None


class ChatService:
    """RAG 对话服务。"""

    def __init__(
        self,
        llm_factory: LLMFactory,
        retriever: Retriever,
        memory: MemoryManager,
        settings: Settings,
    ) -> None:
        self._llm_factory = llm_factory
        self._retriever = retriever
        self._memory = memory
        self._settings = settings

    async def _rewrite_query(
        self,
        llm,
        message: str,
        history,
    ) -> str:
        """
        多轮追问查询改写：用 LLM 将含指代的追问补全为独立检索查询。

        仅在存在历史且启用改写时调用。改写失败不阻断主流程，回退原始查询。

        Args:
            llm: LLM 提供商实例。
            message: 用户最新追问。
            history: 会话历史消息列表。

        Returns:
            str: 用于检索的查询（改写后或原始）。
        """
        recent = history[-6:]
        convo = "\n".join(
            f"{'用户' if h.role == Role.USER.value else '助手'}: {h.content}"
            for h in recent
        )
        prompt = get_template("query_rewrite").render(history=convo, question=message)
        try:
            resp = await llm.generate(
                [Message(Role.USER, prompt)],
                GenerationConfig(temperature=0.0, max_tokens=128),
            )
            rewritten = (resp.content or "").strip()
            if rewritten and rewritten != message:
                logger.info("查询改写: '%s' -> '%s'", message[:30], rewritten[:30])
            return rewritten or message
        except Exception as exc:  # noqa: BLE001  改写失败不阻断主流程
            logger.warning("查询改写失败，回退原始查询: %s", exc)
            return message

    async def _maybe_clarify(
        self,
        llm,
        message: str,
        ctx: ChatContext,
    ) -> Optional[Dict]:
        """
        反问澄清判断：用 LLM 判断用户问题是否模糊，若模糊则生成一句反问与候选方向。

        判断失败（LLM 不可用 / JSON 解析失败）时返回 None，不阻断主干回答流程。

        Args:
            llm: LLM 提供商实例。
            message: 用户最新消息。
            ctx: 已组装的对话上下文（含会话与检索命中情况）。

        Returns:
            Optional[Dict]: 需澄清时返回 {"question", "options"}；否则 None。
        """
        history = self._memory.get_history(ctx.session_id)
        recent = history[-6:]
        convo = (
            "\n".join(
                f"{'用户' if h.role == Role.USER.value else '助手'}: {h.content}"
                for h in recent
            )
            or "（无）"
        )
        has_context = "是" if ctx.used_rag_context else "否"
        prompt = get_template("clarify").render(
            history=convo, question=message, has_context=has_context
        )
        try:
            resp = await llm.generate(
                [Message(Role.USER, prompt)],
                GenerationConfig(temperature=0.0, max_tokens=256),
            )
            data = extract_json(resp.content or "")
            if isinstance(data, dict) and data.get("need_clarify"):
                question = str(data.get("question", "")).strip()
                options = [
                    str(o).strip()
                    for o in (data.get("options") or [])
                    if str(o).strip()
                ]
                if question:
                    logger.info("触发反问澄清 session=%s: %s", ctx.session_id, question[:40])
                    return {"question": question, "options": options[:4]}
        except Exception as exc:  # noqa: BLE001  澄清判断失败不阻断主流程
            logger.warning("澄清判断失败，跳过: %s", exc)
        return None

    async def _prepare_context(
        self,
        llm,
        message: str,
        session_id: Optional[str],
        use_rag: bool,
        top_k: int,
    ) -> ChatContext:
        """
        组装一次对话所需的完整消息列表与检索来源。

        Args:
            llm: LLM 提供商实例（用于多轮查询改写）。
            message: 用户消息。
            session_id: 会话 ID，为空则新建。
            use_rag: 是否启用检索增强。
            top_k: 检索片段数。

        Returns:
            ChatContext: 组装结果。
        """
        # 1) 会话：不存在则创建（标题取首条消息前 20 字）
        if not session_id or self._memory.get_session(session_id) is None:
            title = message[:20] + ("…" if len(message) > 20 else "")
            session = self._memory.create_session(title=title or "新会话")
            session_id = session.id

        history = self._memory.get_history(session_id)

        # 2) RAG 检索（含多轮查询改写与相关性阈值过滤）
        sources: List[RetrievedChunk] = []
        messages: List[Message] = []
        used_rag_context = False
        if use_rag:
            # 多轮追问：若有历史且启用改写，先把含指代的追问改写为独立查询再检索
            retrieval_query = message
            if self._settings.query_rewrite_enabled and history:
                retrieval_query = await self._rewrite_query(llm, message, history)
            sources = self._retriever.retrieve(
                retrieval_query,
                top_k=top_k,
                min_score=self._settings.retrieval_min_score,
            )
            context = self._retriever.build_context(sources)
            if context:
                system_prompt = get_template("rag_system").render(context=context)
                used_rag_context = True
            else:
                # 检索无相关命中：使用兜底提示，如实告知而非编造
                system_prompt = get_template("rag_no_context").template
        else:
            system_prompt = get_template("chat_system").template
        messages.append(Message(Role.SYSTEM, system_prompt))

        # 3) 注入历史消息，维持多轮上下文
        for h in history:
            role = Role(h.role) if h.role in (r.value for r in Role) else Role.USER
            messages.append(Message(role, h.content))

        # 4) 追加当前用户消息
        messages.append(Message(Role.USER, message))

        return ChatContext(
            session_id=session_id,
            messages=messages,
            sources=sources,
            provider_name="",
            model_name="",
            used_rag_context=used_rag_context,
        )

    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        use_rag: bool = True,
        top_k: int = 4,
        allow_clarify: bool = True,
    ) -> Tuple[str, ChatContext]:
        """
        一次性对话生成。

        Returns:
            Tuple[str, ChatContext]: (回答文本, 上下文含来源与会话信息)。
        """
        provider_name = provider or self._settings.default_llm_provider
        llm = self._llm_factory.get_provider(provider_name, model)

        ctx = await self._prepare_context(llm, message, session_id, use_rag, top_k)
        ctx.provider_name = llm.name
        ctx.model_name = llm.model

        # 反问澄清：问题模糊时先反问用户、不生成正文回答
        if allow_clarify and self._settings.clarify_enabled:
            clarify = await self._maybe_clarify(llm, message, ctx)
            if clarify:
                ctx.clarify = clarify
                self._memory.add_message(ctx.session_id, Role.USER.value, message)
                self._memory.add_message(
                    ctx.session_id, Role.ASSISTANT.value, clarify["question"]
                )
                logger.info("反问澄清 session=%s", ctx.session_id)
                return clarify["question"], ctx

        # 命中知识库资料时降温，提高对资料的忠实度
        gen_config = (
            GenerationConfig(temperature=self._settings.rag_temperature)
            if ctx.used_rag_context
            else GenerationConfig()
        )
        resp = await llm.generate(ctx.messages, gen_config)

        # 写回记忆
        self._memory.add_message(ctx.session_id, Role.USER.value, message)
        self._memory.add_message(ctx.session_id, Role.ASSISTANT.value, resp.content)
        logger.info("对话完成 session=%s tokens=%d", ctx.session_id, resp.total_tokens)
        return resp.content, ctx

    async def chat_stream(
        self,
        message: str,
        session_id: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        use_rag: bool = True,
        top_k: int = 4,
        allow_clarify: bool = True,
    ) -> Tuple[AsyncIterator[str], ChatContext]:
        """
        流式对话生成。

        Returns:
            Tuple[AsyncIterator[str], ChatContext]:
                (文本增量异步迭代器, 上下文)。迭代器耗尽后回答会自动写入记忆。
                若 ctx.clarify 不为空，则本次为反问澄清，迭代器不产出正文。
        """
        provider_name = provider or self._settings.default_llm_provider
        llm = self._llm_factory.get_provider(provider_name, model)

        ctx = await self._prepare_context(llm, message, session_id, use_rag, top_k)
        ctx.provider_name = llm.name
        ctx.model_name = llm.model

        # 反问澄清：问题模糊时不调用 LLM 生成正文，仅回复澄清问题
        if allow_clarify and self._settings.clarify_enabled:
            ctx.clarify = await self._maybe_clarify(llm, message, ctx)

        # 命中知识库资料时降温，提高对资料的忠实度
        gen_config = (
            GenerationConfig(temperature=self._settings.rag_temperature)
            if ctx.used_rag_context
            else GenerationConfig()
        )

        async def _generator() -> AsyncIterator[str]:
            """包装底层流：边输出边累积，结束后写回记忆。"""
            # 澄清路径：不生成正文，仅将用户消息与澄清问题写入记忆后结束
            if ctx.clarify is not None:
                self._memory.add_message(ctx.session_id, Role.USER.value, message)
                self._memory.add_message(
                    ctx.session_id, Role.ASSISTANT.value, ctx.clarify["question"]
                )
                logger.info("流式反问澄清 session=%s", ctx.session_id)
                return
            collected: List[str] = []
            async for delta in llm.stream(ctx.messages, gen_config):
                collected.append(delta)
                yield delta
            full_answer = "".join(collected)
            self._memory.add_message(ctx.session_id, Role.USER.value, message)
            self._memory.add_message(
                ctx.session_id, Role.ASSISTANT.value, full_answer
            )
            logger.info("流式对话完成 session=%s", ctx.session_id)

        return _generator(), ctx
