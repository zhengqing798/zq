#!/usr/bin/env bash
# ============================================================================
# 任务12 · Docker 部署验收脚本（在跑着容器的机器上执行，生成验收证据）
#
# 与 scripts/deploy.sh 的分工：
#     deploy.sh        负责"把服务跑起来"
#     verify_deploy.sh 负责"证明它真的对"    ← 本文件
#
# 用法（仓库根目录，容器已在运行）：
#     bash docker/verify_deploy.sh
#
# 验收项（逐条打印 [OK]/[FAIL]，最后给汇总）
#     1  两个镜像都构建成功，并记录体积与分层
#     2  compose 里两个容器都是 running，且 api 通过 healthcheck
#     3  镜像里没有 .env（密钥不进镜像）
#     4  镜像里没有 data/app.db（本地用户库不进镜像），且 /app/var/app.db 已在运行期生成
#     5  走 Nginx 的 80 端口打 8 个关键接口（证明反代链路通，不只是后端自测）
#     6  gzip 压缩生效（前端 JS 体积显著下降）
#     7  镜像内 189 项 pytest 全绿（证明镜像内依赖完整、代码与本地一致）
#     8  镜像内离线加载 BGE 向量模型并检索出结果（容器无外网）
#     9  数据卷持久化：下单/起容器后，用户数据与登录态仍在
#    10  冷启动就绪耗时（读 /api/health 的预加载耗时）
# ============================================================================
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
COMPOSE="docker compose -f docker/docker-compose.yml"
PORT="${PORT:-80}"
BASE="http://127.0.0.1:${PORT}"
PASS=0
FAIL=0
declare -a FAILED_ITEMS=()

