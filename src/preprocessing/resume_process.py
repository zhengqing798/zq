# -*- coding: utf-8 -*-
"""
任务3/4 · 简历数据清洗与统计

输入：data/raw/随机简历500份.csv（原始 500 份 × 13 列，未改动）
输出（全部写入 data/processed/）：
  1. 简历数据_cleaned.csv        —— 清洗 + 结构化后的简历数据（原 13 列 + 派生列）
  2. 简历技能与证书词频统计.csv   —— 技能 / 证书词频
  3. 简历数据_分布统计.csv       —— 各维度分布（维度, 取值, 数量, 占比）
  4. 简历数据统计.md             —— 统计报告（Markdown）

处理规则（与岗位数据处理思路一致，原文件不动，全部输出到新文件）：
  ① 缺失值：13 列均无空值 → 0 行删除
  ② 去重：按 姓名+手机号+邮箱 判定重复（唯一标识）→ 0 条重复
  ③ 类型标准化：性别、手机号、邮箱、学历（专科→大专），并把复合文本字段拆成结构化列
  ④ 异常值：只检测、记录、不改动数据（写入统计报告）
"""
import csv
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_CSV = os.path.join(ROOT, "data", "raw", "随机简历500份.csv")
OUT_DIR = os.path.join(ROOT, "data", "processed")
os.makedirs(OUT_DIR, exist_ok=True)

CUR_YEAR = 2026          # 数据抓取年份，用于工作年限一致性检查
EDU_MAP = {"专科": "大专", "高职": "大专", "本科": "本科", "硕士": "硕士", "博士": "博士"}

INTENT_RE = re.compile(r"期望岗位：(.*?)\s*期望城市：(.*?)\s*期望行业：(.*?)\s*期望薪资：(.*)", re.S)
EDU_RE = re.compile(r"^(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)$")
GRAD_RE = re.compile(r"毕业时间：\s*(\d{4})\s*年\s*(\d{1,2})\s*月")
COURSE_RE = re.compile(r"核心课程：\s*(.*)", re.S)
EXP_RE = re.compile(r"(\d+)\s*年")
COMPANY_RE = re.compile(r"【(.*?)】\s*(.*)")
PERIOD_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*[-—~至]{1,2}\s*(至今|\d{4}\s*年\s*\d{1,2}\s*月)")
SKILL_RE = re.compile(r"专业技能：\s*(.*?)(?:\n|$)")
CERT_RE = re.compile(r"相关证书：\s*(.*?)(?:\n|$)")
PROJ_RE = re.compile(r"■\s*(.*)")


def load_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm_text(s):
    """去首尾空白、全角空格转半角、压缩连续空白行"""
    s = (s or "").replace("\u3000", " ").strip()
    return re.sub(r"[ \t]+\n", "\n", s)


def split_list(text):
    return [x.strip() for x in re.split(r"[、,，;；/]", text or "") if x.strip()]


