#!/usr/bin/env bash
# ============================================================================
# 任务12 · 一键部署脚本（在云服务器上执行）
#
# 作用：把「装 Docker → 取代码 → 写配置 → 构建 → 启动 → 验证 → 打印在线地址」
#       整条链路做成一条命令，避免手工漏步骤。
#
# 用法（在服务器上，仓库根目录）：
#     bash scripts/deploy.sh
#
# 可选环境变量：
#     DEEPSEEK_API_KEY=sk-xxx   bash scripts/deploy.sh    # 非交互式注入密钥
#     PORT=8080                 bash scripts/deploy.sh    # 改对外端口（默认 80）
#     SKIP_INSTALL=1            bash scripts/deploy.sh    # 跳过 Docker 安装步骤
#
# 前置条件：
#     · Ubuntu 22.04+ / Debian 12+（其它发行版需自行调整第 1 步）
#     · 云控制台安全组已放行 22 与对外端口（默认 80）
#     · 内存 ≥ 4GB（实测后端常驻约 0.9GB，2GB 机器会 OOM）
# ============================================================================
set -euo pipefail

PORT="${PORT:-80}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m[x] %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 0. 环境自检
say "0/6 环境自检"
[ -f docker/Dockerfile ] || die "请在仓库根目录执行本脚本（找不到 docker/Dockerfile）"
[ -f docker/docker-compose.yml ] || die "找不到 docker/docker-compose.yml"

MEM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo)
DISK_GB=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
echo "  内存 ${MEM_MB} MB ｜ 根分区可用 ${DISK_GB} GB"
[ "$MEM_MB" -ge 3500 ] || warn "内存不足 4GB：后端实测常驻约 0.9GB，构建 torch 时还会更高，可能 OOM"
[ "$DISK_GB" -ge 20 ] || die "磁盘不足 20GB（镜像约 2.2GB + 构建缓存）"

if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi

# ---------------------------------------------------------------- 1. 装 Docker
if [ "${SKIP_INSTALL:-0}" != "1" ]; then
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    say "1/6 Docker 已安装：$(docker --version)"
  else
    say "1/6 安装 Docker Engine + compose 插件"
    export DEBIAN_FRONTEND=noninteractive
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq ca-certificates curl gnupg
    $SUDO install -m 0755 -d /etc/apt/keyrings
    if [ ! -f /etc/apt/keyrings/docker.asc ]; then
      curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg \
        | $SUDO tee /etc/apt/keyrings/docker.asc > /dev/null
      $SUDO chmod a+r /etc/apt/keyrings/docker.asc
    fi
    CODENAME=$(. /etc/os-release && echo "${VERSION_CODENAME:-jammy}")
    ARCH=$(dpkg --print-architecture)
    # 用阿里云镜像源：国内服务器直连 download.docker.com 经常超时
    echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] https://mirrors.aliyun.com/docker-ce/linux/ubuntu ${CODENAME} stable" \
      | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    $SUDO systemctl enable --now docker
    docker --version && docker compose version
  fi
else
  say "1/6 跳过 Docker 安装（SKIP_INSTALL=1）"
fi

# 非 root 用户需要能直接调 docker（否则下面每句都要 sudo）
if ! docker info >/dev/null 2>&1; then
  if [ -n "$SUDO" ]; then
    warn "当前用户无 docker 权限，尝试加入 docker 组"
    $SUDO usermod -aG docker "$USER" || true
    SUDO="sudo"          # 本次会话仍用 sudo，重新登录后即可免 sudo
    DOCKER="$SUDO docker"
    COMPOSE="$SUDO docker compose"
  else
    DOCKER="docker"; COMPOSE="docker compose"
  fi
else
  DOCKER="docker"; COMPOSE="docker compose"
fi

# ---------------------------------------------------------------- 2. 密钥
say "2/6 检查大模型密钥（.env）"
if [ ! -f .env ]; then
  if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
    cp .env.example .env
    # 用 | 作分隔符，避免 key 里出现 / 时出错
    sed -i "s|^DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}|" .env
    echo "  已根据环境变量写入 .env"
  else
    cp .env.example .env
    warn "已从模板生成 .env，但里面还是占位 key —— 请编辑 .env 填入真实 DEEPSEEK_API_KEY"
    warn "不填也能跑：岗位浏览 / 匹配 / 评分 / 聚类都正常，只有智能问答会报缺少密钥"
  fi
else
  echo "  .env 已存在，沿用"
fi
grep -q '^DEEPSEEK_API_KEY=sk-' .env || warn ".env 里的 DEEPSEEK_API_KEY 看起来还是占位值"
echo "  当前模型：$(grep '^DEEPSEEK_MODEL=' .env | cut -d= -f2)"

# ---------------------------------------------------------------- 3. 构建
say "3/6 构建镜像（首次约 5~15 分钟，取决于网速；torch CPU 轮子约 200MB）"
# 对外端口通过环境变量传进 compose（compose 文件里没有写死 80）
export ZQ_PORT="$PORT"
# 用 docker-compose.override 之外的方式传端口：这里直接改一份临时环境变量文件最直观
$COMPOSE -f docker/docker-compose.yml build