ok()   { printf '  [OK]   %s\n' "$*"; PASS=$((PASS+1)); }
bad()  { printf '  [FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); FAILED_ITEMS+=("$*"); }
head_() { printf '\n\033[1;36m%s\033[0m\n' "$*"; }

code() {  # code <method> <url> [json]
  if [ "$1" = "POST" ]; then
    curl -s -o /tmp/zq_out.json -w '%{http_code}' --max-time 180 -X POST "$2" \
      -H 'Content-Type: application/json' -d "${3:-{\}}" 2>/dev/null || echo 000
  else
    curl -s -o /tmp/zq_out.json -w '%{http_code}' --max-time 90 "$2" 2>/dev/null || echo 000
  fi
}

echo "========================================================================"
echo "任务12 · Docker 部署验收"
echo "========================================================================"

# ---------------------------------------------------------------- 1 镜像
head_ "1/10 镜像构建结果与体积"
for img in zq-api:1.0.0 zq-web:1.0.0; do
  if docker image inspect "$img" >/dev/null 2>&1; then
    size=$(docker image inspect "$img" --format '{{.Size}}')
    ok "$img 存在，体积 $(awk -v b="$size" 'BEGIN{printf "%.2f GB", b/1024/1024/1024}')"
  else
    bad "$img 不存在（先跑 scripts/deploy.sh）"
  fi
done
echo "  ---- zq-api 分层（前 12 层）----"
docker history --no-trunc --format '  {{.Size}}\t{{.CreatedBy}}' zq-api:1.0.0 2>/dev/null \
  | head -12 | cut -c1-140 || true

# ---------------------------------------------------------------- 2 容器状态
head_ "2/10 容器运行状态"
$COMPOSE ps || true
if [ "$(docker inspect -f '{{.State.Running}}' zq-api 2>/dev/null)" = "true" ]; then
  ok "zq-api 运行中"
else
  bad "zq-api 未运行"
fi
if [ "$(docker inspect -f '{{.State.Running}}' zq-web 2>/dev/null)" = "true" ]; then
  ok "zq-web 运行中"
else
  bad "zq-web 未运行"
fi
health_state=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' zq-api 2>/dev/null)
[ "$health_state" = "healthy" ] && ok "zq-api healthcheck = healthy" \
  || bad "zq-api healthcheck = ${health_state}"

# ---------------------------------------------------------------- 3 密钥不进镜像
head_ "3/10 密钥未进入镜像"
if docker run --rm --entrypoint sh zq-api:1.0.0 -c 'test -f /app/.env' 2>/dev/null; then
  bad "镜像里存在 /app/.env —— 密钥泄漏！"
else
  ok "镜像内无 /app/.env（密钥只在容器启动时由 compose 注入）"
fi
if docker run --rm --entrypoint sh zq-api:1.0.0 -c 'test -n "$DEEPSEEK_API_KEY"' 2>/dev/null; then
  bad "镜像层里写死了 DEEPSEEK_API_KEY（ENV）"
else
  ok "镜像层里没有写死 DEEPSEEK_API_KEY"
fi

# ---------------------------------------------------------------- 4 数据库分层
head_ "4/10 数据库：本地库不入镜像，运行库落在数据卷"
if docker run --rm --entrypoint sh zq-api:1.0.0 -c 'test -f /app/data/app.db' 2>/dev/null; then
  bad "镜像里带了 data/app.db（本机用户数据被烤进镜像）"
else
  ok "镜像内无 data/app.db（.dockerignore 生效）"
fi
if [ "$(docker exec zq-api sh -c 'test -s /app/var/app.db && echo yes' 2>/dev/null)" = "yes" ]; then
  ok "运行期数据库 /app/var/app.db 已生成（挂在数据卷上）"
else
  bad "/app/var/app.db 未生成或为空"
fi
vol_size=$(docker exec zq-api sh -c 'ls -l /app/var/ | tail -n +2' 2>/dev/null | wc -l)
ok "数据卷 /app/var 内有 ${vol_size} 个运行期文件"

# ---------------------------------------------------------------- 5 走 Nginx 打接口
head_ "5/10 经 Nginx 反向代理打关键接口（公网链路）"
RESUME='{"resume_text":"张三 本科 3年经验 熟悉 Python Java MySQL，期望厦门，薪资 12k"}'
t() { local name="$1" m="$2" path="$3" data="$4" want="${5:-200}"
      local c; c=$(code "$m" "${BASE}${path}" "$data")
      [ "$c" = "$want" ] && ok "$(printf '%-26s %s' "$name" "$c")" \
                         || bad "$(printf '%-26s %s（期望 %s）' "$name" "$c" "$want")"; }

t "前端首页"        GET  "/"                     ""
t "健康检查"        GET  "/api/health"           ""
t "岗位列表"        GET  "/api/jobs?size=5"      ""
t "岗位详情"        GET  "/api/jobs/J0020"       ""
t "公司列表"        GET  "/api/companies?size=5" ""
t "公司详情"        GET  "/api/companies/C0001"  ""
t "聚类列表"        GET  "/api/cluster/list"     ""
t "首页聚合"        GET  "/api/home"             ""
t "简历解析"        POST "/api/resume/parse_text" "$RESUME"
t "人岗匹配"        POST "/api/match"            "$RESUME"
t "双口径评分"      POST "/api/score"            '{"resume_text":"张三 本科 3年经验 熟悉 Python Java MySQL，期望厦门，薪资 12k","job_id":"J0020"}'
t "Swagger 文档"    GET  "/docs"                 ""

# ---------------------------------------------------------------- 6 gzip
head_ "6/10 Nginx gzip 压缩"
js=$(ls web/dist/assets/index-*.js 2>/dev/null | head -1 | xargs -r basename)
if [ -n "$js" ]; then
  raw=$(curl -s -o /dev/null -w '%{size_download}' -H 'Accept-Encoding: identity' "${BASE}/assets/${js}")
  gz=$(curl -s -o /dev/null -w '%{size_download}' -H 'Accept-Encoding: gzip' "${BASE}/assets/${js}")
  if [ "$gz" -lt "$raw" ]; then
    ok "$(printf 'gzip 生效：%s  %d → %d 字节（省 %d%%）' "$js" "$raw" "$gz" $(( (raw-gz)*100/raw )))"
  else
    bad "gzip 未生效（identity ${raw} 字节 vs gzip ${gz} 字节）"
  fi
else
  bad "找不到 web/dist 里的 index-*.js（无法测 gzip）"
fi

# ---------------------------------------------------------------- 7 容器内 pytest
head_ "7/10 镜像内跑完整测试套件"
if docker exec zq-api python -m pytest -q > /tmp/zq_pytest.log 2>&1; then
  n=$(grep -oE '[0-9]+ passed' /tmp/zq_pytest.log | tail -1)
  ok "镜像内 pytest 全绿：${n:-通过}"
else
  bad "镜像内 pytest 有失败，日志尾部："
  tail -20 /tmp/zq_pytest.log | sed 's/^/        /'
fi

# ---------------------------------------------------------------- 8 离线向量检索
head_ "8/10 容器内离线加载向量模型（无外网）"
off=$(docker exec zq-api python -c "
import sys; sys.path.insert(0,'src/rag')
from query import get_retriever
r = get_retriever()
print('HITS', len(r.search('Java 后端开发', 5)))
" 2>&1 | tail -1)
case "$off" in
  *HITS*) ok "离线检索成功：$off" ;;
  *)      bad "离线检索失败：$off" ;;
