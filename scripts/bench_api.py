# -*- coding: utf-8 -*-
"""任务13 · 接口性能基线测量与优化前后对比

为什么需要它
    "优化响应时间"如果没有优化前的数字，就等于没做这件事。
    这个脚本先把每个接口的 P50/P95/P99 打下来落到 `reports/接口性能基线.json`，
    优化之后再打一次，用 `--compare` 出前后对比表 —— 每一个提升都要有据可查。

用法
    # 打一份基线（标签默认 baseline）
    python scripts/bench_api.py

    # 优化后再打一份
    python scripts/bench_api.py --label after

    # 出对比表
    python scripts/bench_api.py --compare reports/接口性能基线.json reports/接口性能_after.json

说明
    · 需要后端已在 127.0.0.1:8000 运行；
    · 每轮先"热身"一遍，把懒加载的组件（匹配引擎 / RAG 检索 / 评分特征）都触发出来，
      避免把首次加载的几秒算进接口耗时；
    · 用 requests.Session 复用连接，测的是服务端处理时间，不含 TCP 握手；
    · **默认不测 /api/chat**：它会真实调用 DeepSeek 花钱又慢，且耗时主要取决于大模型而不是我们的代码。
      需要测就走 `--with-chat`，且只测缓存命中路径（免费）。
"""
import argparse
import glob
import io
import json
import os
import platform
import statistics
import sys
import time

import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BASE = os.environ.get("ZQ_API", "http://127.0.0.1:8000")
REPORTS = os.path.join(ROOT, "reports")

# (名称, 方法, 路径, 请求体, 轮数)
# 轮数按单次耗时量级分档：慢接口少打几轮，保证整轮跑完在几分钟内
BENCH = [
    ("健康检查",            "GET",  "/api/health",                None, 30),
    ("首页聚合",            "GET",  "/api/home",                  None, 30),
    ("岗位统计",            "GET",  "/api/jobs/stats",            None, 20),
    ("岗位列表(默认随机)",  "GET",  "/api/jobs?size=20&seed=42",  None, 30),
    ("岗位列表(城市筛选)",  "GET",  "/api/jobs?size=20&city=苏州", None, 30),
    ("岗位列表(关键词)",    "GET",  "/api/jobs?size=20&keyword=Java", None, 30),
    ("岗位列表(薪资排序)",  "GET",  "/api/jobs?size=20&sort=salary", None, 30),
    ("岗位详情",            "GET",  "/api/jobs/J0020",            None, 30),
    ("公司列表",            "GET",  "/api/companies?size=20",     None, 30),
    ("公司统计",            "GET",  "/api/companies/stats",       None, 20),
    # 公司ID 是 C+8位序号，不能想当然写 C0001（第一版就写错了，接口直接 400）；
    # 这里用 __CID__ 占位，运行时从 /api/companies 取一个真实 ID
    ("公司详情",            "GET",  "/api/companies/__CID__",     None, 30),
    ("聚类列表",            "GET",  "/api/cluster/list",          None, 20),
    ("聚类画像",            "GET",  "/api/cluster/profile?name=测试", None, 20),
    ("简历解析",            "POST", "/api/resume/parse_text",     "__RESUME__", 20),
    ("人岗匹配 Top10",      "POST", "/api/match",                 "__MATCH10__", 15),
    ("人岗匹配 Top50",      "POST", "/api/match",                 "__MATCH50__", 10),
    ("双口径评分",          "POST", "/api/score",                 "__SCORE__", 15),
]

CHAT_BENCH = ("智能问答(缓存命中)", "POST", "/api/chat",
              {"question": "厦门有哪些Java开发岗位", "use_cache": True}, 10)


def resume_text():
    cands = glob.glob(os.path.join(ROOT, "data", "processed", "*粘贴版*.txt"))
    if cands:
        return io.open(cands[0], encoding="utf-8").read()
    return "张三 本科 3年经验 熟悉 Python Java MySQL，期望厦门，薪资 12k"


def build_payload(marker, res):
    if marker is None:
        return None
    if marker == "__RESUME__":
        return {"resume_text": res}
    if marker == "__MATCH10__":
        return {"resume_text": res, "top_n": 10}
    if marker == "__MATCH50__":
        return {"resume_text": res, "top_n": 50}
    if marker == "__SCORE__":
        return {"resume_text": res, "job_id": "J0020"}
    return marker


def call(sess, method, path, payload):
    url = BASE + path
    t0 = time.perf_counter()
    if method == "POST":
        r = sess.post(url, json=payload, timeout=300)
    else:
        r = sess.get(url, timeout=300)
    dt = (time.perf_counter() - t0) * 1000.0        # 毫秒
    if r.status_code != 200:
        raise RuntimeError("%s %s -> HTTP %d: %s" % (method, path, r.status_code, r.text[:200]))
    return dt, len(r.content)


def pct(vals, p):
    """线性插值分位数；样本少时也不会越界"""
    if not vals:
        return 0.0
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def real_company_id(sess):
    """从公司列表里取一个真实存在的公司ID（ID 形如 C+8位序号，硬编码容易写错）"""
    try:
        r = sess.get(BASE + "/api/companies?size=1", timeout=60).json()
        rows = r.get("公司") or r.get("items") or []
        if rows:
            return rows[0].get("公司ID") or rows[0].get("id") or "C00000001"
    except Exception:
        pass
    return "C00000001"


