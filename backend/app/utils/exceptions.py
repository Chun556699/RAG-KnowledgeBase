"""
自定义异常模块。

定义业务领域异常，统一携带 HTTP 状态码与错误信息，
由 FastAPI 全局异常处理器转换为标准 JSON 错误响应。
"""

from typing import Any, Optional


class AppException(Exception):
    """
    应用基础异常。

    所有业务异常继承此类，便于全局异常处理器统一捕获与格式化。

    Attributes:
        message: 面向用户的错误描述。
        status_code: 对应的 HTTP 状态码。
        detail: 可选的附加调试信息。
    """

    status_code: int = 500

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        detail: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.detail = detail


class NotFoundError(AppException):
    """资源不存在（如会话、文档 ID 无效）。"""

    status_code = 404


class ValidationError(AppException):
    """请求参数校验失败（如不支持的文件类型）。"""

    status_code = 422


class ProviderError(AppException):
    """外部提供商调用失败（LLM / Embedding API 异常）。"""

    status_code = 502


class DocumentParseError(AppException):
    """文档解析失败（文件损坏或格式不支持）。"""

    status_code = 400
