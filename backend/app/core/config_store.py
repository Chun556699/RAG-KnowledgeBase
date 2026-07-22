"""
运行时配置存储（Runtime Config Store）。

在只读的 .env 基线配置（Settings）之上，叠加一层可在运行时通过 Web 界面
修改并持久化的「覆盖配置」——LLM 密钥/端点/模型、嵌入、重排序。用于支撑
「在网页端完成大模型 Key 的接入与切换」，并对敏感字段做脱敏返回保护。

设计要点：
- **单一事实来源**：LLM 工厂 / 嵌入构建 / 重排序构建统一从本存储读取「有效配置」；
- **持久化**：覆盖项写入 ``data/runtime_config.json``（.env 不被修改，作为初始默认）；
- **脱敏保护**：对外快照仅返回掩码后的密钥（如 ``sk-a****wxyz``），真实密钥永不出网页；
- **线程安全**：读写以 RLock 保护，setter 立即落盘并递增 revision 以便上层感知变更。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional

from app.config import Settings, get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

#: 支持在网页端配置的 LLM 提供商及其友好描述（与工厂保持一致）。
_LLM_PROVIDERS: Dict[str, str] = {
    "deepseek": "DeepSeek 深度求索（OpenAI 兼容）",
    "mimo": "小米 MiMo（OpenAI 兼容）",
}


def mask_secret(secret: str) -> str:
    """
    对密钥做脱敏，仅保留首尾少量字符，中间以 ``*`` 遮蔽。

    Args:
        secret: 原始密钥（可能为空）。

    Returns:
        str: 脱敏后的字符串；空密钥返回空串，过短密钥整体遮蔽。
    """
    if not secret:
        return ""
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}****{secret[-4:]}"


def is_masked(value: Optional[str]) -> bool:
    """判断一个值是否为「掩码占位」（含 ``*``），用于避免用回填的掩码覆盖真实密钥。"""
    return bool(value) and "*" in value


class RuntimeConfigStore:
    """运行时配置存储：在 .env 基线之上叠加可持久化的覆盖配置。"""

    def __init__(self, settings: Settings, path: Optional[str] = None) -> None:
        """
        Args:
            settings: 全局只读配置（提供各项默认值）。
            path: 覆盖配置持久化文件路径，缺省取 settings.runtime_config_path。
        """
        self._settings = settings
        self._path = Path(path or settings.runtime_config_path)
        self._lock = threading.RLock()
        self._revision = 0

        # 覆盖层：仅保存被用户显式修改过的字段，未出现的字段回落到 .env 默认。
        self._llm: Dict[str, Dict[str, str]] = {}
        self._embedding: Dict[str, object] = {}
        self._reranker: Dict[str, object] = {}
        self._default_provider: Optional[str] = None

        self._load()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def _load(self) -> None:
        """从磁盘加载覆盖配置（文件不存在或损坏时视为空覆盖，回落到 .env）。"""
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self._llm = data.get("llm", {}) or {}
            self._embedding = data.get("embedding", {}) or {}
            self._reranker = data.get("reranker", {}) or {}
            self._default_provider = data.get("default_provider") or None
            logger.info("运行时配置已加载：%s", self._path)
        except Exception as exc:  # noqa: BLE001  损坏时不阻塞启动
            logger.error("加载运行时配置失败，将回落到 .env 默认: %s", exc)
            self._llm, self._embedding, self._reranker = {}, {}, {}
            self._default_provider = None

    def _persist(self) -> None:
        """将覆盖配置原子落盘（先写临时文件再替换）。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "llm": self._llm,
                    "embedding": self._embedding,
                    "reranker": self._reranker,
                    "default_provider": self._default_provider,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        tmp.replace(self._path)
        self._revision += 1

    @property
    def revision(self) -> int:
        """当前配置版本号（每次成功写入自增），供上层判断是否需重建对象。"""
        return self._revision

    # ------------------------------------------------------------------
    # LLM 提供商
    # ------------------------------------------------------------------
    def llm_providers(self) -> List[str]:
        """返回支持配置的 LLM 提供商标识列表。"""
        return list(_LLM_PROVIDERS.keys())

    def effective_llm(self, provider: str) -> Dict[str, str]:
        """
        获取某 LLM 提供商的「有效配置」（覆盖层优先，回落到 .env 默认）。

        Args:
            provider: 提供商标识（deepseek / mimo）。

        Returns:
            Dict[str, str]: 含 api_key / base_url / model / description。
        """
        provider = provider.lower().strip()
        s = self._settings
        defaults = {
            "deepseek": {
                "api_key": s.deepseek_api_key,
                "base_url": s.deepseek_base_url,
                "model": s.deepseek_model,
            },
            "mimo": {
                "api_key": s.mimo_api_key,
                "base_url": s.mimo_base_url,
                "model": s.mimo_model,
            },
        }.get(provider, {"api_key": "", "base_url": "", "model": ""})

        with self._lock:
            override = self._llm.get(provider, {})
        merged = dict(defaults)
        for key in ("api_key", "base_url", "model"):
            val = override.get(key)
            if val:  # 仅当覆盖值非空时生效
                merged[key] = val
        merged["description"] = _LLM_PROVIDERS.get(provider, provider)
        return merged

    def set_llm(
        self,
        provider: str,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """
        更新某提供商的覆盖配置（None 表示保持不变；掩码值会被忽略以防覆盖真实密钥）。

        Raises:
            ValueError: provider 不受支持时。
        """
        provider = provider.lower().strip()
        if provider not in _LLM_PROVIDERS:
            raise ValueError(f"不支持的 LLM 提供商: {provider}")
        with self._lock:
            cur = dict(self._llm.get(provider, {}))
            if api_key is not None and not is_masked(api_key):
                cur["api_key"] = api_key.strip()
            if base_url is not None:
                cur["base_url"] = base_url.strip()
            if model is not None:
                cur["model"] = model.strip()
            self._llm[provider] = cur
            self._persist()

    def default_provider(self) -> str:
        """有效默认提供商（覆盖优先，回落到 .env）。"""
        with self._lock:
            return self._default_provider or self._settings.default_llm_provider

    def set_default_provider(self, provider: str) -> None:
        """设置默认提供商。"""
        provider = provider.lower().strip()
        if provider not in _LLM_PROVIDERS:
            raise ValueError(f"不支持的 LLM 提供商: {provider}")
        with self._lock:
            self._default_provider = provider
            self._persist()

    def llm_configs(self) -> Dict[str, Dict[str, str]]:
        """返回全部提供商的有效配置字典（供工厂构建实例）。"""
        return {p: self.effective_llm(p) for p in self.llm_providers()}

    # ------------------------------------------------------------------
    # 嵌入
    # ------------------------------------------------------------------
    def effective_embedding(self) -> Dict[str, object]:
        """获取嵌入的有效配置（覆盖优先，回落到 .env）。"""
        s = self._settings
        with self._lock:
            o = dict(self._embedding)
        return {
            "provider": o.get("provider") or s.embedding_provider,
            "api_key": o.get("api_key") or s.embedding_api_key,
            "base_url": o.get("base_url") or s.embedding_base_url,
            "model": o.get("model") or s.embedding_model,
            "dimension": int(o.get("dimension") or s.embedding_dimension),
        }

    def set_embedding(
        self,
        *,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        dimension: Optional[int] = None,
    ) -> None:
        """更新嵌入覆盖配置（None 保持不变，掩码密钥忽略）。"""
        with self._lock:
            cur = dict(self._embedding)
            if provider is not None:
                cur["provider"] = provider.strip().lower()
            if api_key is not None and not is_masked(api_key):
                cur["api_key"] = api_key.strip()
            if base_url is not None:
                cur["base_url"] = base_url.strip()
            if model is not None:
                cur["model"] = model.strip()
            if dimension is not None:
                cur["dimension"] = int(dimension)
            self._embedding = cur
            self._persist()

    # ------------------------------------------------------------------
    # 重排序
    # ------------------------------------------------------------------
    def effective_reranker(self) -> Dict[str, object]:
        """获取重排序的有效配置（覆盖优先，回落到 .env）。"""
        s = self._settings
        with self._lock:
            o = dict(self._reranker)
        return {
            "enabled": bool(o["enabled"]) if "enabled" in o else s.rerank_enabled,
            "api_key": o.get("api_key") or s.rerank_api_key,
            "base_url": o.get("base_url") or s.rerank_base_url,
            "model": o.get("model") or s.rerank_model,
            "top_n": int(o.get("top_n") or s.retrieval_top_k),
            "candidate_k": int(o.get("candidate_k") or s.rerank_candidate_k),
            "timeout": float(o.get("timeout") or s.rerank_timeout),
        }

    def set_reranker(
        self,
        *,
        enabled: Optional[bool] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        top_n: Optional[int] = None,
        candidate_k: Optional[int] = None,
    ) -> None:
        """更新重排序覆盖配置（None 保持不变，掩码密钥忽略）。"""
        with self._lock:
            cur = dict(self._reranker)
            if enabled is not None:
                cur["enabled"] = bool(enabled)
            if api_key is not None and not is_masked(api_key):
                cur["api_key"] = api_key.strip()
            if base_url is not None:
                cur["base_url"] = base_url.strip()
            if model is not None:
                cur["model"] = model.strip()
            if top_n is not None:
                cur["top_n"] = int(top_n)
            if candidate_k is not None:
                cur["candidate_k"] = int(candidate_k)
            self._reranker = cur
            self._persist()

    # ------------------------------------------------------------------
    # 脱敏快照
    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, object]:
        """
        构造对外脱敏快照（密钥仅返回掩码），供 Web 设置界面展示。

        Returns:
            Dict[str, object]: 含 default_provider / llm / embedding / reranker。
        """
        llm_list = []
        for p in self.llm_providers():
            cfg = self.effective_llm(p)
            key = str(cfg.get("api_key") or "")
            llm_list.append(
                {
                    "provider": p,
                    "model": cfg["model"],
                    "base_url": cfg["base_url"],
                    "api_key_masked": mask_secret(key),
                    "has_key": bool(key),
                    "available": bool(key),
                    "description": cfg["description"],
                }
            )
        emb = self.effective_embedding()
        emb_key = str(emb.get("api_key") or "")
        rr = self.effective_reranker()
        rr_key = str(rr.get("api_key") or "")
        return {
            "default_provider": self.default_provider(),
            "llm": llm_list,
            "embedding": {
                "provider": emb["provider"],
                "model": emb["model"],
                "base_url": emb["base_url"],
                "dimension": emb["dimension"],
                "api_key_masked": mask_secret(emb_key),
                "has_key": bool(emb_key),
            },
            "reranker": {
                "enabled": rr["enabled"],
                "model": rr["model"],
                "base_url": rr["base_url"],
                "top_n": rr["top_n"],
                "candidate_k": rr["candidate_k"],
                "api_key_masked": mask_secret(rr_key),
                "has_key": bool(rr_key),
            },
        }


# 全局单例（在容器初始化时与 .env 一同装配）
_store: Optional[RuntimeConfigStore] = None


def get_config_store() -> RuntimeConfigStore:
    """获取全局运行时配置存储单例（缺省从 get_settings 装配）。"""
    global _store
    if _store is None:
        _store = RuntimeConfigStore(get_settings())
    return _store


def reset_config_store() -> None:
    """重置全局单例（主要用于测试隔离）。"""
    global _store
    _store = None
