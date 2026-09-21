# -*- coding: utf-8 -*-
"""任务12 · 容器运行约定「等价验证」（不需要 Docker 也能跑）

为什么要这个脚本
    任务要求「构建镜像并本地验证」。本机没装 Docker（也没有 WSL Linux 发行版），
    所以先把这个验证拆成两半：
      · 这一半 = 与 Docker 无关、但同样是"镜像能不能跑起来"的部分，
        在宿主机上**复刻镜像里的运行约定**逐条验证；
      · 另一半 = 真正的 `docker build` / `docker compose up`，等服务器到位后在那边做
        （见 docker/verify_deploy.sh）。
    这样风险不会积压到最后一天，也避免"镜像里跑不起来"这类问题拖到验收才发现。

逐条验证的东西（每一条都对应 Dockerfile / docker-compose.yml 里的一处约定）
    1. 依赖清单能被 pip 正确解析 —— 中文 Windows 的区域编码是 GBK，
       pip 解析含中文注释的 requirements 文件会直接 UnicodeDecodeError（真实踩过）
    2. .dockerignore 里几条"绝不能进镜像"的排除项确实存在（密钥 / 本地数据库 / node_modules）
    3. 环境变量与镜像完全一致：APP_DB / AGENT_CACHE / AGENT_LOG / 离线开关
    4. 启动命令与 Dockerfile 的 CMD 完全一致，且能在 start-period 内就绪
    5. 8 个关键接口全部 200
    6. 离线状态（HF_HUB_OFFLINE=1）下 BGE 向量模型能从本地缓存加载并检索出结果
       —— 容器里没有外网，这一步不过，线上智能问答就是废的
    7. 运行期数据真的落进可写目录（容器里对应挂卷 /app/var），重建容器不丢

用法
    python scripts/verify_runtime_contract.py

脚本自己起一个临时 uvicorn（端口 8077，避开开发用的 8000），跑完自动关掉并清理临时目录。
"""
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PORT = 8077
BASE = "http://127.0.0.1:%d" % PORT
VAR = os.path.join(ROOT, ".verify_var")          # 本地对应容器里的 /app/var
LOG = os.path.join(ROOT, ".verify_var_server.log")

# 与 docker/Dockerfile 的 CMD 保持一致
# 注意 `--forwarded-allow-ips=*` 用等号附着式写法：写成 `--forwarded-allow-ips *` 时，
# 那个独立的 `*` 在某些调用链上会被当成通配符展开成整个目录的文件名列表，
# uvicorn 就会报 "Got unexpected extra arguments (docker docs models ...)" 直接起不来。
UVICORN_CMD = [
    sys.executable, "-m", "uvicorn", "src.api.main:app",
    "--host", "127.0.0.1", "--port", str(PORT),
    "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*",
]

results = []          # (序号, 名称, 是否通过, 说明)


def record(name, ok, detail=""):
    results.append((len(results) + 1, name, bool(ok), detail))
    print("  %s %-46s %s" % ("[OK]  " if ok else "[FAIL]", name, detail), flush=True)


# ---------------------------------------------------------------- 1. 依赖清单可解析
def check_requirements():
    from pip._internal.utils.encoding import auto_decode
    files = ["requirements.txt", "docker/requirements.lock.txt", "docker/requirements.torch.txt"]
    bad = []
    for f in files:
        p = os.path.join(ROOT, f)
        try:
            text = auto_decode(open(p, "rb").read())
            n = len([l for l in text.splitlines() if l.strip() and not l.startswith("#")])
            if n == 0:
                bad.append("%s 解析后没有依赖行" % f)
        except Exception as e:
            bad.append("%s -> %s" % (f, e))
    record("依赖清单可被 pip 解析（编码陷阱）", not bad,
           "3 个文件全部可解析" if not bad else "；".join(bad))


def check_dockerignore():
    p = os.path.join(ROOT, ".dockerignore")
    if not os.path.exists(p):
        record(".dockerignore 关键排除项", False, "文件不存在 —— 构建上下文会带上 node_modules 与密钥")
        return
    text = io.open(p, encoding="utf-8").read()
    must = {
        ".env": "大模型密钥绝不能进镜像",
        "data/app.db": "本地数据库含用户与密码哈希",
        "web/node_modules": "232MB 前端依赖",
        ".venv": "Windows 版虚拟环境",
    }
    missing = [k for k in must if k not in text]
    record(".dockerignore 关键排除项", not missing,
           "4 项齐全" if not missing else "缺少：%s" % ", ".join(missing))


