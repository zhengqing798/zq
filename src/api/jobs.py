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
import hashlib
import os
import random
import re
import sys
from collections import Counter, defaultdict

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

# 首页「高薪 / 热门岗位」随机推荐的候选池门槛（都是真实列的口径）
HIGH_SALARY_MIN = 10000      # 高薪池：薪资下限 > 10000 元/月（实测 2,472 个岗位）
HOT_REPLY_MIN = 20           # 热门池：招聘者今日回复数 ≥ 20（实测 1,676 个岗位）
REGION_TOP = 5               # 地区推荐只给 Top 5
COMPANY_TOP = 10             # 热门企业 Top 10

SORTS = {
    "default": "默认排序",
    "salary_desc": "薪资从高到低",
    "salary_asc": "薪资从低到高",
    "reply": "回复最积极",
    "online": "在线优先",
}

# 公司列表排序（BOSS直聘「公司」页的排序维度）
COMPANY_SORTS = {
    "jobs_desc": "在招职位最多",
    "salary_desc": "薪资最高",
    "reply_desc": "回复最积极",
    "name": "公司名 A-Z",
}

# 规模分档：数据里**没有**「公司规模」列，这里用「在招职位数」分档代理，
# 页面与文档必须写明口径，不能当成注册资本/员工人数（见《系统设计文档》§3.9）。
SIZE_BUCKETS = [
    ("1个", 1, 1),
    ("2-4个", 2, 4),
    ("5-9个", 5, 9),
    ("10-49个", 10, 49),
    ("50个以上", 50, 10 ** 9),
]


def _comp_id(name):
    """公司名的稳定短 ID（UTF-8 中文公司名直接进 URL 易踩编码坑，用 sha1 前 8 位）"""
    return "C" + hashlib.sha1((name or "").encode("utf-8")).hexdigest()[:8].upper()


