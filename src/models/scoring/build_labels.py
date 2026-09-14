# -*- coding: utf-8 -*-
"""
任务5 · 步骤1：构造人岗匹配标签（连续 0–100 分，不训练任何模型）

输入（均在 data/processed/）：
  · `zhaopin_jobs_cleaned_seg.csv`  岗位 8,836 × 20
  · `简历数据_cleaned.csv`            简历 500 × 47（结构化字段）
  · `简历数据_seg.csv`                简历 500 × 20（分词列）
  · `技能同义词表.csv`                保守档归一映射（宽松档仅登记、不应用）
输出：
  · `技能标签黑名单.csv`              4,724 个标签的全量分类审计表（福利待遇类与行业领域类均不计入技能要求；行业类原值仍保留在岗位表中）
  · `匹配样本_标签数据.csv`           候选配对 + 6 个分项分 + 总分_规则 + 总分(0-100) + 是否匹配
  · `匹配样本_标签统计.md`            分布统计与口径敏感性审计

标签口径（用户已确认）：
  权重：技能 0.30 / 经验 0.20 / 学历 0.15 / 地域 0.15 / 薪资 0.12 / 专业证书 0.08
  ① 技能分 = 0.7 × 岗位技能覆盖率 + 0.3 × 简历技能利用率；岗位技能要求集合 = 技能标签
     （剔除福利类 247 个 + 行业类 512 个标签，岗位行与字段一律不动）
     ∪ 职位描述中出现的简历技能池词；匹配前做保守档同义词归一；集合为空 → 0 分；
     要求项不足 2 项时按 n_req/2 折减小分母置信度
  ② 经验分：超资历不惩罚（w ≥ 下限 → 100，不足 → 100×w/下限）；"不限" → 100；
     错位脏值 / 空值 → 视为信息缺失 → 中性 60（A2：2,182 个岗位）
  ③ 学历分：超学历不惩罚；差 1 档 60 / 差 2 档 30 / 差 3 档以上 0；要求为空 → 100
  ④ 地域分：同城 100；跨城按直线距离 ≤100km 85 / 100–300km 60 / >300km 30
  ⑤ 薪资分：岗位上限 ≥ 简历期望下限 → 100；否则 100×上限/期望下限；"面议" → 80（无偏好）
  ⑥ 专业证书分 =（专业命中 100 / 未命中 40 + 证书 技术方向命中 100 / 仅通用 70 / 无证书 60）/ 2
  标签噪声：随机 10% 配对叠加 N(0,6)（截断 ±15）→ clip [0,100]；同时保留 `总分_规则` 纯净分
  二分类阈值：总分 ≥ 65 记为匹配
  候选配对：同城对全量 + 每份简历抽样 150 个跨城对（seed=42）


运行：python src/models/scoring/build_labels.py
"""
import csv
import math
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
P = os.path.join(ROOT, "data", "processed")
JOBS_CSV = os.path.join(P, "zhaopin_jobs_cleaned_seg.csv")
RES_CLEAN_CSV = os.path.join(P, "简历数据_cleaned.csv")
RES_SEG_CSV = os.path.join(P, "简历数据_seg.csv")
SYN_CSV = os.path.join(P, "技能同义词表.csv")
BLACK_CSV = os.path.join(P, "技能标签黑名单.csv")
OUT_CSV = os.path.join(P, "匹配样本_标签数据.csv")
OUT_MD = os.path.join(P, "匹配样本_标签统计.md")

SEED = 42
CROSS_PER_RESUME = 150
MATCH_THRESHOLD = 65
W = {"技能": 0.30, "经验": 0.20, "学历": 0.15, "地域": 0.15, "薪资": 0.12, "专业证书": 0.08}
NOISE_RATE, NOISE_SD, NOISE_CAP = 0.10, 6.0, 15.0

# ---------------------------------------------------------------- 基础工具

FULL2HALF = str.maketrans("＋＃（）．－／　", "+#().-/ ")


def norm_skill(s):
    """技能词归一：全角转半角 → 小写 → 去空格与 ._-/"""
    s = (s or "").strip().translate(FULL2HALF).lower()
    return re.sub(r"[\s._\-/]+", "", s)


# 城市中心经纬度（32 简历城市 + 16 岗位城市的并集，约 35 城；用于跨城直线距离）
CITY_LATLON = {
    "苏州": (31.30, 120.58), "福州": (26.07, 119.30), "厦门": (24.48, 118.09), "宁波": (29.87, 121.55),
    "嘉兴": (30.75, 120.76), "湖州": (30.89, 120.09), "泉州": (24.87, 118.68), "滁州": (32.30, 118.32),
    "漳州": (24.51, 117.65), "安庆": (30.51, 117.05), "莆田": (25.45, 119.01), "丽水": (28.45, 119.92),
    "南平": (26.64, 118.18), "龙岩": (25.08, 117.02), "三明": (26.26, 117.64), "舟山": (29.99, 122.21),
    "宁德": (26.67, 119.55), "温州": (27.99, 120.70), "南通": (31.98, 120.89), "扬州": (32.39, 119.42),
    "杭州": (30.27, 120.16), "无锡": (31.49, 120.31), "台州": (28.66, 121.42), "南京": (32.06, 118.80),
    "金华": (29.08, 119.65), "阜阳": (32.89, 115.81), "镇江": (32.19, 119.42), "马鞍山": (31.67, 118.51),
    "绍兴": (30.00, 120.58), "常州": (31.81, 119.97), "蚌埠": (32.92, 117.39), "合肥": (31.82, 117.23),
    "芜湖": (31.35, 118.43), "黄山": (29.71, 118.34), "徐州": (34.26, 117.19),
}


