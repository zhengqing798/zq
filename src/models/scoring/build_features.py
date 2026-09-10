# -*- coding: utf-8 -*-
"""
任务5 · 评分模型第二步：构造特征矩阵

输入：data/processed/匹配样本_标签数据.csv（153,872 条配对样本）
输出：data/processed/匹配特征_全量样本.csv（样本ID + 标签 + 特征 + 参考列）
      data/processed/匹配特征_说明.md（特征字典 + 单特征统计）

特征清单（按用户给定口径实现）：
  基础属性匹配：城市匹配度(0/1)、学历匹配度(0/1/2)、经验是否满足(0/1)、经验差值、经验差值归一化
  技能匹配特征：技能 Jaccard 相似度、核心技能命中率、技能覆盖度
  文本语义匹配：岗位-经历文本相似度(TF-IDF 余弦)、岗位-求职意向相似度(TF-IDF 余弦)
  附加特征：专业匹配度(0/1)、证书命中数
"""
import csv
import os
import re
import sys
from collections import Counter

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_labels import (CITY_LL, MAX_DIST_KM, edu_rank_of, exp_range_of, exp_ok,  # noqa: E402
                          haversine, job_city, load_csv, norm_skill, split_skills)

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PAIRS_CSV = os.path.join(ROOT, "data", "processed", "匹配样本_标签数据.csv")
JOB_CSV = os.path.join(ROOT, "data", "processed", "zhaopin_jobs_cleaned.csv")
JOB_SEG_CSV = os.path.join(ROOT, "data", "processed", "zhaopin_jobs_cleaned_seg.csv")
RESUME_CSV = os.path.join(ROOT, "data", "processed", "简历数据_cleaned.csv")
OUT_CSV = os.path.join(ROOT, "data", "processed", "匹配特征_全量样本.csv")
OUT_MD = os.path.join(ROOT, "data", "processed", "匹配特征_说明.md")

# 证书 → 岗位描述中的识别关键词（用于判断岗位是否要求该证书）
CERT_KEYWORDS = {
    "计算机二级": "计算机二级", "计算机一级": "计算机一级",
    "英语四级": "英语四级", "英语六级": "英语六级",
    "软考中级": "软考", "软件设计师（中级）": "软件设计师",
    "红帽RHCE认证": "rhce", "阿里云ACP云计算认证": "acp",
    "系统架构设计师": "系统架构设计师", "PMP项目管理专业人士": "pmp",
    "MySQL数据库认证": "mysql数据库认证", "华为HCIA认证": "hcia",
}

# 专业匹配规则的岗位关键词 → 对口专业关键词
MAJOR_RULES = [
    (["开发", "软件", "测试", "运维", "算法", "数据分析", "数据", "前端", "后端", "全栈",
      "人工智能", "嵌入式", "网络安全", "系统", "技术支持", "实施", "产品", "ui", "架构",
      "java", "python", "c++", "c#", ".net", "it", "信息化", "数字化"],
     ["计算机", "软件", "信息", "数据", "网络", "数字媒体", "智能", "物联网", "人工智能",
      "电子", "通信", "数学", "统计"]),
    (["电子", "硬件", "电路", "射频", "通信", "光电", "半导体", "芯片", "电气", "自动化", "仪表"],
     ["电子", "通信", "自动化", "电气", "物联网", "信息", "光电", "物理"]),
    (["机械", "设备", "工艺", "生产", "制造", "质量", "qc", "qa", "qe", "检测", "化验", "材料"],
     ["机械", "材料", "自动化", "工业", "质量", "电子", "化学", "物理", "工程"]),
]


def major_match(job_title, resume_major):
    """专业匹配度 0/1：岗位名称关键词 → 对口专业关键词 → 简历专业是否命中"""
    if not job_title or not resume_major:
        return 0
    t = job_title.lower()
    for job_kws, major_kws in MAJOR_RULES:
        if any(k in t for k in job_kws):
            if any(m in resume_major for m in major_kws):
                return 1
            return 0
    return 0


def jieba_tokens(text):
    import jieba
    return " ".join(w.strip() for w in jieba.lcut(text or "") if w.strip())