def bench_one(sess, name, method, path, payload, n):
    # 热身：不计入统计，用来触发懒加载
    call(sess, method, path, payload)
    lat, size = [], 0
    for _ in range(n):
        dt, sz = call(sess, method, path, payload)
        lat.append(dt)
        size = sz
    return {
        "轮数": n,
        "p50": round(pct(lat, 0.50), 2),
        "p95": round(pct(lat, 0.95), 2),
        "p99": round(pct(lat, 0.99), 2),
        "均值": round(statistics.fmean(lat), 2),
        "最小": round(min(lat), 2),
        "最大": round(max(lat), 2),
        "响应字节": size,
    }


def run(label, with_chat):
    try:
        h = requests.get(BASE + "/api/health", timeout=30).json()
    except Exception as e:
        print("后端不可达（%s）：%s" % (BASE, e))
        print("请先启动：python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000")
        return 1
    warm = h.get("启动预加载耗时秒", {})
    print("=" * 92)
    print("任务13 · 接口性能测量 ｜ 标签 %s ｜ %s" % (label, BASE))
    print("后端预加载：%s" % (", ".join("%s %ss" % (k, v) for k, v in warm.items()) or "（无）"))
    print("=" * 92)
    print("%-22s %8s %8s %8s %8s %10s" % ("接口", "P50(ms)", "P95(ms)", "P99(ms)", "均值", "响应字节"))
    print("-" * 92)

    res = resume_text()
    sess = requests.Session()
    cid = real_company_id(sess)
    print("（公司详情用真实公司ID：%s）" % cid)
    out = {"标签": label, "地址": BASE, "时间": time.strftime("%Y-%m-%d %H:%M:%S"),
           "主机": {"平台": platform.platform(), "Python": platform.python_version(),
                    "CPU核数": os.cpu_count()},
           "后端预加载耗时秒": warm, "接口": {}}

    items = list(BENCH) + ([CHAT_BENCH] if with_chat else [])
    for name, method, path, marker, n in items:
        path = path.replace("__CID__", cid)
        payload = build_payload(marker, res)
        try:
            r = bench_one(sess, name, method, path, payload, n)
        except Exception as e:
            print("%-22s %s" % (name, ("失败：%s" % e)[:60]))
            continue
        key = "%s %s" % (method, path)
        out["接口"][key] = dict(r, 名称=name)
        print("%-22s %8.1f %8.1f %8.1f %8.1f %10d"
              % (name, r["p50"], r["p95"], r["p99"], r["均值"], r["响应字节"]))

    os.makedirs(REPORTS, exist_ok=True)
    path = os.path.join(REPORTS, "接口性能_%s.json" % label)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("-" * 92)
    print("已保存：%s" % os.path.relpath(path, ROOT).replace("\\", "/"))
    return 0


def compare(paths):
    if len(paths) != 2:
        print("--compare 需要两个文件：优化前 与 优化后")
        return 1
    a = json.load(io.open(paths[0], encoding="utf-8"))
    b = json.load(io.open(paths[1], encoding="utf-8"))
    print("=" * 104)
    print("任务13 · 优化前后对比 ｜ 前：%s（%s） → 后：%s（%s）"
          % (a["标签"], a["时间"], b["标签"], b["时间"]))
    print("=" * 104)
    print("%-22s %10s %10s %10s %8s  %10s %10s %8s" %
          ("接口", "前P50", "后P50", "P50变化", "幅度", "前P95", "后P95", "P95变化"))
    print("-" * 104)
    common = [k for k in a["接口"] if k in b["接口"]]
    better = worse = 0
    for k in common:
        x, y = a["接口"][k], b["接口"][k]
        d50 = y["p50"] - x["p50"]
        d95 = y["p95"] - x["p95"]
        p50 = (d50 / x["p50"] * 100) if x["p50"] else 0
        tag = "↓ 快" if d50 < -0.5 else ("↑ 慢" if d50 > 0.5 else "≈ 持平")
        if d50 < -0.5:
            better += 1
        elif d50 > 0.5:
            worse += 1
        print("%-22s %9.1f %9.1f %+10.1f %7.0f%%  %9.1f %9.1f %+9.1f  %s"
              % (x.get("名称", k), x["p50"], y["p50"], d50, p50, x["p95"], y["p95"], d95, tag))
    print("-" * 104)
    print("共 %d 个接口：变快 %d 个、变慢 %d 个、持平 %d 个"
          % (len(common), better, worse, len(common) - better - worse))
    return 0


def main():
    ap = argparse.ArgumentParser(description="任务13 接口性能基线测量与对比")
    ap.add_argument("--label", default="baseline", help="这次测量的标签（默认 baseline）")
    ap.add_argument("--with-chat", action="store_true",
                    help="额外测 /api/chat 的缓存命中路径（默认不测，避免花钱调大模型）")
    ap.add_argument("--compare", nargs="*", help="对比两个 JSON 结果文件")
    args = ap.parse_args()
    if args.compare:
        return compare(args.compare)
    return run(args.label, args.with_chat)


if __name__ == "__main__":
    sys.exit(main())
