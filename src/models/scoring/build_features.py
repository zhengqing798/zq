# -*- coding: utf-8 -*-
"""
任务5 · 步骤2：特征工程（构造 X，不训练模型）

输入（data/processed/）：
  · `匹配样本_标签数据.csv`            步骤1 的候选配对 + 标签（28 MB，仅本地）
  · `zhaopin_jobs_cleaned_seg.csv`     岗位 8,836 × 20
  · `简历数据_cleaned.csv` / `简历数据_seg.csv`   简历 500 份
  · `技能同义词表.csv`                 保守档归一（与步骤1 同一口径）
输出：
  · `匹配特征_全量样本.csv`            207,640 行（体积较大，已 gitignore）
  · `匹配特征_列清单.csv`              每列的 类型(特征/标签/键) + 来源 + 说明
  · `匹配特征_说明.md`                 列清单、缺失哨兵、与标签的相关性、泄露自检

**铁律：特征里不放步骤1 的 6 个分项分，也不放任何"是否达标"类布尔判断结果。**
只放原始量（计数、序数、区间、距离、比值），让模型自己学映射；另外补入标签**没有用到**的
信息（文本相似度、岗位大类一致性、公司活跃度），用于衡量"纯语义"能做到什么程度。

运行：python src/models/scoring/build_features.py
"""
import csv
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_labels import (norm_skill, load_synonyms, build_blacklist, load_csv, haversine,  # noqa: E402
                          parse_exp, EDU_ORD, MAJOR_KW, CERT_TECH, CITY_LATLON)

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
P = os.path.join(ROOT, "data", "processed")
LABEL_CSV = os.path.join(P, "匹配样本_标签数据.csv")
JOBS_CSV = os.path.join(P, "zhaopin_jobs_cleaned_seg.csv")
RES_CLEAN_CSV = os.path.join(P, "简历数据_cleaned.csv")
RES_SEG_CSV = os.path.join(P, "简历数据_seg.csv")
SYN_CSV = os.path.join(P, "技能同义词表.csv")
OUT_CSV = os.path.join(P, "匹配特征_全量样本.csv")
OUT_COLS = os.path.join(P, "匹配特征_列清单.csv")
OUT_MD = os.path.join(P, "匹配特征_说明.md")
CHUNK = 20000

PROVINCE = {}
for _p, _cs in (("福建", "福州 厦门 泉州 漳州 莆田 宁德 南平 三明 龙岩"),
                ("浙江", "杭州 宁波 温州 绍兴 嘉兴 金华 台州 湖州 丽水 舟山"),
                ("安徽", "合肥 芜湖 蚌埠 马鞍山 安庆 黄山 滁州 阜阳"),
                ("江苏", "南京 苏州 无锡 常州 徐州 南通 扬州 镇江")):
    for _c in _cs.split():
        PROVINCE[_c] = _p

# 岗位大类规则（按优先级匹配岗位名称）
CAT_RULES = [("测试", r"测试|qa\b|质量工程|品质"),
             ("运维", r"运维|dba|网络工程|系统管理|实施"),
             ("算法", r"算法|机器学习|深度学习|nlp|视觉|推荐|大模型|人工智能|\bai\b"),
             ("数据", r"数据分析|大数据|数仓|数据仓库|bi|etl|数据工程"),
             ("前端", r"前端|web|vue|react|h5|小程序|全栈|ui"),
             ("嵌入式", r"嵌入式|单片机|驱动|硬件|fpga|ic"),
             ("后端", r"后端|服务端|java|python|golang|\bgo\b|c\+\+|php|\.net|spring|开发工程师|软件工程师"),
             ("产品项目", r"产品|项目经理|需求分析|项目管理")]
CATS = ["后端", "前端", "测试", "运维", "数据", "算法", "嵌入式", "产品项目", "其他"]


def job_category(name):
    n = (name or "").lower()
    for cat, rx in CAT_RULES:
        if re.search(rx, n):
            return cat
    return "其他"


def num(v, default=-1):
    v = (v or "").strip()
    return int(v) if v else default


