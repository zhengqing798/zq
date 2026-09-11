# -*- coding: utf-8 -*-
"""
任务3 · 简历文本处理：对简历文本列做 jieba 分词

输入：`data/raw/随机简历500份.csv`（500 份 × 13 列，原始，未改动）
输出：
  · `data/processed/简历数据_seg.csv` —— 原 13 列 + 7 个派生列（共 20 列）
      - `个人简介_分词`、`项目经验_分词`、`工作经历_分词`、`自我评价_分词`
        （长文本：保留词频、不去重，供 TF-IDF 等文本相似度使用）
      - `技能特长_分词`（短文本：去重保序）
      - `技能词`、`证书`（结构化列表，顿号分隔）
  · `data/processed/简历技能词频统计.csv` —— 技能/证书词频（出现简历数 + 占比）

做法要点：
  1. **自定义词典**：把 500 份简历里出现的技能词/证书词全部加入 jieba 词典，
     避免"数据可视化 → 数据|可视化""深度学习 → 深度|学习""接口测试 → 接口|测试"这类切错；
  2. **停用词**：过滤标点、结构词（专业技能/相关证书）、"无"、单字等；
  3. 长文本**保留重复词**（词频有意义），技能列表**去重**（集合语义）；
  4. 只新增列，**不覆盖/不修改原始 13 列**。

`教育经历` 未参与分词：其信息已由 `resume_process.py` 结构化为 毕业院校/专业/学历/毕业年月/核心课程，
分词只会引入校名等噪声。

运行：python src/preprocessing/resume_seg.py
"""
import csv
import os
import re
import sys
from collections import Counter

import jieba

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SRC = os.path.join(ROOT, "data", "raw", "随机简历500份.csv")
OUT = os.path.join(ROOT, "data", "processed", "简历数据_seg.csv")
FREQ = os.path.join(ROOT, "data", "processed", "简历技能词频统计.csv")

SKILL_RE = re.compile(r"专业技能[:：]\s*(.*?)(?:\n|$)", re.S)
CERT_RE = re.compile(r"相关证书[:：]\s*(.*?)(?:\n|$)", re.S)
EDU_LINE_RE = re.compile(r"^(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9+#.]+$|^[A-Za-z0-9+#.\u4e00-\u9fa5]+$")
CJK_RE = re.compile(r"^[\u4e00-\u9fa5]+$")

# 需要整体切出的结构短语（切碎后无法被停用词表命中）
STRUCT_PHRASES = ["专业技能", "相关证书", "核心课程", "毕业时间", "项目目标", "项目成果",
                  "个人职责", "校园实践"]

# 长文本字段 → 输出列名（教育经历因已结构化而不分词）
TEXT_FIELDS = [("个人简介", "个人简介_分词"),
               ("项目经验", "项目经验_分词"),
               ("工作/实践经历", "工作经历_分词"),
               ("自我评价", "自我评价_分词"),
               ("技能特长", "技能特长_分词")]

# 停用词：结构词 + 简历中高频但无区分度的虚词/通用词
STOPWORDS = {
    # 文本结构词
    "专业技能", "相关证书", "核心课程", "毕业时间", "项目目标", "项目成果", "个人职责", "校园实践",
    # 虚词 / 连词 / 副词
    "的", "了", "和", "与", "及", "或", "等", "并", "且", "以", "把", "被", "对", "为", "在", "是",
    "有", "无", "能", "会", "可", "该", "其", "之", "上", "下", "中", "内", "外", "后", "前", "时",
    "更加", "比较", "非常", "较为", "一定", "各种", "各项", "其他", "以及", "同时", "通过", "进行",
    # 简历通用表述
    "熟悉", "掌握", "了解", "精通", "具备", "具有", "拥有", "能力", "良好", "优秀", "较强", "扎实",
    "基础", "相关", "负责", "参与", "完成", "协助", "承担", "担任", "从事", "支持", "实现", "使用",
    "运用", "利用", "配合", "积极", "认真", "细致", "耐心", "踏实", "团队", "沟通", "学习", "成长",
    "经验", "工作", "任务", "内容", "要求", "目标", "成果", "职责", "输出", "提升", "优化", "解决",
    "问题", "思路", "意识", "态度", "素质", "表现", "情况", "方面", "过程", "阶段", "期间", "日常",
    "专业", "技能", "证书", "认证", "岗位", "行业", "公司", "校园", "课程", "设计", "毕业", "就业",
    "能够", "期望", "做事", "个人", "在工作中", "工作中", "有限公司", "快速", "注重", "细节", "积累",
}


def split_terms(text):
    """按顿号/逗号/分号切词，去空白"""
    return [t.strip() for t in re.split(r"[、,，;；/]+", text or "") if t.strip()]


