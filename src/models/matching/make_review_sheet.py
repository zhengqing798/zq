# -*- coding: utf-8 -*-
"""
任务6 · 步骤6b：生成人工核验表（供团队/老师按人眼判断推荐是否合理）

不做自动判断，只把「系统给出的推荐 + 系统理由」整理成一张可直接填写的表：
  data/processed/匹配推荐_人工核验表.csv
  data/processed/匹配推荐_样例结果.csv（样例推荐明细，默认用最新权重版本）

人工填写列（留空，由人工填）：
  · 人工判断：相关 / 一般 / 不相关
  · 备注：任意说明（例如"岗位名称看着不相关但职责相符"）

运行：python src/models/matching/make_review_sheet.py [--resumes 10 --top 5]
"""
import argparse
import csv
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "models", "scoring"))
from build_labels import load_csv                              # noqa: E402
from match import JobIndex, match_jobs, load_weights           # noqa: E402

P = os.path.join(ROOT, "data", "processed")
RES_CLEAN_CSV = os.path.join(P, "简历数据_cleaned.csv")
OUT_SAMPLE = os.path.join(P, "匹配推荐_样例结果.csv")
OUT_REVIEW = os.path.join(P, "匹配推荐_人工核验表.csv")


def main():
    ap = argparse.ArgumentParser(description="生成人工核验表")
    ap.add_argument("--resumes", type=int, default=10)
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args()
    weights = load_weights()
    w = weights["权重"]
    print("权重版本 %s" % weights["版本"])
    idx = JobIndex()
    clean = load_csv(RES_CLEAN_CSV)
    n = len(idx.resumes)
    ids = list(range(0, n, max(1, n // a.resumes)))[:a.resumes]

    sample_rows, review_rows = [], []
    for i in ids:
        res = dict(idx.resumes[i])
        res["期望岗位"] = clean[i].get("期望岗位", "")
        res["解析告警"] = ""
        recs, _ = match_jobs(idx, res, w, top_n=a.top)
        for r in recs:
            base = {"简历ID": "R%03d" % (i + 1), "简历姓名": res["姓名"],
                    "期望岗位": res["期望岗位"], "期望城市": res["城市"]}
            sample_rows.append({**base, **r})
            review_rows.append({
                "简历ID": base["简历ID"], "简历姓名": base["简历姓名"],
                "期望岗位": base["期望岗位"], "期望城市": base["期望城市"],
                "排名": r["排名"], "岗位名称": r["岗位名称"], "公司": r["公司"], "城市": r["城市"],
                "岗位薪资": r["岗位薪资"], "总分": r["总分"],
                "技能分": r["技能"], "经验分": r["经验"], "学历分": r["学历"],
                "地域分": r["地域"], "薪资分": r["薪资"], "专证分": r["专业证书"],
                "系统推荐理由": r["推荐理由"],
                "人工判断(相关/一般/不相关)": "", "备注": "",
            })
    with open(OUT_SAMPLE, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(sample_rows[0].keys()))
        wr.writeheader()
        wr.writerows(sample_rows)
    with open(OUT_REVIEW, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(review_rows[0].keys()))
        wr.writeheader()
        wr.writerows(review_rows)
    print("输出：%s（%d 份简历 × Top%d = %d 行）" %
          (os.path.relpath(OUT_SAMPLE, ROOT), len(ids), a.top, len(sample_rows)))
    print("输出：%s（待人工填写 人工判断/备注 两列）" % os.path.relpath(OUT_REVIEW, ROOT))


if __name__ == "__main__":
    main()