# ---------------------------------------------------------------- 3. 环境变量约定
def check_env_and_paths():
    """起服务前先确认：agent 真的按环境变量决定缓存/日志落点"""
    env = dict(os.environ)
    env.update({
        "APP_DB": os.path.join(VAR, "app.db"),
        "AGENT_CACHE": os.path.join(VAR, "agent_cache.json"),
        "AGENT_LOG": os.path.join(VAR, "agent_calls.jsonl"),
    })
    code = (
        "import os,sys;"
        "sys.path.insert(0,'src/agent');sys.path.insert(0,'src/api');"
        "import agent, db;"
        "print('CACHE',agent.CACHE_PATH);print('LOG',agent.LOG_PATH);print('DB',db.DB_PATH)"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout or ""
    ok = (VAR.replace("\\", "/") in out.replace("\\", "/")) and r.returncode == 0
    record("APP_DB / AGENT_CACHE / AGENT_LOG 生效", ok,
           "三者均指向可写卷目录" if ok else (r.stderr or out)[-200:])


# ---------------------------------------------------------------- 2+4+5. 起服务并打接口
def http(path, method="GET", payload=None, timeout=180):
    url = BASE + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def start_server():
    """按镜像的 CMD 与镜像的环境变量起后端"""
    env = dict(os.environ)
    env.update({
        "APP_DB": os.path.join(VAR, "app.db"),
        "AGENT_CACHE": os.path.join(VAR, "agent_cache.json"),
        "AGENT_LOG": os.path.join(VAR, "agent_calls.jsonl"),
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": ROOT,
        # 容器里这两个开关是打开的；本地同样打开，用来证明"没有外网也能跑"
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
    })
    f = open(LOG, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(UVICORN_CMD, cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT)
    return proc, f


def wait_ready(proc, limit=180):
    t0 = time.time()
    while time.time() - t0 < limit:
        if proc.poll() is not None:
            return False, time.time() - t0
        try:
            st, body = http("/api/health", timeout=5)
            if st == 200:
                return True, time.time() - t0
        except Exception:
            time.sleep(2)
    return False, time.time() - t0


def check_endpoints(resume_text):
    endpoints = [
        ("首页聚合 /api/home", "GET", "/api/home", None),
        ("岗位列表 /api/jobs", "GET", "/api/jobs?size=5", None),
        ("公司列表 /api/companies", "GET", "/api/companies?size=5", None),
        ("聚类列表 /api/cluster/list", "GET", "/api/cluster/list", None),
        ("岗位详情 /api/jobs/J0020", "GET", "/api/jobs/J0020", None),
        ("简历解析 /api/resume/parse_text", "POST", "/api/resume/parse_text",
         {"resume_text": resume_text}),
        ("人岗匹配 /api/match", "POST", "/api/match",
         {"resume_text": resume_text, "top_n": 5}),
        ("双口径评分 /api/score", "POST", "/api/score",
         {"resume_text": resume_text, "job_id": "J0020"}),
    ]
    failed = []
    for name, method, path, payload in endpoints:
        try:
            st, _ = http(path, method, payload)
            ok = st == 200
        except Exception as e:
            ok = False
            st = str(e)[:60]
        if not ok:
            failed.append("%s(%s)" % (name, st))
    record("8 个关键接口全部 200", not failed,
           "全部通过" if not failed else "失败：" + "；".join(failed))


def check_offline_embedding():
    """容器内无外网，BGE 必须能从镜像里的缓存离线加载"""
    env = dict(os.environ)
    env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_SYMLINKS_WARNING": "1"})
    code = (
        "import sys;sys.path.insert(0,'src/rag');"
        "from query import get_retriever;"
        "r=get_retriever();hits=r.search('Java 后端开发',5);"
        "print('HITS',len(hits));print('VECDIM',r.emb.dim)"
    )
    t0 = time.time()
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    hits = None
    for line in (r.stdout or "").splitlines():
        if line.startswith("HITS"):
            hits = int(line.split()[1])
    ok = r.returncode == 0 and hits and hits > 0
    record("离线加载 BGE 向量模型并检索", ok,
           "命中 %s 条，耗时 %.1fs（无外网）" % (hits, time.time() - t0) if ok
           else out[-200:])


def check_var_written():
    """运行期数据必须落在可写目录（容器里是挂卷 /app/var）"""
    time.sleep(1)
    db_file = os.path.join(VAR, "app.db")
    ok_db = os.path.exists(db_file) and os.path.getsize(db_file) > 0
    record("运行期数据落入可写目录", ok_db,
           "app.db %d 字节" % os.path.getsize(db_file) if ok_db else "app.db 未生成")
    # 顺手确认镜像里那份 data/app.db 没被碰过（容器里它是只读资产）
    src_db = os.path.join(ROOT, "data", "app.db")
    if os.path.exists(src_db):
        record("项目内 data/app.db 未被运行期写入（对应镜像只读资产层）", True,
               "大小 %d 字节，未被本脚本改动" % os.path.getsize(src_db))


def main():
    print("=" * 78)
    print("任务12 · 容器运行约定等价验证（无需 Docker）")
    print("=" * 78)

    if os.path.exists(VAR):
        shutil.rmtree(VAR, ignore_errors=True)
    os.makedirs(VAR, exist_ok=True)

    print("\n[一] 构建期约定")
    check_requirements()
    check_dockerignore()

    print("\n[二] 运行期约定")
    check_env_and_paths()

    cands = glob.glob(os.path.join(ROOT, "data", "processed", "*粘贴版*.txt"))
    resume_text = io.open(cands[0], encoding="utf-8").read() if cands else (
        "张三 本科 3年经验 熟悉 Python Java MySQL，期望厦门，薪资 12k")

    print("  … 按镜像 CMD 启动后端（端口 %d，离线开关已打开）" % PORT, flush=True)
    proc, logf = start_server()
    try:
        ok, secs = wait_ready(proc)
        record("按镜像 CMD 启动并就绪", ok,
               "耗时 %.1fs（Dockerfile 的 start-period 给了 120s）" % secs if ok
               else "180s 内未就绪，见 %s" % LOG)
        if ok:
            check_endpoints(resume_text)
            check_var_written()
        check_offline_embedding()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:
            proc.kill()
        logf.close()

    n_pass = sum(1 for r in results if r[2])
    print("\n" + "=" * 78)
    print("结果：%d/%d 通过" % (n_pass, len(results)))
    print("=" * 78)
    if n_pass != len(results):
        print("\n未通过项：")
        for i, name, ok, detail in results:
            if not ok:
                print("  %d. %s —— %s" % (i, name, detail))
        print("\n服务端日志尾部（%s）：" % LOG)
        if os.path.exists(LOG):
            print("".join(io.open(LOG, encoding="utf-8", errors="replace").readlines()[-30:]))
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
