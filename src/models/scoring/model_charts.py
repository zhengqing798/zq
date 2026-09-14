# -*- coding: utf-8 -*-
"""
任务5 · 步骤5：模型评估出图（5 张，matplotlib）

输出（reports/figures/）：
  · `12_模型对比_柱状图.png`            2 口径 × 2 任务 × 各对照实验的指标对比
  · `13_预测vs真实_散点图.png`          纯净标签 vs 噪声标签（XGBoost，主口径测试集）
  · `14_残差分布_直方图.png`            4 个回归模型的残差分布（主口径测试集）
  · `15_特征重要性Top15_横向柱状图.png` XGBoost 回归模型（主口径、噪声标签）
  · `16_分类PR曲线_折线图.png`          4 个分类模型的 PR 曲线（主口径测试集）

说明：图 12 数据直接读 `模型评估结果_*.csv`；图 13/14/16 需要在内存里重训对应模型
（沿用 `models/模型元数据.json` 里选出的超参数，种子固定，结果与步骤4 一致）。

运行：python src/models/scoring/model_charts.py
"""
import json
import os
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (average_precision_score, mean_absolute_error, mean_squared_error,
                             precision_recall_curve, r2_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR, LinearSVC

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
P = os.path.join(ROOT, "data", "processed")
FIG = os.path.join(ROOT, "reports", "figures")
os.makedirs(FIG, exist_ok=True)

SEED = 42
SVR_SUB = 20000
TEXT_FEATS = ["岗位名称与期望岗位相似度", "描述与简历文本相似度", "描述与技能特长相似度"]

# 中文字体
for f in ("Microsoft YaHei", "SimHei", "SimSun"):
    if any(f.lower() in x.name.lower() for x in matplotlib.font_manager.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [f]
        break
else:
    print("⚠ 未找到中文字体，图上中文可能显示为方块")
plt.rcParams["axes.unicode_minus"] = False

EXP1, EXP2, EXP3 = "①全特征+纯净标签", "②全特征+噪声标签", "③仅文本相似度特征"
C1, C2 = "按简历", "按岗位"


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def load():
    feat = pd.read_csv(os.path.join(P, "匹配特征_全量样本.csv"), encoding="utf-8-sig")
    cols = pd.read_csv(os.path.join(P, "匹配特征_列清单.csv"), encoding="utf-8-sig")
    feats = cols.loc[cols["类型"] == "特征", "列名"].tolist()
    sp = pd.read_csv(os.path.join(P, "匹配样本_划分_按简历.csv"), encoding="utf-8-sig")
    df = feat.merge(sp, on=["简历ID", "岗位ID"], how="left", validate="one_to_one")
    meta = json.load(open(os.path.join(ROOT, "models", "模型元数据.json"), encoding="utf-8"))
    return df, feats, meta


def fig12_compare():
    reg = pd.read_csv(os.path.join(P, "模型评估结果_回归.csv"), encoding="utf-8-sig")
    cls = pd.read_csv(os.path.join(P, "模型评估结果_分类.csv"), encoding="utf-8-sig")
    t1_models = ["均值基线", "线性回归", "SVR", "随机森林", "XGBoost"]
    t2_models = ["随机基线", "逻辑回归", "LinearSVC", "随机森林", "XGBoost"]
    fig, axes = plt.subplots(2, 2, figsize=(15, 9.5))
    for r, crit in enumerate((C1, C2)):
        # T1
        ax = axes[r][0]
        w = 0.26
        for k, exp in enumerate((EXP1, EXP2, EXP3)):
            v = [reg[(reg.口径 == crit) & (reg.实验 == exp) & (reg.模型 == m)]["测试集_MAE"].mean()
                 for m in t1_models]
            pos = np.arange(len(t1_models)) + (k - 1) * w
            b = ax.bar(pos, v, w, label=exp)
            ax.bar_label(b, fmt="%.2f", fontsize=8, padding=1)
        ax.set_xticks(range(len(t1_models)))
        ax.set_xticklabels(t1_models, fontsize=10)
        ax.set_ylabel("测试集 MAE（分，越低越好）")
        ax.set_title("T1 回归：%s口径" % crit)
        ax.grid(axis="y", alpha=.3)
        ax.legend(fontsize=8)
        # T2
        ax = axes[r][1]
        w = 0.35
        for k, exp in enumerate((EXP2, EXP3)):
            v = [cls[(cls.口径 == crit) & (cls.实验 == exp) & (cls.模型 == m)]["测试集_PR_AUC"].mean()
                 for m in t2_models]
            pos = np.arange(len(t2_models)) + (k - 0.5) * w
            b = ax.bar(pos, v, w, label=exp)
            ax.bar_label(b, fmt="%.3f", fontsize=8, padding=1)
        ax.set_xticks(range(len(t2_models)))
        ax.set_xticklabels(t2_models, fontsize=10)
        ax.set_ylabel("测试集 PR-AUC（越高越好）")
        ax.set_title("T2 二分类（阈值 ≥65）：%s口径" % crit)
        ax.grid(axis="y", alpha=.3)
        ax.legend(fontsize=8)
    fig.suptitle("图12 模型指标对比（测试集；主口径=按简历，对照口径=按岗位）", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(os.path.join(FIG, "12_模型对比_柱状图.png"), dpi=140)
    plt.close(fig)
    log("图12 完成")


def fit_t1(df, feats, meta, target, model_names=("线性回归", "SVR", "随机森林", "XGBoost")):
    tr = df[df.数据集 == "train"]
    te = df[df.数据集 == "test"]
    bp = meta[C1]["最优超参数"]
    out = {}
    sub = tr.sample(n=min(SVR_SUB, len(tr)), random_state=SEED)
    for m in model_names:
        if m == "线性回归":
            est = make_pipeline(StandardScaler(), LinearRegression())
            est.fit(tr[feats], tr[target])
        elif m == "SVR":
            est = make_pipeline(StandardScaler(), SVR(kernel="rbf", C=10.0, epsilon=1.0, gamma="scale"))
            est.fit(sub[feats], sub[target])
        elif m == "随机森林":
            est = RandomForestRegressor(n_estimators=150, min_samples_leaf=1, random_state=SEED,
                                        n_jobs=-1, **bp["T1_RF"]).fit(tr[feats], tr[target])
        else:
            est = xgb.XGBRegressor(n_estimators=300, max_depth=6, subsample=0.8, colsample_bytree=0.8,
                                   tree_method="hist", random_state=SEED, n_jobs=-1, verbosity=0,
                                   **bp["T1_XGB"]).fit(tr[feats], tr[target])
        out[m] = est.predict(te[feats])
        log("  重训 T1 %s 完成（目标 %s）" % (m, target))
    return te[target].to_numpy(dtype=float), out


def fig13_scatter(df, feats, meta):
    yc, pc = fit_t1(df, feats, meta, "总分_规则", ("XGBoost",))
    yn, pn = fit_t1(df, feats, meta, "总分(0-100)", ("XGBoost",))
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.2))
    for ax, (y, p, title) in zip(axes, ((yc, pc["XGBoost"], "① 纯净标签（规则分，无噪声）"),
                                        (yn, pn["XGBoost"], "② 噪声标签（最终标签，10% 配对加噪）"))):
        hb = ax.hexbin(y, p, gridsize=45, cmap="viridis", mincnt=1, bins="log")
        ax.plot([0, 100], [0, 100], "r--", lw=1.2, label="理想线 y=x")
        ax.set_xlabel("真实分")
        ax.set_ylabel("预测分（XGBoost）")
        ax.set_title("%s\nMAE %.3f ｜ RMSE %.3f ｜ R² %.4f" %
                     (title, mean_absolute_error(y, p), mean_squared_error(y, p) ** .5, r2_score(y, p)))
        ax.legend(loc="upper left", fontsize=9)
        ax.grid(alpha=.3)
        fig.colorbar(hb, ax=ax, label="配对数量（对数色阶）")
    fig.suptitle("图13 预测值 vs 真实值（主口径测试集，%d 个配对）" % len(yc), fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(FIG, "13_预测vs真实_散点图.png"), dpi=140)
    plt.close(fig)
    log("图13 完成")


def fig14_residual(df, feats, meta):
    y, preds = fit_t1(df, feats, meta, "总分(0-100)")
    fig, ax = plt.subplots(figsize=(12, 6.2))
    for m, p in preds.items():
        r = p - y
        ax.hist(r, bins=80, histtype="step", lw=1.8,
                label="%s（MAE %.3f ｜ 标准差 %.2f）" % (m, mean_absolute_error(y, p), r.std()))
    ax.axvline(0, color="k", ls="--", lw=1)
    ax.set_xlabel("残差 = 预测分 − 真实分（分）")
    ax.set_ylabel("配对数")
    ax.set_yscale("log")
    ax.set_title("图14 残差分布（主口径测试集；对数纵轴便于看清尾部）\n"
                 "标签含 10% 噪声，残差离散度已接近噪声下限", fontsize=13, fontweight="bold")
    ax.grid(alpha=.3)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "14_残差分布_直方图.png"), dpi=140)
    plt.close(fig)
    log("图14 完成")


