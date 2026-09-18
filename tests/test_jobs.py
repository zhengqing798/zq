# -*- coding: utf-8 -*-
"""任务11 · 岗位浏览（首页）接口测试

覆盖 `/api/jobs/stats`、`/api/jobs`（分页/筛选/排序）、`/api/jobs/{id}` 的正常/边界/异常。
数据来源：`data/processed/zhaopin_jobs_cleaned_seg.csv`（8,836 个清洗后岗位）。
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.api.main import app                                              # noqa: E402

client = TestClient(app)


# ================================================================ 分类统计
class TestJobStats:
    def test_normal(self):
        r = client.get("/api/jobs/stats")
        assert r.status_code == 200
        j = r.json()
        o = j["总体"]
        assert o["岗位总数"] == 8836
        assert o["城市数"] == 16 and o["省份数"] == 4
        assert o["公司数"] > 4000
        assert o["薪资上限中位数"] > 0 and o["薪资下限中位数"] > 0
        # 分类明细：9 个大类，且合计等于岗位总数
        assert len(j["按大类"]) == 9
        assert sum(x["数量"] for x in j["按大类"]) == 8836
        assert len(j["按城市"]) == 16
        assert sum(x["数量"] for x in j["按城市"]) == 8836
        assert len(j["热门技能"]) == 20
        assert j["筛选项"]["排序"] and j["筛选项"]["城市"]
        assert j["来源"]

    def test_category_matches_cluster_sizes(self):
        """口径校验：岗位大类分布应与任务7 聚类的主簇规模一致（同一批岗位、同一套规则）"""
        cats = {x["名称"]: x["数量"] for x in client.get("/api/jobs/stats").json()["按大类"]}
        assert cats["测试"] == 1453      # 与《岗位聚类_说明.md》软件测试簇一致
        assert cats["后端"] == 906
        assert cats["其他"] == 4546


# ================================================================ 列表与分页
class TestJobList:
    def test_normal_first_page(self):
        r = client.get("/api/jobs", params={"page": 1, "size": 20})
        assert r.status_code == 200
        j = r.json()
        assert j["总数"] == 8836 and j["总页数"] == 442 and j["每页"] == 20
        assert len(j["岗位"]) == 20
        x = j["岗位"][0]
        for k in ("岗位ID", "岗位名称", "公司", "城市", "薪资", "学历要求", "岗位大类", "技能标签"):
            assert k in x, k
        assert x["岗位ID"].startswith("J")

    def test_boundary_last_page(self):
        r = client.get("/api/jobs", params={"page": 442, "size": 20})
        assert r.status_code == 200
        assert len(r.json()["岗位"]) == 8836 - 441 * 20

    @pytest.mark.parametrize("size", [1, 50, 100])
    def test_boundary_page_size(self, size):
        r = client.get("/api/jobs", params={"size": size})
        assert r.status_code == 200 and len(r.json()["岗位"]) == size

    def test_boundary_size_capped(self):
        """边界：size 超上限 100 会被夹到 100（而不是报错）"""
        r = client.get("/api/jobs", params={"size": 500})
        assert r.status_code == 200 and r.json()["每页"] == 100

    def test_boundary_page_beyond_end(self):
        """边界：页码超出范围返回空列表而不是 500"""
        r = client.get("/api/jobs", params={"page": 99999, "size": 20})
        assert r.status_code == 200 and r.json()["岗位"] == []

    def test_abnormal_bad_param_type(self):
        r = client.get("/api/jobs", params={"page": "abc"})
        assert r.status_code == 422


# ================================================================ 筛选与排序
class TestJobFilter:
    def test_filter_city(self):
        j = client.get("/api/jobs", params={"city": "苏州", "size": 5}).json()
        assert j["总数"] == 2073                       # 与《数据预处理文档》一致
        assert all(x["城市"] == "苏州" for x in j["岗位"])

    def test_filter_category(self):
        j = client.get("/api/jobs", params={"category": "测试", "size": 5}).json()
        assert j["总数"] == 1453
        assert all(x["岗位大类"] == "测试" for x in j["岗位"])

    def test_filter_keyword(self):
        j = client.get("/api/jobs", params={"keyword": "Java", "size": 5}).json()
        assert j["总数"] > 0
        for x in j["岗位"]:
            blob = (x["岗位名称"] + x["公司"] + x["技能标签原文"] + (x["职位描述"] or "")).lower()
            assert "java" in blob

    def test_filter_edu(self):
        j = client.get("/api/jobs", params={"edu": "大专", "size": 5}).json()
        assert j["总数"] > 0
        assert all("大专" in x["学历要求"] for x in j["岗位"])

    def test_filter_salary_min(self):
        j = client.get("/api/jobs", params={"salary_min": 30000, "size": 5}).json()
        assert j["总数"] > 0
        assert all(x["薪资上限"] >= 30000 for x in j["岗位"])

    def test_filter_cluster(self):
        j = client.get("/api/jobs", params={"cluster": "软件测试", "size": 5}).json()
        assert j["总数"] == 1453
        assert all("软件测试" in x["一级簇名"] for x in j["岗位"])

    def test_filters_combined(self):
        j = client.get("/api/jobs", params={"city": "苏州", "category": "测试", "size": 5}).json()
        assert j["总数"] == 360
        assert all(x["城市"] == "苏州" and x["岗位大类"] == "测试" for x in j["岗位"])

    def test_sort_salary_desc(self):
        j = client.get("/api/jobs", params={"sort": "salary_desc", "size": 10}).json()
        ups = [x["薪资上限"] for x in j["岗位"]]
        assert ups == sorted(ups, reverse=True)
        assert ups[0] == 200000
        # 说明：这里用「薪资上限」列的可靠值。
        # 《可视化分析报告》图11 记的"最大 80,004"来自旧的 parse_salary 文本解析口径（见测试报告「已知问题」）。

    def test_sort_salary_asc(self):
        j = client.get("/api/jobs", params={"sort": "salary_asc", "size": 10}).json()
        ups = [x["薪资上限"] for x in j["岗位"] if x["薪资上限"] > 0]
        assert ups == sorted(ups)

    def test_sort_unknown_falls_back(self):
        """边界：未知排序值不报错，按默认排序返回"""
        r = client.get("/api/jobs", params={"sort": "not-a-sort"})
        assert r.status_code == 200 and r.json()["总数"] == 8836

    def test_filter_no_match(self):
        j = client.get("/api/jobs", params={"city": "北京"}).json()
        assert j["总数"] == 0 and j["岗位"] == []


# ================================================================ 岗位详情
class TestJobDetail:
    def test_normal(self):
        r = client.get("/api/jobs/J0001")
        assert r.status_code == 200
        j = r.json()
        assert j["岗位ID"] == "J0001"
        assert j["岗位名称"] and j["公司"] and j["职位描述"]
        assert isinstance(j["技能标签"], list)

    def test_normal_lowercase(self):
        assert client.get("/api/jobs/j0001").status_code == 200

    def test_boundary_last_job(self):
        assert client.get("/api/jobs/J8836").status_code == 200

    def test_abnormal_not_exists(self):
        r = client.get("/api/jobs/J99999")
        assert r.status_code == 400
        assert "不存在" in r.json()["error"]

    def test_abnormal_bad_format(self):
        r = client.get("/api/jobs/abc")
        assert r.status_code == 400

    def test_detail_has_cluster(self):
        """详情应带上任务7 的簇归属（首页抽屉要展示）"""
        j = client.get("/api/jobs/J0001").json()
        assert "一级簇名" in j and "二级簇名" in j


# ================================================================ 模拟 BOSS直聘：招聘者 / 区域 / 热门职位
class TestBossStyle:
    """首页按 BOSS直聘 城市职位列表改造后新增的能力"""

    def test_job_has_recruiter_fields(self):
        """正常：每个岗位都带「招聘者」行所需字段（全部来自真实数据）"""
        j = client.get("/api/jobs", params={"size": 5}).json()
        for x in j["岗位"]:
            assert x["招聘者"], "招聘者姓名不能为空（发布者姓名非空率 100%）"
            assert x["招聘者职位"], "招聘者职位应有兜底文案"
            assert "在线状态" in x and "回复文案" in x and "来源关键词" in x
            assert isinstance(x["同公司岗位数"], int) and x["同公司岗位数"] >= 1
        # 「区县」应从岗位地区里拆出来
        assert any(x["区县"] for x in j["岗位"])

    def test_reply_count_parsed(self):
        """正常：今日回复数是**从文本解析出的数字**（如「今日回复40次」→40），不能恒为 0"""
        st = client.get("/api/jobs/stats").json()
        assert st["总体"]["有回复数据岗位数"] == 4624          # 与数据探查一致
        j = client.get("/api/jobs", params={"sort": "reply", "size": 5}).json()
        assert j["岗位"][0]["今日回复数"] > 0
        nums = [x["今日回复数"] for x in j["岗位"]]
        assert nums == sorted(nums, reverse=True)

    def test_district_filter(self):
        """正常：按区县筛选（厦门·思明）"""
        j = client.get("/api/jobs", params={"city": "厦门", "district": "思明", "size": 5}).json()
        assert j["总数"] == 303
        assert all(x["城市"] == "厦门" and x["区县"] == "思明" for x in j["岗位"])
        # 与城市总数对比：区县是城市的子集
        total = client.get("/api/jobs", params={"city": "厦门", "size": 1}).json()["总数"]
        assert 0 < j["总数"] < total

    def test_abnormal_unknown_district(self):
        """边界：不存在的区县 → 空结果而不是报错"""
        j = client.get("/api/jobs", params={"city": "厦门", "district": "不存在区"}).json()
        assert j["总数"] == 0 and j["岗位"] == []

    def test_stats_district_index(self):
        """正常：统计里的「按城市区县」索引可支撑区域筛选下拉"""
        st = client.get("/api/jobs/stats").json()
        assert "厦门" in st["按城市区县"]
        xm = st["按城市区县"]["厦门"]
        assert xm[0]["名称"] == "思明" and xm[0]["数量"] == 303
        total = client.get("/api/jobs", params={"city": "厦门", "size": 1}).json()["总数"]
        covered = sum(x["数量"] for x in xm)
        # 少数岗位的「岗位地区」没有区县段（厦门 1169 个里有 11 个），故只要求覆盖率 >99%
        assert covered <= total and (total - covered) < total * 0.01
        assert st["总体"]["区县数"] == 203

    def test_stats_hot_keywords(self):
        """正常：热门职位来自「来源关键词」列（爬虫当初用的 8 个搜索关键词）"""
        st = client.get("/api/jobs/stats").json()
        names = [x["名称"] for x in st["热门搜索"]]
        assert len(names) == 8                       # 数据里只有 8 个不同来源关键词
        assert "数据分析" in names and "测试" in names and "Java" in names
        assert st["热门搜索"][0]["名称"] == "数据分析"
        assert st["热门搜索"][0]["数量"] == 2564

    def test_stats_category_nav(self):
        """正常：分类导航 = 大类 → 该大类下的高频子职位（模拟 BOSS 分类面板）"""
        st = client.get("/api/jobs/stats").json()
        nav = st["分类导航"]
        assert len(nav) == 9
        assert sum(g["数量"] for g in nav) == 8836
        test_grp = next(g for g in nav if g["大类"] == "测试")
        subs = [s["名称"] for s in test_grp["子职位"]]
        assert "测试工程师" in subs
        assert all(s["数量"] >= 3 for s in test_grp["子职位"])   # 低于 3 个的不展示

    def test_stats_hr_coverage(self):
        """正常：招聘者职位覆盖率应如实反映数据（发布者身份非空率 74%）"""
        st = client.get("/api/jobs/stats").json()
        total = st["总体"]["岗位总数"]
        assert st["总体"]["有招聘者职位数"] == 6549
        assert 0.7 < st["总体"]["有招聘者职位数"] / total < 0.8

