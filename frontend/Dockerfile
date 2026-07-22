# ============================================================
# 前端镜像 - AI 知识库产品
# 多阶段构建：Node 构建静态资源 -> Nginx 提供服务并反向代理 API
# ============================================================

# ---------- 阶段一：构建 ----------
FROM node:20-alpine AS builder
WORKDIR /app

# 先复制依赖清单以利用缓存
COPY package.json package-lock.json* ./
# 无 lock 文件时回退到普通 install
RUN npm ci || npm install

# 复制源码并构建生产包（输出到 dist/）
COPY . .
RUN npm run build

# ---------- 阶段二：运行 ----------
FROM nginx:1.27-alpine

# 使用自定义 Nginx 配置（含 /api 反向代理与前端 history 路由回退）
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 拷贝构建产物到 Nginx 静态目录
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