def haversine(a, b):
    lat1, lon1 = CITY_LATLON[a]
    lat2, lon2 = CITY_LATLON[b]
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(h)), 1)


EDU_ORD = {"初中": 0, "初中及以下": 0, "小学": 0, "高中": 1, "中专": 2, "中技": 2, "中专/中技": 2,
           "中专/中技/高中": 2, "大专": 3, "专科": 3, "高职": 3, "本科": 4, "硕士": 5, "研究生": 5, "博士": 6}

EXP_UNLIMITED = re.compile(r"不限")
EXP_FRESH = re.compile(r"应届|无经验|在校")
EXP_RANGE = re.compile(r"^(\d+)\s*[-—~至]\s*(\d+)\s*年$")
EXP_ABOVE = re.compile(r"^(\d+)\s*年以上$")
EXP_BELOW = re.compile(r"^(\d+)\s*年(以内|以下)$")
EXP_EXACT = re.compile(r"^(\d+)\s*年$")


def parse_exp(v):
    """→ (kind, lo, hi)；kind ∈ range / unlimited / missing"""
    v = (v or "").strip()
    if not v:
        return "missing", None, None
    if EXP_UNLIMITED.search(v):
        return "unlimited", None, None
    if EXP_FRESH.search(v):
        return "range", 0, 0
    for rx, mk in ((EXP_RANGE, lambda m: (int(m.group(1)), int(m.group(2)))),
                   (EXP_ABOVE, lambda m: (int(m.group(1)), int(m.group(1)) + 5)),
                   (EXP_BELOW, lambda m: (0, int(m.group(1)))),
                   (EXP_EXACT, lambda m: (int(m.group(1)), int(m.group(1))))):
        m = rx.match(v)
        if m:
            lo, hi = mk(m)
            return "range", lo, hi
    return "missing", None, None          # 含 A11 错位值（JavaScript/QE/32位单片机 等）


# 专业 → 关键词（12 个专业）
MAJOR_KW = {
    "计算机科学与技术": ["计算机", "软件", "开发", "程序", "算法", "系统"],
    "软件工程": ["软件", "开发", "程序", "工程", "后端"],
    "软件技术": ["软件", "开发", "程序", "技术"],
    "计算机应用技术": ["计算机", "应用", "软件", "开发"],
    "信息管理与信息系统": ["信息管理", "信息系统", "数据", "数据库"],
    "网络工程": ["网络工程", "网络", "运维", "通信"],
    "物联网工程": ["物联网", "嵌入式", "硬件", "传感"],
    "电子信息工程": ["电子", "嵌入式", "硬件", "通信", "电路"],
    "通信工程": ["通信", "5g", "信号", "网络"],
    "数字媒体技术": ["数字媒体", "多媒体", "前端", "设计", "动画"],
    "数学与应用数学": ["数学", "算法", "数据", "统计", "建模"],
    "数据科学与大数据技术": ["大数据", "数据科学", "数据", "分析"],
}

# 证书：技术认证（可对应岗位方向）/ 通用证书
CERT_TECH = {"MySQL数据库认证": ["mysql", "数据库", "sql", "后端", "数据"],
             "红帽RHCE认证": ["linux", "运维", "系统", "服务器", "网络"],
             "华为HCIA认证": ["网络", "运维", "云", "通信"],
             "阿里云ACP云计算认证": ["云", "运维", "服务器", "架构"],
             "系统架构设计师": ["架构", "后端", "系统", "微服务", "java"],
             "软件设计师（中级）": ["软件", "开发", "后端", "前端", "程序"],
             "软考中级": ["软件", "开发", "系统", "测试", "网络"]}
CERT_GENERAL = {"英语四级", "英语六级", "计算机一级", "计算机二级", "PMP项目管理专业人士"}

# 福利待遇类标签 → 从岗位技能集合中剔除（用户确认口径）
BEN_PAT = re.compile(r"五险|一金|六险|二金|社保|年金|奖金|奖励|津贴|补贴|补助|福利|培训|包吃|包住|住宿|餐补|"
                     r"房补|话补|班车|体检|双休|大小周|假期|年假|团建|旅游|聚餐|零食|下午茶|期权|股权|提成|"
                     r"晋升|法定|节假日|生日|工龄|满勤|全勤|薪酬|工资|补充医疗|医疗险")
