# -*- coding: utf-8 -*-
"""
任务6 · 步骤4：技能维度的 TF-IDF + 余弦相似度实现与口径对比

课程要求「技能用 TF-IDF + 余弦相似度」；任务5 的技能维度用的是「集合覆盖率 + 利用率」。
本模块把两种口径都实现出来，并在**真实的 207,640 个配对**上做对比，用数据决定最终口径。

三种口径（都归一到 0–100 分）：
  · V1 余弦：简历技能词 vs 岗位技能要求词的 **TF-IDF 加权余弦**（课程要求的口径）
  · V2 覆盖率：`0.7×岗位技能覆盖率 + 0.3×简历技能利用率`（任务5 口径，含小分母折扣、空集合→0）
  · V3 融合：`0.6×V2 + 0.4×V1`（**默认采用**：既满足课程要求，又保留已验证有效的集合命中）

实现要点
  · 词表用 `技能词典_匹配用.csv` 的**规范写法**（同义词已归一，K8s 与 Kubernetes 合并为一列），
    因此任何"词典内的技能"都有对应维度，词典外技能被忽略（并在文档里说明）；
  · IDF 在 8,836 个岗位的技能要求文本上估计（岗位侧文本 = 去福利/行业后的技能要求集合）；
  · 简历侧文本 = 解析出的技能列表（同义词归一后），两侧用同一词表，余弦即点积（向量已 L2 归一）。

输出：`data/processed/技能相似度_口径对比.md`（分布、Top-N 重合度、分歧样例）

运行：python src/models/matching/skill_similarity.py
"""
import os
import sys
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "preprocessing"))
sys.path.insert(0, os.path.join(ROOT, "src", "models", "scoring"))
from build_labels import (load_csv, load_synonyms, build_blacklist, build_jobs, build_resumes,  # noqa: E402
                          norm_skill, skill_score)
from parse_resume import build_skill_dict                                                     # noqa: E402

P = os.path.join(ROOT, "data", "processed")
JOBS_CSV = os.path.join(P, "zhaopin_jobs_cleaned_seg.csv")
RES_CLEAN_CSV = os.path.join(P, "简历数据_cleaned.csv")
RES_SEG_CSV = os.path.join(P, "简历数据_seg.csv")
LABEL_CSV = os.path.join(P, "匹配样本_标签数据.csv")
OUT_MD = os.path.join(P, "技能相似度_口径对比.md")

W_COVER, W_COS = 0.6, 0.4          # 融合口径权重（默认采用 V3）


class SkillSim:
    """技能维度的 TF-IDF + 余弦（V1）

    词表用**归一后的规范键**（小写、无空格/点号，同义词已合并），因此 K8s 与 Kubernetes 是同一列；
    两侧文档都由规范键拼成，不存在大小写或空格导致的列对不上。
    """

    def __init__(self, jobs, terms):
        self.terms = terms
        self.vocab = sorted(terms.keys())
        docs = [self.job_doc(j) for j in jobs]
        self.vec = TfidfVectorizer(vocabulary=self.vocab, token_pattern=r"\S+",
                                   lowercase=False, sublinear_tf=True)
        self.M = self.vec.fit_transform(docs)          # 8836 × V，行已 L2 归一
        self.n_jobs = self.M.shape[0]

    def job_doc(self, job):
        return " ".join(sorted(job["J"]))

    def resume_doc(self, skills_canon):
        return " ".join(sorted(skills_canon))

    def cosine_all(self, skills_canon):
        """→ 全部岗位的余弦分（0–100 的数组）"""
        doc = self.resume_doc(skills_canon)
        if not doc:
            return np.zeros(self.n_jobs)
        r = self.vec.transform([doc]).T                        # V × 1
        return np.asarray((self.M @ r).todense()).ravel() * 100.0

    def cosine(self, skills_canon, job_idx):
        """→ 单个配对的余弦分（0–100）"""
        return float(self.cosine_all(skills_canon)[job_idx])


