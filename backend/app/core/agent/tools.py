"""
Agent 工具模块。

定义 Agent 可调用的工具接口与注册中心，对应需求中的「工具调用」能力。
内置若干演示工具（知识库检索、计算器、时间查询），并支持通过注册表扩展。

工具统一实现 `BaseTool` 接口，Agent 通过工具名 + 参数字符串调用，
返回文本结果，从而将「决策」与「执行」解耦。
"""

from __future__ import annotations

import abc
import ast
import datetime
import operator
from typing import Callable, Dict, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


class BaseTool(abc.ABC):
    """工具抽象基类。"""

    #: 工具名，供 Agent 在规划时引用。
    name: str = "base"
    #: 工具用途描述，会注入到规划提示词中。
    description: str = ""

    @abc.abstractmethod
    def run(self, query: str) -> str:
        """
        执行工具。

        Args:
            query: 工具输入参数（自然语言或简单表达式）。

        Returns:
            str: 工具执行结果文本。
        """
        raise NotImplementedError


class CalculatorTool(BaseTool):
    """安全计算器：仅支持基础算术表达式求值。"""

    name = "calculator"
    description = "计算数学算术表达式，输入如 '2 + 3 * 4'，返回计算结果"

    # 允许出现的字符白名单，防止任意代码执行
    _ALLOWED = set("0123456789+-*/(). ")

    def run(self, query: str) -> str:
        """对算术表达式求值（AST 白名单节点，杜绝任意代码执行）。"""
        expr = query.strip()
        if not expr or not set(expr).issubset(self._ALLOWED):
            return f"无法计算：表达式含非法字符 -> {query}"
        try:
            result = self._safe_eval(expr)
            return f"计算结果：{expr} = {result}"
        except Exception as exc:  # noqa: BLE001
            return f"计算失败：{exc}"

    @staticmethod
    def _safe_eval(expr: str) -> float:
        """用 AST 白名单求值四则运算表达式，杜绝 eval 的代码注入风险。"""
        bin_ops = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
        }
        unary_ops = {
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
        }

        def _eval(node: ast.AST):
            if isinstance(node, ast.Expression):
                return _eval(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp) and type(node.op) in bin_ops:
                return bin_ops[type(node.op)](_eval(node.left), _eval(node.right))
            if isinstance(node, ast.UnaryOp) and type(node.op) in unary_ops:
                return unary_ops[type(node.op)](_eval(node.operand))
            raise ValueError(f"不支持的表达式元素: {type(node).__name__}")

        return _eval(ast.parse(expr, mode="eval"))


class DateTimeTool(BaseTool):
    """时间查询工具：返回当前日期与时间。"""

    name = "datetime"
    description = "查询当前的日期和时间，无需输入参数"

    def run(self, query: str) -> str:
        """返回当前本地时间字符串。"""
        now = datetime.datetime.now()
        return f"当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}"


class KnowledgeSearchTool(BaseTool):
    """
    知识库检索工具。

    将 RAG 检索能力包装为 Agent 工具，使 Agent 可以在规划中主动查询知识库。
    检索函数以依赖注入方式传入，避免 Agent 层直接耦合 RAG 实现。
    """

    name = "knowledge_search"
    description = "在已上传的知识库中检索与问题相关的资料，输入检索关键词"

    def __init__(self, search_fn: Callable[[str], str]) -> None:
        """
        Args:
            search_fn: 检索回调，接收查询串，返回拼接好的上下文文本。
        """
        self._search_fn = search_fn

    def run(self, query: str) -> str:
        """调用注入的检索函数。"""
        context = self._search_fn(query)
        if not context:
            return "知识库中未检索到相关资料。"
        return f"知识库检索结果：\n{context}"


class ToolRegistry:
    """工具注册中心：按名管理工具，供 Agent 查询与调用。"""

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具。"""
        self._tools[tool.name] = tool
        logger.info("注册工具: %s", tool.name)

    def get(self, name: str) -> Optional[BaseTool]:
        """按名获取工具，不存在返回 None。"""
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """列出全部已注册工具。"""
        return list(self._tools.values())

    def describe(self) -> str:
        """
        生成工具清单描述，用于注入规划提示词。

        Returns:
            str: 每行一个「- 工具名: 描述」。
        """
        return "\n".join(f"- {t.name}: {t.description}" for t in self._tools.values())