# 行业/领域类标签 → 仅登记，不剔除（用户要求"不删岗位信息"）
IND_PAT = re.compile(r"行业|制造|半导体|芯片|汽车|银行|保险|金融|房地产|电商|零售|批发|贸易|物流|仓储|货运|"
                     r"快递|餐饮|教育|医疗|医药|制药|生物|化工|材料|能源|电力|水利|环保|食品|饮料|酒水|烟酒|"
                     r"纺织|服装|鞋服|家居|家具|皮革|橡胶|塑料|日化|珠宝|酒店|运营商|电信|建筑|矿业|钢铁|"
                     r"有色金属|政府|公共|协会|组织|科研|检测/认证|软件/it服务|互联网|计算机软件|计算机硬件|"
                     r"产业|工业|农业")


def load_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_synonyms(path):
    """→ (保守映射 dict, 宽松映射 dict, 统计)"""
    strict, loose = {}, {}
    n_loose = 0
    for r in load_csv(path):
        tgt = strict if r["档位"] == "保守" else loose
        canon = norm_skill(r["规范名"])
        for v in re.split(r"[|、,，]", r["同义词变体"]):
            v = v.strip()
            if not v:
                continue
            tgt[norm_skill(v)] = canon
        if r["档位"] != "保守":
            n_loose += 1
    return strict, loose, n_loose


def build_blacklist(job_rows):
    """按规则给全部标签分类，写出审计 CSV → 返回 (剔除集合, 行业集合, 审计记录)"""
    tags = Counter()
    for r in job_rows:
        for t in (r["技能标签"] or "").split("|"):
            if t.strip():
                tags[t.strip()] += 1
    recs, black, indus = [], set(), set()
    for t, c in tags.most_common():
        if BEN_PAT.search(t):
            cls, drop, why = "福利待遇", "是", "福利/待遇关键词规则"
            black.add(norm_skill(t))
        elif IND_PAT.search(t):
            cls, drop, why = "行业领域", "否", "行业/领域关键词规则（按用户口径保留）"
            indus.add(norm_skill(t))
        else:
            cls, drop, why = "技能", "否", "—"
        recs.append([t, c, cls, drop, why])
    with open(BLACK_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["标签", "出现行数", "分类", "是否剔除", "依据"])
        w.writerows(recs)
    return black, indus, recs


# ---------------------------------------------------------------- 读数据 + 建记录

def build_jobs(rows, syn, black, indus, pool_plain):
    """岗位记录：技能集合的 4 个口径 + 经验/学历/薪资/城市/关键词"""
    jobs = []
    for i, r in enumerate(rows):
        shape = (r["岗位地区"] or "").strip().split()
        city = shape[0] if shape else ""
        tags = [t.strip() for t in (r["技能标签"] or "").split("|") if t.strip()]
        tnorm = [(t, norm_skill(t)) for t in tags]
        kept = [n for _, n in tnorm if n not in black]
        desc_tokens = {norm_skill(t) for t in (r["描述分词"] or "").split() if t.strip()}
        desc_plain = {t for t in desc_tokens if t in pool_plain}
        desc_syn = {syn.get(t, t) for t in desc_plain}

        # 主口径：福利标签与行业标签都不计入"岗位技能要求"；职位描述中出现的简历技能词计入
        J_main = {syn.get(n, n) for _, n in tnorm if n not in black and n not in indus} | desc_syn
        J_only_ben = {syn.get(n, n) for n in kept} | desc_syn                             # 敏感性：只剔福利
        J_no_drop = {syn.get(n, n) for _, n in tnorm} | desc_syn                          # 敏感性：一个都不剔
        J_plain = {n for _, n in tnorm if n not in black and n not in indus} | desc_plain  # 敏感性：不归一

        kind, lo, hi = parse_exp(r["经验要求"])
        edu = EDU_ORD.get((r["学历要求"] or "").strip())
        lo_s, hi_s = (r["薪资下限(元/月)"] or "").strip(), (r["薪资上限(元/月)"] or "").strip()
        text = ((r["岗位名称"] or "") + " " + (r["职位描述"] or "")).lower()
        jobs.append({
            "id": "J%04d" % (i + 1), "名称": (r["岗位名称"] or "").strip(), "城市": city,
            "J": J_main, "J_only_ben": J_only_ben, "J_no_drop": J_no_drop, "J_plain": J_plain,
            "exp_kind": kind, "exp_lo": lo, "exp_hi": hi,
            "edu": edu, "sal_lo": int(lo_s) if lo_s else None, "sal_hi": int(hi_s) if hi_s else None,
            "kw": {k for kws in list(MAJOR_KW.values()) + list(CERT_TECH.values()) for k in kws if k in text},
        })
    return jobs


def build_resumes(clean_rows, seg_rows, syn):
    res = []
    assert len(clean_rows) == len(seg_rows), "简历两文件行数不一致"
    for i, (c, s) in enumerate(zip(clean_rows, seg_rows)):
        skills = [x for x in (s["技能词"] or "").split("、") if x]
        plain = {norm_skill(x) for x in skills}
        lo_s = (c["期望薪资下限(元/月)"] or "").strip()
        res.append({
            "id": "R%03d" % (i + 1), "姓名": (c["姓名"] or "").strip(),
            "城市": (c["期望城市"] or "").strip(), "学历序数": EDU_ORD.get((c["最高学历"] or "").strip(), 3),
            "年限": int(c["工作年限"] or 0), "应届": c["是否应届"] == "是",
            "期望下限": int(lo_s) if lo_s else None, "面议": c["期望薪资是否面议"] == "是",
            "专业": (c["专业"] or "").strip(),
            "证书": [x for x in (s["证书"] or "").split("、") if x],
            "技能数": len(plain), "技能canon": {syn.get(x, x) for x in plain}, "技能plain": plain,
        })
    return res


