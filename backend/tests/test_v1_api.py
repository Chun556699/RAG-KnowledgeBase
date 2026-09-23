"""
公开问答 API（/api/v1）集成测试。

验证：API Key 鉴权、scope 检查、密钥绑定知识库的租户隔离、
ask/ask_stream 响应结构、widget.js 与 embed config 可达性、指标端点。

测试内不调用真实 LLM——chat 服务方法以桩替换。
"""

from __future__ import annotations

import json
import os
import tempfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """独立数据目录的完整应用 TestClient（走真实 lifespan）。"""
    tmp = tempfile.mkdtemp(prefix="ragkb_test_")
    env = {
        "APP_ENV": "test",
        "DATA_DIR": tmp,
        "VECTOR_STORE_PATH": os.path.join(tmp, "vectorstore.json"),
        "MEMORY_DB_PATH": os.path.join(tmp, "memory.db"),
        "PLATFORM_DB_PATH": os.path.join(tmp, "platform.db"),
        "UPLOAD_DIR": os.path.join(tmp, "uploads"),
        "CLARIFY_ENABLED": "false",
    }
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        from app.config import get_settings

        get_settings.cache_clear()
        from app.main import app
        from app.services.container import get_container

        with TestClient(app) as c:
            # 桩替换 chat 服务：不触达真实 LLM
            container = get_container()
            kb_capture = {}

            async def _fake_chat(**kwargs):
                kb_capture["kb_id"] = kwargs.get("kb_id")
                ctx = SimpleNamespace(
                    session_id="sess_test",
                    sources=[],
                )
                return "这是回答", ctx

            async def _fake_chat_stream(**kwargs):
                kb_capture["kb_id"] = kwargs.get("kb_id")

                async def gen():
                    yield "流式"
                    yield "回答"

                return gen(), SimpleNamespace(session_id="sess_test", sources=[])

            container.chat.chat = _fake_chat            # type: ignore[method-assign]
            container.chat.chat_stream = _fake_chat_stream  # type: ignore[method-assign]
            c.kb_capture = kb_capture  # type: ignore[attr-defined]
            yield c
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        from app.config import get_settings

        get_settings.cache_clear()


def _create_key(client: TestClient, scopes=None, kb_id=None) -> str:
    payload = {"name": "test", "scopes": scopes or ["ask"]}
    if kb_id:
        payload["kb_id"] = kb_id
    r = client.post("/api/keys", json=payload)
    assert r.status_code == 200
    return r.json()["raw_key"]


class TestAuth:
    def test_no_key_returns_401(self, client):
        r = client.post("/api/v1/ask", json={"question": "q"})
        assert r.status_code == 401

    def test_bad_key_returns_401(self, client):
        r = client.post(
            "/api/v1/ask", json={"question": "q"}, headers={"X-API-Key": "ak_live_bad"}
        )
        assert r.status_code == 401

    def test_revoked_key_returns_401(self, client):
        raw = _create_key(client)
        keys = client.get("/api/keys").json()
        client.delete(f"/api/keys/{keys[0]['key_id']}")
        r = client.post("/api/v1/ask", json={"question": "q"}, headers={"X-API-Key": raw})
        assert r.status_code == 401

    def test_key_without_ask_scope_denied(self, client):
        raw = _create_key(client, scopes=["ingest"])
        r = client.post("/api/v1/ask", json={"question": "q"}, headers={"X-API-Key": raw})
        assert r.status_code == 401


class TestAsk:
    def test_ask_returns_answer(self, client):
        raw = _create_key(client)
        r = client.post(
            "/api/v1/ask", json={"question": "你好"}, headers={"X-API-Key": raw}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["answer"] == "这是回答"
        assert body["session_id"] == "sess_test"
        assert body["kb_id"] == "default"
        assert client.kb_capture["kb_id"] == "default"

    def test_bound_key_forces_kb_isolation(self, client):
        """绑定知识库的密钥，即使请求指定其他库也只查绑定库。"""
        kb = client.post("/api/kbs", json={"name": "私有库"}).json()
        raw = _create_key(client, kb_id=kb["kb_id"])
        r = client.post(
            "/api/v1/ask",
            json={"question": "q", "kb": "default"},
            headers={"X-API-Key": raw},
        )
        assert r.status_code == 200
        assert r.json()["kb_id"] == kb["kb_id"]
        assert client.kb_capture["kb_id"] == kb["kb_id"]

    def test_ask_stream_sse(self, client):
        raw = _create_key(client)
        r = client.post(
            "/api/v1/ask/stream",
            json={"question": "q"},
            headers={"X-API-Key": raw},
        )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        events = [
            json.loads(line[5:].strip())
            for line in r.text.splitlines()
            if line.startswith("data:")
        ]
        types = [e["type"] for e in events]
        assert types[0] == "meta" and types[-1] == "done"
        deltas = "".join(e["content"] for e in events if e["type"] == "delta")
        assert deltas == "流式回答"


class TestKbAndKeysApi:
    def test_create_and_list_kb(self, client):
        r = client.post("/api/kbs", json={"name": "产品库", "description": "d"})
        assert r.status_code == 200
        kbs = client.get("/api/kbs").json()
        assert len(kbs) == 2  # default + 新建
        assert any(k["name"] == "产品库" for k in kbs)

    def test_invalid_scope_rejected(self, client):
        r = client.post("/api/keys", json={"name": "x", "scopes": ["godmode"]})
        assert r.status_code == 422

    def test_key_list_is_masked(self, client):
        raw = _create_key(client)
        keys = client.get("/api/keys").json()
        assert keys and all("…" in k["key_prefix"] for k in keys)
        assert raw not in json.dumps(keys)


class TestEmbedAndMetrics:
    def test_widget_js_served(self, client):
        r = client.get("/embed/widget.js")
        assert r.status_code == 200
        assert "javascript" in r.headers["content-type"]
        assert "data-key" in r.text

    def test_embed_demo_served(self, client):
        r = client.get("/embed/demo")
        assert r.status_code == 200
        assert "widget.js" in r.text

    def test_embed_config(self, client):
        r = client.get("/embed/config")
        assert r.status_code == 200
        assert r.json()["public_api_enabled"] is True

    def test_metrics_endpoint(self, client):
        r = client.get("/api/metrics")
        assert r.status_code == 200
        assert "requests_total" in r.json()

    def test_public_cors_open(self, client):
        """公共面应回 Access-Control-Allow-Origin: *（可嵌入任意站点）。"""
        r = client.get(
            "/embed/config", headers={"Origin": "https://third-party.example"}
        )
        assert r.headers.get("access-control-allow-origin") == "*"

    def test_admin_cors_not_open(self, client):
        """管理面不允许任意源。"""
        r = client.get(
            "/api/metrics", headers={"Origin": "https://evil.example"}
        )
        assert r.headers.get("access-control-allow-origin") != "*"

    def test_request_id_echoed(self, client):
        r = client.get("/api/health", headers={"X-Request-ID": "req_test_123"})
        assert r.headers.get("x-request-id") == "req_test_123"