# ---------------------------------------------------------------- 4. 启动
say "4/6 启动容器（web + api）"
# compose 里写的是 "80:80"，这里若指定了别的端口就用 override 文件覆盖
if [ "$PORT" != "80" ]; then
  cat > docker/docker-compose.override.yml <<EOF
# 由 scripts/deploy.sh 自动生成：把对外端口从 80 改成 ${PORT}
services:
  web:
    ports:
      - "${PORT}:80"
EOF
  warn "已生成 docker/docker-compose.override.yml，对外端口改为 ${PORT}"
  $COMPOSE -f docker/docker-compose.yml -f docker/docker-compose.override.yml up -d
else
  $COMPOSE -f docker/docker-compose.yml up -d
fi

# ---------------------------------------------------------------- 5. 验证
say "5/6 等待后端就绪并自检接口"
echo "  （后端启动要预加载 8,836 岗位库 + 匹配器 + RAG 检索器，约 10~40 秒）"
OK=0
for i in $(seq 1 60); do
  if curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/api/health" > /tmp/zq_health.json 2>/dev/null; then
    OK=1; break
  fi
  sleep 3
done
if [ "$OK" != "1" ]; then
  warn "60 次重试（约 3 分钟）后健康检查仍未通过，下面是诊断信息："
  $COMPOSE -f docker/docker-compose.yml ps || true
  $COMPOSE -f docker/docker-compose.yml logs --tail 80 api || true
  die "部署失败，请把上面的日志发给开发者"
fi

echo "  /api/health 200 OK"
python3 - <<'PY' 2>/dev/null || cat /tmp/zq_health.json
import json
d = json.load(open("/tmp/zq_health.json", encoding="utf-8"))
warm = d.get("启动预加载耗时秒", {})
print("    预加载耗时：", ", ".join("%s %ss" % (k, v) for k, v in warm.items()) or "（未返回）")
PY

# 逐个打一遍关键接口，确认不是只有健康检查能通
check() {
  local name="$1" url="$2" method="${3:-GET}" data="${4:-}"
  local code
  if [ "$method" = "POST" ]; then
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 120 \
      -X POST "$url" -H 'Content-Type: application/json' -d "$data" || echo 000)
  else
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 "$url" || echo 000)
  fi
  if [ "$code" = "200" ]; then printf '    [OK]   %-22s %s\n' "$name" "$code"
  else printf '    [FAIL] %-22s %s\n' "$name" "$code"; FAILED=1; fi
}
FAILED=0
B="http://127.0.0.1:${PORT}"
check "首页聚合"       "$B/api/home"
check "岗位列表"       "$B/api/jobs?size=5"
check "公司列表"       "$B/api/companies?size=5"
check "聚类列表"       "$B/api/cluster/list"
check "岗位详情"       "$B/api/jobs/J0020"
check "简历解析"       "$B/api/resume/parse_text" POST \
      '{"resume_text":"张三 本科 3年经验 熟悉 Python Java MySQL，期望厦门，薪资 12k"}'
check "人岗匹配"       "$B/api/match" POST \
      '{"resume_text":"张三 本科 3年经验 熟悉 Python Java MySQL，期望厦门，薪资 12k","top_n":5}'
check "双口径评分"     "$B/api/score" POST \
      '{"resume_text":"张三 本科 3年经验 熟悉 Python Java MySQL，期望厦门，薪资 12k","job_id":"J0020"}'
check "前端页面"       "$B/"

if [ "$FAILED" = "1" ]; then
  $COMPOSE -f docker/docker-compose.yml logs --tail 60 api || true
  die "有接口自检未通过（见上表）"
fi

# ---------------------------------------------------------------- 6. 交付地址
say "6/6 部署完成"
$COMPOSE -f docker/docker-compose.yml ps

# 取公网 IP：优先用云厂商元数据，失败则用出口 IP 反查
PUBLIC_IP=$(curl -fsS --max-time 5 http://100.100.100.200/latest/meta-data/eipv4 2>/dev/null \
  || curl -fsS --max-time 8 https://api.ipify.org 2>/dev/null || echo "<服务器公网IP>")

echo
echo "  在线演示地址：  http://${PUBLIC_IP}$([ "$PORT" = "80" ] && echo "" || echo ":${PORT}")/"
echo "  接口文档：      http://${PUBLIC_IP}$([ "$PORT" = "80" ] && echo "" || echo ":${PORT}")/docs"
echo "  健康检查：      http://${PUBLIC_IP}$([ "$PORT" = "80" ] && echo "" || echo ":${PORT}")/api/health"
echo
echo "  常用命令（在仓库根目录）："
echo "    docker compose -f docker/docker-compose.yml ps          # 状态"
echo "    docker compose -f docker/docker-compose.yml logs -f api # 后端日志"
echo "    docker compose -f docker/docker-compose.yml restart api # 重启后端"
echo "    docker compose -f docker/docker-compose.yml down        # 停止（保留数据）"
echo
echo "  若公网打不开，99% 是云控制台安全组没放行 ${PORT} 端口。"
