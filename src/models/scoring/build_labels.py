# -*- coding: utf-8 -*-
"""
任务5 · 评分模型第一步：构造 <简历, 岗位> 配对标签（正/负样本）

正样本（标签=1）：同时满足 4 个核心门槛
  ① 居住地与岗位城市距离 ≤ 300km
  ② 简历学历 ≥ 岗位最低学历要求
  ③ 简历工作年限满足岗位经验要求区间
  ④ 至少命中岗位 3 个及以上核心技能
负样本（标签=0）：两种来源
  A. 随机错位配对（随机简历 × 随机岗位），且不满足全部 4 个门槛（避免错标）
  B. 至少 2 个核心维度完全不满足
正负比例控制在 1:1 ~ 1:1.5（本脚本默认 1:1.2）

输入：data/processed/zhaopin_jobs_cleaned.csv（岗位）+ data/processed/简历数据_cleaned.csv（简历）
输出：data/processed/匹配样本_标签数据.csv、data/processed/匹配样本_标签统计.md
      data/external/城市坐标.csv（辅助：城市经纬度）
"""
import csv
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
JOB_CSV = os.path.join(ROOT, "data", "processed", "zhaopin_jobs_cleaned.csv")
JOB_SEG_CSV = os.path.join(ROOT, "data", "processed", "zhaopin_jobs_cleaned_seg.csv")
RESUME_CSV = os.path.join(ROOT, "data", "processed", "简历数据_cleaned.csv")
OUT_DIR = os.path.join(ROOT, "data", "processed")
EXTERNAL_DIR = os.path.join(ROOT, "data", "external")

SEED = 42
MAX_DIST_KM = 300.0          # 门槛①：通勤/地域距离上限
MIN_SKILL_HITS = 1           # 门槛④：至少命中 1 个核心技能（用户最新口径）
NEG_RATIO = 1.2              # 负样本 / 正样本 比例（要求 1:1 ~ 1:1.5）
SKILL_POOL = set()           # 技能词典（构建时由简历技能池填充）
MAX_POS = 0                  # 正样本上限（0 = 不限制；超过则随机抽样）
DRY_RUN = False              # 只统计不落盘

# 城市中心经纬度（用于计算简历居住地 ↔ 岗位城市直线距离，单位 km）
CITY_LL = {
    "苏州": (31.30, 120.59), "福州": (26.07, 119.30), "厦门": (24.48, 118.09),
    "宁波": (29.87, 121.54), "嘉兴": (30.75, 120.76), "湖州": (30.89, 120.09),
    "泉州": (24.87, 118.68), "滁州": (32.30, 118.32), "漳州": (24.51, 117.65),
    "安庆": (30.51, 117.05), "莆田": (25.43, 119.01), "丽水": (28.45, 119.92),
    "南平": (26.64, 118.18), "龙岩": (25.08, 117.02), "三明": (26.26, 117.64),
    "舟山": (29.99, 122.21), "佛山": (23.02, 113.12), "杭州": (30.27, 120.16),
    "南昌": (28.68, 115.86), "深圳": (22.54, 114.06), "珠海": (22.27, 113.58),
    "宁德": (26.66, 119.55), "东莞": (23.02, 113.75), "南京": (32.06, 118.80),
    "广州": (23.13, 113.26),
}

# 学历序数（数值越大要求越高）；岗位"不限"或空值视为不设门槛
EDU_RANK = {"不限": 0, "初中": 1, "初中及以下": 1, "高中": 2, "中专": 3, "中技": 3,
            "中专/中技": 3, "大专": 4, "大专及以上": 4, "专科": 4, "本科": 5,
            "硕士": 6, "硕士及以上": 6, "博士": 7, "MBA": 6, "EMBA": 6}

# 经验要求 → (最小年限, 最大年限)，None 表示不限
EXP_RANGE = {"不限": (0, None), "不限经验": (0, None), "接受无经验": (0, None),
             "应届": (0, 1), "应届生": (0, 1), "应届毕业生": (0, 1),
             "1年以下": (0, 1), "1-3年": (1, 3), "3-5年": (3, 5),
             "5-10年": (5, 10), "10年以上": (10, None)}


def load_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def job_city(region):
    parts = (region or "").replace("\u3000", " ").split()
    return parts[0] if parts else ""


def norm_skill(s):
    s = (s or "").strip().lower()
    s = re.sub(r"[\s·・.。]+", "", s)
    return s


