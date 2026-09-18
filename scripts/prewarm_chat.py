# -*- coding: utf-8 -*-
"""演示预热：把答辩/演示要问的问题**真实跑一遍**并写进 Agent 缓存

为什么需要：
  · 问答默认走缓存（命中则秒回）；演示现场如果临时真调模型要 7~15 秒，容易被认为"卡住了"
  · 提前跑一遍，等于把"真实答案"预热好：演示时秒回、内容仍是真调 API 得到的（缓存里存着 tokens/耗时/来源）
  · 写进的缓存带 `cached_at` 与 7 天 TTL，前端会显示"缓存（时间）"，评委问起来有据可查

用法（后端需已启动）：
    python scripts/prewarm_chat.py                 # 跑内置的 8 个演示问题
    python scripts/prewarm_chat.py "自定义问题"     # 只跑指定问题（可多个）
    python scripts/prewarm_chat.py --force         # 即使已缓存也重新真实调用
"""
import argparse
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
API = "http://127.0.0.1:8000"

DEMO_QUESTIONS = [
    "这批岗位主要分布在哪些城市？各有多少个？",
    "要求硕士学历的岗位有多少个？薪资怎么样？",
    "求职者最常被要求掌握哪些技能？给个前 8 名。",
    "按岗位大类统计一下岗位数量分布。",
    "苏州的岗位按经验要求是怎么分布的？",
    "在招岗位最多的 5 家公司是哪几家？",
    "大专学历、3 年软件测试经验，在苏州能匹配到什么岗位？",
    "你们这个问答系统的知识库是怎么做的？检索效果如何？",
]


def post(path, payload, timeout=180):
    req = urllib.request.Request(API + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser(description="问答缓存预热（真实调用一次，演示时秒回）")
    ap.add_argument("questions", nargs="*", help="要预热的问题；留空则用内置演示问题")
    ap.add_argument("--force", action="store_true", help="忽略已有缓存，强制重新真实调用")
    a = ap.parse_args()
    qs = a.questions or DEMO_QUESTIONS

    try:
        h = json.load(urllib.request.urlopen(API + "/api/health", timeout=10))
        print("后端就绪 ｜ Agent:", h.get("Agent"))
    except Exception as e:
        print("❌ 后端不可用（先运行 scripts/run_api.ps1）：", e)
        return 2

    print("\n预热 %d 个问题（use_cache=%s）…\n" % (len(qs), not a.force))
    ok = 0
    for i, q in enumerate(qs, 1):
        t = time.time()
        try:
            j = post("/api/chat", {"question": q, "use_cache": not a.force})
        except Exception as e:
            print("❌ [%d/%d] %s\n    失败：%s" % (i, len(qs), q, e))
            continue
        hit = j.get("缓存命中")
        tools = " → ".join(x["工具"] for x in j.get("工具轨迹") or []) or "未调用工具"
        print("%s [%d/%d] %s" % ("⚡" if hit else "🔥", i, len(qs), q))
        print("      %s ｜ %s ｜ %d 轮 ｜ %ss ｜ %d tokens ｜ %s ｜ 来源 %d 条" % (
            "缓存命中" if hit else "真实调用", j.get("模型"), j.get("轮数"), j.get("耗时秒"),
            (j.get("tokens", {}).get("prompt", 0) + j.get("tokens", {}).get("completion", 0)),
            tools, len(j.get("来源") or [])))
        print("      回答：%s…" % (j.get("回答", "").replace("\n", " ")[:90]))
        ok += 1
        print("      （端到端 %.1fs）" % (time.time() - t))
    print("\n完成：%d/%d 个问题已就绪；缓存文件 data/rag/agent_cache.json（TTL 7 天）" % (ok, len(qs)))
    return 0 if ok == len(qs) else 1


if __name__ == "__main__":
    sys.exit(main())
