# syntax=docker/dockerfile:1
# ============================================================================
# 任务12 · 前端镜像（Vite 构建产物 + Nginx 托管并反代 /api）
#
# 为什么和后端分成两个镜像，而不是在 API 镜像里塞一个 Node 阶段：
#   ① 关注点分离：前端只依赖 Node 工具链，后端只依赖 Python，互不拖累构建时间；
#   ② 体积：后端镜像已经约 2.2GB（torch + 模型 + 数据），前端镜像是几十 MB，
#      合在一起会让「改一行 CSS」也要重传整个后端镜像；
#   ③ 职责清晰：对外唯一入口是 Nginx，后端容器完全不暴露端口。
#
# 构建（必须在仓库根目录执行）：
#   docker build -f docker/frontend.Dockerfile -t zq-web:1.0.0 .
# ============================================================================

# ---------------------------------------------------------------- 阶段 1：构建
FROM node:22-alpine AS builder

WORKDIR /web

# 依赖清单单独一层：只要 package.json / package-lock.json 没变就复用缓存
COPY web/package.json web/package-lock.json ./

# 用与本地一致的国内镜像源，避免容器里 npm 拉包超时
RUN npm ci --registry=https://registry.npmmirror.com

# 源码 + 构建（产物：/web/dist）
COPY web/ ./
RUN npm run build


# ---------------------------------------------------------------- 阶段 2：运行时
FROM nginx:1.27-alpine AS runtime

ENV TZ=Asia/Shanghai

# 删掉官方默认站点配置（它占着 listen 80 default_server），换成我们的
RUN rm -f /etc/nginx/conf.d/default.conf
COPY docker/nginx.conf /etc/nginx/conf.d/zq.conf

# 只把构建产物搬进来，源码不进运行镜像
COPY --from=builder /web/dist /usr/share/nginx/html

# nginx:alpine 自带 wget（busybox），用它做就绪探针，不额外装 curl
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ > /dev/null || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
