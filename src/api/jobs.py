# -*- coding: utf-8 -*-
"""任务11 · 岗位浏览服务（首页用）：全部 8,836 个清洗后岗位的检索、筛选、分类统计

数据来源：`data/processed/zhaopin_jobs_cleaned_seg.csv`（清洗 + 分词后的岗位表）
          `data/processed/岗位聚类_标签.csv`（任务7 聚类结果，每个岗位的簇名）

设计说明
--------
· 启动时**一次性载入内存**（8,836 行，约 22 MB），之后筛选/统计都是纯内存操作（毫秒级）
· 岗位大类复用任务5 的同一套规则 `job_category()`，保证与模型特征口径一致
· 只做**只读**浏览，不涉及数据库
"""
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (os.path.join(ROOT, "src", "models", "scoring"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from build_labels import load_csv                                        # noqa: E402
from build_features import job_category, CATS, PROVINCE                  # noqa: E402

P = os.path.join(ROOT, "data", "processed")
JOBS_CSV = os.path.join(P, "zhaopin_jobs_cleaned_seg.csv")
CLUSTER_CSV = os.path.join(P, "岗位聚类_标签.csv")

_STORE = None

SORTS = {
    "default": "默认排序",
    "salary_desc": "薪资从高到低",
    "salary_asc": "薪资从低到高",
    "reply": "回复最积极",
    "online": "在线优先",
}


def _num(v, default=-1):
    v = (v or "").strip()
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


class JobStore:
    """岗位浏览单例（进程内只加载一次）"""

    def __init__(self):
        self.rows = load_csv(JOBS_CSV)
        clusters = {}
        if os.path.exists(CLUSTER_CSV):
            for r in load_csv(CLUSTER_CSV):
                clusters[r["岗位ID"]] = (r.get("一级簇名") or "", r.get("二级簇名") or "")
        self.items = []
        for i, r in enumerate(self.rows):
            jid = "J%04d" % (i + 1)
            region = (r["岗位地区"] or "").strip().split()
            city = region[0] if region else ""
            tags = [t.strip() for t in (r["技能标签"] or "").split("|") if t.strip()]
            c1, c2 = clusters.get(jid, ("", ""))
            self.items.append({
                "岗位ID": jid,
                "岗位名称": (r["岗位名称"] or "").strip(),
                "公司": (r["公司名称"] or "").strip(),
                "城市": city,
                "省份": PROVINCE.get(city, ""),
                "地区": (r["岗位地区"] or "").strip(),
                "薪资": (r["岗位薪资"] or "").strip(),
                "薪资下限": _num(r["薪资下限(元/月)"]),
                "薪资上限": _num(r["薪资上限(元/月)"]),
                "经验要求": (r["经验要求"] or "").strip(),
                "学历要求": (r["学历要求"] or "").strip(),
                "技能标签": tags,
                "技能标签原文": (r["技能标签"] or "").strip(),
                "职位描述": (r["职位描述"] or "").strip(),
                "岗位大类": job_category(r["岗位名称"]),
                "一级簇名": c1,
                "二级簇名": c2 if c2 and c2 != "—" else "",
                "今日回复数": _num(r["今日回复数"], 0),
                "是否在线": 1 if "在线" in (r["在线状态"] or "") else 0,
            })
        # 预计算筛选用的检索文本（岗位名称 + 公司 + 技能 + 描述）
        for it in self.items:
            it["_blob"] = (it["岗位名称"] + it["公司"] + it["技能标签原文"] +
                           it["职位描述"]).lower()
        # 下拉选项
        self.cities = sorted({it["城市"] for it in self.items if it["城市"]})
        self.categories = [c for c in CATS if any(it["岗位大类"] == c for it in self.items)]
        self.edus = sorted({it["学历要求"] for it in self.items if it["学历要求"]})
        self.provinces = sorted({it["省份"] for it in self.items if it["省份"]})

    def __len__(self):
        return len(self.items)

    # ------------------------------------------------ 浏览与筛选
    def query(self, page=1, size=20, city=None, category=None, keyword=None,
              salary_min=None, edu=None, cluster=None, sort="default"):
        rows = self.items
        if city:
            rows = [x for x in rows if x["城市"] == city]
        if category:
            rows = [x for x in rows if x["岗位大类"] == category]
        if edu:
            rows = [x for x in rows if edu in x["学历要求"]]
        if cluster:
            rows = [x for x in rows if cluster in x["一级簇名"] or cluster in x["二级簇名"]]
        if salary_min:
            rows = [x for x in rows if x["薪资上限"] >= int(salary_min)]
        if keyword:
            k = str(keyword).strip().lower()
            rows = [x for x in rows if k in x["_blob"]]

        if sort == "salary_desc":
            rows = sorted(rows, key=lambda x: -x["薪资上限"])
        elif sort == "salary_asc":
            rows = sorted(rows, key=lambda x: x["薪资上限"] if x["薪资上限"] > 0 else 10 ** 9)
        elif sort == "reply":
            rows = sorted(rows, key=lambda x: -x["今日回复数"])
        elif sort == "online":
            rows = sorted(rows, key=lambda x: -x["是否在线"])

        total = len(rows)
        page = max(1, int(page))
        size = min(max(1, int(size)), 100)
        start = (page - 1) * size
        page_rows = [{k: v for k, v in x.items() if k != "_blob"} for x in rows[start:start + size]]
        return {
            "总数": total,
            "页码": page,
            "每页": size,
            "总页数": max(1, (total + size - 1) // size),
            "岗位": page_rows,
        }

    def get(self, job_id):
        jid = str(job_id).upper()
        if not jid.startswith("J"):
            jid = "J" + jid.zfill(4)
        for x in self.items:
            if x["岗位ID"] == jid:
                out = {k: v for k, v in x.items() if k != "_blob"}
                out["职位描述"] = out["职位描述"][:1200]
                return out
        return None

    # ------------------------------------------------ 分类统计（首页图表用）
    def stats(self):
        n = len(self.items)
        cities = Counter(x["城市"] for x in self.items if x["城市"])
        cats = Counter(x["岗位大类"] for x in self.items)
        edus = Counter(x["学历要求"] or "不限" for x in self.items)
        exps = Counter(_exp_bucket(x["经验要求"]) for x in self.items)
        clusters = Counter(x["一级簇名"] for x in self.items if x["一级簇名"])
        skills = Counter(s for x in self.items for s in x["技能标签"])
        companies = {x["公司"] for x in self.items if x["公司"]}
        up = [x["薪资上限"] for x in self.items if x["薪资上限"] > 0]
        lo = [x["薪资下限"] for x in self.items if x["薪资下限"] > 0]
        up.sort()
        lo.sort()

        def q(arr, p):
            return arr[min(len(arr) - 1, int(len(arr) * p))] if arr else 0

        return {
            "总体": {
                "岗位总数": n,
                "公司数": len(companies),
                "城市数": len(cities),
                "省份数": len({x["省份"] for x in self.items if x["省份"]}),
                "平均薪资上限": int(sum(up) / len(up)) if up else 0,
                "薪资下限中位数": q(lo, 0.5),
                "薪资上限中位数": q(up, 0.5),
                "在线岗位数": sum(x["是否在线"] for x in self.items),
            },
            "按城市": [{"名称": k, "数量": v} for k, v in cities.most_common(16)],
            "按大类": [{"名称": k, "数量": v} for k, v in cats.most_common()],
            "按学历": [{"名称": k, "数量": v} for k, v in edus.most_common()],
            "按经验": [{"名称": k, "数量": v} for k, v in exps.most_common()],
            "按簇": [{"名称": k, "数量": v} for k, v in clusters.most_common()],
            "热门技能": [{"名称": k, "数量": v} for k, v in skills.most_common(20)],
            "筛选项": {"城市": self.cities, "大类": self.categories,
                     "学历": self.edus, "省份": self.provinces,
                     "排序": [{"value": k, "label": v} for k, v in SORTS.items()]},
            "来源": ["zhaopin_jobs_cleaned_seg.csv（%d 个清洗后岗位）" % n,
                   "岗位聚类_标签.csv（任务7 聚类结果）"],
        }


def _exp_bucket(s):
    t = (s or "").strip()
    if not t or t in ("不限", "-", "—"):
        return "不限"
    if "应届" in t or "实习" in t or "无经验" in t:
        return "应届/无经验"
    m = re.findall(r"\d+", t)
    if not m:
        return "其他"
    lo = int(m[0])
    if lo <= 1:
        return "1年以内"
    if lo <= 3:
        return "1-3年"
    if lo <= 5:
        return "3-5年"
    if lo <= 10:
        return "5-10年"
    return "10年以上"


def get_store():
    global _STORE
    if _STORE is None:
        _STORE = JobStore()
    return _STORE


if __name__ == "__main__":
    st = get_store()
    print("岗位 %d ｜ 城市 %d ｜ 大类 %d ｜ 学历 %d ｜ 公司 %d"
          % (len(st), len(st.cities), len(st.categories), len(st.edus),
             st.stats()["总体"]["公司数"]))
    r = st.query(city="苏州", category="测试", size=3)
    print("\n苏州 + 测试 类：共 %d 个，前 3 条：" % r["总数"])
    for x in r["岗位"]:
        print("   %s ｜ %s ｜ %s ｜ %s" % (x["岗位ID"], x["岗位名称"], x["公司"], x["薪资"]))
    s = st.stats()
    print("\n按大类：", s["按大类"])
    print("总体：", s["总体"])
    print("热门技能 Top5：", [x["名称"] for x in s["热门技能"][:5]])