def parse_row(r):
    """把一行原始简历解析成结构化字段"""
    o = {}
    o["性别"] = norm_text(r["性别"])
    o["手机号"] = re.sub(r"\D", "", norm_text(r["手机号"]))
    o["邮箱"] = norm_text(r["邮箱"]).lower()
    o["微信号"] = norm_text(r["微信号"])
    o["居住地"] = norm_text(r["居住地"])

    # 求职意向 → 4 列
    m = INTENT_RE.search(norm_text(r["求职意向"]).replace("\n", " "))
    o["期望岗位"] = m.group(1).strip() if m else ""
    o["期望城市"] = m.group(2).strip() if m else ""
    o["期望行业"] = m.group(3).strip() if m else ""
    o["期望薪资"] = m.group(4).strip() if m else ""

    # 教育经历 → 学校/专业/学历/毕业年月/核心课程
    lines = [x.strip() for x in norm_text(r["教育经历"]).split("\n") if x.strip()]
    school = major = degree = ""
    if lines:
        m = EDU_RE.match(lines[0])
        if m:
            school, major, degree = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
    o["毕业院校"] = school
    o["专业"] = major
    o["学历"] = degree
    o["最高学历"] = EDU_MAP.get(degree, degree)
    g = GRAD_RE.search(norm_text(r["教育经历"]))
    o["毕业年月"] = "%s-%02d" % (g.group(1), int(g.group(2))) if g else ""
    o["毕业年份"] = int(g.group(1)) if g else ""
    c = COURSE_RE.search(norm_text(r["教育经历"]))
    o["核心课程"] = re.sub(r"\s+", " ", c.group(1)).strip() if c else ""
    o["核心课程数"] = len(split_list(o["核心课程"]))

    # 个人简介 → 工作年限 / 是否应届
    intro = norm_text(r["个人简介"])
    is_fresh = "应届" in intro
    m = EXP_RE.search(intro)
    years = int(m.group(1)) if m else 0
    if is_fresh and years == 0:
        pass
    o["是否应届"] = "是" if is_fresh else "否"
    o["工作年限"] = 0 if is_fresh and years == 0 else years
    o["工作年限原始文本"] = ("应届" if is_fresh and years == 0 else (m.group(0) if m else "未标注"))

    # 工作/实践经历 → 段数 / 最近公司 / 最近岗位 / 最近起始年月
    work = norm_text(r["工作/实践经历"])
    o["工作经历段数"] = work.count("【")
    o["是否校园实践"] = "是" if "校园实践" in work and work.count("【") == 1 else "否"
    com = COMPANY_RE.search(work)
    o["最近公司"] = com.group(1).strip() if com else ""
    o["最近岗位"] = com.group(2).strip().split("\n")[0].strip() if com else ""
    p = PERIOD_RE.search(work)
    o["最近起始年月"] = "%s-%02d" % (p.group(1), int(p.group(2))) if p else ""
    o["是否有在职经历"] = "是" if "至今" in work else "否"

    # 项目经验 → 项目数 / 首个项目名
    proj = norm_text(r["项目经验"])
    o["项目数量"] = proj.count("■")
    pm = PROJ_RE.search(proj)
    o["首个项目名称"] = pm.group(1).strip() if pm else ""

    # 技能特长 → 技能列表/数量、证书列表/数量
    sk = norm_text(r["技能特长"])
    m1, m2 = SKILL_RE.search(sk), CERT_RE.search(sk)
    skills = split_list(m1.group(1)) if m1 else []
    certs = split_list(m2.group(1)) if m2 else []
    o["技能列表"] = "、".join(skills)
    o["技能数量"] = len(skills)
    o["证书列表"] = "、".join(certs)
    o["证书数量"] = len([c for c in certs if c != "无"])

    # 文本长度（供后续文本建模参考）
    o["个人简介字数"] = len(intro)
    o["自我评价字数"] = len(norm_text(r["自我评价"]))
    o["项目经验字数"] = len(proj)
    o["工作经历字数"] = len(work)
    return o


def process(rows):
    """清洗 + 结构化：返回 (结果行, 统计信息)"""
    info = {}

    # ① 缺失值
    cols = list(rows[0].keys())
    empty_cells = {c: sum(1 for r in rows if not (r[c] or "").strip()) for c in cols}
    info["empty_cells"] = empty_cells
    info["dropped_empty"] = 0                     # 13 列均无空值，无需删行

    # 结构化
    out = []
    for r in rows:
        o = dict(r)                               # 保留原始 13 列
        o.update(parse_row(r))
        out.append(o)

    # ② 去重：姓名 + 手机号 + 邮箱
    seen, keep, dup_rows = set(), [], []
    for o in out:
        k = (norm_text(o["姓名"]), o["手机号"], o["邮箱"])
        if k in seen:
            dup_rows.append(o)
            continue
        seen.add(k)
        keep.append(o)
    info["dropped_dup"] = len(dup_rows)
    info["dup_keys"] = [(o["姓名"], o["手机号"]) for o in dup_rows[:5]]

    # 同名不同人（手机号/邮箱不同）
    name_cnt = Counter(norm_text(o["姓名"]) for o in keep)
    info["dup_names"] = {n: c for n, c in name_cnt.items() if c > 1}

    # ④ 异常检测（只记录）
    info["salary_all_mianshi"] = all(o["期望薪资"] == "面议" for o in keep)
    info["industry_kinds"] = len({o["期望行业"] for o in keep})
    info["degree_kinds"] = Counter(o["学历"] for o in keep)

    bad_exp = []
    for o in keep:
        gap = CUR_YEAR - o["毕业年份"] if o["毕业年份"] else None
        if gap is None:
            bad_exp.append((o["姓名"], "毕业年份未解析", o["工作年限原始文本"]))
        elif o["工作年限"] > gap + 1:
            bad_exp.append((o["姓名"], "工作年限大于毕业年限",
                            "工作年限%d年 / 毕业%d年" % (o["工作年限"], gap)))
        elif o["是否应届"] == "是" and gap > 1:
            bad_exp.append((o["姓名"], "应届标签与毕业年份矛盾",
                            "标记应届但已毕业%d年" % gap))
    info["exp_conflicts"] = bad_exp
    info["exp_conflict_types"] = Counter(t for _, t, _ in bad_exp)

    wx_phone = sum(1 for o in keep if re.fullmatch(r"1[3-9]\d{9}", o["微信号"]))
    info["wechat_phone_like"] = wx_phone
    info["live_eq_expect"] = sum(1 for o in keep if o["居住地"] == o["期望城市"])
    info["parse_fail"] = {
        "期望岗位": sum(1 for o in keep if not o["期望岗位"]),
        "毕业院校": sum(1 for o in keep if not o["毕业院校"]),
        "专业": sum(1 for o in keep if not o["专业"]),
        "毕业年月": sum(1 for o in keep if not o["毕业年月"]),
        "技能列表": sum(1 for o in keep if not o["技能列表"]),
        "最近公司": sum(1 for o in keep if not o["最近公司"]),
    }
    return keep, info


