# -*- coding: utf-8 -*-
"""
任务6 · 步骤6a：匹配权重调优实验（v1 → v2 候选对比）

为什么不能用"准确率"选权重：本任务没有人工金标（按既定决定跳过），因此改用**客观代理指标**：
  · 岗位大类一致率：Top-N 里「岗位大类 == 简历期望岗位大类」的比例（用与建模同一套关键词归类规则）
  · 同城率：Top-N 里同城岗位的比例（地域维度是否被合理对待）
  · 平均技能命中数：Top-N 岗位的技能要求被简历覆盖的平均数量（相关性的直接证据）
  · 与基准的 Top-10 Jaccard：换权重对推荐列表的扰动幅度

候选权重（都满足和为 1）：
  C1 基准 v1    0.30/0.20/0.15/0.15/0.12/0.08（= 任务5 标签口径）
  C2 地域加重    0.28/0.18/0.12/0.24/0.10/0.08
  C3 技能加重    0.38/0.18/0.12/0.16/0.10/0.06
  C4 技能+地域  0.34/0.16/0.12/0.22/0.10/0.06

输出：`data/processed/匹配权重调优记录.csv`、`data/processed/匹配权重调优_对比.md`

运行：python src/models/matching/tune_weights.py
"""
import csv
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "models", "scoring"))
from build_features import job_category                                                    # noqa: E402
from build_labels import load_csv                                                          # noqa: E402
from match import DIMS, JobIndex, match_jobs, load_weights                                 # noqa: E402

P = os.path.join(ROOT, "data", "processed")
RES_CLEAN_CSV = os.path.join(P, "简历数据_cleaned.csv")
OUT_CSV = os.path.join(P, "匹配权重调优记录.csv")
OUT_MD = os.path.join(P, "匹配权重调优_对比.md")
N_RESUME = 200

CANDIDATES = [
    ("C1 基准v1（=任务5标签口径）", {"技能": 0.30, "经验": 0.20, "学历": 0.15, "地域": 0.15, "薪资": 0.12, "专业证书": 0.08},
     "基准"),
    ("C2 地域加重", {"技能": 0.28, "经验": 0.18, "学历": 0.12, "地域": 0.24, "薪资": 0.10, "专业证书": 0.08},
     "回应 Top-N 跨城过多、苏州霸榜"),
    ("C3 技能加重", {"技能": 0.38, "经验": 0.18, "学历": 0.12, "地域": 0.16, "薪资": 0.10, "专业证书": 0.06},
     "技能是相关性的主要证据，提高其话语权"),
    ("C4 技能+地域双加重", {"技能": 0.34, "经验": 0.16, "学历": 0.12, "地域": 0.22, "薪资": 0.10, "专业证书": 0.06},
     "同时回应技能相关性与跨城问题"),
]


