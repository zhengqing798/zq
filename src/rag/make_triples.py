# -*- coding: utf-8 -*-
"""
任务10 · 构建「问题—答案—来源」三元组（课程明确要求）

做法：把召回评估用的 **30 条真实问题**逐条交给 Agent（带缓存的 Function Calling），
记录 ① 问题 ② Agent 的最终回答 ③ 回答所依据的来源（工具名 + 来源文件/报告 + 命中的岗位ID/名称样本），
落盘为 `data/processed/RAG_问答三元组.csv`，用于：
  · 追溯每一个答案的来源（答辩时被追问"这个数字哪来的"可直接查表）
  · 作为后续评估/微调的问答样本集（30 条，含类型标签）

同时把"问题类型 → 工具调用序列"统计出来，作为《大模型应用文档》"工作流编排"一节的证据。

运行：python src/rag/make_triples.py
"""
import csv
import json
import os
import sys
import time
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
from evaluate_recall import QUESTIONS                       # noqa: E402  复用同一批问题
from agent import Agent                                     # noqa: E402

OUT_CSV = os.path.join(ROOT, "data", "processed", "RAG_问答三元组.csv")
OUT_FLOW = os.path.join(ROOT, "data", "processed", "RAG_工作流编排统计.csv")


def main():
    ag = Agent(verbose=False)
    rows, flows = [], Counter()
    t0 = time.time()
    for i, (q, typ, city, kw) in enumerate(QUESTIONS, 1):
        r = ag.ask(q)
        tools = [t["工具"] for t in r["tools"]]
        flows[" → ".join(tools) if tools else "（未调用工具）"] += 1
        src = []
        ids, nms = [], []
        for t in r["tools"]:
            src += [s for s in t.get("来源", []) if s]
            ids += t.get("岗位样本", [])
            nms += t.get("名称样本", [])
        src = list(dict.fromkeys(src))
        rows.append({
            "编号": i, "类型": typ, "问题": q,
            "答案": r["answer"].replace("\n", " ").strip(),
            "来源": "；".join(src),
            "命中岗位ID样本": "、".join(list(dict.fromkeys(ids))[:5]),
            "命中岗位名称样本": "、".join(list(dict.fromkeys(nms))[:3]),
            "调用工具": " → ".join(tools) if tools else "（未调用）",
            "工具调用次数": len(tools), "轮数": r["rounds"],
            "耗时秒": r["seconds"], "prompt_tokens": r["tokens"]["prompt"],
            "completion_tokens": r["tokens"]["completion"],
            "prompt版本": r["prompt_version"], "缓存命中": "是" if r["cached"] else "否",
        })
        print("[%2d/%d] %-28s 工具 %d 次 ｜ %s" % (i, len(QUESTIONS), q[:28], len(tools), " → ".join(tools)), flush=True)

    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(OUT_FLOW, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["工具调用序列", "问题数"])
        for k, v in flows.most_common():
            w.writerow([k, v])

    n_src = sum(1 for r in rows if r["来源"])
    print("\n三元组 %d 条 ｜ 有来源标注 %d 条（%.0f%%）｜ 平均工具调用 %.2f 次 ｜ 平均耗时 %.1f s" %
          (len(rows), n_src, n_src / len(rows) * 100,
           sum(r["工具调用次数"] for r in rows) / len(rows),
           sum(r["耗时秒"] for r in rows) / len(rows)))
    print("输出：%s（%.0fs 总耗时）" % (os.path.relpath(OUT_CSV, ROOT), time.time() - t0))
    print("输出：%s" % os.path.relpath(OUT_FLOW, ROOT))
    print("\n工具调用序列 Top8：")
    for k, v in flows.most_common(8):
        print("  %-52s %d" % (k, v))


if __name__ == "__main__":
    main()