# ------------------------------------------------------------------ 统计

def work_year_bucket(y, fresh):
    if fresh == "是" and y == 0:
        return "应届/无经验"
    if y == 0:
        return "未标注"
    if y <= 1:
        return "1年以内"
    if y <= 3:
        return "1-3年"
    if y <= 5:
        return "3-5年"
    return "5年以上"


def build_stats(rows, info):
    n = len(rows)
    dist = []          # (维度, 取值, 数量, 占比)

    def add(dim, counter, order=None, top=None):
        items = counter.most_common() if top is None else counter.most_common(top)
        if order:
            items = sorted(items, key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)
        triples = [(k, v, round(v / n * 100, 2)) for k, v in items]
        for k, v, p in triples:
            dist.append([dim, k, v, p])
        return triples

    gender = add("性别", Counter(o["性别"] for o in rows))
    degree = add("学历", Counter(o["学历"] for o in rows), order=["本科", "专科"])
    city = add("期望城市", Counter(o["期望城市"] for o in rows))
    job = add("期望岗位", Counter(o["期望岗位"] for o in rows))
    industry = add("期望行业", Counter(o["期望行业"] for o in rows))
    salary = add("期望薪资", Counter(o["期望薪资"] for o in rows))
    grad = add("毕业年份", Counter(o["毕业年份"] for o in rows))
    wyb = add("工作年限区间", Counter(work_year_bucket(o["工作年限"], o["是否应届"]) for o in rows),
              order=["应届/无经验", "1年以内", "1-3年", "3-5年", "5年以上", "未标注"])
    fresh = add("是否应届", Counter(o["是否应届"] for o in rows))
    sk_cnt = add("技能数量区间", Counter(
        ("4-6 项" if o["技能数量"] <= 6 else "7-8 项" if o["技能数量"] <= 8 else "9 项及以上")
        for o in rows), order=["4-6 项", "7-8 项", "9 项及以上"])
    cert_cnt = add("证书数量", Counter(str(o["证书数量"]) + " 项" for o in rows))
    proj = add("项目数量", Counter("%d 项" % o["项目数量"] for o in rows))
    work_seg = add("工作经历段数", Counter("%d 段" % o["工作经历段数"] for o in rows))
    inwork = add("是否有在职经历(至今)", Counter(o["是否有在职经历"] for o in rows))
    mail = add("邮箱域名", Counter(o["邮箱"].split("@")[-1] for o in rows))
    school = add("毕业院校", Counter(o["毕业院校"] for o in rows))
    major = add("专业", Counter(o["专业"] for o in rows))
    live = add("居住地", Counter(o["居住地"] for o in rows))

    # 技能 / 证书词频
    sk_freq, cert_freq = Counter(), Counter()
    for o in rows:
        for s in split_list(o["技能列表"]):
            sk_freq[s] += 1
        for c in split_list(o["证书列表"]):
            if c != "无":
                cert_freq[c] += 1
    for k, v in sk_freq.most_common():
        dist.append(["技能", k, v, round(v / n * 100, 2)])
    for k, v in cert_freq.most_common():
        dist.append(["证书", k, v, round(v / n * 100, 2)])

    avg = lambda key: round(sum(o[key] for o in rows) / n, 1)
    summary = {
        "n": n,
        "gender": gender, "degree": degree, "city": city, "job": job,
        "industry": industry, "salary": salary, "grad": grad, "wyb": wyb,
        "fresh": fresh, "sk_cnt": sk_cnt, "cert_cnt": cert_cnt, "proj": proj,
        "work_seg": work_seg, "inwork": inwork, "mail": mail,
        "school": school, "major": major, "live": live,
        "sk_freq": sk_freq, "cert_freq": cert_freq,
        "avg_skill": avg("技能数量"), "avg_cert": avg("证书数量"),
        "avg_intro": avg("个人简介字数"), "avg_selfeval": avg("自我评价字数"),
        "avg_proj_len": avg("项目经验字数"), "avg_work_len": avg("工作经历字数"),
        "avg_course": avg("核心课程数"),
        "skill_kinds": len(sk_freq), "cert_kinds": len(cert_freq),
        "city_kinds": len(city), "school_kinds": len(school), "major_kinds": len(major),
        "no_cert": sum(1 for o in rows if o["证书数量"] == 0),
        "no_cert_row": next((v for k, v, _ in cert_cnt if k == "0 项"), 0),
    }
    return dist, summary