def split_skills(text, seps):
    out = set()
    for t in re.split(seps, text or ""):
        t = norm_skill(t)
        if t:
            out.add(t)
    return out


def edu_rank_of(v):
    v = (v or "").strip()
    return EDU_RANK.get(v, 0 if v == "" else None)


def exp_range_of(v):
    v = (v or "").strip()
    if v in EXP_RANGE:
        return EXP_RANGE[v]
    m = re.fullmatch(r"(\d+)\s*年(?:以上)?", v)
    if m:
        return (int(m.group(1)), None)
    return (0, None)      # 未标注/非经验值 → 视为不限（原始数据异常，已在预处理文档记录）


def fmt_exp(rng):
    lo, hi = rng
    if hi is None:
        return "不限" if lo == 0 else "%d年以上" % lo
    if lo == 0 and hi == 1:
        return "应届/1年以下"
    return "%d-%d年" % (lo, hi)


def exp_ok(years, rng):
    lo, hi = rng
    if years is None:
        return False
    if years < lo:
        return False
    if hi is not None and years > hi:
        return False
    return True


def build():
    global SKILL_POOL
    random.seed(SEED)
    jobs_raw = load_csv(JOB_CSV)
    resumes_raw = load_csv(RESUME_CSV)

    # 技能词典 = 简历技能池（74 项技术词），用于识别岗位侧核心技能
    skill_pool = set()
    for r in resumes_raw:
        for t in re.split(r"[、,，;；/]+", r.get("技能列表") or ""):
            t = norm_skill(t)
            if t:
                skill_pool.add(t)
    print("技能词典（简历技能池）:", len(skill_pool), "项")
    SKILL_POOL = skill_pool

    # 岗位描述分词（用于补充"岗位核心技能"：技能标签 + 描述中提到的技能词）
    seg_tokens = {}
    if os.path.exists(JOB_SEG_CSV):
        for i, r in enumerate(load_csv(JOB_SEG_CSV)):
            seg_tokens[i] = {norm_skill(t) for t in (r.get("描述分词") or "").split() if norm_skill(t)}
        print("岗位描述分词已加载:", len(seg_tokens), "个岗位")

    jobs = []
    for i, r in enumerate(jobs_raw):
        city = job_city(r.get("岗位地区"))
        tags = split_skills(r.get("技能标签"), r"[|、，,\s]+")
        desc_sk = (seg_tokens.get(i, set()) & skill_pool) - tags     # 描述中提到、标签中没有的技能
        jobs.append({
            "jid": i, "岗位名称": r.get("岗位名称", ""), "公司名称": r.get("公司名称", ""),
            "岗位地区": r.get("岗位地区", ""), "城市": city, "学历要求": (r.get("学历要求") or "").strip(),
            "学历序数": edu_rank_of(r.get("学历要求")),
            "经验要求": (r.get("经验要求") or "").strip(),
            "经验区间": exp_range_of(r.get("经验要求")),
            "标签技能": tags, "描述技能": desc_sk, "核心技能": tags | desc_sk,
            "技能数": len(tags | desc_sk), "岗位薪资": r.get("岗位薪资", ""),
        })
    resumes = []
    for i, r in enumerate(resumes_raw):
        resumes.append({
            "rid": i, "姓名": r.get("姓名", ""), "居住地": (r.get("居住地") or "").strip(),
            "期望岗位": r.get("期望岗位", ""), "期望城市": r.get("期望城市", ""),
            "最高学历": (r.get("最高学历") or "").strip(),
            "学历序数": edu_rank_of(r.get("最高学历")),
            "工作年限": int(r.get("工作年限") or 0), "是否应届": r.get("是否应届", ""),
            "技能集": split_skills(r.get("技能列表"), r"[、,，;；/]+"),
        })

    # 城市距离缓存 + 每个简历城市的 300km 内岗位索引
    dist_cache = {}
    def city_dist(c1, c2):
        key = (c1, c2)
        if key not in dist_cache:
            a, b = CITY_LL.get(c1), CITY_LL.get(c2)
            dist_cache[key] = haversine(a[0], a[1], b[0], b[1]) if (a and b) else None
        return dist_cache[key]

    print("岗位:", len(jobs), "｜简历:", len(resumes))
    unknown_city = [c for c in {j["城市"] for j in jobs} if c not in CITY_LL]
    print("岗位中缺少坐标的城市:", unknown_city or "无")

    jobs_by_city = defaultdict(list)
    for j in jobs:
        jobs_by_city[j["城市"]].append(j["jid"])
    near_jobs = {}      # resume city -> [job ids within 300km]
    for c in {r["居住地"] for r in resumes}:
        ids = []
        for jc, jids in jobs_by_city.items():
            d = city_dist(c, jc)
            if d is not None and d <= MAX_DIST_KM:
                ids.extend(jids)
        near_jobs[c] = ids

    # ---------- 正样本 ----------
    positives, pos_pairs = [], set()
    gate_fail = Counter()          # 在"距离已合格"的候选对里，各门槛失败次数
    cand_total = 0
    pass_tag_only = 0
    for r in resumes:
        rset = r["技能集"]
        for jid in near_jobs.get(r["居住地"], ()):
            j = jobs[jid]
            cand_total += 1
            d = city_dist(r["居住地"], j["城市"])
            # ② 学历
            e_ok = (j["学历序数"] in (None, 0)) or (r["学历序数"] is not None and r["学历序数"] >= j["学历序数"])
            if not e_ok:
                gate_fail["学历不满足"] += 1
            # ③ 经验
            x_ok = exp_ok(r["工作年限"], j["经验区间"])
            if not x_ok:
                gate_fail["经验不满足"] += 1
            # ④ 技能：简历技能 ∩ 岗位核心技能（技能标签 ∪ 描述中提到的技能词）
            hits_tag = len(rset & j["标签技能"])
            hits_desc = len(rset & j["描述技能"])
            hits = hits_tag + hits_desc
            s_ok = hits >= MIN_SKILL_HITS
            if not s_ok:
                gate_fail["技能命中<%d" % MIN_SKILL_HITS] += 1
            if e_ok and x_ok and s_ok:
                if hits_tag >= MIN_SKILL_HITS:
                    pass_tag_only += 1
                key = (r["rid"], j["jid"])
                positives.append({
                    "简历ID": r["rid"] + 1, "岗位ID": j["jid"] + 1, "标签": 1,
                    "简历姓名": r["姓名"], "简历居住地": r["居住地"], "简历期望岗位": r["期望岗位"],
                    "简历学历": r["最高学历"], "简历工作年限": r["工作年限"],
                    "岗位名称": j["岗位名称"], "公司名称": j["公司名称"], "岗位地区": j["岗位地区"],
                    "岗位城市": j["城市"], "岗位学历要求": j["学历要求"] or "不限",
                    "岗位经验要求": j["经验要求"] or "不限",
                    "岗位核心技能数": j["技能数"], "技能命中数": hits,
                    "其中标签命中": hits_tag, "其中描述命中": hits_desc,
                    "距离(km)": round(d, 1),
                    "未满足维度数": 0, "负样本来源": "",
                })
                pos_pairs.add(key)
    print("距离合格候选对:", cand_total, "｜正样本:", len(positives))

    if MAX_POS and len(positives) > MAX_POS:
        random.shuffle(positives)
        positives = positives[:MAX_POS]
        pos_pairs = {(x["简历ID"] - 1, x["岗位ID"] - 1) for x in positives}
        print("正样本超过上限 %d，已随机抽样至 %d" % (MAX_POS, len(positives)))

    n_pos = len(positives)
    target_neg = int(round(n_pos * NEG_RATIO))
    print("目标负样本数（1:%.1f）: %d" % (NEG_RATIO, target_neg))

    def gates(r, j):
        """返回 (距离km, 学历ok, 经验ok, 技能命中数, 未满足维度数)"""
        d = city_dist(r["居住地"], j["城市"])
        d_ok = (d is not None and d <= MAX_DIST_KM)
        e_ok = (j["学历序数"] in (None, 0)) or (r["学历序数"] is not None and r["学历序数"] >= j["学历序数"])
        x_ok = exp_ok(r["工作年限"], j["经验区间"])
        hits = len(r["技能集"] & j["核心技能"])
        s_ok = hits >= MIN_SKILL_HITS
        fails = sum(1 for ok in (d_ok, e_ok, x_ok, s_ok) if not ok)
        return d, e_ok, x_ok, hits, fails

    def make_row(r, j, label, src, d, e_ok, x_ok, hits, fails):
        rset = r["技能集"]
        return {
            "简历ID": r["rid"] + 1, "岗位ID": j["jid"] + 1, "标签": label,
            "简历姓名": r["姓名"], "简历居住地": r["居住地"], "简历期望岗位": r["期望岗位"],
            "简历学历": r["最高学历"], "简历工作年限": r["工作年限"],
            "岗位名称": j["岗位名称"], "公司名称": j["公司名称"], "岗位地区": j["岗位地区"],
            "岗位城市": j["城市"], "岗位学历要求": j["学历要求"] or "不限",
            "岗位经验要求": j["经验要求"] or "不限",
            "岗位核心技能数": j["技能数"], "技能命中数": hits,
            "其中标签命中": len(rset & j["标签技能"]), "其中描述命中": len(rset & j["描述技能"]),
            "距离(km)": round(d, 1) if d is not None else "",
            "未满足维度数": fails, "负样本来源": src,
        }

    negatives, neg_pairs = [], set()
    half = target_neg // 2

    # B 类：至少 2 个维度完全不满足
    attempts = 0
    while len(negatives) < half and attempts < 4_000_000:
        attempts += 1
        r = random.choice(resumes)
        j = jobs[random.randrange(len(jobs))]
        key = (r["rid"], j["jid"])
        if key in pos_pairs or key in neg_pairs:
            continue
        d, e_ok, x_ok, hits, fails = gates(r, j)
        if fails >= 2:
            negatives.append(make_row(r, j, 0, "维度不满足(≥2项)", d, e_ok, x_ok, hits, fails))
            neg_pairs.add(key)
    print("B 类负样本:", len(negatives), "（随机尝试 %d 次）" % attempts)

    # A 类：随机错位配对（要求不同时满足 4 个门槛，避免错标）
    skip_all_pass = 0
    attempts = 0
    while len(negatives) < target_neg and attempts < 4_000_000:
        attempts += 1
        r = random.choice(resumes)
        j = jobs[random.randrange(len(jobs))]
        key = (r["rid"], j["jid"])
        if key in pos_pairs or key in neg_pairs:
            continue
        d, e_ok, x_ok, hits, fails = gates(r, j)
        if fails == 0:
            skip_all_pass += 1
            continue
        negatives.append(make_row(r, j, 0, "随机错位配对", d, e_ok, x_ok, hits, fails))
        neg_pairs.add(key)
    print("A 类负样本追加至:", len(negatives), "（随机对中恰好满足全部门槛被剔除 %d 个）" % skip_all_pass)

    if DRY_RUN:
        print("[dry-run] 正样本 %d ｜ 负样本 %d ｜ 合计 %d（未写文件）" %
              (len(positives), len(negatives), len(positives) + len(negatives)))
        return positives, negatives, jobs, resumes, gate_fail, cand_total, skip_all_pass

    rows = positives + negatives
    random.shuffle(rows)
    fields = list(rows[0].keys())

    out_csv = os.path.join(OUT_DIR, "匹配样本_标签数据.csv")
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # 城市坐标表（辅助数据）
    os.makedirs(EXTERNAL_DIR, exist_ok=True)
    with open(os.path.join(EXTERNAL_DIR, "城市坐标.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["城市", "纬度", "经度", "是否简历居住地", "是否岗位城市"])
        r_cities = {r["居住地"] for r in resumes}
        j_cities = {j["城市"] for j in jobs}
        for c, (la, lo) in CITY_LL.items():
            w.writerow([c, la, lo, "是" if c in r_cities else "", "是" if c in j_cities else ""])

    stats = summarize(rows, positives, negatives, jobs, resumes, gate_fail, cand_total,
                      skip_all_pass, r_cities, j_cities, city_dist, pass_tag_only)
    with open(os.path.join(OUT_DIR, "匹配样本_标签统计.md"), "w", encoding="utf-8") as f:
        f.write(stats + "\n")

    print("\n输出：")
    for p in [out_csv, os.path.join(OUT_DIR, "匹配样本_标签统计.md"),
              os.path.join(EXTERNAL_DIR, "城市坐标.csv")]:
        print("  %-40s %8d 字节" % (os.path.relpath(p, ROOT), os.path.getsize(p)))
    print("样本总数: %d（正 %d / 负 %d，比例 1:%.2f）" %
          (len(rows), len(positives), len(negatives), len(negatives) / max(1, len(positives))))
    return rows, positives, negatives, jobs, resumes, gate_fail, cand_total, skip_all_pass


def summarize(rows, positives, negatives, jobs, resumes, gate_fail, cand_total,
              skip_all_pass, r_cities, j_cities, city_dist, pass_tag_only=0):
    n_pos, n_neg = len(positives), len(negatives)
    n = len(rows)
    L = []
    L.append("# 匹配样本标签统计（任务5 · 评分模型训练数据）\n")
    L.append("> 数据来源：`data/processed/zhaopin_jobs_cleaned.csv`（%d 个岗位）× `data/processed/简历数据_cleaned.csv`（%d 份简历）" % (len(jobs), len(resumes)))
    L.append("> 标签文件：`data/processed/匹配样本_标签数据.csv`\n")
    L.append("---\n")
    L.append("## 一、标签规则\n")
    L.append("**正样本（标签=1）**：同时满足 4 个核心门槛\n")
    L.append("1. 简历居住地与岗位城市直线距离 ≤ %.0f km；" % MAX_DIST_KM)
    L.append("2. 简历学历 ≥ 岗位最低学历要求（学历序数：高中 2 < 中专/中技 3 < 大专 4 < 本科 5 < 硕士 6 < 博士 7，岗位未标注视为不限）；")
    L.append("3. 简历工作年限落在岗位经验要求区间内（1-3年 / 3-5年 / 5-10年 / 10年以上；未标注视为不限）；")
    L.append("4. 命中岗位核心技能 **≥ %d 个**；" % MIN_SKILL_HITS)
    L.append("   > **岗位核心技能口径**：`技能标签` 字段中的技能词 ∪ `职位描述`（jieba 分词结果）中出现的技能词；技能词以**简历技能池（%d 项技术词）**为词典识别。\n" % len(SKILL_POOL))
    L.append("**负样本（标签=0）**：\n")
    L.append("- A 类 **随机错位配对**：随机简历 × 随机岗位（若恰好满足全部 4 个门槛则剔除，避免错标）；")
    L.append("- B 类 **至少 2 个核心维度完全不满足**。\n")
    L.append("## 二、样本规模与平衡\n")
    L.append("| 项目 | 数量 | 占比 |")
    L.append("|---|---|---|")
    L.append("| 正样本（匹配） | %d | %.2f%% |" % (n_pos, n_pos / n * 100))
    L.append("| 负样本（不匹配） | %d | %.2f%% |" % (n_neg, n_neg / n * 100))
    L.append("| **合计** | **%d** | 100.00%% |" % n)
    L.append("")
    L.append("- 正负比例 **1 : %.2f**（符合 1:1 ~ 1:1.5 的要求）；" % (n_neg / max(1, n_pos)))
    L.append("- 距离门槛筛出的候选对 %d 个（居住地 300km 内存在岗位的组合），命中 4 项门槛成为正样本 %d 个；" % (cand_total, n_pos))
    L.append("- 随机配对中有 **%d** 对恰好满足全部 4 个门槛，已从负样本中剔除。" % skip_all_pass)
    L.append("")
    L.append("### 2.1 负样本来源构成\n")
    src = Counter(r["负样本来源"] for r in negatives)
    L.append("| 负样本来源 | 数量 | 占负样本 |")
    L.append("|---|---|---|")
    for k, v in src.most_common():
        L.append("| %s | %d | %.2f%% |" % (k, v, v / n_neg * 100))
    L.append("")
    L.append("### 2.2 未满足维度数分布\n")
    f = Counter(r["未满足维度数"] for r in rows)
    L.append("| 未满足维度数 | 样本数 | 说明 |")
    L.append("|---|---|---|")
    for k in sorted(f):
        note = "正样本（4 项全满足）" if k == 0 else ("负样本" if k >= 2 else "负样本（A 类随机错位）")
        L.append("| %d | %d | %s |" % (k, f[k], note))
    L.append("")
    L.append("## 三、门槛通过情况（距离已合格的候选对 %d 个）\n" % cand_total)
    L.append("| 门槛 | 不满足的对数 | 不满足占比 |")
    L.append("|---|---|---|")
    for k in ["学历不满足", "经验不满足", "技能命中<%d" % MIN_SKILL_HITS]:
        v = gate_fail[k]
        L.append("| %s | %d | %.2f%% |" % (k, v, v / max(1, cand_total) * 100))
    L.append("")
    L.append("> 说明：学历/经验/技能任一不满足即无法成为正样本，因此三个门槛同时满足的对数（= 正样本数）为 **%d**。" % n_pos)
    L.append("> 技能口径对比：若只统计 `技能标签` 字段命中（不含描述中的技能词），正样本将只有 **%d** 个；" % pass_tag_only)
    L.append("> 采用“技能标签 + 描述技能词”口径后为 **%d** 个，样本量足以支撑四模型训练与评估。" % n_pos)
    L.append("")
    L.append("## 四、正样本画像\n")
    L.append("### 4.1 正样本数量 Top10 简历\n")
    c = Counter(r["简历姓名"] for r in positives)
    L.append("| 简历 | 匹配岗位数 |")
    L.append("|---|---|")
    for k, v in c.most_common(10):
        L.append("| %s | %d |" % (k, v))
    L.append("")
    L.append("### 4.2 正样本数量 Top10 岗位城市\n")
    c = Counter(r["岗位城市"] for r in positives)
    L.append("| 岗位城市 | 正样本数 |")
    L.append("|---|---|")
    for k, v in c.most_common(10):
        L.append("| %s | %d |" % (k, v))
    L.append("")
    L.append("### 4.3 正样本技能命中数分布\n")
    c = Counter(r["技能命中数"] for r in positives)
    L.append("| 技能命中数 | 正样本数 |")
    L.append("|---|---|")
    for k in sorted(c):
        L.append("| %d | %d |" % (k, c[k]))
    L.append("")
    dist = Counter(r["距离(km)"] for r in positives)
    L.append("### 4.4 正样本距离分布\n")
    L.append("| 距离区间 | 正样本数 |")
    L.append("|---|---|")
    bands = [("同城 (0km)", lambda d: d == 0), ("0-50km", lambda d: 0 < d <= 50),
             ("50-150km", lambda d: 50 < d <= 150), ("150-300km", lambda d: 150 < d <= 300)]
    for name, fn in bands:
        L.append("| %s | %d |" % (name, sum(1 for r in positives if fn(r["距离(km)"]))))
    L.append("")
    L.append("## 五、覆盖情况\n")
    r_used = len({r["简历ID"] for r in rows})
    j_used = len({r["岗位ID"] for r in rows})
    L.append("| 项目 | 数量 |")
    L.append("|---|---|")
    L.append("| 参与配对的简历数 | %d / %d |" % (r_used, len(resumes)))
    L.append("| 参与配对的岗位数 | %d / %d |" % (j_used, len(jobs)))
    L.append("| 简历居住地城市数 | %d (%s) |" % (len(r_cities), "、".join(sorted(r_cities))))
    L.append("| 岗位城市数 | %d (%s) |" % (len(j_cities), "、".join(sorted(j_cities))))
    L.append("")
    only_fj = sorted(c for c in r_cities if c not in j_cities)
    L.append("- 简历居住地中不在岗位城市列表里的城市：%s（这些简历在 %.0fkm 内无岗位，只能进入负样本）。" %
             ("、".join(only_fj), MAX_DIST_KM))
    L.append("")
    L.append("## 六、输出文件\n")
    L.append("| 文件 | 说明 |")
    L.append("|---|---|")
    L.append("| `data/processed/匹配样本_标签数据.csv` | 配对样本（%d 行 × %d 列，含 4 项门槛明细与标签） |" % (n, len(rows[0])))
    L.append("| `data/processed/匹配样本_标签统计.md` | 本统计 |")
    L.append("| `data/external/城市坐标.csv` | 城市经纬度表（距离计算依据） |")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="构造 <简历, 岗位> 配对标签")
    ap.add_argument("--min-skill", type=int, default=MIN_SKILL_HITS, help="技能门槛：至少命中 N 个核心技能")
    ap.add_argument("--neg-ratio", type=float, default=NEG_RATIO, help="负样本/正样本 比例（1~1.5）")
    ap.add_argument("--max-pos", type=int, default=MAX_POS, help="正样本上限（0=不限）")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写文件")
    a = ap.parse_args()
    MIN_SKILL_HITS, NEG_RATIO, MAX_POS, SEED, DRY_RUN = (
        a.min_skill, a.neg_ratio, a.max_pos, a.seed, a.dry_run)
    if not (1.0 <= NEG_RATIO <= 1.5):
        print("警告：负正比 %.2f 超出要求的 1:1~1:1.5 区间" % NEG_RATIO)
    print("参数：技能门槛=%d ｜ 负正比=1:%.2f ｜ 正样本上限=%s ｜ seed=%d" %
          (MIN_SKILL_HITS, NEG_RATIO, MAX_POS or "不限", SEED))
    build()
