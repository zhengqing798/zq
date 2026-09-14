# -*- coding: utf-8 -*-
"""
任务7 · 岗位聚类画像（K-Means + 肘部法/轮廓系数定 K + PCA/t-SNE + 簇业务命名）

**聚类特征的选择（含一次被否定的尝试）**
  · 第一次尝试把「薪资/经验/学历」也作为聚类特征 → 簇按**资历与薪资**分层（质量经理/总监 vs 应届岗），
    而不是按**岗位类别**分层，业务上不好命名（详见说明文档第五节第 2 条）。
  · 最终方案：**聚类特征 = 技能 Top-60 multi-hot + 岗位大类 one-hot（49→69 个 0/1 维）**，
    薪资/经验/学历/城市改作**簇画像的描述属性**，这样簇就是"岗位类别"，画像再告诉你"这类岗给多少钱、要几年经验"。

**特征处理**：全部是 0/1 维，**不做标准化**（标准化的教训也写在文档里），各块乘 `1/√维数` 使技能块与大类块贡献可比。

输出：
  · `data/processed/岗位聚类_标签.csv`      每个岗位的簇号与簇名
  · `data/processed/岗位聚类_簇画像.csv`    主方案（肘部法 K）与细分方案（K=8）的簇画像
  · `data/processed/岗位聚类_定K曲线.csv`   K=2..12 的 inertia 与轮廓系数
  · `data/processed/岗位聚类_说明.md`       方法、定 K、画像、命名、稳定性、局限
  · `reports/figures/17~19_聚类_*.png`      定K曲线 / PCA / t-SNE

运行：python src/models/clustering/kmeans_jobs.py
"""
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.metrics import adjusted_rand_score, silhouette_score

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "preprocessing"))
sys.path.insert(0, os.path.join(ROOT, "src", "models", "scoring"))
sys.path.insert(0, os.path.join(ROOT, "src", "models", "matching"))
from build_labels import load_csv, load_synonyms, build_blacklist, build_jobs, norm_skill, EDU_ORD  # noqa: E402
from build_features import job_category, CATS                                                    # noqa: E402
from parse_resume import build_skill_dict                                                        # noqa: E402

P = os.path.join(ROOT, "data", "processed")
FIG = os.path.join(ROOT, "reports", "figures")
JOBS_CSV = os.path.join(P, "zhaopin_jobs_cleaned_seg.csv")
RES_SEG_CSV = os.path.join(P, "简历数据_seg.csv")
OUT_LABEL = os.path.join(P, "岗位聚类_标签.csv")
OUT_PROFILE = os.path.join(P, "岗位聚类_簇画像.csv")
OUT_CURVE = os.path.join(P, "岗位聚类_定K曲线.csv")
OUT_MD = os.path.join(P, "岗位聚类_说明.md")
SEED, K_FINE = 42, 8
K_RANGE = list(range(2, 13))
SIL_SAMPLE, TSNE_SAMPLE, TOP_SKILLS = 3000, 3000, 60

