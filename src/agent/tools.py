# -*- coding: utf-8 -*-
"""
任务10 · Agent 工具集（Function Calling 的"手"）

每个工具都**直接调用本项目已验证的模块**，而不是让模型凭空回答：
  · `search_jobs`      —— RAG 语义检索岗位（可带城市过滤）
  · `filter_jobs`      —— 结构化筛选（城市/关键词/薪资下限/学历），返回命中总数 + 样例
  · `salary_stats`     —— 薪资统计（中位数/分位数），可按城市
  · `match_resume`     —— 任务6 人岗匹配：简历文本 → Top-N 岗位 + 分项得分 + 推荐理由
  · `cluster_profile`  —— 任务7 岗位聚类画像（按簇名/方案）
  · `kb_stats`         —— 知识库自述（卡片数、模型、召回指标），用于回答"你这个系统怎么做的"
  · `company_query`    —— 公司维度（招人最多的公司 / 某公司的全部在招岗位）
  · `home_stats`       —— 首页各类榜单的确定性版本（分类/地区/企业/技能/高薪岗位/热门岗位）
  · `generic_agg`      —— 通用分组统计（按任意维度下钻岗位数/占比/薪资）

工具返回统一结构：{"ok": bool, "summary": str, "data": ..., "来源": [...]}，便于拼进上下文与溯源。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "rag"))
sys.path.insert(0, os.path.join(ROOT, "src", "models", "matching"))

TOOLS = [
    {"type": "function", "function": {
        "name": "search_jobs",
        "description": "按语义检索岗位，返回**最相似的 Top-k 样例**（适合「厦门有哪些 Java 岗位」这类问“有哪些”的问题）。"
                       "**它答不了“有多少个”**——问数量请用 filter_jobs。可指定城市做硬过滤。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "检索语句，如「厦门 Java 开发 3-5 年」"},
            "k": {"type": "integer", "description": "返回条数，默认 5"},
            "city": {"type": "string", "description": "可选，城市名（如 厦门/苏州），用于硬过滤"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "filter_jobs",
        "description": "结构化筛选岗位并返回**命中总数**——凡问「有多少个」「几个」「数量」必须用本工具（search_jobs 只给 Top-k 样例，答不出数量）。"
                       "关键词按**核心词匹配**：传「Java」即可召回所有含 Java 的岗位（含 Java工程师/Java后端/全栈+Java技能）。"
                       "返回值同时给出三个口径：岗位名称命中（严格）、名称或技能标签命中（推荐主口径）、全字段命中（宽口径）。",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "城市，可选"},
            "keyword": {"type": "string", "description": "**只传核心专业词**，如「Java」「软件测试」「前端」；"
                                                        "不要传「Java 开发工程师」这类组合短语（会被拆成核心词处理，但直接传核心词更稳）"},
            "salary_min": {"type": "integer", "description": "薪资下限门槛（元/月），可选"},
            "edu": {"type": "string", "description": "学历要求，如 大专/本科，可选"},
            "k": {"type": "integer", "description": "返回样例条数，默认 5"}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "salary_stats",
        "description": "薪资统计：返回样本数、下限/上限中位数、区间中点中位数、P25/P75。可按城市过滤。",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "城市，可选"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "match_resume",
        "description": "人岗匹配：输入一段简历文本，返回最匹配的 Top-N 岗位及 6 个维度得分与推荐理由。",
        "parameters": {"type": "object", "properties": {
            "resume_text": {"type": "string", "description": "简历文本（含期望岗位/城市/技能/经验等）"},
            "top_n": {"type": "integer", "description": "返回岗位数，默认 5"}},
            "required": ["resume_text"]}}},
    {"type": "function", "function": {
        "name": "cluster_profile",
        "description": "岗位聚类画像（任务7）：按簇名关键词返回该簇的规模、薪资中位数、主要岗位与技能。",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "簇名或关键词，如 软件测试 / 算法 / 质量检验；留空返回全部"}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "salary_rank",
        "description": "各城市薪资排名（按区间中点中位数降序）：回答「哪个城市薪资最高」这类问题用一次调用即可，不要逐城调用 salary_stats。",
        "parameters": {"type": "object", "properties": {
            "top": {"type": "integer", "description": "返回前几名，默认全部 16 个城市"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "city_list",
        "description": "返回岗位库覆盖的城市列表与各省岗位数（回答「覆盖哪些城市」「有没有某城市」时先调它）。",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "search_kb",
        "description": "检索**结论卡**（项目报告里的统计结论与口径）：问「中位数多少」「占比多少」「岗位分几类」"
                       "「评分模型和匹配规则哪个好」「某指标怎么算」这类**统计/口径/方法论**问题必须先调它。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "检索语句，尽量复述用户的统计意图"},
            "k": {"type": "integer", "description": "返回条数，默认 4"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "kb_stats",
        "description": "返回知识库自身的构成与检索评估指标（卡片数、Embedding 模型、召回 P@5 等）。",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "company_query",
        "description": "**公司维度**查询：① 问「哪家公司招人最多 / 招人最多的公司」→ 不传 name，返回在招岗位数最多的公司 Top-N；"
                       "② 问「某公司在招什么岗位 / 某某公司的岗位」→ 传 name（公司名关键词），返回该公司档案 + 它的全部在招岗位。"
                       "注意：岗位库有「公司名称」但没有公司规模/融资/行业字段。",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "公司名或关键词，如「软通动力」「三一」。留空则返回招人最多的公司"},
            "top": {"type": "integer", "description": "不传 name 时返回的公司数，默认 10"},
            "city": {"type": "string", "description": "可选，只看该公司在该城市有在招岗位的"},
            "category": {"type": "string", "description": "可选，岗位大类，如 测试/后端/算法"}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "home_stats",
        "description": "首页各类榜单的**确定性**版本（同一次提问结果稳定、可复现）：kind=分类（8 个热门分类及岗位数）｜"
                       "地区（岗位数 Top5 城市及公司数/平均薪资）｜企业（在招最多的公司 Top10）｜技能（热门技能 Top-N）｜"
                       "高薪岗位（按薪资上限降序 Top-N）｜热门岗位（按招聘者今日回复数降序 Top-N）。"
                       "问「热门/高薪/地区/技能」类问题时用它，一次调用即可，不要逐项去调别的工具。",
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["分类", "地区", "企业", "技能", "高薪岗位", "热门岗位"],
                     "description": "要哪一类榜单"},
            "n": {"type": "integer", "description": "返回条数，默认 10"}},
            "required": ["kind"]}}},
    {"type": "function", "function": {
        "name": "generic_agg",
        "description": "**通用分组统计**：按任意维度下钻，回答「按 X 统计岗位数/占比/薪资」这类任意切分的问题。"
                       "field 可选：城市、省份、区县、学历要求、经验要求、岗位大类、公司、来源关键词、一级簇名、招聘者职位、技能标签。"
                       "可叠加筛选条件（city/keyword/edu/salary_min/category）。返回每组的岗位数、占比、平均薪资上限与薪资中位数。"
                       "例：field=学历要求 → 各学历岗位数；field=公司 → 招人最多的公司；field=经验要求&city=苏州 → 苏州各经验段分布。",
        "parameters": {"type": "object", "properties": {
            "field": {"type": "string", "description": "分组维度，见工具说明"},
            "top": {"type": "integer", "description": "返回前几组，默认 15"},
            "city": {"type": "string", "description": "可选，城市筛选"},
            "keyword": {"type": "string", "description": "可选，关键词（岗位名/公司/技能/描述）"},
            "edu": {"type": "string", "description": "可选，学历筛选，如 大专"},
            "salary_min": {"type": "integer", "description": "可选，薪资上限门槛（元/月）"},
            "category": {"type": "string", "description": "可选，岗位大类，如 测试"}},
            "required": ["field"]}}},
]

_MATCHER = None
_STORE = None


def _matcher():
    global _MATCHER
    if _MATCHER is None:
        from match import JobIndex, match_jobs, load_weights, resume_record_from_parsed
        from parse_resume import parse_resume_text
        idx = JobIndex()
        w = load_weights()
        _MATCHER = (idx, match_jobs, w, parse_resume_text, resume_record_from_parsed)
    return _MATCHER


def t_search_jobs(query, k=5, city=None):
    from query import get_retriever
    hits = get_retriever().search(query, k=int(k), only_jobs=True, city=city)
    data = [{"岗位ID": h["岗位ID"], "岗位名称": h["岗位名称"], "公司": h["公司"],
             "城市": h["城市"], "薪资": h["薪资"], "相似度": h["score"]} for h in hits]
    return {"ok": bool(data), "summary": "语义检索到 %d 个岗位" % len(data), "data": data,
            "来源": ["RAG 知识库（岗位卡语义检索）"]}


def t_filter_jobs(city=None, keyword=None, salary_min=None, edu=None, k=5):
    from query import get_retriever, keyword_terms
    n, sample, tiers = get_retriever().structured_filter(city=city, keyword=keyword,
                                                         salary_min=salary_min, edu=edu, k=int(k))
    cond = "、".join(x for x in [city and "城市=%s" % city, keyword and "关键词=%s" % keyword,
                                 salary_min and "薪资下限≥%d" % salary_min, edu and "学历=%s" % edu] if x)
    if keyword:
        summary = ("条件（%s）命中 %d 个岗位（口径：岗位名称含「%s」%d 个；名称或技能标签口径 %d 个；"
                   "若把职位描述里提及的也算上共 %d 个）"
                   % (cond or "无", n, keyword, tiers["岗位名称"], tiers["名称或技能标签"], tiers["全字段"]))
        if "任一核心词_名称或技能标签" in tiers:
            summary += "；按任一核心词口径 %d 个" % tiers["任一核心词_名称或技能标签"]
    else:
        summary = "条件（%s）命中 %d 个岗位" % (cond or "无", n)
    return {"ok": n > 0, "summary": summary, "data": sample, "命中口径": tiers,
            "解析后的核心词": keyword_terms(keyword) if keyword else [],
            "来源": ["zhaopin_jobs_cleaned_seg.csv（结构化筛选）"]}


def t_salary_stats(city=None):
    from query import get_retriever
    s = get_retriever().salary_stats(city=city)
    if not s:
        return {"ok": False, "summary": "没有可用的薪资数据", "data": None, "来源": []}
    return {"ok": True, "summary": "%s：样本 %d 条，下限中位数 %d 元、上限中位数 %d 元" %
            (s["城市"], s["样本数"], s["下限中位数"], s["上限中位数"]), "data": s,
            "来源": ["zhaopin_jobs_cleaned_seg.csv（薪资数值列）"]}


def t_match_resume(resume_text, top_n=5):
    idx, match_jobs, w, parse_resume_text, to_record = _matcher()
    parsed = parse_resume_text(resume_text)
    res = to_record(parsed)
    recs, _ = match_jobs(idx, res, w["权重"], top_n=int(top_n))
    data = [{"排名": r["排名"], "总分": r["总分"], "岗位名称": r["岗位名称"], "公司": r["公司"],
             "城市": r["城市"], "薪资": r["岗位薪资"], "推荐理由": r["推荐理由"]} for r in recs]
    return {"ok": True, "summary": "解析出技能 %d 项、期望城市 %s；返回 Top-%d 推荐" %
            (res["技能数"], res["城市"] or "未识别", len(data)), "data": data,
            "来源": ["任务6 人岗匹配（权重版本 %s）" % w["版本"], "简历解析告警：%s" % (parsed.get("解析告警") or "无")]}


def _csv_num(x):
    """把 CSV 里的数字字符串转成真正的数字

    `岗位聚类_簇画像.csv` 读出来每个字段都是字符串，早期直接把 `"4546"`、`"51.45"`
    原样塞进接口返回，于是 `/api/cluster/profile` 的「岗位数/占比/薪资中位数」是**字符串**，
    而兄弟接口 `/api/cluster/list` 的「岗位数」是**整数**（`test_api.py` 里能直接 `sum()`）。
    同一个系统的两个聚类接口字段类型不一致，调用方只能自己猜，属于实打实的接口缺陷
    （见《测试报告》缺陷 14）。这里统一转成 int/float，转不动就原样返回、不抛异常。
    """
    s = str(x).strip().replace(",", "")
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except ValueError:
        return x


def t_cluster_profile(name=None):
    from query import get_retriever
    rows = get_retriever().cluster_profile(name)
    data = [{"方案": r["方案"], "簇名": r["簇名"],
             "岗位数": _csv_num(r["岗位数"]),
             "占比": _csv_num(r["占比(%)"]),
             "薪资中位数": _csv_num(r["薪资中位数(元)"]),
             "主要岗位": r["主要岗位"][:40],
             "特征技能": r["特征技能(lift Top10)"][:40]} for r in rows]
    return {"ok": bool(data), "summary": "匹配到 %d 条聚类画像记录" % len(data), "data": data,
            "来源": ["岗位聚类_簇画像.csv（任务7 K-Means）"]}


def t_salary_rank(top=None):
    from query import get_retriever
    r = get_retriever()
    rows = []
    for c in r.cities:
        s = r.salary_stats(city=c)
        if s:
            rows.append({"城市": c, "样本数": s["样本数"], "下限中位数": s["下限中位数"],
                         "上限中位数": s["上限中位数"], "区间中点中位数": s["区间中点中位数"]})
    rows.sort(key=lambda x: -x["区间中点中位数"])
    data = rows[:int(top)] if top else rows
    return {"ok": bool(data), "summary": "共 %d 个城市有薪资数据，最高：%s（中点中位数 %d 元）" %
            (len(rows), data[0]["城市"] if data else "—", data[0]["区间中点中位数"] if data else 0),
            "data": data, "来源": ["zhaopin_jobs_cleaned_seg.csv（按城市聚合）"]}


def t_city_list():
    from query import get_retriever
    import csv as _csv
    r = get_retriever()
    from build_labels import load_csv as _load
    rows = _load(os.path.join(ROOT, "data", "processed", "zhaopin_jobs_cleaned_seg.csv"))
    cnt = {}
    for x in rows:
        c = (x["岗位地区"] or "").split()
        if c:
            cnt[c[0]] = cnt.get(c[0], 0) + 1
    data = sorted(({"城市": k, "岗位数": v} for k, v in cnt.items()), key=lambda d: -d["岗位数"])
    return {"ok": True, "summary": "岗位库覆盖 %d 个城市（共 %d 条岗位）；覆盖省份：福建/浙江/江苏/安徽" %
            (len(data), sum(v for v in cnt.values())), "data": data,
            "来源": ["zhaopin_jobs_cleaned_seg.csv"]}


def t_search_kb(query, k=4):
    """检索结论卡（统计结论与口径）——Agent 回答"中位数/占比/口径/模型对比"这类问题的依据"""
    from query import get_retriever
    hits = get_retriever().search(query, k=int(k), mode="conclusions", fallback=False)
    data = [{"结论": h["文本"], "来源": h.get("来源") or "", "类型": h["类型"], "相似度": h["score"]}
            for h in hits]
    return {"ok": bool(data), "summary": "检索到 %d 条结论卡" % len(data), "data": data,
            "来源": list(dict.fromkeys(h["来源"] for h in hits if h.get("来源")))}


def t_kb_stats():
    import json
    cards = json.load(open(os.path.join(ROOT, "data", "rag", "jobs_kb_cards.json"), encoding="utf-8"))
    types = {}
    for c in cards:
        types[c["类型"]] = types.get(c["类型"], 0) + 1
    eval_md = os.path.join(ROOT, "data", "processed", "RAG召回评估.md")
    p5 = "见 RAG召回评估.md"
    if os.path.exists(eval_md):
        for line in open(eval_md, encoding="utf-8"):
            if "路由+城市过滤" in line and "**" in line and "P@5" not in line:
                parts = [x.strip() for x in line.strip().strip("|").split("|")]
                if len(parts) >= 3:
                    p5 = "路由+城市过滤 全部问题的 P@5 = %s（详见 RAG召回评估.md）" % parts[2]
    return {"ok": True,
            "summary": "知识库共 %d 张卡片（岗位卡 %d、结论卡 %d）；Embedding = BAAI/bge-small-zh-v1.5（512 维）；"
                       "向量库 = FAISS 内存索引；%s" % (len(cards), types.get("岗位卡", 0),
                                                  len(cards) - types.get("岗位卡", 0), p5),
            "data": {"卡片类型分布": types, "模型": "BAAI/bge-small-zh-v1.5", "维度": 512,
                     "检索": "FAISS IndexFlatIP（余弦）", "检索评估": p5},
            "来源": ["RAG_入库说明.md", "RAG召回评估.md"]}


def _job_store():
    """复用 API 层的岗位/公司库单例（只读）——保证 Agent 与页面口径完全一致"""
    global _STORE
    if _STORE is None:
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from src.api.jobs import get_store
        _STORE = get_store()
    return _STORE


def t_company_query(name=None, top=10, city=None, category=None):
    st = _job_store()
    if name:
        key = str(name).strip()
        # 先按公司名精确/包含匹配，找不到再退回模糊
        hit = st.company_by_name.get(key)
        if not hit:
            cands = [c for c in st.companies if key and key in c["公司名称"]]
            if city:
                cands = [c for c in cands if any(x["名称"] == city for x in c["城市列表"])]
            if category:
                cands = [c for c in cands if any(x["名称"] == category for x in c["岗位大类"])]
            if not cands:
                return {"ok": False, "data": None,
                        "summary": "没有找到公司名含「%s」的公司（岗位库共 %d 家公司）" % (key, len(st.companies)),
                        "来源": ["zhaopin_jobs_cleaned_seg.csv（公司名称去重）"]}
            hit = cands[0]
        detail = st.company_get(hit["公司ID"])
        jobs = [{"岗位ID": j["岗位ID"], "岗位名称": j["岗位名称"], "城市": j["城市"], "区县": j["区县"],
                 "薪资": j["薪资"], "经验要求": j["经验要求"], "学历要求": j["学历要求"],
                 "技能标签": j["技能标签"][:6]} for j in detail["在招岗位"][:20]]
        return {"ok": True,
                "summary": "%s：在招 %d 个岗位（主要城市 %s、主要大类 %s、薪资下限中位数 %d 元、上限中位数 %d 元），"
                           "下面给出前 %d 个岗位" % (detail["公司名称"], detail["在招岗位数"], detail["主要城市"],
                                                detail["主要大类"], detail["薪资下限中位数"],
                                                detail["薪资上限中位数"], len(jobs)),
                "data": jobs,
                "公司档案": {k: detail[k] for k in ("公司名称", "公司ID", "在招岗位数", "主要城市", "主要大类",
                                               "城市列表", "岗位大类", "技能需求", "学历要求", "经验要求",
                                               "薪资下限中位数", "薪资上限中位数", "招聘者数", "今日回复总数")},
                "其他候选": [c["公司名称"] for c in st.companies
                          if key and key in c["公司名称"] and c["公司名称"] != detail["公司名称"]][:5],
                "来源": ["zhaopin_jobs_cleaned_seg.csv（按公司名聚合）"]}

    res = st.company_query(page=1, size=int(top), city=city, category=category, sort="jobs_desc")
    data = [{"公司名称": c["公司名称"], "公司ID": c["公司ID"], "在招岗位数": c["在招岗位数"],
             "主要城市": c["主要城市"], "城市数": c["城市数"], "主要大类": c["主要大类"],
             "薪资下限中位数": c["薪资下限中位数"], "薪资上限中位数": c["薪资上限中位数"],
             "招聘者数": c["招聘者数"], "热招职位": [j["岗位名称"] for j in c["热招职位"]]}
            for c in res["公司"]]
    cond = "、".join(x for x in [city and "城市=%s" % city, category and "大类=%s" % category] if x) or "无筛选"
    return {"ok": bool(data), "summary": "命中 %d 家公司（%s），下面按在招岗位数降序给出前 %d 家" %
            (res["总数"], cond, len(data)), "data": data,
            "来源": ["zhaopin_jobs_cleaned_seg.csv（按公司名聚合）"]}


def t_home_stats(kind, n=10):
    st = _job_store()
    kind = (kind or "").strip()
    if kind == "分类":
        h = st.home()
        data = [{"分类": c["分类"], "岗位数": c["岗位数"], "公司数": c["公司数"],
                 "平均薪资上限": c["平均薪资上限"], "热门技能": c["热门技能"][:5]}
                for c in h["热门分类"]]
        return {"ok": True, "summary": "共 %d 个热门分类，岗位数合计 %d" %
                (len(data), sum(x["岗位数"] for x in data)), "data": data,
                "来源": ["zhaopin_jobs_cleaned_seg.csv（来源关键词列）"]}
    if kind == "地区":
        h = st.home()
        data = h["地区推荐"][:int(n)]
        return {"ok": True, "summary": "岗位数 Top%d 城市：%s" %
                (len(data), "、".join("%s(%d)" % (x["城市"], x["岗位数"]) for x in data)), "data": data,
                "来源": ["zhaopin_jobs_cleaned_seg.csv（按城市聚合）"]}
    if kind == "企业":
        data = st.company_query(page=1, size=int(n), sort="jobs_desc")["公司"]
        return {"ok": True, "summary": "在招岗位最多的 %d 家公司，第一名 %s（%d 个岗位）" %
                (len(data), data[0]["公司名称"], data[0]["在招岗位数"]) if data else "没有数据",
                "data": [{"公司名称": c["公司名称"], "在招岗位数": c["在招岗位数"], "主要城市": c["主要城市"],
                          "主要大类": c["主要大类"]} for c in data],
                "来源": ["zhaopin_jobs_cleaned_seg.csv（按公司名聚合）"]}
    if kind == "技能":
        data = st.stats()["热门技能"][:int(n)]
        return {"ok": True, "summary": "热门技能 Top%d：%s" %
                (len(data), "、".join(x["名称"] for x in data[:6])), "data": data,
                "来源": ["zhaopin_jobs_cleaned_seg.csv（技能标签列）"]}
    if kind == "高薪岗位":
        data, total = st.top_jobs(by="salary", n=int(n))
        return {"ok": True, "summary": "全库按薪资上限降序的前 %d 个岗位（共 %d 个岗位参与排序）" % (len(data), total),
                "data": [{"岗位ID": x["岗位ID"], "岗位名称": x["岗位名称"], "公司": x["公司"], "城市": x["城市"],
                          "薪资": x["薪资"], "技能标签": x["技能标签"][:5]} for x in data],
                "来源": ["zhaopin_jobs_cleaned_seg.csv（薪资数值列）"]}
    if kind == "热门岗位":
        data, total = st.top_jobs(by="reply", n=int(n))
        return {"ok": True, "summary": "按招聘者今日回复数降序的前 %d 个岗位（共 %d 个岗位参与排序）" % (len(data), total),
                "data": [{"岗位ID": x["岗位ID"], "岗位名称": x["岗位名称"], "公司": x["公司"], "城市": x["城市"],
                          "薪资": x["薪资"], "今日回复数": x["今日回复数"], "招聘者": x["招聘者"]} for x in data],
                "来源": ["zhaopin_jobs_cleaned_seg.csv（今日回复数列）"]}
    return {"ok": False, "data": None,
            "summary": "kind 只能是：分类 / 地区 / 企业 / 技能 / 高薪岗位 / 热门岗位", "来源": []}


def t_generic_agg(field, top=15, city=None, keyword=None, edu=None, salary_min=None, category=None):
    st = _job_store()
    try:
        res = st.group_by(field, top=int(top), city=city, keyword=keyword, edu=edu,
                          salary_min=salary_min, category=category)
    except ValueError as e:
        return {"ok": False, "data": None, "summary": str(e),
                "可选维度": st.GROUP_FIELDS, "来源": []}
    cond = "、".join(x for x in [city and "城市=%s" % city, category and "大类=%s" % category,
                                 keyword and "关键词=%s" % keyword, edu and "学历=%s" % edu,
                                 salary_min and "薪资上限≥%d" % salary_min] if x) or "无筛选"
    head = "、".join("%s %d 个(%.1f%%)" % (d["分组"], d["岗位数"], d["占比"]) for d in res["明细"][:5])
    return {"ok": bool(res["明细"]),
            "summary": "按「%s」分组（%s，样本 %d 个岗位，共 %d 组）：%s" %
                       (field, cond, res["筛选后岗位总数"], res["分组数"], head or "无数据"),
            "data": res["明细"], "来源": ["zhaopin_jobs_cleaned_seg.csv（%s 列聚合）" % field]}


DISPATCH = {"search_jobs": t_search_jobs, "filter_jobs": t_filter_jobs, "salary_stats": t_salary_stats,
            "salary_rank": t_salary_rank, "city_list": t_city_list, "match_resume": t_match_resume,
            "cluster_profile": t_cluster_profile, "search_kb": t_search_kb, "kb_stats": t_kb_stats,
            "company_query": t_company_query, "home_stats": t_home_stats, "generic_agg": t_generic_agg}


def call_tool(name, args):
    fn = DISPATCH.get(name)
    if not fn:
        return {"ok": False, "summary": "未知工具：%s" % name, "data": None, "来源": []}
    try:
        return fn(**(args or {}))
    except Exception as e:                      # 工具失败要如实返回，不能静默
        return {"ok": False, "summary": "工具 %s 执行失败：%s: %s" % (name, type(e).__name__, e),
                "data": None, "来源": []}