def tokenize(text, dedup=False):
    """分词 + 过滤停用词/标点/单字；dedup=True 时去重保序"""
    toks = []
    for w in jieba.lcut(text or ""):
        w = w.strip()
        if not w or w in STOPWORDS or not TOKEN_RE.match(w):
            continue
        if CJK_RE.match(w) and len(w) < 2:        # 单个汉字
            continue
        if w.isdigit():                           # 纯数字（年份等）
            continue
        if len(w) < 2 and not CJK_RE.match(w):   # 单个字母/符号
            continue
        toks.append(w)
    return list(dict.fromkeys(toks)) if dedup else toks


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig", newline="")))
    src_fields = list(rows[0].keys())
    print("输入：%s（%d 行 × %d 列）" % (os.path.relpath(SRC, ROOT), len(rows), len(src_fields)))

    # ---------- ① 从简历自身抽取技能/证书/专业词，构建自定义词典 ----------
    skill_cnt, cert_cnt, major_set = Counter(), Counter(), set()
    for r in rows:
        t = r.get("技能特长") or ""
        m1, m2 = SKILL_RE.search(t), CERT_RE.search(t)
        for w in split_terms(m1.group(1)) if m1 else []:
            if w != "无":
                skill_cnt[w] += 1
        for w in split_terms(m2.group(1)) if m2 else []:
            if w != "无":
                cert_cnt[w] += 1
        edu = (r.get("教育经历") or "").split("\n")[0].strip()
        me = EDU_LINE_RE.match(edu)
        if me and me.group(2).strip():
            major_set.add(me.group(2).strip())
    dict_words = set(skill_cnt) | set(cert_cnt) | major_set | set(STRUCT_PHRASES)
    for w in dict_words:
        jieba.add_word(w, freq=10 ** 7)          # 高频，保证不被切开
    print("自定义词典：技能 %d 种、证书 %d 种、专业 %d 种（合计 %d 词）" % (
        len(skill_cnt), len(cert_cnt), len(major_set), len(dict_words)))

    # ---------- ② 逐行分词 ----------
    out_rows = []
    field_stats = {col: Counter() for _, col in TEXT_FIELDS}
    per_doc = {col: [] for _, col in TEXT_FIELDS}
    for r in rows:
        row = dict(r)
        for src_col, out_col in TEXT_FIELDS:
            toks = tokenize(r.get(src_col) or "", dedup=(src_col == "技能特长"))
            row[out_col] = " ".join(toks)
            field_stats[out_col].update(toks)
            per_doc[out_col].append(len(toks))

        t = r.get("技能特长") or ""
        m1, m2 = SKILL_RE.search(t), CERT_RE.search(t)
        row["技能词"] = "、".join(w for w in split_terms(m1.group(1)) if w != "无") if m1 else ""
        row["证书"] = "、".join(w for w in split_terms(m2.group(1)) if w != "无") if m2 else ""
        out_rows.append(row)

    new_fields = src_fields + [c for _, c in TEXT_FIELDS] + ["技能词", "证书"]
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=new_fields)
        w.writeheader()
        w.writerows(out_rows)
    print("输出：%s（%d 行 × %d 列）" % (os.path.relpath(OUT, ROOT), len(out_rows), len(new_fields)))

    # ---------- ③ 技能 / 证书词频 ----------
    with open(FREQ, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["类型", "关键词", "出现简历数", "占全部简历比例(%)"])
        for typ, cnt in (("技能", skill_cnt), ("证书", cert_cnt)):
            for k, v in cnt.most_common():
                w.writerow([typ, k, v, round(v / len(rows) * 100, 2)])
    print("输出：%s（技能 %d + 证书 %d 行）" % (
        os.path.relpath(FREQ, ROOT), len(skill_cnt), len(cert_cnt)))

    # ---------- ④ 统计与样例 ----------
    print("\n分词统计（平均词数 / 最少 / 最多 / 词种数）：")
    for _, col in TEXT_FIELDS:
        v = per_doc[col]
        print("  %-12s %6.1f ｜ %3d ｜ %3d ｜ %4d" % (
            col, sum(v) / len(v), min(v), max(v), len(field_stats[col])))
    print("\n各字段 Top10 词：")
    for _, col in TEXT_FIELDS:
        print("  %-12s %s" % (col, "、".join("%s(%d)" % kv for kv in field_stats[col].most_common(10))))

    print("\n样例（前 2 条）：")
    for r in out_rows[:2]:
        print("  【%s】" % r["姓名"])
        for src_col, out_col in TEXT_FIELDS:
            print("    %-14s %s" % (out_col, (r[out_col] or "")[:90]))
        print("    %-14s %s ｜ %s" % ("技能词/证书", r["技能词"], r["证书"]))


if __name__ == "__main__":
    main()
