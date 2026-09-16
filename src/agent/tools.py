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
]

_MATCHER = None


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


def t_cluster_profile(name=None):
    from query import get_retriever
    rows = get_retriever().cluster_profile(name)
    data = [{"方案": r["方案"], "簇名": r["簇名"], "岗位数": r["岗位数"], "占比": r["占比(%)"],
             "薪资中位数": r["薪资中位数(元)"], "主要岗位": r["主要岗位"][:40],
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


DISPATCH = {"search_jobs": t_search_jobs, "filter_jobs": t_filter_jobs, "salary_stats": t_salary_stats,
            "salary_rank": t_salary_rank, "city_list": t_city_list, "match_resume": t_match_resume,
            "cluster_profile": t_cluster_profile, "search_kb": t_search_kb, "kb_stats": t_kb_stats}


def call_tool(name, args):
    fn = DISPATCH.get(name)
    if not fn:
        return {"ok": False, "summary": "未知工具：%s" % name, "data": None, "来源": []}
    try:
        return fn(**(args or {}))
    except Exception as e:                      # 工具失败要如实返回，不能静默
        return {"ok": False, "summary": "工具 %s 执行失败：%s: %s" % (name, type(e).__name__, e),
                "data": None, "来源": []}
