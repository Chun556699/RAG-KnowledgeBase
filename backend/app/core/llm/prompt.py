"""
提示工程（Prompt Engineering）模块。

集中管理所有提示词模板，支持变量插值与动态组装。将提示词与业务代码解耦，
便于统一优化与 A/B 测试。这是「动态提示模板管理」能力的核心。

设计要点：
- 模板集中注册，命名清晰，便于检索与复用；
- 使用 str.format 风格占位符，简单直观；
- RAG 模板遵循「参考资料：」约定，便于模型识别检索上下文。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PromptTemplate:
    """
    提示词模板。

    Attributes:
        name: 模板唯一标识。
        template: 含占位符的模板字符串（如 {question}）。
        description: 模板用途说明。
    """

    name: str
    template: str
    description: str = ""

    def render(self, **kwargs: str) -> str:
        """
        渲染模板，将占位符替换为实际值。

        Args:
            **kwargs: 占位符对应的变量值。

        Returns:
            str: 渲染后的提示词。

        Raises:
            KeyError: 当缺少必需的占位符变量时。
        """
        return self.template.format(**kwargs)


# ---------------------------------------------------------------------------
# 内置模板注册表
# ---------------------------------------------------------------------------

# RAG 问答系统提示词：把检索到的资料注入 system prompt
RAG_SYSTEM = PromptTemplate(
    name="rag_system",
    description="RAG 检索增强问答的系统提示词，注入检索上下文",
    template=(
        "你是一个严谨的知识库问答助手。请**仅依据下方参考资料**回答用户问题：\n"
        "1. 回答必须忠于资料，不得自行发挥或补充资料中没有的信息；\n"
        "2. **每一句结论都需在句尾标注来源编号**，形如 [资料1]、[资料2]；若引用图谱关系则以 [图谱关系N] 标注，多个来源可并列；\n"
        "3. 若资料不足以回答，请如实说明「根据现有资料无法回答」，不要编造；\n"
        "4. 回答需条理清晰，使用与用户相同的语言。\n\n"
        "参考资料：{context}"
    ),
)

# RAG 启用但检索无命中时的系统提示词（避免基于空上下文编造）
RAG_NO_CONTEXT = PromptTemplate(
    name="rag_no_context",
    description="RAG 检索无相关命中时的兜底回答提示词",
    template=(
        "你是一个严谨的知识库问答助手。本次检索未在知识库中找到与问题相关的资料。"
        "请如实告知用户「知识库中未找到相关内容」，不要凭空编造事实；"
        "若问题属于常识性内容，可谨慎作答并明确标注「此为通用知识，非来自知识库」。"
    ),
)

# 多轮追问查询改写：将含指代的追问改写为可独立检索的完整查询
QUERY_REWRITE = PromptTemplate(
    name="query_rewrite",
    description="多轮对话下将含指代的追问改写为独立查询，以提升检索命中率",
    template=(
        "下面是一段对话历史与用户的最新追问。请结合历史，将追问中的指代词（如“它”“这个”“上面提到的”）"
        "补全为一个无需上下文即可理解的、独立完整的检索查询。\n"
        "要求：只输出改写后的查询本身，不要任何解释、引号或前缀；若追问本身已独立完整，则原样输出。\n\n"
        "对话历史：\n{history}\n\n用户追问：{question}\n\n改写后的独立查询："
    ),
)

# 反问澄清：判断用户问题是否足够清晰，模糊时先反问用户再作答
CLARIFY = PromptTemplate(
    name="clarify",
    description="判断用户问题是否需要澄清，模糊时生成一句反问与候选澄清方向",
    template=(
        "你是一个善于沟通、追求精准的助手。请判断用户的最新问题是否足够清晰、可直接作答。\n"
        "当问题存在明显歧义、指代不清、缺少关键信息（如对象、范围、时间、目标不明确），"
        "或同一问法可能对应多种截然不同的意图时，才需要先反问澄清；"
        "若问题已足够具体，或历史中你已问过澄清且用户已作出回应，则无需再澄清，直接作答。\n"
        "本次是否检索到相关知识库资料：{has_context}\n\n"
        "对话历史：\n{history}\n\n"
        "用户最新问题：{question}\n\n"
        "请严格输出 JSON："
        '{{"need_clarify": true/false, "question": "要反问用户的一句话（无需澄清则留空）", '
        '"options": ["候选澄清方向1", "候选澄清方向2"]}}。\n'
        "要求：question 简洁友好、只问最关键的一点；options 给 2-4 个用户可能的具体意图，"
        "便于其一键选择；若无需澄清，need_clarify 为 false 且 options 为空数组。只输出 JSON。"
    ),
)

# 无上下文时的通用助手提示词
CHAT_SYSTEM = PromptTemplate(
    name="chat_system",
    description="通用对话助手系统提示词",
    template=(
        "你是一个专业、友好的 AI 助手，擅长清晰、准确地回答用户的问题。"
        "请使用与用户相同的语言作答。"
    ),
)

# Agent 任务规划提示词（ReAct 风格：每步显式携带推理依据）
AGENT_PLANNER = PromptTemplate(
    name="agent_planner",
    description="Agent 任务分解（ReAct），输出带推理依据的 JSON 子任务列表",
    template=(
        "你是一个采用 ReAct（推理+行动）范式的任务规划专家。请将用户的复杂请求"
        "分解为有序的子任务，每个子任务先给出推理依据（thought），再给出具体行动（description）。"
        "可用工具如下：\n{tools}\n\n"
        "用户请求：{query}\n\n"
        "请严格输出 JSON 数组，每个元素形如 "
        '{{"step": 1, "thought": "为什么要做这一步的推理", "description": "子任务描述", "tool": "工具名或null"}}。'
        "只输出 JSON，不要额外解释。"
    ),
)

# Agent 反思提示词：评估执行结果并给出改进建议
AGENT_REFLECTION = PromptTemplate(
    name="agent_reflection",
    description="Agent 自我评估与改进",
    template=(
        "你是一个质量审查员。请评估以下任务执行结果是否充分回答了原始问题。\n\n"
        "原始问题：{query}\n\n"
        "执行结果：{result}\n\n"
        "请输出 JSON：{{\"satisfied\": true/false, \"reason\": \"评价\", "
        "\"suggestion\": \"若不满意，给出改进建议\"}}。只输出 JSON。"
    ),
)

# Agent 最终答案汇总提示词
AGENT_SYNTHESIZE = PromptTemplate(
    name="agent_synthesize",
    description="将各子任务结果汇总为最终答案",
    template=(
        "请基于以下各步骤的执行结果，综合生成对用户原始问题的完整回答。\n\n"
        "原始问题：{query}\n\n"
        "各步骤结果：\n{steps}\n\n"
        "请给出结构清晰、连贯的最终回答。"
    ),
)

# 知识图谱实体关系抽取：从文档片段中抽取「实体-关系-实体」三元组
GRAPH_EXTRACT = PromptTemplate(
    name="graph_extract",
    description="从文档片段中抽取实体及实体间关系的三元组，用于构建知识图谱",
    template=(
        "你是一个知识图谱构建专家。请从下方文本中抽取关键实体以及实体之间的语义关系，"
        "组织为「实体-关系-实体」三元组。\n"
        "要求：\n"
        "1. 实体应为具体、有意义的名词（人物、组织、概念、技术、地点、事件等），去除无意义的代词与虚词；\n"
        "2. 关系用简短的动词短语描述（如“属于”“包含”“依赖”“提出”）；\n"
        "3. 只抽取文本中明确表达的关系，不要自行脑补；\n"
        "4. 若文本中无明确实体关系，返回空数组。\n\n"
        "文本：\n{text}\n\n"
        "请严格输出 JSON 数组，每个元素形如 "
        '{{"source": "实体A", "relation": "关系", "target": "实体B"}}。'
        "只输出 JSON，不要任何解释。"
    ),
)


# CRAG 检索质量评估：判断检索结果是否足以回答，不足则给出更优检索查询
RETRIEVAL_EVAL = PromptTemplate(
    name="retrieval_eval",
    description="CRAG 检索质量评估：判断检索资料是否足以回答，不足时给出更优检索查询",
    template=(
        "你是一个检索质量评估员。请判断下方检索到的资料是否足以回答用户问题。\n"
        "评估标准：资料是否包含回答问题所需的关键信息；若资料与问题无关或关键信息缺失，则视为不充分。\n\n"
        "用户问题：{query}\n\n"
        "检索资料：\n{context}\n\n"
        "请严格输出 JSON："
        '{{"sufficient": true/false, "reason": "评估理由", '
        '"rewritten_query": "若不充分，给出一个更可能命中相关资料的新检索查询；若充分则留空"}}。'
        "只输出 JSON。"
    ),
)


# RAGAS 忠实度评估：判断回答是否忠于检索上下文
RAGAS_FAITHFULNESS = PromptTemplate(
    name="ragas_faithfulness",
    description="RAGAS 忠实度评估：判断回答是否忠于检索上下文，是否存在编造",
    template=(
        "你是一个 RAG 质量评估员。请评估以下回答是否忠实于给定的参考资料上下文，"
        "即回答中的陈述是否都能在上下文中找到依据，是否存在编造（幻觉）。\n\n"
        "用户问题：{question}\n\n"
        "参考资料：\n{context}\n\n"
        "回答：\n{answer}\n\n"
        "请严格输出 JSON：{{\"score\": 0到1之间的忠实度分数, \"reason\": \"评估理由\"}}。"
        "score 越接近 1 表示回答越忠实于上下文、无编造。只输出 JSON。"
    ),
)

# RAGAS 答案相关性评估：判断回答是否切题
RAGAS_ANSWER_RELEVANCY = PromptTemplate(
    name="ragas_answer_relevancy",
    description="RAGAS 答案相关性评估：判断回答是否直接、完整地回应问题",
    template=(
        "你是一个 RAG 质量评估员。请评估以下回答与用户问题的相关性，"
        "即回答是否直接、完整地回应了问题，是否有无关内容。\n\n"
        "用户问题：{question}\n\n"
        "回答：\n{answer}\n\n"
        "请严格输出 JSON：{{\"score\": 0到1之间的相关性分数, \"reason\": \"评估理由\"}}。"
        "score 越接近 1 表示回答越切题。只输出 JSON。"
    ),
)


# 内置模板注册表（只读基线：始终存在，可被用户覆盖但不可删除）
_BUILTIN: Dict[str, PromptTemplate] = {
    t.name: t
    for t in (
        RAG_SYSTEM,
        RAG_NO_CONTEXT,
        QUERY_REWRITE,
        CLARIFY,
        CHAT_SYSTEM,
        AGENT_PLANNER,
        AGENT_REFLECTION,
        AGENT_SYNTHESIZE,
        GRAPH_EXTRACT,
        RETRIEVAL_EVAL,
        RAGAS_FAITHFULNESS,
        RAGAS_ANSWER_RELEVANCY,
    )
}


class PromptStore:
    """
    提示词存储：内置模板 + 用户自定义/覆盖（持久化到 JSON）。

    - 内置模板作为只读基线，始终存在；
    - 用户可新增自定义模板，或覆盖内置模板的内容；
    - 覆盖内容与自定义模板持久化到磁盘，重启后仍生效；
    - 删除自定义模板会移除它；删除被覆盖的内置模板将「重置为默认」。
    """

    def __init__(self, persist_path: str) -> None:
        """
        Args:
            persist_path: 自定义/覆盖模板的持久化文件路径。
        """
        self._path = Path(persist_path)
        # name -> PromptTemplate（用户自定义或对内置的覆盖）
        self._custom: Dict[str, PromptTemplate] = {}
        self._load()

    def _load(self) -> None:
        """从磁盘加载用户模板（文件不存在或损坏时安全忽略）。"""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for item in data:
                name = str(item["name"])
                self._custom[name] = PromptTemplate(
                    name=name,
                    template=str(item.get("template", "")),
                    description=str(item.get("description", "")),
                )
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("加载自定义提示词失败，已忽略: %s", exc)

    def _save(self) -> None:
        """将用户模板写回磁盘。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {"name": t.name, "description": t.description, "template": t.template}
            for t in self._custom.values()
        ]
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get(self, name: str) -> PromptTemplate:
        """按名获取模板（用户覆盖优先于内置）。"""
        if name in self._custom:
            return self._custom[name]
        if name in _BUILTIN:
            return _BUILTIN[name]
        raise KeyError(f"提示词模板不存在: {name}")

    def list(self) -> List[dict]:
        """列出全部模板（内置在前，自定义在后），带来源标记。"""
        names = list(_BUILTIN.keys()) + [
            n for n in self._custom if n not in _BUILTIN
        ]
        result: List[dict] = []
        for name in names:
            tpl = self._custom.get(name) or _BUILTIN[name]
            result.append(
                {
                    "name": tpl.name,
                    "description": tpl.description,
                    "template": tpl.template,
                    "is_builtin": name in _BUILTIN,
                    "is_overridden": name in _BUILTIN and name in self._custom,
                }
            )
        return result

    def create(self, name: str, template: str, description: str = "") -> PromptTemplate:
        """新增自定义模板（名称不得与已有模板冲突）。"""
        name = name.strip()
        if not name:
            raise ValueError("模板名不能为空")
        if name in _BUILTIN or name in self._custom:
            raise ValueError(f"模板已存在: {name}")
        self._custom[name] = PromptTemplate(name, template, description)
        self._save()
        return self._custom[name]

    def update(self, name: str, template: str, description: str = "") -> PromptTemplate:
        """更新模板（可覆盖内置模板；目标不存在时报错）。"""
        if name not in _BUILTIN and name not in self._custom:
            raise KeyError(f"提示词模板不存在: {name}")
        self._custom[name] = PromptTemplate(name, template, description)
        self._save()
        return self._custom[name]

    def delete(self, name: str) -> None:
        """
        删除模板。

        - 自定义模板：直接移除；
        - 被覆盖的内置模板：移除覆盖，重置为默认；
        - 未被覆盖的内置模板：不允许删除。
        """
        if name in _BUILTIN:
            if name in self._custom:
                del self._custom[name]
                self._save()
                return
            raise ValueError(f"内置模板不可删除: {name}")
        if name in self._custom:
            del self._custom[name]
            self._save()
            return
        raise KeyError(f"提示词模板不存在: {name}")


@lru_cache
def get_prompt_store() -> PromptStore:
    """获取全局提示词存储单例（按配置路径初始化）。"""
    from app.config import get_settings

    return PromptStore(get_settings().prompt_store_path)


def get_template(name: str) -> PromptTemplate:
    """
    按名称获取提示词模板（委托给全局存储，用户覆盖优先）。

    Args:
        name: 模板名。

    Returns:
        PromptTemplate: 模板对象。

    Raises:
        KeyError: 模板不存在时。
    """
    return get_prompt_store().get(name)


def list_templates() -> List[dict]:
    """列出所有模板（供前端「提示工程」面板展示与管理）。"""
    return get_prompt_store().list()