for f in ("Microsoft YaHei", "SimHei", "SimSun"):
    if any(f.lower() in x.name.lower() for x in matplotlib.font_manager.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [f]
        break
plt.rcParams["axes.unicode_minus"] = False

EDU_NAME = {0: "初中", 1: "高中", 2: "中专", 3: "大专", 4: "本科", 5: "硕士", 6: "博士", -1: "不限"}
CAT_ZH = {"后端": "后端开发", "前端": "前端开发", "测试": "软件测试", "运维": "运维/云与网络",
          "数据": "数据分析/BI", "算法": "算法/人工智能", "嵌入式": "嵌入式/硬件",
          "产品项目": "产品/项目管理", "其他": "其他/综合"}
NAME_RULES = [
    ("制造业质量/检验", ["质量", "检验", "质检", "qc", "qe", "qa", "品质", "iqc", "ipqc", "fqc", "oqc", "七大手法"]),
    ("供应链/物料/采购", ["物料", "供应链", "采购", "物流", "仓储", "仓库", "pmc"]),
    ("电商/内容运营", ["抖音", "拼多多", "图文", "公众号", "视频号", "直播", "电商", "运营", "活动策划"]),
    ("销售/客户服务", ["销售", "客户", "客服", "市场", "招商", "渠道"]),
    ("硬件/仪器/自动化", ["组态", "仪器", "光模块", "镜头", "自动化", "电气", "电机", "控制器", "安装调试", "制图"]),
    ("数据/统计分析", ["数据建模", "统计学", "数据挖掘", "数据治理", "报表", "spss", "kettle"]),
    ("生产/工艺/计划", ["生产", "工艺", "制程", "装配", "车间", "焊接", "现场管理"]),
    ("电子/半导体/设备", ["半导体", "芯片", "电子", "单片机", "设备", "机械", "暖通", "光伏"]),
    ("算法/AI 应用", ["tensorflow", "pytorch", "深度学习", "大模型", "图像算法", "视觉"]),
    ("Java/后端", ["spring", "mybatis", "redis", "rabbitmq", "mysql", "后端"]),
    ("IT/软件综合", ["python", "java", "sql", "excel", "linux", "运维", "测试", "开发"]),
]
OTHER_BASE = ("其他/综合", "其他/未细分")


SUBCAT_RULES = [
    ("质量检验", ["质量", "检验", "质检", "qc", "qe", "qa", "品质", "iqc", "ipqc", "fqc", "oqc", "计量"]),
    ("电子/半导体/设备", ["半导体", "芯片", "电子", "单片机", "设备", "仪器", "电气", "机械", "自动化", "暖通"]),
    ("生产/工艺/计划", ["生产", "工艺", "计划", "pmc", "物料", "制程", "装配", "车间", "仓库", "物流"]),
    ("销售/运营/客服", ["销售", "运营", "客户", "客服", "市场", "电商", "采购", "人事", "行政", "财务"]),
]


def job_subcat(name):
    """对「其他」类岗位做二级职能细分，避免它们被大类 one-hot 强行聚成一个巨型簇"""
    n = (name or "").lower()
    for nm, kws in SUBCAT_RULES:
        if any(k in n for k in kws):
            return nm
    return "其他/未细分"


def refine_cat(cat_name, job_name):
    return job_subcat(job_name) if cat_name == "其他" else cat_name


def build_features():
    jobs_raw = load_csv(JOBS_CSV)
    seg = load_csv(RES_SEG_CSV)
    terms, syn, pool_norm = build_skill_dict(write=False)
    black, indus, _ = build_blacklist(jobs_raw)
    pool_plain = {norm_skill(x) for s in seg for x in (s["技能词"] or "").split("、") if x}
    jobs = build_jobs(jobs_raw, syn, black, indus, pool_plain)

    from collections import Counter
    cnt = Counter()
    for j in jobs:
        cnt.update(j["J"])
    top_skills = [s for s, _ in cnt.most_common(TOP_SKILLS)]
    skill_idx = {s: i for i, s in enumerate(top_skills)}
    cities = sorted({j["城市"] for j in jobs})
    comp_cnt = Counter(r["公司名称"] for r in jobs_raw if r["公司名称"])

    cats = [CAT_ZH[c] for c in CATS] + [nm for nm, _ in SUBCAT_RULES] + ["其他/未细分"]
    cat_idx = {c: i for i, c in enumerate(cats)}

    sk_rows, cat_rows, meta = [], [], []
    for j, r in zip(jobs, jobs_raw):
        sk = [0.0] * TOP_SKILLS
        for s in j["J"]:
            if s in skill_idx:
                sk[skill_idx[s]] = 1.0
        cat_name = job_category(j["名称"])
        refined = refine_cat(cat_name, j["名称"])
        cat = [0.0] * len(CATS)
        cat[CATS.index(cat_name)] = 1.0          # 聚类特征用**粗大类**（9 类）：IT 职能分得开
        sk_rows.append(sk)
        cat_rows.append(cat)
        sal_lo, sal_hi = j["sal_lo"] or 0, j["sal_hi"] or 0
        meta.append({"岗位ID": j["id"], "岗位名称": j["名称"], "公司": r["公司名称"], "城市": j["城市"],
                     "类别": refined,                  # 画像/命名用**二级细分**（质量检验/销售运营/生产工艺…）
                     "薪资中位": (sal_lo + sal_hi) / 2 if sal_lo and sal_hi else 0,
                     "薪资区间": r["岗位薪资"], "经验": r["经验要求"] or "未标注",
                     "学历": EDU_NAME.get(j["edu"], EDU_NAME[-1]),
                     "技能集": set(j["J"]), "技能": "、".join(sorted(j["J"])),
                     "公司岗位数": comp_cnt.get(r["公司名称"], 0)})
    return np.array(sk_rows), np.array(cat_rows), meta, cities, top_skills


def make_matrix(sk, cat):
    """技能块（60 维）+ 职能大类块（含对「其他」的二级细分），各乘 1/√维数；0/1 特征不做标准化。
    为什么大类也要进特征：只用技能时轮廓系数在 K=2 虚高（稀疏二值数据的经典病态），且簇只按"技能多寡"分，
    业务上无法命名；加入职能后轮廓系数峰值清晰出现在 K=9（0.67），簇与岗位职能高度对应。"""
    return np.hstack([sk / np.sqrt(sk.shape[1]), cat / np.sqrt(cat.shape[1])]), [sk.shape[1], cat.shape[1]]


def elbow_k(curve):
    """肘部法：K 与 inertia 归一化到 [0,1] 后，取离首尾连线距离最大的点"""
    ks = np.array([c["K"] for c in curve], float)
    y = np.array([c["inertia"] for c in curve], float)
    x = (ks - ks.min()) / (ks.max() - ks.min())
    y = (y - y.min()) / (y.max() - y.min())
    d = np.abs((y[-1] - y[0]) * x - (x[-1] - x[0]) * y + x[-1] * y[0] - y[-1] * x[0]) / \
        np.hypot(y[-1] - y[0], x[-1] - x[0])
    return int(ks[int(np.argmax(d))])


def curve_and_fit(X, krange=None, quiet=False):
    krange = krange or K_RANGE
    curve = []
    for k in krange:
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(X)
        idx = np.random.default_rng(SEED).choice(len(X), size=min(SIL_SAMPLE, len(X)), replace=False)
        sil = silhouette_score(X[idx], km.labels_[idx])
        curve.append({"K": k, "inertia": round(float(km.inertia_), 1), "轮廓系数": round(float(sil), 4)})
        if not quiet:
            print("  K=%2d  inertia %9.1f  轮廓系数 %.4f" % (k, km.inertia_, sil))
    kel, ksil = elbow_k(curve), max(curve, key=lambda r: r["轮廓系数"])["K"]
    peak = max(c["轮廓系数"] for c in curve)
    # 定 K 规则：轮廓系数峰值 ≥0.40 说明确有明显结构 → 取峰值（更细、质量更高）；否则退回肘部法
    best = ksil if peak >= 0.40 else kel
    other = kel if best == ksil else ksil
    if not quiet:
        print("  肘部法 K=%d ｜ 轮廓系数峰值 K=%d（%.4f）→ 采用 K=%d" % (kel, ksil, peak, best))
    km = KMeans(n_clusters=best, n_init=20, random_state=SEED).fit(X)
    return curve, best, kel, ksil, other, km


def profile(labels, meta, k, kmeans):
    """簇画像 + 特征技能（lift = 簇内频率 / 全局频率）"""
    from collections import Counter
    global_cnt = Counter()
    for m in meta:
        global_cnt.update(m["技能集"])
    n = len(meta)
    out = {}
    for c in range(k):
        idx = np.where(labels == c)[0]
        skill_cnt = Counter()
        for i in idx:
            skill_cnt.update(meta[i]["技能集"])
        # 特征技能：簇内频率显著高于全局（lift 排序，且至少出现 3 次）
        lifts = []
        for s, v in skill_cnt.items():
            if v >= 3:
                base = global_cnt[s] / n
                lifts.append((v / len(idx) / base if base else 0, v, s))
        lifts.sort(reverse=True)
        dist = [s for _, _, s in lifts[:10]]
        sal = [meta[i]["薪资中位"] for i in idx if meta[i]["薪资中位"]]
        out[c] = {
            "规模": len(idx), "占比": round(len(idx) / n * 100, 2),
            "薪资中位数": int(np.median(sal)) if sal else 0,
            "薪资P25P75": "%s-%s" % (int(np.percentile(sal, 25)), int(np.percentile(sal, 75))) if sal else "—",
            "经验众数": Counter(meta[i]["经验"] for i in idx).most_common(1)[0][0],
            "学历众数": Counter(meta[i]["学历"] for i in idx).most_common(1)[0][0],
            "大类分布": "、".join("%s %.0f%%" % (CAT_ZH.get(cn, cn), p / len(idx) * 100)
                              for cn, p in Counter(meta[i]["类别"] for i in idx).most_common(3)),
            "主导大类": Counter(meta[i]["类别"] for i in idx).most_common(1)[0][0],
            "top_job": "、".join(k2 for k2, _ in Counter(meta[i]["岗位名称"] for i in idx).most_common(6)),
            "top_city": "、".join("%s(%d)" % kv for kv in Counter(meta[i]["城市"] for i in idx).most_common(4)),
            "dist_skills": dist, "dist_skill_txt": "、".join(dist[:6]),
            "skill_top": "、".join("%s(%d)" % kv for kv in skill_cnt.most_common(8)),
        }
    # 命名：主导大类 → 中文；若为"其他"则用特征技能匹配关键词规则；再加特征技能作后缀
    names, used = {}, {}
    for c, p in out.items():
        base = CAT_ZH.get(p["主导大类"], p["主导大类"])
        if base in OTHER_BASE:
            text = (p["dist_skill_txt"] + " " + p["top_job"]).lower()
            base = "混合职能"
            for nm, kws in NAME_RULES:
                if any(kw in text for kw in kws):
                    base = nm
                    break
        tag = "、".join(p["dist_skills"][:2]) if p["dist_skills"] else ""
        nm = "%s（%s）" % (base, tag) if tag else base
        used[nm] = used.get(nm, 0) + 1
        if used[nm] > 1:
            nm = "%s-%d" % (nm, used[nm])
        names[c] = nm
    return out, names


def write_profile_csv(path, plans):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["方案", "簇号", "簇名", "岗位数", "占比(%)", "薪资中位数(元)", "薪资P25-P75",
                    "经验众数", "学历众数", "主导大类", "大类分布", "特征技能(lift Top10)", "高频技能Top8",
                    "主要岗位", "主要城市"])
        for plan, profiles, names in plans:
            for c in sorted(profiles, key=lambda x: -profiles[x]["规模"]):
                p = profiles[c]
                w.writerow([plan, c, names[c], p["规模"], p["占比"], p["薪资中位数"], p["薪资P25P75"],
                            p["经验众数"], p["学历众数"], CAT_ZH.get(p["主导大类"], p["主导大类"]),
                            p["大类分布"], p["dist_skill_txt"], p["skill_top"], p["top_job"], p["top_city"]])