# ---------------------------------------------------------------- 六个维度打分

def skill_score(hits, n_req, n_res):
    """技能分 = 0.7×覆盖率 + 0.3×利用率

    · 岗位技能要求集合为空 → 0 分（无技能证据即视为技能不匹配，不给中性分）
    · 小分母折扣：要求项不足 2 项时按 n_req/2 折算置信度。只列了 1 项技能要求时，
      命中即得 100% 覆盖率，证据强度不足，会把"质量部经理"这类跨领域岗位高估。
    """
    if n_req == 0:
        return 0.0, None, None
    cov, util = hits / n_req, hits / n_res
    raw = (0.7 * cov + 0.3 * util) * 100
    if n_req < 2:
        raw *= n_req / 2.0
    return round(raw, 2), round(cov * 100, 2), round(util * 100, 2)


def exp_score(w, kind, lo):
    if kind == "unlimited":
        return 100.0
    if kind == "missing":
        return 60.0
    if lo is None or lo == 0 or w >= lo:
        return 100.0
    return round(100.0 * w / lo, 2)


def edu_score(job_edu, res_edu):
    if job_edu is None:
        return 100.0
    gap = job_edu - res_edu
    if gap <= 0:
        return 100.0
    return {1: 60.0, 2: 30.0}.get(gap, 0.0)


def geo_score(d):
    if d == 0:
        return 100.0
    if d <= 100:
        return 85.0
    if d <= 300:
        return 60.0
    return 30.0


def sal_score(res_lo, nego, j_lo, j_hi):
    if nego or res_lo is None:
        return 80.0 if nego else 60.0
    if j_lo is None or j_hi is None:
        return 60.0
    if j_hi >= res_lo:
        return 100.0
    return round(100.0 * j_hi / res_lo, 2)


def pc_score(job_kw, major, certs):
    kws = MAJOR_KW.get(major) or [major.lower() if major else "____"]
    prof = 100.0 if any(k in job_kw for k in kws) else 40.0
    tech = [c for c in certs if c in CERT_TECH]
    if any(any(k in job_kw for k in CERT_TECH[c]) for c in tech):
        cert = 100.0
    elif certs:
        cert = 70.0
    else:
        cert = 60.0
    return round((prof + cert) / 2, 2), prof, cert


# ---------------------------------------------------------------- 主流程