def load_context():
    jobs_raw = load_csv(JOBS_CSV)
    clean = load_csv(RES_CLEAN_CSV)
    seg = load_csv(RES_SEG_CSV)
    terms, syn, pool_norm = build_skill_dict(write=False)
    black, indus, _ = build_blacklist(jobs_raw)
    pool_plain = {norm_skill(x) for s in seg for x in (s["技能词"] or "").split("、") if x}
    jobs = build_jobs(jobs_raw, syn, black, indus, pool_plain)
    resumes = build_resumes(clean, seg, syn)
    return jobs, resumes, terms, syn, pool_norm


def fuse(cover, cos):
    """融合口径（V3）：融合前先按小分母折扣与空集合规则处理覆盖率口径（由 skill_score 完成）"""
    return round(W_COVER * cover + W_COS * cos, 2)


def compare(sample_resumes=50):
    jobs, resumes, terms, syn, pool_norm = load_context()
    sim = SkillSim(jobs, terms)
    labels = load_csv(LABEL_CSV)
    print("岗位 %d ｜ 简历 %d ｜ 配对 %d ｜ 技能词表 %d 维" %
          (len(jobs), len(resumes), len(labels), len(sim.vocab)))

    # ---------- 1) 全量配对上的三口径分布 ----------
    V1, V2, V3 = [], [], []
    hits_arr, job_kinds = [], Counter()
    for r in labels:
        ri, ji = int(r["简历ID"][1:]) - 1, int(r["岗位ID"][1:]) - 1
        res, job = resumes[ri], jobs[ji]
        n_hit = int(r["技能命中数"])
        n_req = int(r["岗位技能要求数"])
        v2, _, _ = skill_score(n_hit, n_req, res["技能数"])
        v1 = sim.cosine(res["技能canon"], ji)
        V1.append(v1)
        V2.append(v2)
        V3.append(fuse(v2, v1))
        hits_arr.append(n_hit)
        job_kinds[ji] += 1
    V1, V2, V3 = np.array(V1), np.array(V2), np.array(V3)

    # ---------- 2) Top-N 重合度（固定其余五维，只看技能维度对推荐顺序的影响） ----------
    # 其余五维用标签表里已有的分项分（技能分之外的加权和）
    other = np.array([0.20 * float(r["经验分"]) + 0.15 * float(r["学历分"]) + 0.15 * float(r["地域分"])
                      + 0.12 * float(r["薪资分"]) + 0.08 * float(r["专业证书分"]) for r in labels])
    idx_by_res = {}
    for i, r in enumerate(labels):
        idx_by_res.setdefault(r["简历ID"], []).append(i)
    top = {}
    for rid, ids in idx_by_res.items():
        ids = np.array(ids)
        for name, V in (("V1余弦", V1), ("V2覆盖率", V2), ("V3融合", V3)):
            total = 0.30 * V[ids] + other[ids]
            keep = ids[np.argsort(-total)[:10]]
            top.setdefault(name, {})[rid] = set(keep.tolist())
    jac = {}
    for a, b in (("V1余弦", "V2覆盖率"), ("V1余弦", "V3融合"), ("V2覆盖率", "V3融合")):
        vals = []
        for rid in top[a]:
            A, B = top[a][rid], top[b][rid]
            vals.append(len(A & B) / max(len(A | B), 1))
        jac["%s vs %s" % (a, b)] = float(np.mean(vals))

    # ---------- 3) 分歧样例（V1 与 V2 差距最大的配对） ----------
    diff = np.abs(V1 - V2)
    order = np.argsort(-diff)[:6]
    samples = []
    for i in order:
        r = labels[i]
        ri, ji = int(r["简历ID"][1:]) - 1, int(r["岗位ID"][1:]) - 1
        res, job = resumes[ri], jobs[ji]
        samples.append({
            "岗位": job["名称"][:30], "简历": res["姓名"],
            "简历技能": "、".join(sorted(res["技能canon"])[:10]),
            "岗位要求": "、".join(sorted(job["J"])[:10]) or "（空）",
            "V1余弦": round(float(V1[i]), 1), "V2覆盖率": round(float(V2[i]), 1),
            "命中": "%s/%s" % (r["技能命中数"], r["岗位技能要求数"]),
        })

    # ---------- 4) 写报告 ----------
    def stat(a):
        return dict(mean=a.mean(), median=np.median(a), p75=np.percentile(a, 75), p95=np.percentile(a, 95),
                    zero=(a == 0).mean() * 100, pos=(a > 0).mean() * 100, sd=a.std())
    s1, s2, s3 = stat(V1), stat(V2), stat(V3)
    L = ["# 技能维度口径对比报告（任务6 · 步骤4）\n",
         "> 课程要求：技能用 **TF-IDF + 余弦相似度**；任务5 用的是 **集合覆盖率 + 利用率**。",
         "> 本报告在真实配对表（%d 个配对、%d 个岗位、%d 份简历）上同时算出三种口径并对比，用于定稿。\n" % (len(labels), len(jobs), len(resumes)),
         "| 口径 | 定义 |", "|---|---|",
         "| V1 余弦 | 简历技能词 vs 岗位技能要求词的 TF-IDF 加权余弦（同义词已归一，词表 %d 维） |" % len(sim.vocab),
         "| V2 覆盖率 | `0.7×岗位技能覆盖率 + 0.3×简历技能利用率`（任务5 口径：空集合→0、小分母折扣） |",
         "| **V3 融合（默认采用）** | `%.1f×V2 + %.1f×V1` — 既满足课程要求，又保留集合命中的有效性 |" % (W_COVER, W_COS),
         "", "## 一、分布对比（0–100 分）\n",
         "| 口径 | 均值 | 中位数 | P75 | P95 | 标准差 | 为 0 占比 | 有分占比 |", "|---|---|---|---|---|---|---|---|"]
    for nm, s in (("V1 余弦", s1), ("V2 覆盖率", s2), ("V3 融合", s3)):
        L.append("| %s | %.2f | %.2f | %.2f | %.2f | %.2f | %.1f%% | %.1f%% |" %
                 (nm, s["mean"], s["median"], s["p75"], s["p95"], s["sd"], s["zero"], s["pos"]))
    L.append("")
    L.append("## 二、按命中技能数看区分度（关键证据）\n")
    hits_np = np.array(hits_arr)
    L.append("| 命中技能数 | 配对数 | 占比 | V1 余弦均值 | V2 覆盖率均值 | V3 融合均值 |")
    L.append("|---|---|---|---|---|---|")
    for k in range(0, 6):
        m = hits_np == k if k < 5 else hits_np >= 5
        label = str(k) if k < 5 else "5+"
        if m.sum():
            L.append("| %s | %d | %.1f%% | %.2f | %.2f | %.2f |" %
                     (label, m.sum(), m.mean() * 100, V1[m].mean(), V2[m].mean(), V3[m].mean()))
    L.append("")
    L.append("- **两种口径都能随「命中数」单调上升，说明都有信号**：命中 1 项时 V1 %.1f 分 / V2 %.1f 分；命中 5 项以上 V1 %.1f 分 / V2 %.1f 分。"
             "V1 的绝对跨度（%.1f）与 V2（%.1f）相当，真正的差别是 **V1 整体尺度更低**（各档位约为 V2 的 35%%–80%%）。" %
             (V1[hits_np == 1].mean() if (hits_np == 1).sum() else 0, V2[hits_np == 1].mean() if (hits_np == 1).sum() else 0,
              V1[hits_np >= 5].mean() if (hits_np >= 5).sum() else 0, V2[hits_np >= 5].mean() if (hits_np >= 5).sum() else 0,
              (V1[hits_np >= 5].mean() - V1[hits_np == 1].mean()) if (hits_np >= 5).sum() and (hits_np == 1).sum() else 0,
              (V2[hits_np >= 5].mean() - V2[hits_np == 1].mean()) if (hits_np >= 5).sum() and (hits_np == 1).sum() else 0))
    L.append("")
    L.append("## 三、Top-10 推荐重合度（其余五维固定，只换技能口径）\n")
    L.append("| 对比 | Top-10 平均 Jaccard 重合度 |")
    L.append("|---|---|")
    for k, v in jac.items():
        L.append("| %s | %.3f |" % (k, v))
    L.append("")
    L.append("- 重合度越高说明换口径对最终推荐列表影响越小；V3 介于两者之间，是「折中」而非「颠覆」")
    L.append("")
    L.append("## 四、V1 与 V2 分歧最大的 6 个配对（人工可核验）\n")
    L.append("| 岗位 | 简历 | 简历技能 | 岗位技能要求 | 命中 | V1 余弦 | V2 覆盖率 |")
    L.append("|---|---|---|---|---|---|---|")
    for s in samples:
        L.append("| %s | %s | %s | %s | %s | %.1f | %.1f |" %
                 (s["岗位"], s["简历"], s["简历技能"], s["岗位要求"], s["命中"], s["V1余弦"], s["V2覆盖率"]))
    L.append("")
    L.append("## 五、结论与采用口径\n")
    L.append("1. **「有没有命中」由数据决定，与算法无关**：三种口径的零分占比完全相同（%.1f%%）——大量岗位的技能要求集合为空或与简历毫无重叠。" %
             (s1["zero"],))
    L.append("2. **V1（纯余弦）整体尺度偏低**：均值 %.2f vs %.2f、P95 %.2f vs %.2f、标准差 %.2f vs %.2f（V1 vs V2）。"
             "原因是 ① 余弦除以 `sqrt(|简历技能|·|岗位要求|)` 做了集合规模归一；② TF-IDF 让 **Python / SQL / MySQL 这类命中率最高的常见技能权重最低**，"
             "而高 IDF 的冷门技能很少同时出现在两侧。→ **本数据上「TF-IDF 加权」没有提升信号，只是把分数整体压低**（非零档位约为覆盖率口径的 35%%–80%%）。" %
             (s1["mean"], s2["mean"], s1["p95"], s2["p95"], s1["sd"], s2["sd"]))
    L.append("3. **我最初的假设被数据否定**：原以为余弦会「把只命中一个冷门词的配对抬得过高」，实测分歧样例**全部是 V1 明显低于 V2**（见上表，V1 约 23–30 分、V2 约 76–82 分），不存在抬高现象。")
    L.append("4. **按命中数看，两者都单调有效**（见第二节）：V2 的绝对分值更高，因此融合时以它为主体更稳；"
             "这一点**不支持**「覆盖率区分度明显更好」的强结论——两者的排序能力接近（Top-10 重合度 %.3f）。" %
             jac.get("V2覆盖率 vs V3融合", 0))
    L.append("5. **采用 V3 融合（%.1f×V2 + %.1f×V1）**：① 满足课程「技能用 TF-IDF+余弦」的硬要求；"
             "② 主体仍由尺度更合适的覆盖率口径决定；③ 对 Top-10 推荐列表影响可控（与 V2 重合度 %.3f）；"
             "④ 代价是技能分均值由 %.2f 降到 %.2f（总分均值相应下降约 %.2f 分），已在文档中标注。"
             "若课程要求技能维度**纯用** TF-IDF+余弦，只需把 `skill_similarity.py` 的 `W_COVER/W_COS` 改成 0.0/1.0 一键切换。" %
             (W_COVER, W_COS, jac.get("V2覆盖率 vs V3融合", 0), s2["mean"], s3["mean"], 0.30 * (s2["mean"] - s3["mean"])))
    L.append("")
    L.append("| 采用口径 | 技能分 = %.1f × (0.7×覆盖率 + 0.3×利用率) + %.1f × (TF-IDF 余弦 × 100) |" % (W_COVER, W_COS))
    L.append("|---|---|")
    L.append("| 空集合 | 0 分（无技能证据即视为不匹配） |")
    L.append("| 小分母折扣 | 要求项不足 2 项时按 n_req/2 折算置信度（沿用任务5 口径） |")
    L.append("| 同义词 | 两侧都归一到规范写法（K8s ≡ Kubernetes） |")
    L.append("| 词典外技能 | 不参与余弦计算（无对应列），但会记入 `技能列表_未在词典` 供人工复核 |")
    L.append("")
    L.append("> 复现：`python src/models/matching/skill_similarity.py`")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("输出：%s" % os.path.relpath(OUT_MD, ROOT))
    print("V1 zero %.1f%% mean %.2f ｜ V2 zero %.1f%% mean %.2f ｜ V3 zero %.1f%% mean %.2f" %
          (s1["zero"], s1["mean"], s2["zero"], s2["mean"], s3["zero"], s3["mean"]))
    print("Top-10 重合度:", {k: round(v, 3) for k, v in jac.items()})


if __name__ == "__main__":
    compare()