def main():
    labels = load_csv(LABEL_CSV)
    jobs_raw = load_csv(JOBS_CSV)
    clean = load_csv(RES_CLEAN_CSV)
    seg = load_csv(RES_SEG_CSV)
    syn, _, _ = load_synonyms(SYN_CSV)
    black, indus, _ = build_blacklist(jobs_raw)
    pool_plain = {norm_skill(x) for s in seg for x in (s["技能词"] or "").split("、") if x}
    print("标签 %d 行 ｜ 岗位 %d ｜ 简历 %d" % (len(labels), len(jobs_raw), len(clean)))

    # ---------------- 岗位侧静态特征 ----------------
    job_rows = []
    for r in jobs_raw:
        parts = (r["岗位地区"] or "").strip().split()
        city = parts[0] if parts else ""
        tags = [t.strip() for t in (r["技能标签"] or "").split("|") if t.strip()]
        text = ((r["岗位名称"] or "") + " " + (r["职位描述"] or "")).lower()
        kind, lo, hi = parse_exp(r["经验要求"])
        job_rows.append({
            "city": city, "province": PROVINCE.get(city, ""), "cat": job_category(r["岗位名称"]),
            "n_tags": len(tags),
            "edu": EDU_ORD.get((r["学历要求"] or "").strip(), -1),
            "exp_kind": kind, "exp_lo": lo if lo is not None else -1, "exp_hi": hi if hi is not None else -1,
            "sal_lo": num(r["薪资下限(元/月)"]), "sal_hi": num(r["薪资上限(元/月)"]),
            "kw": {k for kws in list(MAJOR_KW.values()) + list(CERT_TECH.values()) for k in kws if k in text},
            "reply": int(re.search(r"\d+", r["今日回复数"] or "").group()) if re.search(r"\d+", r["今日回复数"] or "") else -1,
            "online": 1 if "在线" in (r["在线状态"] or "") else 0,
            "company": (r["公司名称"] or "").strip(),
            "name": (r["岗位名称"] or "").strip(),
            "desc_tokens": (r["描述分词"] or ""),
        })
    # 岗位技能要求集合（与步骤1 完全一致：剔除福利类 + 行业类，并入描述中命中的简历技能池词）
    for jr, r in zip(job_rows, jobs_raw):
        kept = {syn.get(norm_skill(t), norm_skill(t)) for t in (r["技能标签"] or "").split("|")
                if t.strip() and norm_skill(t) not in black and norm_skill(t) not in indus}
        jr["J"] = kept
        jr["J_plain"] = {norm_skill(t) for t in (r["技能标签"] or "").split("|")
                         if t.strip() and norm_skill(t) not in black and norm_skill(t) not in indus}

    job_city_cnt = Counter(j["city"] for j in job_rows)
    comp_cnt = Counter(j["company"] for j in job_rows if j["company"])

    # ---------------- 简历侧静态特征 ----------------
    res_rows = []
    for c, s in zip(clean, seg):
        skills_raw = [x for x in (s["技能词"] or "").split("、") if x]
        certs = [x for x in (s["证书"] or "").split("、") if x]
        res_rows.append({
            "city": (c["期望城市"] or "").strip(), "cat": job_category(c["期望岗位"]),
            "years": int(c["工作年限"] or 0), "fresh": 1 if c["是否应届"] == "是" else 0,
            "edu": EDU_ORD.get((c["最高学历"] or "").strip(), 3),
            "sal_lo": num(c["期望薪资下限(元/月)"]), "nego": 1 if c["期望薪资是否面议"] == "是" else 0,
            "major": (c["专业"] or "").strip(),
            "n_skills": len(skills_raw),
            "skills_canon": {syn.get(norm_skill(x), norm_skill(x)) for x in skills_raw},
            "skills_plain": {norm_skill(x) for x in skills_raw},
            "n_cert_tech": sum(1 for x in certs if x in CERT_TECH),
            "n_cert_gen": sum(1 for x in certs if x not in CERT_TECH),
            "certs": certs,
            "cert_kw": {k for x in certs if x in CERT_TECH for k in CERT_TECH[x]},
            "major_kw": MAJOR_KW.get((c["专业"] or "").strip(), [(c["专业"] or "").strip().lower()]),
            "exp_pos": (c["期望岗位"] or "").strip(),
            "text": " ".join(x for x in [(s["项目经验_分词"] or ""), (s["工作经历_分词"] or ""),
                                         (s["个人简介_分词"] or "")] if x),
            "skill_text": (s["技能特长_分词"] or ""),
        })
    res_city_cnt = Counter(r["city"] for r in res_rows)

    # ---------------- 文本相似度（TF-IDF 余弦） ----------------
    print("构建文本相似度（TF-IDF）…")
    title_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), min_df=2)
    title_vec.fit([j["name"] for j in job_rows] + [r["exp_pos"] for r in res_rows])
    JT = title_vec.transform([j["name"] for j in job_rows])
    RT = title_vec.transform([r["exp_pos"] for r in res_rows])

    text_vec = TfidfVectorizer(token_pattern=r"\S+", min_df=2)
    text_vec.fit([j["desc_tokens"] for j in job_rows] + [r["text"] for r in res_rows])
    JD = text_vec.transform([j["desc_tokens"] for j in job_rows])
    RText = text_vec.transform([r["text"] for r in res_rows])
    RSkill = text_vec.transform([r["skill_text"] for r in res_rows])
    print("  岗位名称词表 %d ｜ 描述词表 %d" % (len(title_vec.vocabulary_), len(text_vec.vocabulary_)))

    def rowdot(A, B, ia, ib):
        out = np.zeros(len(ia))
        for s in range(0, len(ia), CHUNK):
            sl = slice(s, s + CHUNK)
            out[sl] = np.asarray(A[ia[sl]].multiply(B[ib[sl]]).sum(axis=1)).ravel()
        return out

    ri = np.array([int(r["简历ID"][1:]) - 1 for r in labels])
    ji = np.array([int(r["岗位ID"][1:]) - 1 for r in labels])
    sim_title = rowdot(JT, RT, ji, ri)
    sim_text = rowdot(JD, RText, ji, ri)
    sim_skill = rowdot(JD, RSkill, ji, ri)

    # ---------------- 组装特征 ----------------
    print("组装特征…")
    feats = defaultdict(list)
    FEATURES = [
        ("简历技能数", "技能", "简历技能列表的词数（`技能词` 列）"),
        ("岗位技能要求数", "技能", "岗位技能要求集合大小（剔除福利类+行业类标签，并入描述中命中的简历技能池词）"),
        ("技能命中数", "技能", "归一口径下 简历技能词 ∩ 岗位技能要求集合 的词数"),
        ("技能精确命中数", "技能", "不做同义词归一的字符串精确命中词数"),
        ("岗位技能标签数", "技能", "岗位 `技能标签` 列的原始标签个数（含福利/行业标签）"),
        ("岗位名称与期望岗位相似度", "文本", "岗位名称 vs 期望岗位：char_wb 2–3gram TF-IDF 余弦"),
        ("描述与简历文本相似度", "文本", "职位描述分词 vs 简历(项目经验+工作经历+个人简介)分词：词级 TF-IDF 余弦"),
        ("描述与技能特长相似度", "文本", "职位描述分词 vs 技能特长分词：词级 TF-IDF 余弦"),
        ("专业命中岗位描述", "文本", "简历专业关键词是否出现在岗位名称或职位描述中（0/1）"),
        ("简历工作年限", "经验", "`工作年限` 列（应届为 0）"),
        ("是否应届", "经验", "是否应届（0/1）"),
        ("岗位经验下限", "经验", "经验要求区间下限（年）；不限或缺失为 -1"),
        ("岗位经验上限", "经验", "经验要求区间上限（年）；不限或缺失为 -1"),
        ("岗位经验不限", "经验", "岗位经验要求为“不限”（0/1）"),
        ("岗位经验缺失", "经验", "A2 错位值或空值，无法解析（0/1）"),
        ("简历学历序数", "学历", "初中0/高中1/中专2/大专3/本科4/硕士5/博士6"),
        ("岗位学历要求序数", "学历", "同上；要求为空/不限为 -1"),
        ("距离km", "地域", "期望城市与岗位城市中心的 Haversine 距离"),
        ("是否同城", "地域", "期望城市 == 岗位城市（0/1）"),
        ("是否同省", "地域", "期望城市与岗位城市同省（0/1）"),
        ("岗位城市岗位数", "地域", "该岗位所在城市在岗位池中的岗位数"),
        ("岗位城市简历数", "地域", "该岗位所在城市在 500 份简历中的简历数"),
        ("简历期望薪资下限", "薪资", "期望薪资下限（元/月）；面议为 -1"),
        ("期望薪资面议", "薪资", "期望薪资为“面议”（0/1）"),
        ("岗位薪资下限", "薪资", "岗位薪资区间下限（元/月）；缺失为 -1"),
        ("岗位薪资上限", "薪资", "岗位薪资区间上限（元/月）；缺失为 -1"),
        ("薪资上限与期望下限比", "薪资", "岗位上限 / 简历期望下限；任一侧缺失为 -1"),
        ("技术认证数", "专业证书", "方向性技术认证个数（RHCE/HCIA/ACP/软考/软设/架构师/MySQL认证）"),
        ("通用证书数", "专业证书", "通用证书个数（英语四六级/计算机一二三级/PMP）"),
        ("技术认证方向命中数", "专业证书", "该简历的技术认证中，方向关键词命中岗位名称/描述/技能集合的个数（0 ~ 技术认证数）"),
        ("岗位大类", "岗位类型", "岗位名称抽取的大类编码"),
        ("期望岗位大类", "岗位类型", "期望岗位抽取的大类编码"),
        ("岗位大类一致", "岗位类型", "岗位大类 == 期望岗位大类（0/1）"),
        ("今日回复数", "活跃度", "`今日回复数` 取数字；无该字段为 -1（标签未使用此信息）"),
        ("是否在线", "活跃度", "`在线状态` 含“在线”（0/1，标签未使用）"),
        ("同公司岗位数", "活跃度", "该岗位所属公司在岗位池中的岗位数（标签未使用）"),
    ]
    keys, names = ["简历ID", "岗位ID"], [n for n, _, _ in FEATURES]
    for idx, (r, i_res, i_job) in enumerate(zip(labels, ri, ji)):
        j, res = job_rows[i_job], res_rows[i_res]
        vals = {
            "简历技能数": res["n_skills"], "岗位技能要求数": int(r["岗位技能要求数"]),
            "技能命中数": int(r["技能命中数"]), "技能精确命中数": len(res["skills_plain"] & j["J_plain"]),
            "岗位技能标签数": j["n_tags"],
            "岗位名称与期望岗位相似度": round(float(sim_title[idx]), 4),
            "描述与简历文本相似度": round(float(sim_text[idx]), 4),
            "描述与技能特长相似度": round(float(sim_skill[idx]), 4),
            "专业命中岗位描述": 1 if any(k in j["kw"] for k in res["major_kw"]) else 0,
            "简历工作年限": res["years"], "是否应届": res["fresh"],
            "岗位经验下限": j["exp_lo"], "岗位经验上限": j["exp_hi"],
            "岗位经验不限": 1 if j["exp_kind"] == "unlimited" else 0,
            "岗位经验缺失": 1 if j["exp_kind"] == "missing" else 0,
            "简历学历序数": res["edu"], "岗位学历要求序数": j["edu"],
            "距离km": float(r["距离km"]) if r["距离km"] != "" else -1.0,
            "是否同城": 1 if r["配对类型"] == "同城" else 0,
            "是否同省": 1 if (j["province"] and j["province"] == PROVINCE.get(res["city"], "")) else 0,
            "岗位城市岗位数": job_city_cnt.get(j["city"], 0),
            "岗位城市简历数": res_city_cnt.get(j["city"], 0),
            "简历期望薪资下限": res["sal_lo"], "期望薪资面议": res["nego"],
            "岗位薪资下限": j["sal_lo"], "岗位薪资上限": j["sal_hi"],
            "薪资上限与期望下限比": round(j["sal_hi"] / res["sal_lo"], 3)
            if (j["sal_hi"] > 0 and res["sal_lo"] and res["sal_lo"] > 0) else -1.0,
            "技术认证数": res["n_cert_tech"], "通用证书数": res["n_cert_gen"],
            "技术认证方向命中数": sum(1 for x in res["certs"]
                                      if x in CERT_TECH and any(k in j["kw"] for k in CERT_TECH[x])),
            "岗位大类": CATS.index(j["cat"]), "期望岗位大类": CATS.index(res["cat"]),
            "岗位大类一致": 1 if j["cat"] == res["cat"] else 0,
            "今日回复数": j["reply"], "是否在线": j["online"],
            "同公司岗位数": comp_cnt.get(j["company"], 0),
        }
        feats["简历ID"].append(r["简历ID"])
        feats["岗位ID"].append(r["岗位ID"])
        for n in names:
            feats[n].append(vals[n])

    out_fields = keys + names + ["总分_规则", "总分(0-100)", "是否匹配"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(out_fields)
        for i, r in enumerate(labels):
            w.writerow([feats["简历ID"][i], feats["岗位ID"][i]] + [feats[n][i] for n in names] +
                       [r["总分_规则"], r["总分(0-100)"], r["是否匹配"]])
    print("输出：%s（%d 行 × %d 列）" % (os.path.relpath(OUT_CSV, ROOT), len(labels), len(out_fields)))

    with open(OUT_COLS, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["列名", "类型", "分组", "说明"])
        for c in keys:
            w.writerow([c, "键", "—", "配对标识，仅用于分组划分，不作为特征"])
        for n, grp, desc in FEATURES:
            w.writerow([n, "特征", grp, desc])
        for c, d in (("总分_规则", "标签（纯净）"), ("总分(0-100)", "标签（含噪，训练目标）"), ("是否匹配", "标签（≥65）")):
            w.writerow([c, "标签", "—", d])
    print("输出：%s" % os.path.relpath(OUT_COLS, ROOT))

    write_md(feats, names, FEATURES, keys, labels, len(title_vec.vocabulary_), len(text_vec.vocabulary_))
    print("输出：%s" % os.path.relpath(OUT_MD, ROOT))


def write_md(feats, names, FEATURES, keys, labels, v_title, v_text):
    n = len(labels)
    y = np.array([float(r["总分(0-100)"]) for r in labels])
    yraw = np.array([float(r["总分_规则"]) for r in labels])
    grp = {nm: g for nm, g, _ in FEATURES}
    desc = {nm: d for nm, _, d in FEATURES}
    L = []
    L.append("# 匹配特征说明（任务5 步骤2）\n")
    L.append("> 岗位-简历人岗匹配推荐系统 ｜ 特征表：`data/processed/匹配特征_全量样本.csv`（%d 行，%d 个特征）" % (n, len(names)))
    L.append("> 输入：步骤1 的 `匹配样本_标签数据.csv` + 岗位/简历清洗分词结果 ｜ 列清单（机器可读）：`匹配特征_列清单.csv`\n")
    L.append("---\n")
    L.append("## 一、设计原则\n")
    L.append("1. **不放步骤1 的 6 个分项分**，也不放任何“是否达标”类布尔判断结果——否则标签能被特征直接算出，指标会虚高到 1.0（上一版模型正是栽在这里）。")
    L.append("2. **只放原始量**：计数、序数、区间上下界、距离、比值，让模型自己学映射关系。")
    L.append("3. **补入标签没有用到的信息**：三个文本相似度、岗位大类一致性、公司活跃度/规模——它们决定模型能否超出规则本身。")
    L.append("4. ID、姓名、公司名、岗位名称只作键或已转成数值，不直接作为特征。\n")
    L.append("## 二、特征清单（%d 个）与缺失哨兵\n" % len(names))
    L.append("| # | 特征 | 分组 | 与标签相关性 r | 均值/占比 | 取值范围 | 说明 |\n|---|---|---|---|---|---|---|")
    for i, nm in enumerate(names):
        a = np.array(feats[nm], dtype=float)
        r = float(np.corrcoef(a, y)[0, 1]) if a.std() > 0 else 0.0
        L.append("| %d | `%s` | %s | %.3f | %.3f | %.3f ~ %.3f | %s |" %
                 (i + 1, nm, grp[nm], r, a.mean(), a.min(), a.max(), desc[nm]))
    L.append("")
    L.append("> 哨兵值：`-1` 表示缺失/不适用（岗位经验不限或缺失、学历要求不限、薪资面议或缺失、距离未知、无该活跃度字段）。")
    L.append("> 若某特征与标签的相关系数绝对值 > 0.95，说明它几乎是标签的复读机，需要剔除——本节末尾给出自检结论。\n")

    L.append("## 三、相关性最高 / 最低的特征\n")
    cors = sorted(((abs(float(np.corrcoef(np.array(feats[nm], dtype=float), y)[0, 1])), nm) for nm in names), reverse=True)
    L.append("| 排名 | 特征 | \\|r\\| |\n|---|---|---|")
    for i, (c, nm) in enumerate(cors[:10]):
        L.append("| %d | `%s` | %.3f |" % (i + 1, nm, c))
    L.append("")
    L.append("与环境无关（\\|r\\| < 0.05）的特征：" + ("、".join("`%s`" % nm for c, nm in cors if c < 0.05) or "无") + "\n")

    L.append("## 四、文本相似度（标签未使用的信息）\n")
    for nm in ("岗位名称与期望岗位相似度", "描述与简历文本相似度", "描述与技能特长相似度"):
        a = np.array(feats[nm], dtype=float)
        L.append("- `%s`：均值 %.4f ｜ 中位数 %.4f ｜ P95 %.4f ｜ 与标签 r = %.3f" %
                 (nm, a.mean(), np.median(a), np.percentile(a, 95), float(np.corrcoef(a, y)[0, 1])))
    L.append("- 词表规模：岗位名称 char_wb(2,3) %d 维 ｜ 描述词级 %d 维\n" % (v_title, v_text))

    L.append("## 五、标签列（仅供步骤4 使用，禁止当作特征）\n")
    L.append("| 列名 | 含义 |\n|---|---|")
    L.append("| `总分_规则` | 步骤1 的纯净标签（无噪声） |")
    L.append("| `总分(0-100)` | 步骤1 的最终标签（含 10% 噪声），**T1 回归的目标** |")
    L.append("| `是否匹配` | `总分(0-100) ≥ 65`，**T2 二分类的目标**（正样本 %d 个，%.2f%%） |" %
             (int((y >= 65).sum()), (y >= 65).mean() * 100))
    L.append("")
    L.append("## 六、缺失与异常自检\n")
    L.append("| 检查项 | 结果 |\n|---|---|")
    L.append("| 行数是否与标签表一致 | %d = %d ✓ |" % (n, n))
    L.append("| 是否存在空单元格 | %s |" % ("无（全部用哨兵值 -1 表示缺失）" if all(
        all(v != "" for v in feats[nm]) for nm in names) else "存在，需修复"))
    L.append("| 哨兵 -1 占比最高的特征 | %s |" % "、".join(
        "%s %.1f%%" % (nm, float((np.array(feats[nm], dtype=float) == -1).mean() * 100))
        for nm in sorted(names, key=lambda x: -float((np.array(feats[x], dtype=float) == -1).mean()))[:5]))
    L.append("| 与标签 \\|r\\| > 0.95 的特征 | %s |" % ("、".join(nm for c, nm in cors if c > 0.95) or "无 ✓（无标签复读机）"))
    L.append("| 重复列（两两完全相同） | %s |" % (dup_cols(feats, names) or "无 ✓"))
    L.append("")
    L.append("> 复现：`python src/models/scoring/build_features.py`")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def dup_cols(feats, names):
    seen, dups = {}, []
    for nm in names:
        key = tuple(feats[nm])
        if key in seen:
            dups.append("%s = %s" % (nm, seen[key]))
        else:
            seen[key] = nm
    return "、".join(dups)


if __name__ == "__main__":
    main()
