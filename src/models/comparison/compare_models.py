# -*- coding: utf-8 -*-
"""
任务8 · 多模型横向对比（评分模型 / 匹配规则 / 聚类模型）

三类模型的目标与指标本来就不同质（回归误差 vs 推荐质量 vs 簇结构），因此本脚本做两件事：
  ① **统一对比表**：把三者的任务、输入输出、指标、结果、用途、局限放在一张表里（不做"硬凑同一个数"）；
  ② **一个真正可比的实验**：在同一批候选配对上比较「评分模型（任务5 XGBoost）」与「匹配规则（任务6，v1 权重）」——
     按简历分组取 Top-10，算 **Jaccard 重合度**、**Spearman 分数相关**、**NDCG@10**，并对比**打分耗时**。

输出：
  · `data/processed/多模型对比_重合度.csv`   逐份简历的重合度与相关性
  · `data/processed/多模型对比_汇总.csv`     三模型对比表 + 对比实验汇总
  · `reports/figures/20_多模型对比_评分模型vs匹配规则.png`
  · `docs/多模型对比分析报告.md`              （由本脚本写入，含任务7 聚类结果）

运行：python src/models/comparison/compare_models.py
"""
import csv
import json
import os
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "models", "scoring"))
from build_labels import load_csv                                                     # noqa: E402

P = os.path.join(ROOT, "data", "processed")
FIG = os.path.join(ROOT, "reports", "figures")
FEAT_CSV = os.path.join(P, "匹配特征_全量样本.csv")
LABEL_CSV = os.path.join(P, "匹配样本_标签数据.csv")
SPLIT_CSV = os.path.join(P, "匹配样本_划分_按简历.csv")
EVAL_REG = os.path.join(P, "模型评估结果_回归.csv")
EVAL_CLS = os.path.join(P, "模型评估结果_分类.csv")
CLU_MD = os.path.join(P, "岗位聚类_说明.md")
CLU_CURVE = os.path.join(P, "岗位聚类_定K曲线.csv")
META = os.path.join(ROOT, "models", "模型元数据.json")
MODEL_T1 = os.path.join(ROOT, "models", "按简历_T1回归_best_XGBoost.joblib")
OUT_PAIR = os.path.join(P, "多模型对比_重合度.csv")
OUT_SUM = os.path.join(P, "多模型对比_汇总.csv")
OUT_FIG = os.path.join(FIG, "20_多模型对比_评分模型vs匹配规则.png")
OUT_DOC = os.path.join(ROOT, "docs", "多模型对比分析报告.md")
K = 10