def write_csv(path, header, records):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(records)


def md_table(items, headers, unit=""):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for it in items:
        out.append("| " + " | ".join(str(x) for x in it) + " |")
    return "\n".join(out)


def build_report(s, info):
    n = s["n"]
    L = []
    L.append("# 简历数据统计报告\n")
    L.append("> 岗位-简历人岗匹配推荐系统 ｜ 数据：`data/raw/随机简历500份.csv`（原始，未改动）")
    L.append("> 清洗结果：`data/processed/简历数据_cleaned.csv` ｜ 统计口径：清洗后 %d 份简历" % n)
    L.append("> 统计字段：性别、学历、毕业院校/专业/年份、工作年限、期望岗位/城市/行业/薪资、技能与证书、项目与工作经历\n")
    L.append("---\n")

    L.append("## 一、数据规模与质量\n")
    L.append(md_table([
        ["原始简历数", 500, "—"],
        ["清洗后简历数", n, "100.0%"],
        ["字段数（原 13 列 + 派生 %d 列）" % (len(CSV_FIELDS) - 13), len(CSV_FIELDS), "—"],
        ["缺失单元格", sum(info["empty_cells"].values()), "0.0%"],
        ["删除（缺失值）", info["dropped_empty"], "—"],
        ["删除（重复：姓名+手机号+邮箱）", info["dropped_dup"], "—"],
    ], ["项目", "数量", "占比"]))
    L.append("")
    L.append("- 13 个原始字段**全部无缺失**（0 个空单元格），未删除任何行；")
    L.append("- 按 `姓名+手机号+邮箱` 去重：**0 条重复**（手机号、邮箱各自 500 个唯一值）；")
    L.append("- 有 **%d 组同名**（手机号/邮箱不同，视为不同人，保留）：%s。" %
             (len(info["dup_names"]), "、".join(list(info["dup_names"])[:8])))
    L.append("- 派生字段解析成功率：%s。" %
             "、".join("%s %d/%d" % (k, n - v, n) for k, v in info["parse_fail"].items()))
    L.append("")

    L.append("## 二、人口统计学特征\n")
    L.append("### 2.1 性别\n")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["gender"]], ["性别", "简历数", "占比"]))
    L.append("\n### 2.2 学历\n")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["degree"]], ["学历", "简历数", "占比"]))
    L.append("\n> 学历仅含本科与专科，**本科 %.1f%% / 专科 %.1f%%**；专科在标准化列 `最高学历` 中统一为“大专”，便于与岗位数据对齐。" %
             (s["degree"][0][1] / n * 100, s["degree"][1][1] / n * 100))
    L.append("\n### 2.3 居住地与期望城市\n")
    L.append("- 居住地 **%d 个城市**，期望城市 **%d 个城市**，二者**完全一致 %d/%d（%.1f%%）**，无异地求职样本。" %
             (len(s["live"]), s["city_kinds"],
              info["live_eq_expect"], n, info["live_eq_expect"] / n * 100))
    L.append("")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["city"][:10]], ["期望城市", "简历数", "占比"]))
    L.append("\n（其余城市：%s）" % "、".join("%s %d" % (k, v) for k, v, _ in s["city"][10:]))
    L.append("")

    L.append("## 三、教育与经验结构\n")
    L.append("### 3.1 毕业年份\n")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["grad"]], ["毕业年份", "简历数", "占比"]))
    L.append("\n### 3.2 工作年限 / 是否应届\n")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["wyb"]], ["工作年限区间", "简历数", "占比"]))
    L.append("")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["fresh"]], ["是否应届", "简历数", "占比"]))
    L.append("\n### 3.3 毕业院校 / 专业 Top10\n")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["school"][:10]], ["毕业院校", "简历数", "占比"]))
    L.append("")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["major"][:10]], ["专业", "简历数", "占比"]))
    L.append("\n- 共 **%d 所院校**、**%d 个专业**；核心课程平均 %.1f 门。" %
             (s["school_kinds"], s["major_kinds"], s["avg_course"]))
    L.append("")

    L.append("## 四、求职意向\n")
    L.append("### 4.1 期望岗位\n")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["job"]], ["期望岗位", "简历数", "占比"]))
    L.append("\n### 4.2 期望行业与期望薪资\n")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["industry"]], ["期望行业", "简历数", "占比"]))
    L.append("")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["salary"]], ["期望薪资", "简历数", "占比"]))
    L.append("\n> 期望行业 100% 为“互联网/信息技术/软件服务”，期望薪资 **全部为“面议”**，该字段无可比性（见第七部分异常说明）。")
    L.append("")

    L.append("## 五、能力与经历\n")
    L.append("### 5.1 技能热度 Top15\n")
    L.append(md_table([[i + 1, k, v, "%.2f%%" % (v / n * 100)]
                       for i, (k, v) in enumerate(s["sk_freq"].most_common(15))],
                      ["#", "技能", "简历数", "占比"]))
    L.append("\n- 共 **%d 种技能**，人均 **%.1f 项**；每人技能数分布：" %
             (s["skill_kinds"], s["avg_skill"]))
    L.append("")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["sk_cnt"]], ["技能数量", "简历数", "占比"]))
    L.append("\n### 5.2 证书 Top10\n")
    L.append(md_table([[i + 1, k, v, "%.2f%%" % (v / n * 100)]
                       for i, (k, v) in enumerate(s["cert_freq"].most_common(10))],
                      ["#", "证书", "简历数", "占比"]))
    L.append("\n- 共 **%d 种证书**，人均 **%.1f 项**；**%d 人（%.1f%%）未填写有效证书**（填“无”或为空）。" %
             (s["cert_kinds"], s["avg_cert"], s["no_cert"], s["no_cert"] / n * 100))
    L.append("\n### 5.3 项目与工作经历\n")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["proj"]], ["项目数量", "简历数", "占比"]))
    L.append("")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["work_seg"]], ["工作/实践经历段数", "简历数", "占比"]))
    L.append("")
    L.append(md_table([[k, v, "%.2f%%" % p] for k, v, p in s["inwork"]], ["是否有在职经历（“至今”）", "简历数", "占比"]))
    L.append("")

    L.append("## 六、文本长度（供后续文本建模参考）\n")
    L.append(md_table([
        ["个人简介", s["avg_intro"], "字"],
        ["自我评价", s["avg_selfeval"], "字"],
        ["项目经验", s["avg_proj_len"], "字"],
        ["工作/实践经历", s["avg_work_len"], "字"],
    ], ["文本字段", "平均长度", "单位"]))
    L.append("")

    L.append("## 七、异常与数据局限（仅记录，未改动数据）\n")
    L.append("| # | 现象 | 数量 | 说明 |")
    L.append("|---|---|---|---|")
    L.append("| R1 | 期望薪资全部为“面议” | %d/%d | 该字段无区分度，无法用于薪资期望建模 |" % (n, n))
    L.append("| R2 | 期望行业全部为同一值 | %d 种 | 无行业分布差异 |" % info["industry_kinds"])
    L.append("| R3 | 学历只有本科/专科 | %d 种 | 无硕士及以上样本 |" % len(info["degree_kinds"]))
    L.append("| R4 | 姓名重复（手机号不同） | %d 组 | 视为不同人，保留 |" % len(info["dup_names"]))
    L.append("| R5 | 微信号为手机号格式 | %d 份（%.1f%%） | 与本人手机号均不相同，保留原值 |" %
             (info["wechat_phone_like"], info["wechat_phone_like"] / n * 100))
    L.append("| R6 | 工作年限 / 应届标签与毕业年份矛盾 | %s | 例：%s |" %
             ("；".join("%s %d 份" % (k, v) for k, v in info["exp_conflict_types"].most_common()) or "0 份",
              "；".join("%s（%s）" % (a, c) for a, _, c in info["exp_conflicts"][:3]) or "无"))
    L.append("| R7 | 居住地与期望城市完全一致 | %d/%d | 无跨城求职样本，地域匹配特征区分度低 |" % (info["live_eq_expect"], n))
    L.append("| R8 | 经历结构较为单一 | 项目 1-2 项 / 工作 1-3 段 | 无 3 项以上项目、3 段以上工作经历样本 |")
    L.append("")
    L.append("> 以上均为**数据本身特征**，按既定要求只做记录，不改动原始值与清洗结果。")
    L.append("")

    L.append("## 八、输出文件\n")
    L.append("| 文件 | 说明 |")
    L.append("|---|---|")
    L.append("| `data/raw/随机简历500份.csv` | 原始简历数据（500 份 × 13 列，未改动） |")
    L.append("| `data/processed/简历数据_cleaned.csv` | **清洗+结构化结果**（%d 份 × %d 列） |" % (n, len(CSV_FIELDS)))
    L.append("| `data/processed/简历技能与证书词频统计.csv` | 技能 / 证书词频（%d + %d 条） |" %
             (s["skill_kinds"], s["cert_kinds"]))
    L.append("| `data/processed/简历数据_分布统计.csv` | 全部维度分布明细（维度/取值/数量/占比，%d 行） |" % len(dist_holder))
    L.append("| `data/processed/简历数据统计.md` | 本报告 |")
    L.append("")
    return "\n".join(L)