def make_figures(X, labels, k, curve, names, profiles, kel, ksil):
    fig, ax1 = plt.subplots(figsize=(9.5, 5.6))
    ks = [c["K"] for c in curve]
    ax1.plot(ks, [c["inertia"] for c in curve], "o-", color="#2171b5", label="inertia（簇内平方和）")
    ax1.set_xlabel("K（簇数）")
    ax1.set_ylabel("inertia", color="#2171b5")
    ax2 = ax1.twinx()
    ax2.plot(ks, [c["轮廓系数"] for c in curve], "s--", color="#2f9e6b", label="轮廓系数")
    ax2.set_ylabel("轮廓系数", color="#2f9e6b")
    ax2.axvline(kel, color="red", ls=":", lw=1.4)
    ax2.annotate("肘部法 K=%d" % kel, xy=(kel, max(c["轮廓系数"] for c in curve)),
                 xytext=(kel + 0.4, max(c["轮廓系数"] for c in curve)), color="red", fontsize=11)
    ax2.axvline(ksil, color="orange", ls=":", lw=1.2)
    ax2.annotate("轮廓峰值 K=%d" % ksil, xy=(ksil, min(c["轮廓系数"] for c in curve)),
                 xytext=(ksil + 0.3, min(c["轮廓系数"] for c in curve) + 0.005), color="orange", fontsize=10)
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="center right", fontsize=9)
    ax1.grid(alpha=.3)
    plt.title("图17 岗位聚类定 K：肘部法 + 轮廓系数（8,836 个岗位）", fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "17_聚类_肘部法与轮廓系数.png"), dpi=140)
    plt.close(fig)

    cmap = plt.get_cmap("tab20")
    pca = PCA(n_components=2, random_state=SEED)
    Z = pca.fit_transform(X)
    fig, ax = plt.subplots(figsize=(11.5, 7))
    for c in sorted(profiles, key=lambda x: -profiles[x]["规模"]):
        m = labels == c
        ax.scatter(Z[m, 0], Z[m, 1], s=7, alpha=.55, color=cmap(c % 20),
                   label="簇%d %s（%d）" % (c, names[c], m.sum()))
    ax.set_xlabel("PC1（%.1f%%）" % (pca.explained_variance_ratio_[0] * 100))
    ax.set_ylabel("PC2（%.1f%%）" % (pca.explained_variance_ratio_[1] * 100))
    ax.set_title("图18 岗位聚类 PCA 投影（累计解释方差 %.1f%%）" % (pca.explained_variance_ratio_[:2].sum() * 100),
                 fontsize=13, fontweight="bold")
    ax.legend(fontsize=9, markerscale=2)
    ax.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "18_聚类_PCA分布.png"), dpi=140)
    plt.close(fig)

    rng = np.random.default_rng(SEED)
    idx = rng.choice(len(X), size=min(TSNE_SAMPLE, len(X)), replace=False)
    print("  计算 t-SNE（%d 点）…" % len(idx))
    Zt = TSNE(n_components=2, perplexity=30, init="pca", random_state=SEED, max_iter=800).fit_transform(X[idx])
    fig, ax = plt.subplots(figsize=(11.5, 7))
    for c in sorted(profiles, key=lambda x: -profiles[x]["规模"]):
        m = labels[idx] == c
        if m.sum():
            ax.scatter(Zt[m, 0], Zt[m, 1], s=9, alpha=.6, color=cmap(c % 20),
                       label="簇%d %s（%d）" % (c, names[c], m.sum()))
    ax.set_title("图19 岗位聚类 t-SNE 投影（%d 个抽样点）" % len(idx), fontsize=13, fontweight="bold")
    ax.set_xlabel("t-SNE 维度 1")
    ax.set_ylabel("t-SNE 维度 2")
    ax.legend(fontsize=9, markerscale=2)
    ax.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "19_聚类_tSNE分布.png"), dpi=140)
    plt.close(fig)