def exp_norm(years, lo, hi):
    """经验差值归一化：以 5 年为尺度，截断到 [-1, 2]"""
    diff = years - lo
    v = diff / 5.0
    return float(max(-1.0, min(2.0, v)))


def main():
    import jieba
    from sklearn.feature_extraction.text import TfidfVectorizer

    pairs = load_csv(PAIRS_CSV)
    jobs_raw = load_csv(JOB_CSV)
    resumes_raw = load_csv(RESUME_CSV)
    print("配对样本:", len(pairs), "｜岗位:", len(jobs_raw), "｜简历:", len(resumes_raw))

    seg = {}
    if os.path.exists(JOB_SEG_CSV):
        for i, r in enumerate(load_csv(JOB_SEG_CSV)):
            seg[i] = r.get("描述分词", "") or ""

    # ---------------- 岗位侧 ----------------
    # 技能词典 = 简历技能池（与标签构造 build_labels.py 完全一致）
    skill_pool = set()
    for r in resumes_raw:
        for t in re.split(r"[、,，;；/]+", r.get("技能列表") or ""):
            t = norm_skill(t)
            if t:
                skill_pool.add(t)
    print("技能词典（简历技能池）:", len(skill_pool), "项")

    job_doc, job_title_doc, job_cert = {}, {}, {}
    job_core_skills = {}
    for i, r in enumerate(jobs_raw):
        title = (r.get("岗位名称") or "").strip()
        job_title_doc[i] = title
        desc_tokens = seg.get(i) or jieba_tokens(r.get("职位描述", ""))
        job_doc[i] = desc_tokens
        text = re.sub(r"[\s（）()·]+", "", (r.get("职位描述") or "")).lower()
        certs = {c for c, kw in CERT_KEYWORDS.items() if kw.lower() in text}
        job_cert[i] = certs
        # 岗位核心技能 = 技能标签 ∪ 描述分词中命中技能词典的词（-技能标签去重）
        tags = split_skills(r.get("技能标签"), r"[|、，,\s]+")
        desc_sk = ({norm_skill(t) for t in desc_tokens.split() if norm_skill(t)} & skill_pool) - tags
        job_core_skills[i] = tags | desc_sk

    # ---------------- 简历侧 ----------------
    res_exp_doc, res_intent_doc, res_cert = {}, {}, {}
    for i, r in enumerate(resumes_raw):
        exp_text = (r.get("工作/实践经历", "") or "") + "\n" + (r.get("项目经验", "") or "")
        res_exp_doc[i] = jieba_tokens(exp_text)
        res_intent_doc[i] = (r.get("期望岗位", "") or "").strip()
        res_cert[i] = set(split_skills(r.get("证书列表"), r"[、,，;；/]+")) - {"无"}

    # ---------------- TF-IDF 余弦相似度 ----------------
    def sim_matrix(docs_a, docs_b, analyzer, ngram=(1, 1), token_pattern=None):
        corpus = list(docs_a) + list(docs_b)
        kw = {"analyzer": analyzer, "ngram_range": ngram}
        if analyzer == "word":
            kw["token_pattern"] = token_pattern or r"\S+"
        vec = TfidfVectorizer(**kw)
        m = vec.fit_transform(corpus)
        A = m[:len(docs_a)]
        B = m[len(docs_a):]
        S = (A @ B.T).toarray()          # 已 L2 归一化 → 点积即余弦
        return S, vec

    job_ids = list(range(len(jobs_raw)))
    res_ids = list(range(len(resumes_raw)))
    print("计算 岗位描述 × 简历经历 相似度矩阵 ...")
    S_exp, vec_exp = sim_matrix([job_doc[i] for i in job_ids],
                                [res_exp_doc[i] for i in res_ids],
                                analyzer="word", token_pattern=r"\S+")
    print("计算 岗位名称 × 简历求职意向 相似度矩阵 ...")
    S_intent, vec_intent = sim_matrix([job_title_doc[i] for i in job_ids],
                                      [res_intent_doc[i] for i in res_ids],
                                      analyzer="char_wb", ngram=(2, 3))
    print("  词表规模：经历 %d 维 ｜ 意向 %d 维" % (len(vec_exp.vocabulary_), len(vec_intent.vocabulary_)))

    # ---------------- 逐对构造特征 ----------------
    rows = []
    for p in pairs:
        rid = int(p["简历ID"]) - 1
        jid = int(p["岗位ID"]) - 1
        jr = jobs_raw[jid]
        rr = resumes_raw[rid]

        city_r = (rr.get("居住地") or "").strip()
        city_j = job_city(jr.get("岗位地区"))
        a, b = CITY_LL.get(city_r), CITY_LL.get(city_j)
        dist = haversine(a[0], a[1], b[0], b[1]) if (a and b) else None
        f_city = 1 if (dist is not None and dist <= MAX_DIST_KM) else 0

        r_edu = edu_rank_of(rr.get("最高学历"))
        j_edu = edu_rank_of(jr.get("学历要求"))
        j_edu_eff = j_edu or 0
        edu_diff = (r_edu or 0) - j_edu_eff
        f_edu = 0 if edu_diff < 0 else (1 if edu_diff == 0 else 2)

        years = int(rr.get("工作年限") or 0)
        lo, hi = exp_range_of(jr.get("经验要求"))
        f_exp_ok = 1 if exp_ok(years, (lo, hi)) else 0
        f_exp_diff = years - lo
        f_exp_norm = exp_norm(years, lo, hi)

        rset = split_skills(rr.get("技能列表"), r"[、,，;；/]+")
        jset = job_core_skills[jid]
        inter = len(rset & jset)
        union = len(rset | jset)
        f_jaccard = round(inter / union, 6) if union else 0.0
        f_hitrate = round(inter / len(jset), 6) if jset else 0.0
        f_cover = round(inter / len(rset), 6) if rset else 0.0

        f_sim_exp = round(float(S_exp[jid, rid]), 6)
        f_sim_intent = round(float(S_intent[jid, rid]), 6)
        f_major = major_match(jr.get("岗位名称") or "", rr.get("专业") or "")
        f_cert = len(res_cert[rid] & job_cert[jid])

        rows.append({
            "样本ID": len(rows) + 1, "标签": int(p["标签"]),
            # —— 特征 ——
            "城市匹配度": f_city,
            "学历匹配度": f_edu,
            "经验是否满足": f_exp_ok,
            "经验差值": f_exp_diff,
            "经验差值归一化": round(f_exp_norm, 4),
            "技能Jaccard": f_jaccard,
            "核心技能命中率": f_hitrate,
            "技能覆盖度": f_cover,
            "岗位-经历文本相似度": f_sim_exp,
            "岗位-求职意向相似度": f_sim_intent,
            "专业匹配度": f_major,
            "证书命中数": f_cert,
            # —— 参考列（不进模型，便于抽查/复现） ——
            "简历ID": rid + 1, "岗位ID": jid + 1,
            "简历姓名": rr.get("姓名"), "岗位名称": jr.get("岗位名称"), "公司名称": jr.get("公司名称"),
            "简历居住地": city_r, "岗位城市": city_j, "距离(km)": round(dist, 1) if dist is not None else "",
            "简历学历": rr.get("最高学历"), "岗位学历要求": (jr.get("学历要求") or "不限"),
            "简历工作年限": years, "岗位经验要求": (jr.get("经验要求") or "不限"),
            "简历技能数": len(rset), "岗位核心技能数": len(jset), "技能命中数": inter,
            "岗位要求证书数": len(job_cert[jid]), "简历证书数": len(res_cert[rid]),
            "未满足维度数": p.get("未满足维度数", ""), "负样本来源": p.get("负样本来源", ""),
        })

    fields = list(rows[0].keys())
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print("特征矩阵:", len(rows), "行 ×", len(fields), "列")

    # ---------------- 单特征统计（区分度） ----------------
    FEATS = ["城市匹配度", "学历匹配度", "经验是否满足", "经验差值", "经验差值归一化",
             "技能Jaccard", "核心技能命中率", "技能覆盖度",
             "岗位-经历文本相似度", "岗位-求职意向相似度", "专业匹配度", "证书命中数"]
    y = np.array([r["标签"] for r in rows])
    X = {k: np.array([r[k] for r in rows], dtype=float) for k in FEATS}
    report = build_report(rows, X, y, FEATS, len(vec_exp.vocabulary_), len(vec_intent.vocabulary_),
                          job_cert, res_cert)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(report + "\n")

    print("\n输出：")
    for p in [OUT_CSV, OUT_MD]:
        print("  %-40s %8.1f MB" % (os.path.relpath(p, ROOT), os.path.getsize(p) / 1024 / 1024))