def fig15_importance():
    imp = pd.read_csv(os.path.join(P, "模型特征重要性.csv"), encoding="utf-8-sig")
    d = imp[(imp.口径 == C1) & (imp.任务 == "T1回归") & (imp.实验 == EXP2) & (imp.模型 == "XGBoost")]
    d = d.sort_values("重要性", ascending=False).head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(11, 7))
    b = ax.barh(d.特征, d.重要性, color="#4C78A8")
    ax.bar_label(b, fmt="%.3f", fontsize=9, padding=2)
    ax.set_xlabel("特征重要性（XGBoost gain 归一化）")
    ax.set_title("图15 特征重要性 Top15（XGBoost 回归 · 主口径 · 噪声标签）\n"
                 "前四位是经验与地域类特征，技能类仅排第 10", fontsize=13, fontweight="bold")
    ax.grid(axis="x", alpha=.3)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "15_特征重要性Top15_横向柱状图.png"), dpi=140)
    plt.close(fig)
    log("图15 完成")


def fig16_pr(df, feats, meta):
    tr = df[df.数据集 == "train"]
    te = df[df.数据集 == "test"]
    bp = meta[C1]["最优超参数"]
    y = te["是否匹配"].to_numpy()
    pos_w = float((tr["是否匹配"] == 0).sum() / max((tr["是否匹配"] == 1).sum(), 1))
    models = {
        "逻辑回归": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced",
                                                                      random_state=SEED)),
        "LinearSVC": make_pipeline(StandardScaler(), LinearSVC(class_weight="balanced", random_state=SEED)),
        "随机森林": RandomForestClassifier(n_estimators=150, min_samples_leaf=1,
                                          class_weight="balanced_subsample", random_state=SEED,
                                          n_jobs=-1, **bp["T2_RF"]),
        "XGBoost": xgb.XGBClassifier(n_estimators=300, max_depth=6, subsample=0.8, colsample_bytree=0.8,
                                     tree_method="hist", scale_pos_weight=pos_w, random_state=SEED,
                                     n_jobs=-1, verbosity=0, **bp["T2_XGB"]),
    }
    fig, ax = plt.subplots(figsize=(9.5, 7))
    for name, m in models.items():
        m.fit(tr[feats], tr["是否匹配"])
        s = m.predict_proba(te[feats])[:, 1] if hasattr(m, "predict_proba") else m.decision_function(te[feats])
        pr, rc, _ = precision_recall_curve(y, s)
        ax.plot(rc, pr, lw=1.9, label="%s（AP=%.3f）" % (name, average_precision_score(y, s)))
        log("  重训 T2 %s 完成" % name)
    ax.axhline(y.mean(), color="gray", ls="--", lw=1.2, label="随机基线（正样本率 %.3f）" % y.mean())
    ax.set_xlabel("召回率 Recall")
    ax.set_ylabel("精确率 Precision")
    ax.set_title("图16 分类 PR 曲线（主口径测试集，正样本 %d / %d = %.1f%%）" %
                 (y.sum(), len(y), y.mean() * 100), fontsize=13, fontweight="bold")
    ax.grid(alpha=.3)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "16_分类PR曲线_折线图.png"), dpi=140)
    plt.close(fig)
    log("图16 完成")


def main():
    df, feats, meta = load()
    log("数据 %s ｜ 特征 %d" % (df.shape, len(feats)))
    fig12_compare()
    fig13_scatter(df, feats, meta)
    fig14_residual(df, feats, meta)
    fig15_importance()
    fig16_pr(df, feats, meta)
    print("\n输出目录：%s" % FIG)
    for f in sorted(os.listdir(FIG)):
        if f.startswith(("12_", "13_", "14_", "15_", "16_")):
            print("  %-46s %6.0f KB" % (f, os.path.getsize(os.path.join(FIG, f)) / 1024))


if __name__ == "__main__":
    main()