esac

# ---------------------------------------------------------------- 9 数据卷持久化
head_ "9/10 数据卷持久化（重建容器后数据仍在）"
USER_NAME="verify_$(date +%s)"
TOKEN=$(curl -s --max-time 30 -X POST "${BASE}/api/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${USER_NAME}\",\"password\":\"verify123456\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
if [ -n "$TOKEN" ]; then
  ok "注册测试用户 ${USER_NAME} 并拿到令牌"
  curl -s --max-time 30 -X POST "${BASE}/api/user/resumes" -H "Authorization: Bearer ${TOKEN}" \
    -H 'Content-Type: application/json' \
    -d '{"title":"验收用简历","text":"张三 本科 3年 熟悉 Python Java MySQL"}' > /dev/null
  curl -s --max-time 30 -X POST "${BASE}/api/user/favorites" -H "Authorization: Bearer ${TOKEN}" \
    -H 'Content-Type: application/json' -d '{"job_id":"J0020"}' > /dev/null
  before=$(curl -s --max-time 30 "${BASE}/api/user/resumes" -H "Authorization: Bearer ${TOKEN}" \
    | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("items",[])))' 2>/dev/null)
  ok "重建前：该用户已保存 ${before:-0} 份简历 + 1 个收藏"

  echo "  … docker compose down（保留数据卷）→ up -d"
  $COMPOSE down > /dev/null 2>&1
  $COMPOSE up -d > /dev/null 2>&1
  for i in $(seq 1 60); do
    curl -fsS --max-time 5 "${BASE}/api/health" > /dev/null 2>&1 && break
    sleep 3
  done
  after=$(curl -s --max-time 30 "${BASE}/api/user/resumes" -H "Authorization: Bearer ${TOKEN}" \
    | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("items",[])))' 2>/dev/null)
  favs=$(curl -s --max-time 30 "${BASE}/api/user/favorites" -H "Authorization: Bearer ${TOKEN}" \
    | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("items",[])))' 2>/dev/null)
  if [ -n "$after" ] && [ "$after" != "0" ] && [ "${favs:-0}" != "0" ]; then
    ok "重建后：简历 ${after} 份、收藏 ${favs} 个、令牌仍有效 —— 数据卷持久化成功"
  else
    bad "重建后数据丢失（简历 ${after:-空}、收藏 ${favs:-空}）"
  fi
else
  bad "注册测试用户失败，跳过持久化验证"
fi

# ---------------------------------------------------------------- 10 就绪耗时
head_ "10/10 冷启动就绪耗时"
python3 - <<'PY' 2>/dev/null || echo "  （无法解析 /api/health）"
import json, urllib.request
d = json.load(urllib.request.urlopen("http://127.0.0.1:80/api/health", timeout=30))
w = d.get("启动预加载耗时秒", {})
print("  预加载各项耗时：", ", ".join("%s %ss" % (k, v) for k, v in w.items()))
print("  说明：matcher = 六维匹配引擎，retriever = RAG 向量检索，features = 评分特征（后台线程预热）")
PY

# ---------------------------------------------------------------- 汇总
echo
echo "========================================================================"
printf '验收结果：通过 %d 项，失败 %d 项\n' "$PASS" "$FAIL"
echo "========================================================================"
if [ "$FAIL" -gt 0 ]; then
  echo
  echo "未通过项："
  for i in "${FAILED_ITEMS[@]}"; do echo "  · $i"; done
  echo
  echo "诊断命令："
  echo "  docker compose -f docker/docker-compose.yml ps"
  echo "  docker compose -f docker/docker-compose.yml logs --tail 100 api"
  echo "  docker compose -f docker/docker-compose.yml logs --tail 50 web"
  exit 1
fi
echo "全部通过。"
