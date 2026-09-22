---
name: testing-ragkb
description: How to run and E2E-test the RAG-KnowledgeBase app (backend uvicorn + frontend vite) on Windows
---

# Testing RAG-KnowledgeBase

## Start the app
- Backend: `cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000` (venv lives at `backend/.venv`; call python via `.venv/Scripts/python`, not `python`). Health: `GET /api/health`.
- Frontend: `cd frontend && npm run dev` → http://localhost:5173. Vite proxies `/api` and `/embed` to :8000.
- `/api/v1/*` IS proxied (under `/api`); `/embed/demo` and `/embed/widget.js` work on :5173 via the `/embed` proxy too — testing widget flows on :8000 directly is equally fine.

## Keys / auth
- No `.env` needed: `admin_api_key` empty → all `/api/*` admin endpoints (kbs, keys, metrics) are OPEN.
- `POST /api/keys {"name","scopes":["ask"],"kb_id"?}` → `raw_key` (`ak_live_<40hex>`) shown once; `key_id` for revoke via `DELETE /api/keys/{key_id}`.
- `POST /api/kbs {"name","description"}` — auto-generates `kb_<hex>`; schema ignores a client-supplied `kb_id`.
- Public ask auth: `X-API-Key: <raw>` or `Authorization: Bearer <raw>`; needs `ask` scope (ingest-only → 401).
- LLM keys (DEEPSEEK_API_KEY / MIMO_API_KEY) absent → chat/ask return 502 `ProviderError` JSON — expected, verify graceful error surfaces in UI.
- Embedder is offline MockEmbedder — upload/search/retrieval fully work with zero keys.

## Curl on Windows Git Bash
- Chinese text in `-d` bodies gets mangled by cp1252 console (e.g. 租户B → `??B`). Write JSON with ASCII or post via the UI / python. Responses themselves are fine UTF-8.
- Rate limit (default 60/min per key on /api/v1) needs a FAST burst — sequential curl loops refill the token bucket between requests and won't trip it. Use `seq 1 30 | xargs -P 20 ...` after warming the bucket, expect 429.

## UI specifics
- Theme toggle is a moon/sun icon in the sidebar FOOTER — the nav list may push it below the fold at 768px; zoom out (ctrl+-) to reach it. Persists in localStorage `ragkb_theme`.
- kb selector in ChatPanel only renders when >1 kb exists AND "启用知识库检索" is checked.
- Doc kb_id tag only renders for non-default kbs.
- File upload opens a native Windows dialog — type the full path into "File name" (use `cygpath -w` to resolve /tmp paths).

## Devin Secrets Needed
None for offline testing. Optional: DEEPSEEK_API_KEY or MIMO_API_KEY to test real LLM answers/markdown rendering.