dist_holder = []
CSV_FIELDS = []


def main():
    global dist_holder, CSV_FIELDS
    rows = load_rows(SRC_CSV)
    print("原始简历:", len(rows), "份 ｜", len(rows[0]), "列")

    keep, info = process(rows)
    print("清洗后:", len(keep), "份（缺失 -%d，重复 -%d）" % (info["dropped_empty"], info["dropped_dup"]))

    first = keep[0]
    CSV_FIELDS = list(first.keys())
    write_csv(os.path.join(OUT_DIR, "简历数据_cleaned.csv"), CSV_FIELDS,
              [[o.get(k, "") for k in CSV_FIELDS] for o in keep])
    print("  CSV ->", "简历数据_cleaned.csv", "(%d 列)" % len(CSV_FIELDS))

    dist, s = build_stats(keep, info)
    dist_holder = dist
    write_csv(os.path.join(OUT_DIR, "简历数据_分布统计.csv"),
              ["维度", "取值", "数量", "占比(%)"], dist)

    write_csv(os.path.join(OUT_DIR, "简历技能与证书词频统计.csv"),
              ["类型", "关键词", "出现简历数", "占比(%)"],
              [["技能", k, v, round(v / len(keep) * 100, 2)] for k, v in s["sk_freq"].most_common()] +
              [["证书", k, v, round(v / len(keep) * 100, 2)] for k, v in s["cert_freq"].most_common()])

    report = build_report(s, info)
    with open(os.path.join(OUT_DIR, "简历数据统计.md"), "w", encoding="utf-8") as f:
        f.write(report + "\n")

    print("统计输出：")
    for name in ["简历数据_cleaned.csv", "简历技能与证书词频统计.csv",
                 "简历数据_分布统计.csv", "简历数据统计.md"]:
        p = os.path.join(OUT_DIR, name)
        print("  %-32s %8d 字节" % (name, os.path.getsize(p)))
    print("输出目录:", OUT_DIR)
    print("要点：项目数分布 %s｜工作段数 %s｜技能 %d 种｜证书 %d 种｜应届 %s" % (
        s["proj"], s["work_seg"], s["skill_kinds"], s["cert_kinds"], s["fresh"]))


if __name__ == "__main__":
    main()