def _median(arr):
    a = sorted(x for x in arr if x > 0)
    return a[len(a) // 2] if a else 0


def _size_bucket(n):
    for label, lo, hi in SIZE_BUCKETS:
        if lo <= n <= hi:
            return label
    return SIZE_BUCKETS[-1][0]


def _num(v, default=-1):
    v = (v or "").strip()
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _reply_num(s):
    """「今日回复40次」/「今日回复50+次」→ 40 / 50（原始列是文本，不能直接 float）"""
    m = re.search(r"(\d+)", s or "")
    return int(m.group(1)) if m else 0


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
            district = region[1] if len(region) > 1 else ""
            tags = [t.strip() for t in (r["技能标签"] or "").split("|") if t.strip()]
            c1, c2 = clusters.get(jid, ("", ""))
            # 「发布者身份」形如「人事经理 · 三一集团有限公司」→ 拆出招聘者职位
            ident = (r["发布者身份"] or "").strip()
            hr_title = ident.split("·")[0].strip() if ident else ""
            self.items.append({
                "岗位ID": jid,
                "岗位名称": (r["岗位名称"] or "").strip(),
                "公司": (r["公司名称"] or "").strip(),
                "城市": city,
                "区县": district,
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
                "今日回复数": _reply_num(r["今日回复数"]),
                "是否在线": 1 if "在线" in (r["在线状态"] or "") else 0,
                # —— 模拟 BOSS直聘「招聘者」行所需字段（全部来自真实数据）——
                "招聘者": (r["发布者姓名"] or "").strip() or "招聘者",
                "招聘者职位": hr_title or "招聘者",
                "在线状态": (r["在线状态"] or "").strip(),
                "回复文案": (r["今日回复数"] or "").strip(),
                "来源关键词": (r["来源关键词"] or "").strip(),
                "同公司岗位数": 0,
            })
        comp_cnt = Counter(x["公司"] for x in self.items if x["公司"])
        for it in self.items:
            it["同公司岗位数"] = comp_cnt.get(it["公司"], 0)
        # 预计算筛选用的检索文本（岗位名称 + 公司 + 技能 + 描述）
        for it in self.items:
            it["_blob"] = (it["岗位名称"] + it["公司"] + it["技能标签原文"] +
                           it["职位描述"]).lower()
        # 下拉选项
        self.cities = sorted({it["城市"] for it in self.items if it["城市"]})
        self.categories = [c for c in CATS if any(it["岗位大类"] == c for it in self.items)]
        self.edus = sorted({it["学历要求"] for it in self.items if it["学历要求"]})
        self.provinces = sorted({it["省份"] for it in self.items if it["省份"]})
        self._build_companies()

    def __len__(self):
        return len(self.items)

    # ------------------------------------------------ 公司维度聚合（任务11 公司页）
    def _build_companies(self):
        """把 8,836 个岗位按「公司名称」聚成 4,096 家公司。

        只用真实存在的列：公司名称 / 岗位地区 / 岗位大类 / 技能标签 / 薪资区间 /
        学历 / 经验 / 发布者 / 在线状态 / 今日回复数。**没有**行业、规模、融资阶段列，
        因此不编造这些字段（规模用「在招职位数」分档代理，口径见 SIZE_BUCKETS）。
        """
        groups = defaultdict(list)
        for it in self.items:
            if it["公司"]:
                groups[it["公司"]].append(it)

        comps = []
        for name, rows in groups.items():
            cid = _comp_id(name)
            for r in rows:
                r["公司ID"] = cid          # 让岗位卡片能一键跳到该公司详情页
            cities = Counter(r["城市"] for r in rows if r["城市"])
            cats = Counter(r["岗位大类"] for r in rows)
            skills = Counter(s for r in rows for s in r["技能标签"])
            edus = Counter(r["学历要求"] or "不限" for r in rows)
            exps = Counter(_exp_bucket(r["经验要求"]) for r in rows)
            hrs, seen = [], set()
            for r in rows:
                key = (r["招聘者"], r["招聘者职位"])
                if key in seen:
                    continue
                seen.add(key)
                hrs.append({"姓名": r["招聘者"], "职位": r["招聘者职位"],
                            "回复文案": r["回复文案"] or "暂无回复数据",
                            "回复数": r["今日回复数"]})
            hrs.sort(key=lambda h: -h["回复数"])
            n_jobs = len(rows)
            # 「热招职位」口径：先按招聘者「今日回复数」再按薪资上限——都是真实列，
            # 没有回复数据的公司退化为「薪资最高」，页面/文档写明该口径。
            top_jobs = sorted(rows, key=lambda r: (-r["今日回复数"], -r["薪资上限"]))[:3]
            up_med, lo_med = _median([r["薪资上限"] for r in rows]), _median([r["薪资下限"] for r in rows])
            comps.append({
                "公司ID": cid,
                "公司名称": name,
                "在招岗位数": n_jobs,
                "规模分档": _size_bucket(n_jobs),
                "城市数": len(cities),
                "主要城市": cities.most_common(1)[0][0] if cities else "",
                "城市列表": [{"名称": k, "数量": v} for k, v in cities.most_common()],
                "区县数": len({r["区县"] for r in rows if r["区县"]}),
                "主要大类": cats.most_common(1)[0][0] if cats else "",
                "岗位大类": [{"名称": k, "数量": v} for k, v in cats.most_common()],
                "技能需求": [{"名称": k, "数量": v} for k, v in skills.most_common(12)],
                "学历要求": [{"名称": k, "数量": v} for k, v in edus.most_common()],
                "经验要求": [{"名称": k, "数量": v} for k, v in exps.most_common()],
                "薪资下限中位数": lo_med,
                "薪资上限中位数": up_med,
                "最高薪资上限": max([r["薪资上限"] for r in rows] + [0]),
                "招聘者": hrs,
                "招聘者数": len(hrs),
                "在线岗位数": sum(1 for r in rows if r["是否在线"]),
                "有回复岗位数": sum(1 for r in rows if r["今日回复数"] > 0),
                "今日回复总数": sum(r["今日回复数"] for r in rows),
                "来源关键词": [{"名称": k, "数量": v} for k, v in
                            Counter(r["来源关键词"] for r in rows if r["来源关键词"]).most_common(5)],
                "热招职位": [{"岗位ID": r["岗位ID"], "岗位名称": r["岗位名称"],
                            "薪资": r["薪资"], "城市": r["城市"], "区县": r["区县"]}
                           for r in top_jobs],
                "_rows": rows,          # 详情接口用；列表接口会剔除
            })
        comps.sort(key=lambda c: (-c["在招岗位数"], c["公司名称"]))
        self.companies = comps
        self.company_index = {c["公司ID"]: c for c in comps}
        self.company_by_name = {c["公司名称"]: c for c in comps}
        self.company_cities = sorted({c["主要城市"] for c in comps if c["主要城市"]})

    @staticmethod
    def _card(c):
        """公司列表的卡片字段（不含全部在招岗位，避免列表接口过大）"""
        return {k: v for k, v in c.items() if k != "_rows"}

    # ------------------------------------------------ 浏览与筛选
    def query(self, page=1, size=20, city=None, district=None, category=None, keyword=None,
              salary_min=None, edu=None, cluster=None, sort="default", source_kw=None):
        rows = self.items
        if city:
            rows = [x for x in rows if x["城市"] == city]
        if district:
            rows = [x for x in rows if x["区县"] == district]
        if category:
            rows = [x for x in rows if x["岗位大类"] == category]
        if source_kw:
            # 精确匹配「来源关键词」列（首页热门分类卡上的数字就是这么来的，
            # 用模糊 keyword 搜出来会更多，两者口径不同）
            rows = [x for x in rows if x["来源关键词"] == source_kw]
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

    # ------------------------------------------------ 公司浏览（任务11 公司页）
    def company_query(self, page=1, size=20, city=None, category=None, keyword=None,
                      bucket=None, sort="jobs_desc"):
        rows = self.companies
        if city:
            rows = [c for c in rows if any(x["名称"] == city for x in c["城市列表"])]
        if category:
            rows = [c for c in rows if any(x["名称"] == category for x in c["岗位大类"])]
        if bucket:
            rows = [c for c in rows if c["规模分档"] == bucket]
        if keyword:
            k = str(keyword).strip().lower()
            rows = [c for c in rows if k in c["公司名称"].lower()]

        rows = list(rows)                       # 拷贝，避免 sort 弄乱主列表
        if sort == "salary_desc":
            rows.sort(key=lambda c: (-c["薪资上限中位数"], -c["在招岗位数"]))
        elif sort == "reply_desc":
            rows.sort(key=lambda c: (-c["今日回复总数"], -c["在招岗位数"]))
        elif sort == "name":
            rows.sort(key=lambda c: c["公司名称"])
        else:                                   # jobs_desc：主列表默认已是这个顺序
            rows.sort(key=lambda c: (-c["在招岗位数"], c["公司名称"]))

        total = len(rows)
        page = max(1, int(page))
        size = min(max(1, int(size)), 100)
        start = (page - 1) * size
        return {
            "总数": total,
            "页码": page,
            "每页": size,
            "总页数": max(1, (total + size - 1) // size),
            "公司": [self._card(c) for c in rows[start:start + size]],
        }

    def company_get(self, key):
        """公司详情：支持公司ID（C+8位）或公司名（URL 里建议用 ID）"""
        k = str(key or "").strip()
        c = self.company_index.get(k.upper()) or self.company_by_name.get(k)
        if not c:
            return None
        out = self._card(c)
        rows = list(c["_rows"])
        rows.sort(key=lambda r: (-r["今日回复数"], -r["薪资上限"]))
        out["在招岗位"] = [{kk: vv for kk, vv in r.items() if kk != "_blob"} for r in rows]
        # 同城同类公司（详情页底部「相似公司」，用真实同城+同最主大类匹配）
        sim = [x for x in self.companies
               if x["公司ID"] != c["公司ID"] and x["主要城市"] == c["主要城市"]
               and x["主要大类"] == c["主要大类"]]
        out["相似公司"] = [self._card(x) for x in sim[:6]]
        return out

    def company_stats(self):
        """公司页顶部统计（全部基于公司聚合，口径与岗位页一致）"""
        comps = self.companies
        n_comp, n_jobs = len(comps), sum(c["在招岗位数"] for c in comps)
        by_city = Counter()
        for c in comps:
            for x in c["城市列表"]:
                by_city[x["名称"]] += 1
        by_cat = Counter()
        for c in comps:
            for x in c["岗位大类"]:
                by_cat[x["名称"]] += 1
        buckets = Counter(c["规模分档"] for c in comps)
        top = comps[0] if comps else None
        return {
            "总体": {
                "公司总数": n_comp,
                "在招岗位总数": n_jobs,
                "平均每司岗位数": round(n_jobs / n_comp, 2) if n_comp else 0,
                "只招1个岗位的公司数": buckets.get("1个", 0),
                "在招10个以上的公司数": sum(v for k, v in buckets.items()
                                       if k in ("10-49个", "50个以上")),
                "城市数": len(by_city),
                "岗位数最多公司": top["公司名称"] if top else "",
                "岗位数最多公司岗位数": top["在招岗位数"] if top else 0,
                "有回复活跃的公司数": sum(1 for c in comps if c["今日回复总数"] > 0),
            },
            "规模分档": [{"名称": k, "数量": buckets.get(k, 0),
                       "说明": "在招职位数 %s" % k} for k, _, _ in SIZE_BUCKETS],
            "按城市": [{"名称": k, "数量": v} for k, v in by_city.most_common(16)],
            "按大类": [{"名称": k, "数量": v} for k, v in by_cat.most_common()],
            "热门企业": [self._card(c) for c in comps[:20]],
            "最活跃企业": [self._card(c) for c in
                       sorted(comps, key=lambda c: -c["今日回复总数"])[:10]],
            "筛选项": {"城市": self.company_cities, "大类": self.categories,
                     "规模分档": [k for k, _, _ in SIZE_BUCKETS],
                     "排序": [{"value": k, "label": v} for k, v in COMPANY_SORTS.items()]},
            "口径说明": [
                "公司 = 「公司名称」列去重；数据里没有行业/规模/融资阶段列，故不展示这些字段。",
                "「规模分档」用该公司的在招职位数代理，不等于员工人数或注册资本。",
                "「按城市/按大类」统计的是「该公司在该城市/大类有在招职位」的公司数，"
                "同一公司可计入多个城市/大类，故合计大于公司总数 %d。" % n_comp,
                "「热招职位」取该公司前 3 个岗位，排序为「今日回复数 → 薪资上限」（均为真实列）。",
                "薪资中位数由该公司的真实薪资上下限（元/月）计算，剔除无薪资的岗位。",
            ],
            "来源": ["zhaopin_jobs_cleaned_seg.csv（%d 个岗位 → %d 家公司）" % (n_jobs, n_comp)],
        }

    # ------------------------------------------------ 首页推荐（任务11 首页改版）
    @staticmethod
    def _job_brief(x):
        """首页/榜单用的岗位精简卡（字段够渲染卡片，不含描述全文）"""
        return {
            "岗位ID": x["岗位ID"], "岗位名称": x["岗位名称"], "公司": x["公司"],
            "公司ID": x.get("公司ID", ""), "城市": x["城市"], "区县": x["区县"],
            "薪资": x["薪资"], "薪资下限": x["薪资下限"], "薪资上限": x["薪资上限"],
            "岗位大类": x["岗位大类"],
            "经验要求": x["经验要求"], "学历要求": x["学历要求"],
            "技能标签": x["技能标签"][:5], "是否在线": x["是否在线"],
            "今日回复数": x["今日回复数"], "回复文案": x["回复文案"],
            "招聘者": x["招聘者"], "招聘者职位": x["招聘者职位"],
            "同公司岗位数": x["同公司岗位数"],
        }

    def home(self, hot_n=8):
        """首页推荐数据：热门分类轮播 + 地区推荐 Top5 + 高薪/热门岗位（随机）+ 热门企业 Top10。

        · 地区与热门企业是**固定榜单**（Top N，可复现）；
        · 高薪 / 热门岗位是**随机抽取**：从真实条件的候选池里 `random.sample`，
          因此每次进首页看到的都不一样，池子与门槛见 HIGH_SALARY_MIN / HOT_REPLY_MIN；
        · 全部只用真实存在的列，没有浏览量/投递量这类数据（说明见 `口径说明`，页面不展示）。
        """
        # ① 热门分类 = 抓取这批岗位时用的「来源关键词」列（真实列，共 8 个）
        kws = Counter(x["来源关键词"] for x in self.items if x["来源关键词"])
        hero = []
        for kw, cnt in kws.most_common():
            sub = [x for x in self.items if x["来源关键词"] == kw]
            ups = [x["薪资上限"] for x in sub if x["薪资上限"] > 0]
            samples = sorted(sub, key=lambda x: (-x["今日回复数"], -x["薪资上限"]))[:3]
            hero.append({
                "分类": kw, "岗位数": cnt,
                "在线岗位数": sum(1 for x in sub if x["是否在线"]),
                "公司数": len({x["公司"] for x in sub if x["公司"]}),
                "平均薪资上限": int(sum(ups) / len(ups)) if ups else 0,
                "热门技能": [k for k, _ in Counter(s for x in sub for s in x["技能标签"]).most_common(6)],
                "示例岗位": [self._job_brief(x) for x in samples],
            })

        # ② 地区推荐（只给 Top 5；岗位数 / 公司数 / 平均薪资 / 热门区县）
        regions = []
        for city, cnt in Counter(x["城市"] for x in self.items if x["城市"]).most_common(REGION_TOP):
            sub = [x for x in self.items if x["城市"] == city]
            ups = [x["薪资上限"] for x in sub if x["薪资上限"] > 0]
            regions.append({
                "城市": city, "省份": PROVINCE.get(city, ""), "岗位数": cnt,
                "公司数": len({x["公司"] for x in sub if x["公司"]}),
                "平均薪资上限": int(sum(ups) / len(ups)) if ups else 0,
                "在线岗位数": sum(1 for x in sub if x["是否在线"]),
                "热门区县": [{"名称": k, "数量": v} for k, v in
                          Counter(x["区县"] for x in sub if x["区县"]).most_common(3)],
            })

        # ③ 高薪岗位：从「薪资下限 > 10000 元/月」的池子里**随机抽**（每次请求都不一样），
        #    抽出来后按薪资上限降序展示，榜首仍是本批里最高的
        high_pool = [x for x in self.items if x["薪资下限"] > HIGH_SALARY_MIN]
        high = random.sample(high_pool, min(hot_n, len(high_pool))) if high_pool else []
        high.sort(key=lambda x: -x["薪资上限"])
        # ④ 热门岗位：从「招聘者今日回复数 ≥ HOT_REPLY_MIN」的池子里**随机抽**，再按回复数降序
        hot_pool = [x for x in self.items if x["今日回复数"] >= HOT_REPLY_MIN]
        hot = random.sample(hot_pool, min(hot_n, len(hot_pool))) if hot_pool else []
        hot.sort(key=lambda x: (-x["今日回复数"], -x["是否在线"], -x["薪资上限"]))

        return {
            "热门分类": hero,
            "地区推荐": regions,
            "高薪岗位": [self._job_brief(x) for x in high],
            "热门岗位": [self._job_brief(x) for x in hot],
            "热门企业": [self._card(c) for c in self.companies[:COMPANY_TOP]],
            "热门技能": [{"名称": k, "数量": v} for k, v in
                     Counter(s for x in self.items for s in x["技能标签"]).most_common(12)],
            "总体": {
                "岗位数": len(self.items), "公司数": len(self.companies),
                "城市数": len(self.cities), "在线岗位数": sum(1 for x in self.items if x["是否在线"]),
                "有回复岗位数": sum(1 for x in self.items if x["今日回复数"] > 0),
            },
            "口径说明": [
                "「热门分类」取自真实的「来源关键词」列（抓取这批岗位时用的搜索词，共 8 个）。",
                "「地区推荐」只给岗位数 Top %d 的城市，数字由该城市真实岗位聚合。" % REGION_TOP,
                "「高薪岗位」从薪资下限 > %d 元/月的 %d 个岗位中**随机抽取**（每次请求重新抽），"
                "抽出来后按薪资上限降序展示；薪资面议的不进池。" % (
                    HIGH_SALARY_MIN, len(high_pool)),
                "「热门岗位」从招聘者今日回复数 ≥ %d 的 %d 个岗位中**随机抽取**（每次请求重新抽），"
                "再按回复数降序；数据里没有浏览/投递量，故不写“热度”。" % (
                    HOT_REPLY_MIN, len(hot_pool)),
                "「热门企业」按在招职位数降序取 Top %d。" % COMPANY_TOP,
            ],
            "来源": ["zhaopin_jobs_cleaned_seg.csv（%d 个清洗后岗位）" % len(self.items),
                   "岗位聚类_标签.csv（任务7 聚类结果）"],
        }

    # ------------------------------------------------ 通用聚合（Agent 工具用）
    GROUP_FIELDS = ["城市", "省份", "区县", "学历要求", "经验要求", "岗位大类",
                    "公司", "来源关键词", "一级簇名", "招聘者职位", "技能标签"]

    def _filtered(self, city=None, district=None, category=None, keyword=None,
                  edu=None, salary_min=None, source_kw=None):
        """与 query() 同一套筛选语义，但不分页（给聚合用）"""
        rows = self.items
        if city:
            rows = [x for x in rows if x["城市"] == city]
        if district:
            rows = [x for x in rows if x["区县"] == district]
        if category:
            rows = [x for x in rows if x["岗位大类"] == category]
        if source_kw:
            rows = [x for x in rows if x["来源关键词"] == source_kw]
        if edu:
            rows = [x for x in rows if edu in x["学历要求"]]
        if salary_min:
            rows = [x for x in rows if x["薪资上限"] >= int(salary_min)]
        if keyword:
            k = str(keyword).strip().lower()
            rows = [x for x in rows if k in x["_blob"]]
        return rows

    def group_by(self, field, top=15, **filters):
        """按任意维度分组统计（岗位数 / 占比 / 平均薪资上限 / 薪资上限中位数）

        `field` 取 GROUP_FIELDS 之一；`技能标签` 是多值列，会拆成单个标签分别计数。
        """
        if field not in self.GROUP_FIELDS:
            raise ValueError("不支持的分组维度：%s（可选：%s）" % (field, "、".join(self.GROUP_FIELDS)))
        rows = self._filtered(**filters)

        def key_of(x):
            if field == "技能标签":
                return list(x["技能标签"])
            return [(x.get(field) or "（空）")]

        buckets = defaultdict(list)
        for x in rows:
            for k in key_of(x):
                buckets[k].append(x)

        total = len(rows)
        out = []
        for name, group in buckets.items():
            ups = [g["薪资上限"] for g in group if g["薪资上限"] > 0]
            out.append({
                "分组": name, "岗位数": len(group),
                "占比": round(len(group) / total * 100, 1) if total else 0,
                "平均薪资上限": int(sum(ups) / len(ups)) if ups else 0,
                "薪资上限中位数": _median(ups),
                "有回复岗位数": sum(1 for g in group if g["今日回复数"] > 0),
            })
        out.sort(key=lambda d: (-d["岗位数"], d["分组"]))
        return {"分组维度": field, "筛选后岗位总数": total, "分组数": len(out),
                "明细": out[:int(top)] if top else out}

    def top_jobs(self, by="salary", n=10, **filters):
        """确定性 Top 榜单（Agent 用；与首页的"随机推荐"区分开，保证可复现）

        by = salary（薪资上限降序）｜ reply（招聘者今日回复数降序）｜ online
        """
        rows = self._filtered(**filters)
        if by == "salary":
            rows = sorted(rows, key=lambda x: (-(x["薪资上限"] if x["薪资上限"] > 0 else -1),
                                              -x["今日回复数"]))
        elif by == "reply":
            rows = sorted(rows, key=lambda x: (-x["今日回复数"], -x["是否在线"], -x["薪资上限"]))
        elif by == "online":
            rows = sorted(rows, key=lambda x: (-x["是否在线"], -x["今日回复数"]))
        else:
            raise ValueError("不支持的排序：%s（可选 salary / reply / online）" % by)
        return [self._job_brief(x) for x in rows[:int(n)]], len(rows)

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

        # —— 按城市的区县分布（BOSS直聘 筛选项「区域」用）——
        district_by_city = {}
        for city in self.cities:
            sub = [x["区县"] for x in self.items if x["城市"] == city and x["区县"]]
            district_by_city[city] = [{"名称": k, "数量": v}
                                     for k, v in Counter(sub).most_common()]

        # —— 热门职位（用「来源关键词」，即这批岗位当初是用什么词搜到的）——
        hot_kw = Counter(x["来源关键词"] for x in self.items if x["来源关键词"])

        # —— 分类导航：大类 → 该大类下的高频岗位名（模拟 BOSS 的职位分类面板）——
        nav = []
        for cat, cnt in cats.most_common():
            names = Counter(_norm_job_name(x["岗位名称"]) for x in self.items
                            if x["岗位大类"] == cat)
            subs = [{"名称": k, "数量": v} for k, v in names.most_common(8) if v >= 3]
            nav.append({"大类": cat, "数量": cnt, "子职位": subs})

        # —— 招聘者活跃度（BOSS直聘 卡片右侧那一行）——
        online = sum(1 for x in self.items if x["是否在线"])
        has_hr = sum(1 for x in self.items if x["招聘者职位"] != "招聘者")
        replied = sum(1 for x in self.items if x["今日回复数"] > 0)

        return {
            "总体": {
                "岗位总数": n,
                "公司数": len(companies),
                "城市数": len(cities),
                "省份数": len({x["省份"] for x in self.items if x["省份"]}),
                "平均薪资上限": int(sum(up) / len(up)) if up else 0,
                "薪资下限中位数": q(lo, 0.5),
                "薪资上限中位数": q(up, 0.5),
                "在线岗位数": online,
                "区县数": len({x["区县"] for x in self.items if x["区县"]}),
                "有招聘者职位数": has_hr,
                "有回复数据岗位数": replied,
            },
            "按城市": [{"名称": k, "数量": v} for k, v in cities.most_common(16)],
            "按大类": [{"名称": k, "数量": v} for k, v in cats.most_common()],
            "按学历": [{"名称": k, "数量": v} for k, v in edus.most_common()],
            "按经验": [{"名称": k, "数量": v} for k, v in exps.most_common()],
            "按簇": [{"名称": k, "数量": v} for k, v in clusters.most_common()],
            "热门技能": [{"名称": k, "数量": v} for k, v in skills.most_common(20)],
            "热门搜索": [{"名称": k, "数量": v} for k, v in hot_kw.most_common(12)],
            "按城市区县": district_by_city,
            "分类导航": nav,
            "筛选项": {"城市": self.cities, "大类": self.categories,
                     "学历": self.edus, "省份": self.provinces,
                     "排序": [{"value": k, "label": v} for k, v in SORTS.items()]},
            "来源": ["zhaopin_jobs_cleaned_seg.csv（%d 个清洗后岗位）" % n,
                   "岗位聚类_标签.csv（任务7 聚类结果）"],
        }


def _norm_job_name(name):
    """岗位名称归一：去掉括号后缀、城市后缀与常见修饰词，便于统计"高频职位" """
    s = (name or "").strip()
    s = re.sub(r"[（(\[【][^）)\]】]*[）)\]】]", "", s)          # 去括号内容
    s = re.sub(r"[-—_·|/]\s*(厦门|福州|泉州|漳州|莆田|宁德|南平|三明|龙岩|"
               r"苏州|南京|无锡|常州|徐州|南通|扬州|镇江|"
               r"杭州|宁波|温州|绍兴|嘉兴|金华|台州|湖州|丽水|舟山|"
               r"合肥|芜湖|蚌埠|马鞍山|安庆|黄山|滁州|阜阳).*$", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -—_·|/")
    return s or (name or "").strip()


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
    cs = st.company_stats()
    print("\n公司：", cs["总体"])
    print("规模分档：", [(x["名称"], x["数量"]) for x in cs["规模分档"]])
    c = cs["热门企业"][0]
    print("在招最多：%s（%d 个岗位，%s）" % (c["公司名称"], c["在招岗位数"], c["规模分档"]))
    crow = st.company_query(city="厦门", category="测试", size=2)
    print("厦门+测试 公司：共 %d 家，前 2 家：" % crow["总数"])
    for x in crow["公司"]:
        print("   %s ｜ %s ｜ 在招 %d 个 ｜ %s" % (x["公司ID"], x["公司名称"],
                                              x["在招岗位数"], x["主要城市"]))
    one = st.company_get(c["公司ID"])
    print("详情：%s ｜ 在招岗位 %d 个 ｜ 相似公司 %d 家"
          % (one["公司名称"], len(one["在招岗位"]), len(one["相似公司"])))