def main():
    job_rows = load_csv(JOBS_CSV)
    clean_rows = load_csv(RES_CLEAN_CSV)
    seg_rows = load_csv(RES_SEG_CSV)
    syn, loose, n_loose = load_synonyms(SYN_CSV)
    print("岗位 %d 行 ｜ 简历 %d 份 ｜ 同义词：保守 %d 条映射、宽松 %d 组（未应用）" %
          (len(job_rows), len(clean_rows), len(syn), n_loose))

    pool_plain = {norm_skill(x) for s in seg_rows for x in (s["技能词"] or "").split("、") if x}
    black, indus, audit = build_blacklist(job_rows)
    print("标签审计：%d 个标签 ｜ 福利待遇 %d 个不计入技能要求 ｜ 行业领域 %d 个也不计入（岗位表原值保留）" %
          (len(audit), len(black), len(indus)))

    jobs = build_jobs(job_rows, syn, black, indus, pool_plain)
    resumes = build_resumes(clean_rows, seg_rows, syn)
    missing_city = {j["城市"] for j in jobs if j["城市"] not in CITY_LATLON} | \
                   {r["城市"] for r in resumes if r["城市"] not in CITY_LATLON}
    if missing_city:
        print("⚠ 缺少经纬度的城市：", missing_city)

    # ---------- 生成候选配对 ----------
    by_city = defaultdict(list)
    for ji, j in enumerate(jobs):
        by_city[j["城市"]].append(ji)
    all_idx = np.arange(len(jobs))
    rng = np.random.default_rng(SEED)
    pairs = []
    for ri, r in enumerate(resumes):
        same = by_city.get(r["城市"], [])
        for ji in same:
            pairs.append((ri, ji, "同城"))
        mask = np.ones(len(jobs), dtype=bool)
        if same:
            mask[same] = False
        cand = all_idx[mask]
        pick = rng.choice(cand, size=min(CROSS_PER_RESUME, len(cand)), replace=False)
        for ji in pick:
            pairs.append((ri, int(ji), "跨城"))
    n_same = sum(1 for _, _, t in pairs if t == "同城")
    print("候选配对：%d 对（同城 %d / 跨城 %d）" % (len(pairs), n_same, len(pairs) - n_same))

    dist_cache = {}

    def dist(a, b):
        if a == b:
            return 0.0
        k = (a, b)
        if k not in dist_cache:
            dist_cache[k] = haversine(a, b) if (a in CITY_LATLON and b in CITY_LATLON) else -1.0
        return dist_cache[k]

    # ---------- 逐对打分 ----------
    out, diag = [], {k: [] for k in ("技能", "技能_只剔福利", "技能_不剔标签", "技能_不归一",
                                     "经验", "学历", "地域", "薪资", "专业证书")}
    for ri, ji, ptype in pairs:
        r, j = resumes[ri], jobs[ji]
        # ① 技能分（主口径 + 3 个敏感性口径）
        nA = len(j["J"])
        hA = len(r["技能canon"] & j["J"])
        sk, cov, util = skill_score(hA, nA, r["技能数"])
        skB = skill_score(len(r["技能canon"] & j["J_only_ben"]), len(j["J_only_ben"]), r["技能数"])[0]
        skC = skill_score(len(r["技能canon"] & j["J_no_drop"]), len(j["J_no_drop"]), r["技能数"])[0]
        skD = skill_score(len(r["技能plain"] & j["J_plain"]), len(j["J_plain"]), r["技能数"])[0]
        # ②③④⑤⑥
        ex = exp_score(r["年限"], j["exp_kind"], j["exp_lo"])
        ed = edu_score(j["edu"], r["学历序数"])
        d = dist(r["城市"], j["城市"])
        geo = geo_score(d) if d >= 0 else 60.0
        sa = sal_score(r["期望下限"], r["面议"], j["sal_lo"], j["sal_hi"])
        pc, prof, cert = pc_score(j["kw"], r["专业"], r["证书"])

        other = W["经验"] * ex + W["学历"] * ed + W["地域"] * geo + W["薪资"] * sa + W["专业证书"] * pc
        total = round(W["技能"] * sk + other, 2)

        for key, val in (("技能", sk), ("技能_只剔福利", skB), ("技能_不剔标签", skC), ("技能_不归一", skD),
                         ("经验", ex), ("学历", ed), ("地域", geo), ("薪资", sa), ("专业证书", pc)):
            diag[key].append(val)

        out.append({"简历ID": r["id"], "岗位ID": j["id"], "简历姓名": r["姓名"], "岗位名称": j["名称"],
                    "期望城市": r["城市"], "岗位城市": j["城市"], "配对类型": ptype,
                    "距离km": d if d >= 0 else "", "技能分": sk, "经验分": ex, "学历分": ed,
                    "地域分": geo, "薪资分": sa, "专业证书分": pc, "总分_规则": total,
                    "_other": other, "技能命中数": hA, "岗位技能要求数": nA, "简历技能数": r["技能数"],
                    "经验要求类型": j["exp_kind"], "专业项分": prof, "证书项分": cert,
                    "_cov": cov, "_util": util})

    # ---------- 标签噪声 ----------
    rng2 = np.random.default_rng(SEED + 1)
    n = len(out)
    hit = rng2.random(n) < NOISE_RATE
    noise = np.clip(rng2.normal(0, NOISE_SD, n), -NOISE_CAP, NOISE_CAP)
    clean_tot = np.array([o["总分_规则"] for o in out])
    noisy = np.clip(clean_tot + np.where(hit, noise, 0.0), 0, 100)
    for o, t, flag in zip(out, noisy, hit):
        o["总分(0-100)"] = round(float(t), 2)
        o["是否匹配"] = int(t >= MATCH_THRESHOLD)
        o["_噪声扰动"] = int(flag)

    fields = ["简历ID", "岗位ID", "简历姓名", "岗位名称", "期望城市", "岗位城市", "配对类型", "距离km",
              "技能分", "经验分", "学历分", "地域分", "薪资分", "专业证书分", "总分_规则", "总分(0-100)",
              "是否匹配", "技能命中数", "岗位技能要求数", "简历技能数", "经验要求类型", "专业项分", "证书项分"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    print("输出：%s（%d 行 × %d 列）" % (os.path.relpath(OUT_CSV, ROOT), len(out), len(fields)))

    write_report(out, diag, jobs, resumes, audit, black, indus, len(syn), n_loose, n_same)
    print("输出：%s" % os.path.relpath(OUT_MD, ROOT))


# ---------------------------------------------------------------- 统计报告

def _q(a, p):
    return round(float(np.percentile(a, p)), 2)


def write_report(out, diag, jobs, resumes, audit, black, indus, n_syn_strict, n_loose, n_same):
    n = len(out)
    tot = np.array([o["总分(0-100)"] for o in out])
    raw = np.array([o["总分_规则"] for o in out])
    pos = int((tot >= MATCH_THRESHOLD).sum())
    pos_raw = int((raw >= MATCH_THRESHOLD).sum())
    dims = ["技能", "经验", "学历", "地域", "薪资", "专业证书"]
    L = []
    L.append("# 匹配样本标签统计报告\n")
    L.append("> 岗位-简历人岗匹配推荐系统 ｜ 任务5 步骤1：标签构造（连续 0–100 分）")
    L.append("> 输入：`data/processed/zhaopin_jobs_cleaned_seg.csv`（8,836 岗位）、`简历数据_cleaned.csv` + `简历数据_seg.csv`（500 简历）")
    L.append("> 输出：`data/processed/匹配样本_标签数据.csv`（%d 行）、`技能标签黑名单.csv`、本报告 ｜ 随机种子 %d\n" % (n, SEED))
    L.append("---\n")

    L.append("## 〇、标签口径（本报告全部数字均基于此口径）\n")
    L.append("| 维度 | 权重 | 算分规则 |\n|---|---|---|")
    L.append("| 技能 | 0.30 | `0.7 × 岗位技能覆盖率 + 0.3 × 简历技能利用率`。岗位技能要求集合 = 岗位 `技能标签`（**剔除福利类 %d 个 + 行业类 %d 个标签**）∪ 职位描述中出现的简历技能池词；匹配前做保守档同义词归一；**集合为空 → 0 分**（无技能证据即视为不匹配，不给中性分）；**要求项不足 2 项时按 n_req/2 折减小分母置信度** |"
             % (len(black), len(indus)))
    L.append("| 经验 | 0.20 | 满足岗位下限 → 100；不足 → `100 × 简历年限 / 下限`（**超资历不惩罚**）；岗位\"不限\" → 100；`经验要求` 错位/空值（A2，2,182 个岗位）→ 中性 60 |")
    L.append("| 学历 | 0.15 | 超学历不惩罚；差 1 档 60 分、差 2 档 30 分、差 3 档以上 0 分；岗位学历要求为空 → 100 |")
    L.append("| 地域 | 0.15 | 同城 100；跨城按城市中心直线距离：≤100km 85 分、100–300km 60 分、>300km 30 分 |")
    L.append("| 薪资 | 0.12 | 岗位上限 ≥ 简历期望下限 → 100；否则 `100 × 岗位上限 / 期望下限`；期望\"面议\" → 80（无偏好）；岗位薪资缺失 → 60 |")
    L.append("| 专业证书 | 0.08 | （专业项 + 证书项）/ 2。专业命中岗位名称或描述 → 100，未命中 → 40（底分）；证书技术方向命中 → 100、仅通用证书 → 70、无有效证书 → 60（底分） |")
    L.append("")
    L.append("- **标签噪声**：随机 %.0f%% 的配对叠加 N(0, %.0f)（截断 ±%.0f）后 clip 到 [0,100]；同时保留 `总分_规则` 纯净分作对照。" %
             (NOISE_RATE * 100, NOISE_SD, NOISE_CAP))
    L.append("- **二分类阈值**：`总分(0-100) ≥ %d` 记为匹配。" % MATCH_THRESHOLD)
    L.append("- **候选配对**：同城对全量 + 每份简历抽样 %d 个跨城对（种子 %d）。" % (CROSS_PER_RESUME, SEED))
    L.append("")

    L.append("## 一、候选配对规模\n")
    L.append("| 配对类型 | 对数 | 占比 |\n|---|---|---|")
    L.append("| 同城对（全量） | %d | %.2f%% |" % (n_same, n_same / n * 100))
    L.append("| 跨城对（每简历 %d 个抽样） | %d | %.2f%% |" % (CROSS_PER_RESUME, n - n_same, (n - n_same) / n * 100))
    L.append("| **合计** | **%d** | 100.00%% |" % n)
    L.append("\n- 全量交叉为 8,836 × 500 = 4,418,000 对，本方案只用其中 %.2f%%。" % (n / 4418000 * 100))
    L.append("- 岗位覆盖 %d 个城市、简历覆盖 %d 个城市。" %
             (len({j["城市"] for j in jobs}), len({r["城市"] for r in resumes})) + "\n")

    L.append("## 二、标签分布\n")
    L.append("| 统计量 | 总分（含噪标签） | 总分_规则（纯净） |\n|---|---|---|")
    for label, f in (("最小", np.min), ("P5", lambda x: np.percentile(x, 5)), ("P25", lambda x: np.percentile(x, 25)),
                     ("中位数", np.median), ("均值", np.mean), ("P75", lambda x: np.percentile(x, 75)),
                     ("P95", lambda x: np.percentile(x, 95)), ("最大", np.max), ("标准差", np.std)):
        L.append("| %s | %.2f | %.2f |" % (label, f(tot), f(raw)))
    L.append("")
    bins = np.arange(0, 101, 10)
    h_raw, _ = np.histogram(raw, bins=bins)
    h_tot, _ = np.histogram(tot, bins=bins)
    L.append("| 分数区间 | 配对数（含噪） | 占比 | 配对数（纯净） | 占比 |\n|---|---|---|---|---|")
    for i in range(len(bins) - 1):
        L.append("| [%d, %d) | %d | %.2f%% | %d | %.2f%% |" %
                 (bins[i], bins[i + 1], h_tot[i], h_tot[i] / n * 100, h_raw[i], h_raw[i] / n * 100))
    L.append("")
    L.append("### 2.1 二分类正样本（阈值 ≥ %d）\n" % MATCH_THRESHOLD)
    L.append("| 口径 | 正样本 | 占比 | 负样本 |\n|---|---|---|---|")
    L.append("| 含噪标签（T2 用） | %d | %.2f%% | %d |" % (pos, pos / n * 100, n - pos))
    L.append("| 纯净标签（对照） | %d | %.2f%% | %d |" % (pos_raw, pos_raw / n * 100, n - pos_raw))
    L.append("")

    L.append("## 三、六个分项分\n")
    L.append("| 分项 | 权重 | 均值 | 中位数 | 标准差 | 最小 | 最大 | 与总分相关性 |\n|---|---|---|---|---|---|---|---|")
    for d in dims:
        a = np.array(diag[d])
        L.append("| %s | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f | %.3f |" %
                 (d, W[d], a.mean(), np.median(a), a.std(), a.min(), a.max(), np.corrcoef(a, raw)[0, 1]))
    L.append("")

    L.append("### 3.1 缺失/中性分处理的影响面\n")
    ex = np.array(diag["经验"])
    sk = np.array(diag["技能"])
    sa = np.array(diag["薪资"])
    pc = np.array(diag["专业证书"])
    ed = np.array(diag["学历"])
    geo = np.array(diag["地域"])
    cert60 = sum(1 for o in out if o["证书项分"] == 60)
    nreq = [int(o["岗位技能要求数"]) for o in out]
    empty_j = sum(1 for v in nreq if v == 0)
    rows = [
        ("经验分 = 60（信息缺失，A2 错位值 + 空值）", int((ex == 60).sum())),
        ("经验分 = 100（满足或岗位不限经验）", int((ex == 100).sum())),
        ("经验分 = 0（应届简历遇 1 年以上要求）", int((ex == 0).sum())),
        ("技能分 = 0（岗位技能要求集合为空 → 按 0 处理）", empty_j),
        ("技能分 = 0（有技能要求但一条都没命中）", int((sk == 0).sum()) - empty_j),
        ("技能分 > 0（至少命中一项技能）", int((sk > 0).sum())),
        ("技能分受小分母折扣（岗位技能要求数 = 1）", sum(1 for v in nreq if v == 1)),
        ("薪资分 = 80（简历期望为“面议”）", int((sa == 80).sum())),
        ("薪资分 = 60（岗位薪资无法解析）", int((sa == 60).sum())),
        ("证书项分 = 60（简历无有效证书，121 人）", cert60),
        ("学历分 = 100（超学历或岗位学历不限）", int((ed == 100).sum())),
        ("地域分 = 100（同城）", int((geo == 100).sum())),
    ]
    L.append("| 情况 | 配对数 | 占比 |\n|---|---|---|")
    for k, v in rows:
        L.append("| %s | %d | %.2f%% |" % (k, v, v / n * 100))
    L.append("")

    L.append("## 四、口径敏感性审计\n")
    L.append("### 4.1 岗位技能标签口径（主口径：福利类 + 行业类标签都不计入技能要求）\n")
    tag_total = len(audit)
    n_ben = sum(1 for _, _, c, d, _ in audit if c == "福利待遇")
    n_ind = sum(1 for _, _, c, d, _ in audit if c == "行业领域")
    rows_ben = sum(r[1] for r in audit if r[2] == "福利待遇")
    L.append("- 标签全量 **%d** 个（字符串去重口径）：福利待遇 **%d** 个、行业领域 **%d** 个（**两类都不计入“岗位技能要求”**，但岗位表中原值保留）、技能 **%d** 个。" %
             (tag_total, n_ben, n_ind, tag_total - n_ben - n_ind))
    L.append("- 归一后去重：福利待遇 **%d** 个、行业领域 **%d** 个。" % (len(black), len(indus)))
    L.append("- 福利标签覆盖岗位标签出现次数约 **%d** 次（同一标签在多个岗位上重复计数）。" % rows_ben)
    L.append("- 各口径技能分对比：")
    a_sk, b_sk, c_sk, d_sk = (np.array(diag[k]) for k in ("技能", "技能_只剔福利", "技能_不剔标签", "技能_不归一"))
    L.append("")
    L.append("| 技能分口径 | 均值 | 中位数 |\n|---|---|---|")
    L.append("| **A 主口径（福利 + 行业标签都剔除 + 保守同义词归一）** | %.2f | %.2f |" % (a_sk.mean(), np.median(a_sk)))
    L.append("| B 只剔福利标签（上一版口径） | %.2f | %.2f |" % (b_sk.mean(), np.median(b_sk)))
    L.append("| C 标签一个都不剔 | %.2f | %.2f |" % (c_sk.mean(), np.median(c_sk)))
    L.append("| D 剔除福利 + 行业标签但不做同义词归一 | %.2f | %.2f |" % (d_sk.mean(), np.median(d_sk)))
    other = np.array([o["_other"] for o in out])
    L.append("")
    L.append("| 总分口径 | 均值 | 中位数 | 正样本率(≥%d) |\n|---|---|---|---|" % MATCH_THRESHOLD)
    for name, s in (("A 主口径", a_sk), ("B 只剔福利", b_sk), ("C 一个都不剔", c_sk), ("D 不归一", d_sk)):
        t = np.clip(W["技能"] * s + other, 0, 100)
        L.append("| %s | %.2f | %.2f | %.2f%% |" % (name, t.mean(), np.median(t), (t >= MATCH_THRESHOLD).mean() * 100))
    L.append("")
    L.append("> **口径修订说明**：上一版口径把“岗位技能要求集合为空”当作信息缺失、给中性 60 分。该规则让 %d 个配对（%.2f%%）凭空拿到 60 分（高于 %.1f%% 的其余配对），并使若干**无技能标签的无关岗位**（如连锁KTV门店店长、制程质量工程师）以 93–99 分排到榜首。现改为 **0 分**（无技能证据即视为技能不匹配），并把行业类标签一并排除出技能要求集合。" %
             (empty_j, empty_j / n * 100, (sk <= 60).mean() * 100))
    L.append("> 两项修订相互作用：上一版测算中“剔除行业标签”带来的技能分均值提升（6.30 → 10.65）主要来自“空集合吃 60 分中性分”这一副作用；改为 0 分后，主口径与只剔福利口径的技能分差距仅 **%+.2f** 分。剔除行业标签在概念上仍然更正确（行业词不是技能要求），故保留为主口径。" %
             (a_sk.mean() - b_sk.mean()))
    L.append("")

    L.append("### 4.2 同义词归一\n")
    L.append("- 保守档生效映射 **%d** 条；宽松档 **%d** 组仅登记未应用（见 `技能同义词表.csv`）。" % (n_syn_strict, n_loose))
    L.append("- 归一使技能分平均变化 **%+.2f** 分（主口径 %.2f → 不做归一 %.2f）；差异很小，说明保守档只修正了少量写法差异。" %
             (a_sk.mean() - d_sk.mean(), a_sk.mean(), d_sk.mean()))
    L.append("- 技能覆盖率均值 %.2f%%、简历技能利用率均值 %.2f%%（仅统计岗位技能要求集合非空的配对）。" %
             (np.mean([o["_cov"] for o in out if o["_cov"] is not None]),
              np.mean([o["_util"] for o in out if o["_util"] is not None])))
    L.append("")

    L.append("### 4.3 标签噪声\n")
    L.append("- 随机 **%.0f%%** 的配对叠加 N(0, %.0f)（截断 ±%.0f）：实际扰动 **%d** 对（%.2f%%）。" %
             (NOISE_RATE * 100, NOISE_SD, NOISE_CAP, sum(o["_噪声扰动"] for o in out),
              sum(o["_噪声扰动"] for o in out) / n * 100))
    L.append("- 噪声带来的总分变化：MAE %.2f 分、最大 %.2f 分；正样本率 %.2f%% → %.2f%%。" %
             (np.abs(tot - raw).mean(), np.abs(tot - raw).max(), pos_raw / n * 100, pos / n * 100))
    L.append("")

    L.append("## 五、分组对比\n")
    same = np.array([o["总分(0-100)"] for o in out if o["配对类型"] == "同城"])
    cross = np.array([o["总分(0-100)"] for o in out if o["配对类型"] == "跨城"])
    L.append("| 分组 | 配对数 | 总分均值 | 中位数 | 正样本率 |\n|---|---|---|---|---|")
    for name, a in (("同城", same), ("跨城", cross)):
        L.append("| %s | %d | %.2f | %.2f | %.2f%% |" %
                 (name, len(a), a.mean(), np.median(a), (a >= MATCH_THRESHOLD).mean() * 100))
    L.append("")
    job_cities = {j["城市"] for j in jobs}
    no_job_res = {r["id"] for r in resumes if r["城市"] not in job_cities}
    a1 = np.array([o["总分(0-100)"] for o in out if o["简历ID"] in no_job_res])
    a2 = np.array([o["总分(0-100)"] for o in out if o["简历ID"] not in no_job_res])
    L.append("- 所在城市**无任何岗位**的简历 **%d 份**：总分均值 %.2f、正样本率 %.2f%%；" %
             (len(no_job_res), a1.mean() if len(a1) else 0, (a1 >= MATCH_THRESHOLD).mean() * 100 if len(a1) else 0))
    L.append("  其余 %d 份简历：总分均值 %.2f、正样本率 %.2f%%。" %
             (len(resumes) - len(no_job_res), a2.mean() if len(a2) else 0,
              (a2 >= MATCH_THRESHOLD).mean() * 100 if len(a2) else 0))
    L.append("")
    L.append("| 经验要求类型 | 配对数 | 总分均值 |\n|---|---|---|")
    for k in ("range", "unlimited", "missing"):
        a = np.array([o["总分(0-100)"] for o in out if o["经验要求类型"] == k])
        if len(a):
            L.append("| %s | %d | %.2f |" % (k, len(a), a.mean()))
    L.append("")

    L.append("## 六、输出文件\n")
    L.append("| 文件 | 说明 |\n|---|---|")
    L.append("| `data/processed/匹配样本_标签数据.csv` | 候选配对 + 6 个分项分 + `总分_规则` + `总分(0-100)` + `是否匹配`（%d 行） |" % n)
    L.append("| `data/processed/技能标签黑名单.csv` | 全部 %d 个标签的分类审计表（含出现行数、是否剔除、依据） |" % tag_total)
    L.append("| `data/processed/技能同义词表.csv` | 同义词映射（保守档生效 / 宽松档登记） |")
    L.append("| `data/processed/匹配样本_标签统计.md` | 本报告 |")
    L.append("")
    L.append("> 复现：`python src/models/scoring/build_labels.py`（随机种子 %d，结果可完全复现）" % SEED)

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
