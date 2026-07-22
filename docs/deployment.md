# 部署指南

本文档介绍在**本地开发环境**与**云服务器**上部署 AI 知识库平台的方法。

---

## 1. 环境要求

| 场景 | 依赖 |
| --- | --- |
| Docker 部署（推荐） | Docker 20.10+ 与 Docker Compose v2 |
| 本地开发 | Python 3.11+、Node.js 18+ |

---

## 2. Docker 一键部署（推荐）

### 2.1 启动

在项目根目录执行：

```bash
docker compose up -d --build
```

Compose 会构建并启动两个服务：

- **backend**（`aikb-backend`）：FastAPI，暴露 `8000` 端口，数据持久化到命名卷 `backend_data`（挂载到容器 `/app/data`）。
- **frontend**（`aikb-frontend`）：Nginx 托管前端静态资源并将 `/api` 反向代理到 backend，暴露 `80` 端口。前端在 backend 健康后才启动（`depends_on: condition: service_healthy`）。

### 2.2 访问

- 前端：<http://localhost>
- 后端 API 文档：<http://localhost:8000/docs>

### 2.3 常用命令

```bash
docker compose ps              # 查看状态
docker compose logs -f backend # 查看后端日志
docker compose down            # 停止并移除容器（数据卷保留）
docker compose down -v         # 连同数据卷一并删除（清空数据）
```

### 2.4 配置模型密钥

方式一：直接编辑 `docker-compose.yml` 中 `backend.environment`，取消注释并填入密钥：

```yaml
environment:
  DEFAULT_LLM_PROVIDER: deepseek
  DEEPSEEK_API_KEY: sk-xxxxxxxx
  # 或小米 MiMo
  # MIMO_API_KEY: xxxxxxxx
```

方式二：在项目根目录创建 `.env` 文件（Compose 会自动读取 `${VAR}` 引用）：

```ini
DEFAULT_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxxxxxx
```

修改后重建后端：`docker compose up -d --build backend`。

---

## 3. 本地开发部署

### 3.1 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
copy .env.example .env            # Windows；macOS/Linux 用 cp
uvicorn app.main:app --reload --port 8000
```

数据默认写入 `backend/data/`（本地向量库 vectorstore.json、SQLite、上传文件）。首次启动会自动创建目录。

### 3.2 前端

```bash
cd frontend
npm install
npm run dev        # 开发服务器 http://localhost:5173
```

Vite 通过 `vite.config.ts` 中的代理把 `/api` 转发到 `http://localhost:8000`。若后端不在默认地址，可设置环境变量 `VITE_API_TARGET`。

### 3.3 前端生产构建

```bash
cd frontend
npm run build      # 产物输出到 dist/
npm run preview    # 本地预览生产包
```

---

## 4. 云服务器部署

以一台安装了 Docker 的 Linux 云主机为例：

```bash
# 1. 拉取代码
git clone <your-repo-url> && cd our-project

# 2.（可选）配置模型密钥（对话/Agent 所需；嵌入与检索离线可用）
echo "DEFAULT_LLM_PROVIDER=deepseek" >> .env
echo "DEEPSEEK_API_KEY=sk-xxxxxxxx" >> .env

# 3. 启动
docker compose up -d --build

# 4. 开放安全组/防火墙端口 80（前端）和 8000（如需直接访问 API 文档）
```

### 4.1 建议的生产加固

- **HTTPS**：在 `frontend` 容器前再挂一层反向代理（如 Caddy / Traefik / 云厂商 LB）终止 TLS，或在 `nginx.conf` 中配置证书。
- **CORS**：生产下前端与 API 同源（都经 Nginx），默认无需放宽；如分域部署，设置后端 `CORS_ORIGINS` 环境变量为前端域名。
- **数据备份**：定期备份 `backend_data` 卷（含向量库与记忆库）。
- **资源限制**：在 compose 中为服务添加 `deploy.resources.limits` 约束内存/CPU。
- **仅内网暴露 API**：如不需外部直连后端，可移除 `backend` 的 `ports` 映射，仅通过前端 Nginx 访问。

---

## 5. 关键环境变量

完整清单见 `backend/.env.example`，常用项：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DEFAULT_LLM_PROVIDER` | `deepseek` | 默认 LLM 提供商：deepseek/mimo |
| `EMBEDDING_PROVIDER` | `mock` | 嵌入提供商：固定 mock（离线） |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek 密钥 |
| `MIMO_API_KEY` | 空 | 小米 MiMo 密钥 |
| `VECTOR_STORE_PATH` | `./data/vectorstore.json` | 本地向量库持久化文件 |
| `MEMORY_DB_PATH` | `./data/memory.db` | 记忆库路径 |
| `UPLOAD_DIR` | `./data/uploads` | 上传文件目录（含文档元数据） |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `500` / `50` | 分块参数 |
| `RETRIEVAL_TOP_K` | `4` | 默认检索片段数 |
| `MEMORY_TTL_DAYS` | `30` | 长期记忆默认存活天数 |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | 允许跨域来源（逗号分隔） |

---

## 6. 故障排查

| 现象 | 排查 |
| --- | --- |
| 前端显示「服务离线」 | 后端未启动或健康检查失败；`docker compose logs -f backend` |
| 流式对话无增量输出 | 反向代理未关闭缓冲；确认 `nginx.conf` 的 `proxy_buffering off` |
| 上传报「不支持的文件格式」 | 仅支持 .pdf/.docx/.txt/.md/.markdown |
| 对话报密钥错误或不可用 | 检查 `.env` 中 `DEEPSEEK_API_KEY` / `MIMO_API_KEY` 是否填写并已重启后端 |
