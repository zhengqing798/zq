# -*- coding: utf-8 -*-
"""
任务10 · Agent 示例问答（用于文档与人工抽检）

跑一组覆盖不同工具的问题，把「问题 / 调用了哪些工具 / 最终回答 / 耗时与 tokens」落盘成
`data/processed/Agent示例问答.md`，供《大模型应用文档》引用与人工核验。

运行：python src/agent/demo.py [--no-cache]
"""
import argparse
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from agent import Agent, PROMPT_VERSION          # noqa: E402

OUT = os.path.join(ROOT, "data", "processed", "Agent示例问答.md")

QUESTIONS = [
    ("岗位检索 + 统计", "厦门有哪些 Java 开发岗位？顺便说下厦门整体的薪资水平。"),
    ("结构化筛选（数值条件）", "月薪 2 万以上的算法岗位有多少个？举个例子。"),
    ("统计类问题", "这批岗位的月薪中位数是多少？薪资最高的城市是哪个？"),
    ("聚类画像", "岗位可以分成哪几类？软件测试类岗位大概是什么样的？"),
    ("人岗匹配（贴简历）", "我大专学历，3 年软件测试经验，会用 Selenium、JMeter、Python 和 MySQL，"
                          "期望在苏州做测试开发，帮我推荐几个岗位。"),
    ("知识库自述", "你们这个问答系统的知识库是怎么做的？检索效果如何？"),
    ("能力边界测试", "帮我看看北京有没有合适的岗位，我想投字节跳动。"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    ag = Agent()
    rows = []
    for tag, q in QUESTIONS:
        print("\n=== [%s] %s" % (tag, q), flush=True)
        r = ag.ask(q, use_cache=not a.no_cache)
        tools = "、".join("%s(%s)" % (t["工具"], "ok" if t["ok"] else "失败") for t in r["tools"]) or "—"
        print("    工具：%s ｜ %.1fs ｜ tokens %s ｜ 缓存 %s" % (tools, r["seconds"], r["tokens"], r["cached"]))
        rows.append((tag, q, r, tools))

    L = ["# Agent 示例问答（任务10 · 步骤4）\n",
         "> 模型 `%s` ｜ Prompt 版本 **%s** ｜ 工具 6 个（search_jobs / filter_jobs / salary_stats / match_resume / cluster_profile / kb_stats）" % (ag.model, PROMPT_VERSION),
         "> 说明：以下回答**全部由 Agent 自动生成**，未做人工修改；数字均来自工具返回，括号内为来源。",
         "> 本文件同时作为人工抽检材料：回答中的数字可逐条回查 `data/processed/` 下的原始数据与报告。\n",
         "| # | 类别 | 问题 | 调用工具 | 耗时 | tokens | 缓存命中 |",
         "|---|---|---|---|---|---|---|"]
    for i, (tag, q, r, tools) in enumerate(rows, 1):
        tk = r["tokens"]
        L.append("| %d | %s | %s | %s | %.1fs | %d+%d | %s |" %
                 (i, tag, q[:34], tools, r["seconds"], tk["prompt"], tk["completion"],
                  "是" if r["cached"] else "否"))
    L.append("")
    for i, (tag, q, r, tools) in enumerate(rows, 1):
        L.append("---\n")
        L.append("### 示例 %d · %s\n" % (i, tag))
        L.append("**问**：%s\n" % q)
        L.append("**工具调用**：%s\n" % tools)
        L.append("**答**：\n")
        L.append(r["answer"])
        L.append("")
    L.append("---\n")
    L.append("## 人工抽检要点（如实说明）\n")
    L.append("| # | 检查项 | 怎么看 |\n|---|---|---|")
    L.append("| 1 | 数字是否可回溯 | 例如「样本 1168 条」应对应 `salary_stats(city=厦门)` 的返回；可运行同一条问句复现 |")
    L.append("| 2 | 是否编造了不存在的岗位/公司 | 岗位卡都带 `岗位ID`，可在 `zhaopin_jobs_cleaned_seg.csv` 里按 ID 核对 |")
    L.append("| 3 | 是否声明了数据局限 | 期望回答里出现「16 个城市」「24.69% 经验字段错位」等提示 |")
    L.append("| 4 | 能力边界 | 示例 7 故意问「北京/字节跳动」（数据里没有），正确行为是**直说查不到**而不是编答案 |")
    L.append("")
    L.append("> 复现：`python src/agent/demo.py`（缓存命中则秒回；加 `--no-cache` 强制重新调用）")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n输出：%s" % os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    main()
