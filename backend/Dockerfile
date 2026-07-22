# ============================================================
# 后端镜像 - AI 知识库产品
# 基于官方 Python slim 镜像，多阶段以减小体积
# ============================================================
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 环境变量：
# - PYTHONUNBUFFERED 保证日志实时输出（不缓冲）
# - PYTHONDONTWRITEBYTECODE 不生成 .pyc 文件
# - PIP_NO_CACHE_DIR 减小镜像体积
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# 安装系统依赖（部分 Python 包需要编译工具）
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖清单并安装，充分利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据持久化目录（本地向量库、SQLite 记忆库、文档元数据）
RUN mkdir -p /app/data

# 暴露服务端口
EXPOSE 8000

# 容器健康检查：定期请求健康端点
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 启动命令（生产模式，不启用 --reload）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