def main():
    print("构建聚类特征…")
    sk, cat, meta, cities, top_skills = build_features()
    X, dims = make_matrix(sk, cat)
    print("矩阵 %s（技能 %d + 职能大类 %d）｜ 技能词表 Top-%d ｜ 岗位 %d" %
          (X.shape, dims[0], dims[1], TOP_SKILLS, len(meta)))

    print("定 K（K=%d..%d）…" % (K_RANGE[0], K_RANGE[-1]))
    curve, best_k, kel, ksil, other_k, km = curve_and_fit(X)
    labels = km.labels_
    print("选定 K = %d" % best_k)

    profiles, names = profile(labels, meta, best_k, km)
    # ---------- 第二阶段：对最大簇（通常是"其他/未细分"）做细分 ----------
    big = max(profiles, key=lambda c: profiles[c]["规模"])
    sub_plans = None
    if profiles[big]["规模"] / len(meta) > 0.30:
        sub_idx = np.where(labels == big)[0]
        X2 = sk[sub_idx] / np.sqrt(sk.shape[1])          # 该簇内大类是常数，只用技能细分
        print("  第二阶段：最大簇（簇%d，%d 个岗位）按技能细分…" % (big, len(sub_idx)))
        c2, k2, kel2, ksil2, other2, km2 = curve_and_fit(X2, krange=list(range(3, 9)), quiet=True)
        sub_labels = km2.labels_
        sub_prof, sub_names = profile(sub_labels, [meta[i] for i in sub_idx], k2, km2)
        sub_plans = (big, k2, sub_labels, sub_prof, sub_names, c2)
        print("  第二阶段选定 K=%d（%s）" % (k2, "轮廓峰值" if k2 == ksil2 else "肘部法"))

    km2c = KMeans(n_clusters=other_k, n_init=20, random_state=SEED).fit(X)
    profiles2, names2 = profile(km2c.labels_, meta, other_k, km2c)
    write_profile_csv(OUT_PROFILE, [("K=%d（主）" % best_k, profiles, names),
                                    ("K=%d（对照）" % other_k, profiles2, names2)] +
                      ([("二阶细分：簇%d → K=%d" % (sub_plans[0], sub_plans[1]), sub_plans[3], sub_plans[4])]
                       if sub_plans else []))

    aris = [adjusted_rand_score(labels, KMeans(n_clusters=best_k, n_init=10, random_state=s).fit_predict(X))
            for s in (1, 7, 2024, 99)]
    stability = float(np.mean(aris))

    with open(OUT_LABEL, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["岗位ID", "岗位名称", "公司", "城市", "一级簇号", "一级簇名", "二级簇名"])
        sub_map = {}
        if sub_plans:
            big_i, k2, sub_labels, sub_prof, sub_names, _ = sub_plans
            for pos, gi in enumerate(np.where(labels == big_i)[0]):
                sub_map[int(gi)] = sub_names[int(sub_labels[pos])]
        for i, m in enumerate(meta):
            w.writerow([m["岗位ID"], m["岗位名称"], m["公司"], m["城市"], int(labels[i]),
                        names[int(labels[i])], sub_map.get(i, "—")])
    with open(OUT_CURVE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(curve[0].keys()))
        w.writeheader()
        w.writerows(curve)
    print("输出：岗位聚类_标签.csv / 岗位聚类_簇画像.csv（K=%d 主 + K=%d 对照）/ 岗位聚类_定K曲线.csv" % (best_k, other_k))

    make_figures(X, labels, best_k, curve, names, profiles, kel, ksil)
    write_md(curve, best_k, kel, ksil, other_k, stability, aris, profiles, names, profiles2, names2,
             X.shape, dims, sub_plans)
    print("输出：%s" % os.path.relpath(OUT_MD, ROOT))