def auc_score(x, y):
    """单特征 AUC（用秩和公式，等价于 Mann-Whitney U）"""
    from scipy.stats import rankdata
    r = rankdata(x)
    n1 = int(y.sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return 0.5
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def build_report(rows, X, y, FEATS, v_exp, v_intent, job_cert, res_cert):
    n = len(rows)
    n1 = int(y.sum())
    n0 = n - n1
    L = []
    L.append("# 匹配特征说明与单特征分析（任务5 · 评分模型）\n")
    L.append("> 数据来源：`data/processed/匹配样本_标签数据.csv`（%d 条配对样本，正 %d / 负 %d，比例 1:%.2f）" % (n, n1, n0, n0 / n1))
    L.append("> 特征矩阵（全量标注样本）：`data/processed/匹配特征_全量样本.csv`\n")
    L.append("---\n")
    L.append("## 一、特征字典\n")
    L.append("| 特征类别 | 特征 | 计算方式 |")
    L.append("|---|---|---|")
    defs = [
        ("基础属性匹配", "城市匹配度", "0/1：简历居住地与岗位城市直线距离 ≤%.0fkm 记为 1" % MAX_DIST_KM),
        ("基础属性匹配", "学历匹配度", "0/1/2：学历序数差 <0 不满足=0；=0 刚好满足=1；>0 超出要求=2"),
        ("基础属性匹配", "经验是否满足", "0/1：简历工作年限是否落在岗位经验要求区间内"),
        ("基础属性匹配", "经验差值", "简历工作年限 − 岗位经验要求下限（年）"),
        ("基础属性匹配", "经验差值归一化", "经验差值 ÷ 5，截断到 [-1, 2]"),
        ("技能匹配特征", "技能Jaccard", "|简历技能 ∩ 岗位核心技能| ÷ |简历技能 ∪ 岗位核心技能|"),
        ("技能匹配特征", "核心技能命中率", "|命中技能| ÷ |岗位核心技能|（岗位视角）"),
        ("技能匹配特征", "技能覆盖度", "|命中技能| ÷ |简历技能|（简历视角，与命中率互补）"),
        ("文本语义匹配", "岗位-经历文本相似度", "TF-IDF 余弦：岗位描述分词 vs 简历(工作经历+项目经验)分词，词表 %d 维" % v_exp),
        ("文本语义匹配", "岗位-求职意向相似度", "TF-IDF 余弦：岗位名称 vs 简历期望岗位，字符 2-3 gram，词表 %d 维" % v_intent),
        ("附加特征", "专业匹配度", "0/1：岗位名称关键词 → 对口专业关键词规则表 → 简历专业是否命中"),
        ("附加特征", "证书命中数", "岗位描述中出现的证书要求 ∩ 简历持有证书 的个数"),
    ]
    for a, b, c in defs:
        L.append("| %s | %s | %s |" % (a, b, c))
    L.append("")
    L.append("> 技能口径与标签构造一致：**岗位核心技能 = `技能标签` ∪ `职位描述`分词中的技能词（词典=简历技能池 74 项）**。")
    L.append("> 文本相似度中，岗位描述使用已有的 jieba `描述分词` 列，简历经历/求职意向现场分词。\n")
    L.append("## 二、单特征统计（正负样本对比 + 单特征 AUC）\n")
    L.append("| 特征 | 正样本均值 | 负样本均值 | 正样本标准差 | 负样本标准差 | 单特征 AUC |")
    L.append("|---|---|---|---|---|---|")
    for k in FEATS:
        x = X[k]
        a = auc_score(x, y)
        L.append("| %s | %.4f | %.4f | %.4f | %.4f | %.4f |" % (
            k, x[y == 1].mean(), x[y == 0].mean(), x[y == 1].std(), x[y == 0].std(), a))
    L.append("")
    L.append("> AUC = 0.5 表示该特征单独没有区分力；越接近 1 区分力越强（<0.5 表示方向相反，可直接取反或交给模型学习）。\n")
    L.append("## 三、特征取值分布\n")
    for k in ["城市匹配度", "学历匹配度", "经验是否满足", "专业匹配度", "证书命中数"]:
        x = X[k]
        c_all = Counter(x.tolist())
        L.append("**%s**\n" % k)
        L.append("| 取值 | 全样本 | 正样本 | 负样本 |")
        L.append("|---|---|---|---|")
        for v in sorted(c_all):
            L.append("| %g | %d | %d | %d |" % (v, int((x == v).sum()), int((x[y == 1] == v).sum()), int((x[y == 0] == v).sum())))
        L.append("")
    L.append("## 四、文本/技能特征分位\n")
    L.append("| 特征 | 最小值 | 25% | 中位数 | 75% | 最大值 |")
    L.append("|---|---|---|---|---|---|")
    for k in ["技能Jaccard", "核心技能命中率", "技能覆盖度", "岗位-经历文本相似度", "岗位-求职意向相似度", "经验差值"]:
        x = X[k]
        q = np.percentile(x, [0, 25, 50, 75, 100])
        L.append("| %s | %.4f | %.4f | %.4f | %.4f | %.4f |" % (k, q[0], q[1], q[2], q[3], q[4]))
    L.append("")
    n_job_cert = sum(1 for v in job_cert.values() if v)
    n_res_cert = sum(1 for v in res_cert.values() if v)
    L.append("- 岗位中有 %d / %d 个岗位的职位描述提到证书要求；有 %d / %d 份简历持有至少一项可识别证书。" %
             (n_job_cert, len(job_cert), n_res_cert, len(res_cert)))
    L.append("- 证书命中数 >0 的样本占比 %.2f%%。\n" % (float((X["证书命中数"] > 0).mean()) * 100))
    L.append("### 特征可用性提示\n")
    L.append("| 特征 | 说明 |")
    L.append("|---|---|")
    L.append("| 城市匹配度 / 经验是否满足 / 学历匹配度 | 与标签规则直接相关（正样本必然满足），因此正样本内取值为常数；作为模型输入时它们承载了标签规则本身 |")
    L.append("| 技能Jaccard / 核心技能命中率 / 技能覆盖度 | 单特征区分力最强（AUC≈0.94~0.95）；由于正样本要求“命中 ≥1 个技能”，三个特征在正样本内均大于 0 |")
    L.append("| 证书命中数 | **弱特征**：仅 %d 个岗位（%.1f%%）的职位描述提到证书要求，%.2f%% 的样本取值为 0，单特征 AUC≈0.50；建议建模时保留但需说明其贡献有限（或按岗位证书要求做二值化后再用） |" %
             (n_job_cert, n_job_cert / len(job_cert) * 100, float((X["证书命中数"] == 0).mean()) * 100))
    L.append("| 文本相似度 | 岗位-经历相似度 AUC≈0.69、岗位-意向相似度 AUC≈0.65，属于中等区分力，可与技能特征形成互补 |")
    L.append("")
    L.append("## 五、输出文件\n")
    L.append("| 文件 | 说明 |")
    L.append("|---|---|")
    L.append("| `data/processed/匹配特征_全量样本.csv` | **全量标注特征矩阵**（%d 行 × %d 列 = 样本ID + 标签 + %d 个特征 + %d 个参考列；训练/验证/测试集的切分见 `数据集划分_*.csv`） |" %
             (n, len(rows[0]), len(FEATS), len(rows[0]) - 2 - len(FEATS)))
    L.append("| `data/processed/匹配特征_说明.md` | 本说明 |")
    L.append("| `src/models/scoring/build_features.py` | 特征构造脚本 |")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    main()