def main():
    idx = JobIndex()
    clean = load_csv(RES_CLEAN_CSV)
    ids = list(range(0, len(idx.resumes), max(1, len(idx.resumes) // N_RESUME)))[:N_RESUME]
    print("岗位 %d ｜ 参与调优的简历 %d 份" % (len(idx), len(ids)))

    base_top, rows, per_res = {}, [], {}
    for name, w, why in CANDIDATES:
        assert abs(sum(w.values()) - 1) < 1e-9, name
        same_city, same_cat, hits, totals, tops = [], [], [], [], {}
        for i in ids:
            res = dict(idx.resumes[i])
            exp_cat = job_category(clean[i].get("期望岗位", ""))
            recs, full = match_jobs(idx, res, w, top_n=10)
            tops[i] = {r["岗位ID"] for r in recs}
            same_city.append(sum(1 for r in recs if r["地域"] >= 100) / len(recs))
            same_cat.append(sum(1 for r in recs if job_category(r["岗位名称"]) == exp_cat) / len(recs))
            hits.append(np.mean([float(r["技能命中数"]) for r in recs]))
            totals.append(np.mean([r["总分"] for r in recs]))
        if name.startswith("C1"):
            base_top = tops
        jac = float(np.mean([len(tops[i] & base_top[i]) / max(len(tops[i] | base_top[i]), 1) for i in ids])) \
            if base_top else 1.0
        rows.append({"候选": name, "调整理由": why, **w,
                     "Top10同城率": round(float(np.mean(same_city)) * 100, 2),
                     "Top10岗位大类一致率": round(float(np.mean(same_cat)) * 100, 2),
                     "Top10平均技能命中数": round(float(np.mean(hits)), 2),
                     "Top10平均总分": round(float(np.mean(totals)), 2),
                     "与C1的Top10重合度": round(jac, 3)})
        per_res[name] = {"同城率": float(np.mean(same_city)) * 100,
                         "大类一致率": float(np.mean(same_cat)) * 100,
                         "平均命中": float(np.mean(hits))}
        print("  %-22s 同城率 %5.1f%% ｜ 大类一致率 %5.1f%% ｜ 平均命中 %.2f ｜ 与C1重合 %.3f" %
              (name, rows[-1]["Top10同城率"], rows[-1]["Top10岗位大类一致率"],
               rows[-1]["Top10平均技能命中数"], jac))

    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("输出：%s" % os.path.relpath(OUT_CSV, ROOT))

    # 选优：大类一致率优先，其次同城率与技能命中
    best = max(rows, key=lambda r: (r["Top10岗位大类一致率"], r["Top10同城率"], r["Top10平均技能命中数"]))
    base = rows[0]
    L = ["# 匹配权重调优对比报告（任务6 · 步骤6a）\n",
         "> 说明：本任务**没有人工金标**（按既定决定跳过），因此用客观代理指标选权重：",
         "> ① Top-N 岗位大类一致率（与期望岗位同类，用建模同一套关键词归类规则）② Top-N 同城率 ③ Top-N 平均技能命中数 ④ 与基准的 Top-10 重合度。",
         "> 参与调优的简历：%d 份（从 500 份中均匀抽取）｜ 每次打分都跑全量 %d 个岗位\n" % (len(ids), len(idx)),
         "## 一、候选权重与指标\n",
         "| 候选 | 调整理由 | 技能 | 经验 | 学历 | 地域 | 薪资 | 专业证书 | 同城率 | 大类一致率 | 平均技能命中 | 平均总分 | 与C1重合度 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f%% | %.2f%% | %.2f | %.2f | %.3f |" %
                 (r["候选"], r["调整理由"], r["技能"], r["经验"], r["学历"], r["地域"], r["薪资"], r["专业证书"],
                  r["Top10同城率"], r["Top10岗位大类一致率"], r["Top10平均技能命中数"],
                  r["Top10平均总分"], r["与C1的Top10重合度"]))
    L.append("")
    L.append("## 二、抽样误差（判断差异是否可信）\n")
    n_obs = len(ids) * 10
    sd = (0.25 / n_obs) ** 0.5 * 100
    L.append("- 每份简历看 Top-10，共 **%d 条推荐**；大类一致率的标准误约 **±%.2f 个百分点**（二项分布近似，p≈0.5）。" % (n_obs, sd))
    L.append("- 因此**只有超过约 2 倍标准误（±%.1f 个百分点）的差异才值得当作真实差异**；未超过的一律按「与基准无显著差别」处理。" % (2 * sd))
    L.append("")
    L.append("## 三、结论\n")
    L.append("- 指标最优候选：**%s**（大类一致率 %.2f%%、同城率 %.2f%%、平均技能命中 %.2f）" %
             (best["候选"], best["Top10岗位大类一致率"], best["Top10同城率"], best["Top10平均技能命中数"]))
    L.append("- 基准 %s：大类一致率 %.2f%%、同城率 %.2f%%、平均技能命中 %.2f" %
             (base["候选"], base["Top10岗位大类一致率"], base["Top10同城率"], base["Top10平均技能命中数"]))
    gain = best["Top10岗位大类一致率"] - base["Top10岗位大类一致率"]
    sig = abs(gain) >= 2 * sd
    L.append("- 相对基准的大类一致率变化：**%+.2f 个百分点**（%s）；换权重对推荐列表的扰动（与 C1 重合度）为 %.3f。" %
             (gain, "超出 ±%.1f pp 的噪声带，差异可信" % (2 * sd) if sig else "落在 ±%.1f pp 噪声带内，差异不可信" % (2 * sd),
              best["与C1的Top10重合度"]))
    L.append("")
    L.append("## 四、采用结论\n")
    if best["候选"].startswith("C1") or not sig:
        L.append("**维持 v1 权重（与任务5 标签口径完全一致），不新增 v2。**")
        L.append("")
        L.append("理由：① 各候选的大类一致率差异未超过抽样噪声带（±%.1f pp），没有足够证据说明换权重更好；"
                 "② v1 与任务5 标签口径一致，任务8 的「评分模型 vs 匹配规则」对比才是同口径可比的；"
                 "③ 若后续人工核验表（`匹配推荐_人工核验表.csv`）显示技能维度确实更该加权，可一键切到 C3（技能 0.38）。" % (2 * sd))
    else:
        L.append("**采用 %s 作为 v2**（新增到 `匹配权重表.csv`）：大类一致率相对 v1 提升 %+.2f 个百分点（超出噪声带），"
                 "且与 v1 的 Top-10 重合度 %.3f（幅度可控）。" % (best["候选"], gain, best["与C1的Top10重合度"]))
        L.append("")
        L.append("> v1 仍是**任务5 标签口径**，任务8 的多模型对比统一用 v1；v2 只用于任务6 在线推荐，差异在《人岗匹配文档》中标注。")
    L.append("")
    L.append("- **代理指标的局限（如实说明）**：大类一致率只看「岗位大类是否对口」，无法判断「这家公司、这个薪资、这条发展路径是否合适」；"
             "同城率高也不等于推荐更好（简历所在城市可能本来就没有岗位）。因此本表只用于**排除明显更差的权重**，"
             "最终权重仍建议由人工核验表（`匹配推荐_人工核验表.csv`）确认。")
    L.append("")
    L.append("> 复现：`python src/models/matching/tune_weights.py`")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("输出：%s" % os.path.relpath(OUT_MD, ROOT))


if __name__ == "__main__":
    main()