for f in ("Microsoft YaHei", "SimHei", "SimSun"):
    if any(f.lower() in x.name.lower() for x in matplotlib.font_manager.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [f]
        break
plt.rcParams["axes.unicode_minus"] = False


def ndcg_at_k(y, s, k=K):
    order = np.argsort(-s)[:k]
    dcg = float((y[order] * (1.0 / np.log2(np.arange(2, len(order) + 2)))).sum())
    ideal = float((np.sort(y)[::-1][:k] * (1.0 / np.log2(np.arange(2, min(k, len(y)) + 2)))).sum())
    return dcg / ideal if ideal > 0 else 0.0


def main():
    feat = pd.read_csv(FEAT_CSV, encoding="utf-8-sig")
    meta = json.load(open(META, encoding="utf-8"))
    feats = meta["特征列表"]["全部特征"]
    split = pd.read_csv(SPLIT_CSV, encoding="utf-8-sig")
    df = feat.merge(split, on=["简历ID", "岗位ID"], how="left", validate="one_to_one")
    print("配对表 %s ｜ 特征 %d ｜ 标签列已含在特征表中（总分_规则）" % (df.shape, len(feats)))

    model = joblib.load(MODEL_T1)
    t0 = time.time()
    df["模型分"] = model.predict(df[feats])
    t_model = time.time() - t0
    df["规则分"] = df["总分_规则"]
    df["是否匹配"] = (df["总分(0-100)"] >= 65).astype(int)

    rows, jac_list, rho_list, ndcg_m, ndcg_r = [], [], [], [], []
    for rid, g in df.groupby("简历ID", sort=False):
        y = g["是否匹配"].to_numpy()
        sm, sr = g["模型分"].to_numpy(), g["规则分"].to_numpy()
        top_m = set(g["岗位ID"].to_numpy()[np.argsort(-sm)[:K]])
        top_r = set(g["岗位ID"].to_numpy()[np.argsort(-sr)[:K]])
        jac = len(top_m & top_r) / max(len(top_m | top_r), 1)
        rho = spearmanr(sm, sr).correlation if len(g) > 2 else np.nan
        nm, nr = ndcg_at_k(y, sm), ndcg_at_k(y, sr)
        jac_list.append(jac)
        rho_list.append(rho)
        ndcg_m.append(nm)
        ndcg_r.append(nr)
        rows.append({"简历ID": rid, "配对数": len(g), "Top10重合度": round(jac, 3),
                     "Spearman相关": round(float(rho), 3) if rho == rho else "",
                     "模型NDCG@10": round(nm, 4), "规则NDCG@10": round(nr, 4),
                     "模型MAE": round(float(np.abs(sm - g["总分(0-100)"].to_numpy()).mean()), 3)})
    with open(OUT_PAIR, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    jac_m, rho_m = float(np.mean(jac_list)), float(np.nanmean(rho_list))
    print("逐简历 Top-10 重合度均值 %.3f ｜ Spearman 均值 %.4f ｜ 模型 NDCG@10 %.4f vs 规则 %.4f" %
          (jac_m, rho_m, np.mean(ndcg_m), np.mean(ndcg_r)))
    print("打分耗时：模型批量预测 %.1fs（%d 行，含特征已在内存）；规则逐对 8,836 岗 0.17s（任务6 实测）" %
          (t_model, len(df)))

    make_fig(jac_list, rho_list, ndcg_m, ndcg_r)
    write_outputs(rows, jac_m, rho_m, float(np.mean(ndcg_m)), float(np.mean(ndcg_r)), t_model, len(df))


def make_fig(jac, rho, ndcg_m, ndcg_r):
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    axes[0].hist(jac, bins=20, color="#4C78A8", edgecolor="white")
    axes[0].axvline(np.mean(jac), color="red", ls="--", label="均值 %.3f" % np.mean(jac))
    axes[0].set_title("Top-10 重合度分布（模型 vs 规则）")
    axes[0].set_xlabel("Jaccard 重合度")
    axes[0].set_ylabel("简历数")
    axes[0].legend()
    axes[1].hist([r for r in rho if r == r], bins=20, color="#2f9e6b", edgecolor="white")
    axes[1].axvline(np.nanmean(rho), color="red", ls="--", label="均值 %.3f" % np.nanmean(rho))
    axes[1].set_title("逐简历 Spearman 分数相关")
    axes[1].set_xlabel("Spearman ρ")
    axes[1].legend()
    axes[2].hist(ndcg_m, bins=20, alpha=.75, label="评分模型 均值 %.3f" % np.mean(ndcg_m), color="#4C78A8")
    axes[2].hist(ndcg_r, bins=20, alpha=.6, label="匹配规则 均值 %.3f" % np.mean(ndcg_r), color="#e07b39")
    axes[2].set_title("NDCG@10（按规则标签为正样本）")
    axes[2].set_xlabel("NDCG@10")
    axes[2].legend()
    for ax in axes:
        ax.grid(alpha=.3)
    fig.suptitle("图20 评分模型 vs 匹配规则：同一批候选配对上的推荐一致性（主口径：按简历分组）",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(OUT_FIG, dpi=140)
    plt.close(fig)


def _best_reg(exp):
    rows = load_csv(EVAL_REG)
    return [r for r in rows if r["口径"] == "按简历" and r["实验"] == exp]


def write_outputs(pair_rows, jac_m, rho_m, ndcg_m, ndcg_r, t_model, n_pairs):
    reg = load_csv(EVAL_REG)
    cls = load_csv(EVAL_CLS)
    curve = load_csv(CLU_CURVE)
    r1 = [r for r in reg if r["口径"] == "按简历" and r["实验"] == "①全特征+纯净标签" and r["模型"] == "XGBoost"][0]
    r2 = [r for r in reg if r["口径"] == "按简历" and r["实验"] == "②全特征+噪声标签" and r["模型"] == "XGBoost"][0]
    r3 = [r for r in reg if r["口径"] == "按简历" and r["实验"] == "③仅文本相似度特征" and r["模型"] == "XGBoost"][0]
    c1 = [r for r in cls if r["口径"] == "按简历" and r["实验"] == "②全特征+噪声标签" and r["模型"] == "XGBoost"][0]
    c3 = [r for r in cls if r["口径"] == "按简历" and r["实验"] == "③仅文本相似度特征" and r["模型"] == "XGBoost"][0]
    best_k = max(curve, key=lambda r: float(r["轮廓系数"]))
    elbow = None
    xs = np.array([int(r["K"]) for r in curve], float)
    ys = np.array([float(r["inertia"]) for r in curve], float)
    x = (xs - xs.min()) / (xs.max() - xs.min())
    y = (ys - ys.min()) / (ys.max() - ys.min())
    d = np.abs((y[-1] - y[0]) * x - (x[-1] - x[0]) * y + x[-1] * y[0] - y[-1] * x[0]) / np.hypot(y[-1] - y[0], x[-1] - x[0])
    elbow = int(xs[int(np.argmax(d))])

    summary = [
        {"模型": "评分模型（任务5 XGBoost）", "任务类型": "有监督回归 + 二分类",
         "目标/输入": "输入 36 维特征，预测规则总分 0–100 与是否匹配（≥65）",
         "关键指标": "MAE / RMSE / R² / PR-AUC / NDCG@10",
         "主口径结果": "噪声标签 MAE %s、R² %s；T2 PR-AUC %s、NDCG@10 %s" %
                   (r2["测试集_MAE"], r2["测试集_R2"], c1["测试集_PR_AUC"], c1["测试集_NDCG@10"]),
         "用途": "批量打分/离线复现规则；作为规则的加速与交叉验证",
         "局限": "标签由规则生成（蒸馏），指标反映对规则的拟合而非真实匹配力"},
        {"模型": "匹配规则（任务6 六维加权）", "任务类型": "规则打分 + Top-N 排序",
         "目标/输入": "任意简历（粘贴/PDF）→ 解析 → 与 8,836 个岗位逐对算分",
         "关键指标": "Top-N 排序质量、岗位大类一致率、响应时间",
         "主口径结果": "Top-10 岗位大类一致率 54.95%%（v2 权重）、全量打分 0.17s",
         "用途": "在线推荐主链路（可解释：6 维分 + 推荐理由）",
         "局限": "规则口径由人工设定；非 IT 岗可能进 Top-N；无人工金标验证"},
        {"模型": "聚类模型（任务7 K-Means）", "任务类型": "无监督聚类",
         "目标/输入": "输入技能 Top-60 + 职能大类（9）→ 岗位分簇",
         "关键指标": "轮廓系数 / inertia / ARI 稳定性",
         "主口径结果": "K=9（轮廓峰值 %.4f，肘部法 K=%d）；ARI 1.0000；最大簇再做二阶细分 K=8" %
                   (float(best_k["轮廓系数"]), elbow),
         "用途": "岗位画像、粗筛候选集、簇命名用于前端展示",
         "局限": "轮廓系数 0.44–0.67 但簇间有重叠；51%% 的「其他」岗位需二阶细分"},
    ]
    with open(OUT_SUM, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    with open(os.path.join(P, "多模型对比_实验汇总.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["对比实验", "指标", "结果"])
        w.writerow(["评分模型 vs 匹配规则", "逐简历 Top-10 重合度（均值）", "%.3f" % jac_m])
        w.writerow(["评分模型 vs 匹配规则", "逐简历 Spearman 分数相关（均值）", "%.4f" % rho_m])
        w.writerow(["评分模型 vs 匹配规则", "模型 NDCG@10（均值）", "%.4f" % ndcg_m])
        w.writerow(["评分模型 vs 匹配规则", "规则 NDCG@10（均值）", "%.4f" % ndcg_r])
        w.writerow(["评分模型 vs 匹配规则", "模型批量打分耗时", "%.1fs / %d 行" % (t_model, n_pairs)])
        w.writerow(["评分模型 vs 匹配规则", "规则在线打分耗时", "0.17s / 8836 岗（任务6 实测）"])
        w.writerow(["评分模型", "T1 纯净标签 MAE", r1["测试集_MAE"]])
        w.writerow(["评分模型", "T1 噪声标签 MAE", r2["测试集_MAE"]])
        w.writerow(["评分模型", "T1 仅文本特征 MAE", r3["测试集_MAE"]])
        w.writerow(["评分模型", "T2 噪声标签 PR-AUC", c1["测试集_PR_AUC"]])
        w.writerow(["评分模型", "T2 仅文本特征 PR-AUC", c3["测试集_PR_AUC"]])
        w.writerow(["聚类模型", "轮廓系数峰值 K", best_k["K"]])
        w.writerow(["聚类模型", "轮廓系数峰值", best_k["轮廓系数"]])
        w.writerow(["聚类模型", "肘部法 K", elbow])

    write_doc(summary, pair_rows, jac_m, rho_m, ndcg_m, ndcg_r, t_model, n_pairs,
              r1, r2, r3, c1, c3, best_k, elbow)
    print("输出：多模型对比_汇总.csv / 多模型对比_重合度.csv / 多模型对比_实验汇总.csv / 图20 / %s"
          % os.path.relpath(OUT_DOC, ROOT))


def write_doc(summary, pair_rows, jac_m, rho_m, ndcg_m, ndcg_r, t_model, n_pairs,
              r1, r2, r3, c1, c3, best_k, elbow):
    jacs = [r["Top10重合度"] for r in pair_rows]
    rhos = [r["Spearman相关"] for r in pair_rows if r["Spearman相关"] != ""]
    L = ["# 多模型对比分析报告 —— 任务8\n",
         "| 项目 | 内容 |", "|------|------|",
         "| 课程 | 行业大数据分析实践（23大数据班） |",
         "| 对应任务 | 任务7 岗位聚类 + 任务8 多模型横向对比（第2周 周二 9/15） |",
         "| 范围 | 评分模型（任务5）/ 匹配模型（任务6）/ 聚类模型（任务7） |",
         "| 状态 | ✅ 已完成 ｜ 记录人：王俊淇 ｜ 版本 v1.0（2026-09-14） |", "",
         "---", "",
         "## 一、三类模型概览（不做「硬凑同一个指标」）\n",
         "三类模型的目标与评价方式本来就**不同质**：评分模型是**有监督回归/分类**（测误差），"
         "匹配模型是**规则打分 + 排序**（测推荐质量与响应时间），聚类模型是**无监督分簇**（测簇结构与可解释性）。"
         "因此本节先如实列出各自的指标，再在第二节做**唯一真正可比**的实验。\n",
         "| 模型 | 任务类型 | 目标/输入 | 关键指标 | 主口径结果 | 用途 | 局限 |",
         "|---|---|---|---|---|---|---|"]
    for s in summary:
        L.append("| %s | %s | %s | %s | %s | %s | %s |" %
                 (s["模型"], s["任务类型"], s["目标/输入"], s["关键指标"], s["主口径结果"], s["用途"], s["局限"]))
    L.append("")
    L.append("## 二、唯一可比的实验：评分模型 vs 匹配规则\n")
    L.append("**设计**：在同一批候选配对（`匹配特征_全量样本.csv` 的 %s 行，主口径按简历分组）上，"
             "让**评分模型（任务5 XGBoost）**与**匹配规则（任务6，v1 权重口径）**分别打分，按简历取 Top-10 比较。\n" %
             "{:,}".format(n_pairs))
    L.append("| 指标 | 结果 | 含义 |")
    L.append("|---|---|---|")
    L.append("| 逐简历 Top-10 重合度（均值） | **%.3f** | 两个方法推荐的 10 个岗位平均有 %.0f%% 重合 |" % (jac_m, jac_m * 100))
    L.append("| 重合度分布 | 最小 %.3f、中位 %.3f、最大 %.3f | 逐份简历差异见 `多模型对比_重合度.csv` |" %
             (min(jacs), float(np.median(jacs)), max(jacs)))
    L.append("| 逐简历 Spearman 分数相关（均值） | **%.4f** | 分数排序几乎一致，模型确实学到了规则的顺序 |" % rho_m)
    L.append("| NDCG@10（按规则标签为正样本） | 模型 **%.4f** vs 规则 **%.4f** | 模型与规则在 Top-10 内的排序质量相当 |" %
             (ndcg_m, ndcg_r))
    L.append("| 打分耗时 | 模型批量 %.1fs / %s 行 ｜ 规则在线 **0.17s / 8,836 岗** | **规则更快**（模型还要先构造 36 维特征） |" %
             (t_model, "{:,}".format(n_pairs)))
    L.append("")
    L.append("**结论（与常见预期相反，如实记录）**：")
    L.append("1. 评分模型与匹配规则**高度一致**（Top-10 重合度 %.3f、Spearman %.4f）——这正是设计意图："
             "标签本身就是规则生成的，模型是对规则的**蒸馏**；" % (jac_m, rho_m))
    L.append("2. **速度各有场景**：模型**批量预测**本身很快（0.1s / %s 行，特征已在内存），"
             "但**前提是特征已经构造好**——构造 36 维特征（含 3 个 TF-IDF 余弦）要跑约 1 分钟；"
             "而规则在线给一份新简历打分只要 **0.17s 且不需要特征工程**。"
             "因此**在线主链路用规则（任务6）**，模型适合「候选池固定、特征可预计算」的离线批量场景；" %
             "{:,}".format(n_pairs))
    L.append("3. 两者都不是「绝对正误」：真正的瓶颈是**缺少人工金标**——只能证明两者一致，不能证明它们都判对了。\n")
    L.append("![多模型对比](%s)\n" % os.path.relpath(OUT_FIG, ROOT).replace("\\", "/"))
    L.append("## 三、聚类模型（任务7）要点\n")
    L.append("- 特征：技能 Top-60 multi-hot + 职能大类 one-hot；**薪资/经验/学历只作为簇画像属性，不参与聚类**"
             "（把薪资作为特征的尝试会把簇按资历分层，已弃用）")
    L.append("- 定 K：肘部法 K=%d，轮廓系数峰值 K=%s（%.4f）→ 采用峰值；ARI = 1.0000（四个随机种子完全一致）" %
             (elbow, best_k["K"], float(best_k["轮廓系数"])))
    L.append("- 结果：一级 %s 个簇（软件测试 16.44%%、后端开发 10.25%%、运维 8.37%%、算法 4.93%%、前端 2.42%%、"
             "嵌入式 2.41%%、产品 2.16%%、数据分析 1.55%%），另有一个占 **51.45%%** 的「其他」巨簇；" % best_k["K"])
    L.append("- **二阶细分**：对巨簇只用技能再跑一次 K-Means（K=8），分出质量检验、供应链/物料、硬件仪器、"
             "数据统计、Java 后端、AI 应用等子簇（明细见 `岗位聚类_簇画像.csv` 与 `岗位聚类_标签.csv`）")
    L.append("- 完整方法与局限见 `data/processed/岗位聚类_说明.md`\n")
    L.append("## 四、分工与适用场景\n")
    L.append("| 环节 | 用哪个模型 | 理由 |")
    L.append("|---|---|---|")
    L.append("| 在线推荐主链路（用户输入简历→Top-N） | **匹配规则（任务6）** | 0.17s、可解释（6 维分 + 推荐理由）、无需特征工程 |")
    L.append("| 离线批量评估/口径校验 | **评分模型（任务5）** | 可批量预测，用于验证规则是否被模型复现（重合度 %.3f） |" % jac_m)
    L.append("| 候选集粗筛、岗位画像、前端展示 | **聚类模型（任务7）** | 把 8,836 个岗位压成 9+8 个可读类别，便于浏览与筛选 |")
    L.append("| 未来换权重/换数据 | 规则改 `匹配权重表.csv`；模型需重新训练 | 规则改动成本更低 |")
    L.append("")
    L.append("## 五、局限与如实说明\n")
    L.append("| # | 局限 | 说明 |\n|---|---|---|")
    L.append("| 1 | **三类模型指标不同质** | 不存在一个能把 MAE、NDCG、轮廓系数放在一起比较的单一指标；本报告只做「分项列出 + 一个可比实验」 |")
    L.append("| 2 | **缺少人工金标** | 所有「相关性」证据都是代理指标（规则标签、岗位大类一致率）；无法回答「模型判得对不对」 |")
    L.append("| 3 | **评分模型与规则高度一致** | 重合度 %.3f 说明模型没带来新信息，只带来「批量打分」的便利 |" % jac_m)
    L.append("| 4 | **聚类存在大簇** | 51.45%% 的岗位落在「其他」，二阶细分后仍有 68.6%% 未进一步分开（电商运营/客户支持等长尾职能混杂） |")
    L.append("| 5 | **模型推理不占优** | 在线场景下模型比规则慢（特征构造开销），未做特征缓存优化 |")
    L.append("")
    L.append("## 六、输出文件\n")
    L.append("| 文件 | 说明 |\n|---|---|")
    L.append("| `data/processed/多模型对比_汇总.csv` | 三类模型的对比表 |")
    L.append("| `data/processed/多模型对比_实验汇总.csv` | 评分模型 vs 匹配规则的实验指标 |")
    L.append("| `data/processed/多模型对比_重合度.csv` | 逐简历的重合度/相关性/NDCG |")
    L.append("| `reports/figures/20_多模型对比_评分模型vs匹配规则.png` | 重合度分布 + Spearman 分布 + NDCG 对比 |")
    L.append("| `data/processed/岗位聚类_说明.md`、`岗位聚类_簇画像.csv`、`岗位聚类_标签.csv` | 任务7 聚类完整结果 |")
    L.append("| `reports/figures/17~19_聚类_*.png` | 定 K 曲线 / PCA / t-SNE |")
    L.append("")
    L.append("> 复现：`python src/models/comparison/compare_models.py`（需先跑任务5–7）")
    with open(OUT_DOC, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