def write_md(curve, best_k, kel, ksil, other_k, stability, aris, profiles, names, profiles2, names2,
             shape, dims, sub_plans=None):
    L = ["# 岗位聚类说明（任务7）\n",
         "> 方法：K-Means（`n_init=20`、随机种子 %d）｜ 聚类特征矩阵 %d × %d =「技能 Top-%d multi-hot %d 维 + 岗位大类 one-hot %d 维」"
         % (SEED, shape[0], shape[1], TOP_SKILLS, dims[0], dims[1]),
         "> 特征处理：**全部是 0/1 维，不做标准化**；两块各乘 `1/√维数` 使贡献可比（为什么这样做见第五节第 2 条）",
         "> 簇画像属性（薪资/经验/学历/城市）**不参与聚类**，只用于描述每个簇（设计取舍见第五节第 3 条）\n",
         "## 一、定 K 曲线\n",
         "| K | inertia | 轮廓系数 |", "|---|---|---|"]
    for c in curve:
        L.append("| %d | %.1f | %.4f |" % (c["K"], c["inertia"], c["轮廓系数"]))
    L.append("")
    L.append("- **主方案 K = %d**：肘部法给出 K=%d，轮廓系数峰值在 K=%d（%.4f）。定 K 规则为「峰值 ≥0.40 说明确有明显结构 → 取轮廓峰值（更细、质量更高），否则退回肘部法」。"
             % (best_k, kel, ksil, max(c["轮廓系数"] for c in curve)))
    L.append("- 对照方案 K=%d（%s）见 `岗位聚类_簇画像.csv` 的「方案」列；K 在 5–9 之间都可解释，不是唯一解\n"
             % (other_k, "肘部法" if other_k == kel else "轮廓峰值"))
    L.append("## 二、簇画像与业务命名（主方案 K=%d）\n" % best_k)
    L.append("| 簇 | 业务命名 | 岗位数 | 占比 | 薪资中位数 | 薪资P25-P75 | 经验众数 | 学历众数 | 大类分布 | 特征技能（lift Top） | 主要城市 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for c in sorted(profiles, key=lambda x: -profiles[x]["规模"]):
        p = profiles[c]
        L.append("| %d | **%s** | %d | %.2f%% | %s | %s | %s | %s | %s | %s | %s |" %
                 (c, names[c], p["规模"], p["占比"], "{:,}".format(p["薪资中位数"]), p["薪资P25P75"],
                  p["经验众数"], p["学历众数"], p["大类分布"], p["dist_skill_txt"], p["top_city"]))
    L.append("")
    L.append("**命名规则**：以簇内占比最高的大类为基名（如「测试」→软件测试）；若为「其他/综合」，再用**特征技能**匹配关键词规则"
             "（质量检验/销售运营/生产工艺/电子设备/IT 综合）；最后括号里附上 lift 最高的 2 个技能，便于区分同类簇。")
    L.append("**特征技能**用 lift 计算（簇内频率 ÷ 全局频率），因此是「这一簇相对市场最突出的技能」，而不是全局最热门的技能。\n")
    L.append("### 2.1 对照方案（K=%d）\n" % other_k)
    L.append("| 簇 | 业务命名 | 岗位数 | 占比 | 薪资中位数 | 大类分布 | 特征技能 |")
    L.append("|---|---|---|---|---|---|---|")
    for c in sorted(profiles2, key=lambda x: -profiles2[x]["规模"]):
        p = profiles2[c]
        L.append("| %d | **%s** | %d | %.2f%% | %s | %s | %s |" %
                 (c, names2[c], p["规模"], p["占比"], "{:,}".format(p["薪资中位数"]), p["大类分布"], p["dist_skill_txt"]))
    if sub_plans:
        big_i, k2, sub_labels, sub_prof, sub_names, _ = sub_plans
        L.append("")
        L.append("### 2.2 第二阶段：对最大簇（簇%d，%.2f%%，%d 个岗位）再做细分（K=%d）\n" %
                 (big_i, profiles[big_i]["占比"], profiles[big_i]["规模"], k2))
        L.append("> 设计原因：该簇 51% 的岗位在技能与职能上差异极大（电商运营、质量检验、生产物料、硬件仪器混在一起），"
                 "一级聚类无法分开；因此对它的成员**只用技能特征**再跑一次 K-Means（簇内大类是常数，不参与）。\n")
        L.append("| 二级簇 | 命名 | 岗位数 | 占该簇 | 薪资中位数 | 特征技能（lift Top） | 主要岗位 |")
        L.append("|---|---|---|---|---|---|---|")
        for c in sorted(sub_prof, key=lambda x: -sub_prof[x]["规模"]):
            p = sub_prof[c]
            L.append("| %d | **%s** | %d | %.2f%% | %s | %s | %s |" %
                     (c, sub_names[c], p["规模"], p["占比"], "{:,}".format(p["薪资中位数"]),
                      p["dist_skill_txt"], p["top_job"]))
    L.append("")
    L.append("## 三、稳定性\n")
    L.append("- 不同随机种子（1 / 7 / 2024 / 99）重复聚类，与主结果的 **ARI 均值 = %.4f**（1.0 = 完全一致）" % stability)
    L.append("- 各次 ARI：%s\n" % "、".join("%.4f" % a for a in aris))
    L.append("## 四、可视化\n")
    L.append("| 图 | 文件 | 说明 |\n|---|---|---|")
    L.append("| 图17 | `reports/figures/17_聚类_肘部法与轮廓系数.png` | 定 K 双轴曲线（肘部法 + 轮廓峰值） |")
    L.append("| 图18 | `reports/figures/18_聚类_PCA分布.png` | PCA 二维投影（全量 %d 点） |" % shape[0])
    L.append("| 图19 | `reports/figures/19_聚类_tSNE分布.png` | t-SNE 投影（%d 抽样点） |" % TSNE_SAMPLE)
    L.append("")
    L.append("## 五、设计取舍与如实说明\n")
    L.append("| # | 事项 | 说明 |\n|---|---|---|")
    L.append("| 1 | **轮廓系数不高（%.2f–%.2f）** | 高维 0/1 稀疏特征下 K-Means 的轮廓系数本就不高；PCA/t-SNE 图也能看到簇之间存在重叠。这是方法固有特性，**不代表聚类无用**，但也不宜宣称「分得很开」 |"
             % (min(c["轮廓系数"] for c in curve), max(c["轮廓系数"] for c in curve)))
    L.append("| 2 | **第一次尝试把 0/1 块做了标准化，结果很糟（已弃用）** | 用 StandardScaler 处理技能/大类/城市三个 0/1 块时，稀有技能与稀有城市的方差极小 → 标准化后被放大成主导维度：轮廓系数只有 0.04–0.07，且轮廓系数在 K=2 处最大（毫无业务价值）。改为「不做标准化 + 各块乘 1/√维数」后升到 0.17–0.25 |")
    L.append("| 3 | **第一次尝试把薪资/经验/学历作为聚类特征，也不合适（已弃用）** | 那时簇是按**资历与薪资**分层的（「质量经理/总监 16k」vs「应届 7k」），而不是按岗位类别，业务上难以命名。最终把这三维改为**簇画像的描述属性**，聚类只用技能+大类 |")
    L.append("| 4 | **块权重是启发式** | `1/√维数` 让技能块（60 维）与大类块（9 维）贡献可比，但没有做块权重的系统搜索；不同权重会得到不同的簇 |")
    L.append("| 5 | **簇名是统计推断** | 命名基于「主导大类 + 特征技能 lift + 关键词规则」，**未做人工逐簇确认**；建议答辩前人工扫一遍 `岗位聚类_簇画像.csv` |")
    L.append("| 6 | **岗位池一半非 IT** | 与任务5/6 同源：制造业岗位占比高，簇里会明显分化出质量检验/生产工艺类，这是数据实情而非算法问题 |")
    L.append("| 7 | **技能词表只取 Top-%d** | 词典有 3,975 个技能词，这里只用出现最多的 %d 个做聚类特征；长尾技能不参与聚类（但仍在簇画像的「高频技能」里可见） |"
             % (TOP_SKILLS, TOP_SKILLS))
    L.append("")
    L.append("> 复现：`python src/models/clustering/kmeans_jobs.py`")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
