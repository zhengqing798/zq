# syntax=docker/dockerfile:1
# ============================================================================
# 任务12 · 后端 API 镜像
#   FastAPI：岗位浏览 / 六维人岗匹配 / XGBoost 评分 / RAG 检索 / DeepSeek Agent 问答
#
# 分层策略（每一层只放"变化频率相近"的东西，吃满 Docker 层缓存）：
#   ① 系统层    curl + tini
#   ② 依赖层    requirements.torch.txt（CPU 专用源）+ requirements.lock.txt
#   ③ 模型层    构建期从 hf-mirror 拉 BGE 中文向量模型，运行期完全离线
#   ④ 数据层    岗位库 / 聚类标签 / 简历库 / RAG 卡片与向量 / XGBoost 模型
#   ⑤ 代码层    src/ scripts/ tests/
#   ⑥ 运行期    非 root 用户 + 可写卷 /app/var
#
# 效果：只改 src/ 里的代码时，②③④ 三层全部命中缓存，重建只要几秒，
#       不会为了改一行 Python 重新下载 2GB 依赖。
#
# 构建（必须在仓库根目录执行，上下文要包含 data/ 与 models/）：
#   docker build -f docker/Dockerfile -t zq-api:1.0.0 .
# 海外机器可加快镜像源：
#   docker build -f docker/Dockerfile -t zq-api:1.0.0 \
#     --build-arg PIP_INDEX=https://pypi.org/simple .
# 单容器试跑：
#   docker run --rm -p 8000:8000 --env-file .env zq-api:1.0.0
# 正式部署见 docker/docker-compose.yml 与 docs/部署手册.md
# ============================================================================
FROM python:3.12-slim AS runtime


# ---------------------------------------------------------------- ① 系统层
# PYTHONUNBUFFERED：日志实时刷出，docker logs 才看得到启动预加载进度
# tini：作为 PID 1 正确转发信号，docker compose stop 时不会留僵尸进程
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8 \
    TZ=Asia/Shanghai

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl tini \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app


# ---------------------------------------------------------------- ② 依赖层
# 只先复制依赖清单：只要清单不变，改代码就不会触发重装
COPY docker/requirements.torch.txt docker/requirements.lock.txt /app/docker/

# 镜像源可用构建参数覆盖，默认清华源（国内服务器快很多）
ARG PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu

# torch 必须走 CPU 专用源：PyPI 上 Linux 的 torch 是 CUDA 构建，
# 会连带拉约 2.5GB 的 nvidia-* 依赖，而本项目只用 CPU 做向量推理
RUN pip install --index-url ${TORCH_INDEX} -r /app/docker/requirements.torch.txt

# 其余依赖。
#
# ⚠️ 必须先单独用 `--no-deps` 装 xgboost，否则 pip 会把 Linux 上那个 240MB 的 CUDA 库下载下来。
#   xgboost 3.4.1 的元数据在 Linux 上**无条件**依赖 nvidia-nccl-cu13
#   （`nvidia-nccl-cu13; platform_system == "Linux"`，单个 wheel **240.7MB**），
#   而它是 CUDA 的集合通信库，本项目纯 CPU 推理完全用不到。
#   依据：xgboost 的 Python 代码根本不 import 它，同一个版本在本机 Windows 上没装它也一切正常。
#
#   用 `--no-deps` 先装好 xgboost 之后，下面那份锁定清单会认为 xgboost 已满足、
#   不再去解析它的依赖 —— 于是 nccl **连下载都不会发生**。
#   实测差别：先下载再卸载要多花 240MB 流量与好几分钟（国内拉 PyPI 大包很慢，
#   首次云上构建就卡在这一步），而 xgboost 真正需要的 numpy / scipy 本来就在锁定清单里。
RUN pip install --index-url ${PIP_INDEX} --no-deps xgboost==3.4.1

# 锁定清单（88 个包）。
# 兜底：万一将来 xgboost 的元数据变了、nccl 仍被装进来，就在同一层里卸掉它 ——
# 安装与卸载放同一层，被删的文件不会留在镜像里。
ARG STRIP_GPU_LIBS=1
RUN pip install --index-url ${PIP_INDEX} -r /app/docker/requirements.lock.txt \
 && if [ "${STRIP_GPU_LIBS}" = "1" ] && pip show nvidia-nccl-cu13 > /dev/null 2>&1; then \
        echo "[strip] 卸载 CPU 容器用不到的 nvidia-nccl-cu13（约 241MB）"; \
        pip uninstall -y nvidia-nccl-cu13; \
    fi


# ---------------------------------------------------------------- ③ 向量模型层
# 构建期把 BAAI/bge-small-zh-v1.5 下载进镜像（经 hf-mirror），运行期就不需要外网。
# 这一步不能省：容器里没有模型缓存时，第一次问答会现场去 huggingface 拉 92MB，
# 国内网络下要么超时要么失败。
ENV HF_HOME=/app/.hf_cache
ARG HF_ENDPOINT=https://hf-mirror.com
RUN HF_ENDPOINT=${HF_ENDPOINT} python -c \
    "from huggingface_hub import snapshot_download as d; print('bge-small-zh-v1.5 ->', d('BAAI/bge-small-zh-v1.5'))"

# 下载完成之后才打开离线开关：模型已在镜像里，任何情况下都不再联网
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1


# ---------------------------------------------------------------- ④ 数据与模型层
# 只读资产层：改动频率远低于代码，独立成层避免每次改代码都重传约 190MB 数据
# 注意 .dockerignore 已排除 data/app.db（含用户账号与密码哈希，绝不入镜像）
COPY data/ /app/data/
COPY models/ /app/models/


# ---------------------------------------------------------------- ⑤ 代码层
COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY tests/ /app/tests/
COPY pytest.ini /app/pytest.ini


# ---------------------------------------------------------------- ⑥ 运行期配置
# 可写目录集中到 /app/var，由 compose 挂卷持久化：
#   APP_DB       用户 / 简历 / 收藏 / 匹配历史（sqlite）
#   AGENT_CACHE  Agent 问答结果缓存（TTL 7 天）
#   AGENT_LOG    Agent 每次调用的审计日志（jsonl）
# 这样镜像里的 data/ 可以当成纯只读资产，容器重建也不丢数据
ENV APP_DB=/app/var/app.db \
    AGENT_CACHE=/app/var/agent_cache.json \
    AGENT_LOG=/app/var/agent_calls.jsonl \
    PYTHONPATH=/app

# 非 root 运行：即使容器被攻破也拿不到 root
RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p /app/var \
 && chown -R appuser:appuser /app/var
USER appuser


# ---------------------------------------------------------------- 就绪探针
# start-period 给 120s：启动时要同步预加载 8,836 岗位库 + 匹配器 + RAG 检索器
# （实测 10~20s），特征构造器在后台线程预热。给足时间避免被误判为不健康。
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]

# 单 worker 是刻意的：岗位库 / FAISS 索引 / XGBoost 模型都是进程内单例（实测常驻约 0.9GB），
# 多 worker 会让内存翻倍却收益有限 —— 本项目瓶颈是 CPU 推理，不是 IO，
# 并发由 uvicorn 的异步事件循环 + 线程池承担即可。
# --proxy-headers + --forwarded-allow-ips：让访问日志记录到 Nginx 传来的真实客户端 IP。
# 值用等号附着式写法（--forwarded-allow-ips=*）：写成空格分隔时，独立的 `*` 在部分调用链上
# 会被通配展开成目录文件名列表，uvicorn 会直接报 "unexpected extra arguments" 起不来。
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
