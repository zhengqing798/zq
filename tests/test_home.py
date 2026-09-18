# -*- coding: utf-8 -*-
"""任务11 · 首页推荐接口测试（首页改版）

覆盖 `GET /api/home`：热门分类轮播 / 地区推荐 / 高薪岗位 / 热门岗位 / 热门企业。

设计要点（与页面文案一致，别让测试和口径打架）：
· 「热门分类」取自真实的 `来源关键词` 列 → 分类数应为 **8**，且各分类岗位数之和 = 8,836；
· 「高薪岗位」按 `薪资上限(元/月)` 降序 → 第一名应与 `/api/jobs?sort=salary_desc` 一致；
· 「热门岗位」按 `今日回复数 → 是否在线 → 薪资上限` 降序 → 第一名的回复数应等于全局最大回复数；
· **数据里没有浏览/投递量**，所以接口不得凭空出现 `浏览量/投递量/热度` 之类别名字段。
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


def _home(**params):
    r = client.get("/api/home", params=params)
    assert r.status_code == 200
    return r.json()


# ================================================================ 正常路径
class TestHomeNormal:
    def test_normal_structure(self):
        j = _home()
        for k in ("热门分类", "地区推荐", "高薪岗位", "热门岗位", "热门企业", "热门技能",
                  "总体", "口径说明", "来源"):
            assert k in j, k

    def test_hot_categories_from_real_column(self):
        """热门分类 = 真实的「来源关键词」列（爬虫当初用的搜索词，共 8 个）"""
        j = _home()
        cats = j["热门分类"]
        assert len(cats) == 8
        assert [c["分类"] for c in cats] == [
            "数据分析", "测试", "Java", "Python", "运维", "后端", "算法", "前端"]
        assert cats[0]["岗位数"] == 2564
        # 每个分类都要有轮播所需的内容
        for c in cats:
            assert c["岗位数"] > 0 and c["公司数"] > 0
            assert c["平均薪资上限"] > 0
            assert 1 <= len(c["示例岗位"]) <= 3
            assert c["热门技能"]
            for s in c["示例岗位"]:
                assert s["岗位ID"].startswith("J") and s["岗位名称"] and s["公司"]

    def test_hot_categories_cover_all_jobs(self):
        """口径校验：每个岗位都带来源关键词，故各分类岗位数之和应等于岗位总数"""
        j = _home()
        assert sum(c["岗位数"] for c in j["热门分类"]) == 8836
        assert j["总体"]["岗位数"] == 8836

    def test_category_count_matches_jobs_page(self):
        """跨接口一致性：首页分类卡上的数字 = /api/jobs?source_kw=分类 的条数

        （这正是首页点分类跳「岗位」页时用的参数；用模糊 keyword 会更多，故不能用它）
        """
        for c in _home()["热门分类"]:
            got = client.get("/api/jobs", params={"source_kw": c["分类"], "size": 1}).json()["总数"]
            assert got == c["岗位数"], "「%s」首页显示 %d，岗位页筛出 %d" % (
                c["分类"], c["岗位数"], got)

    def test_region_recommendation_top5(self):
        """地区推荐只给 Top 5（按岗位数），每张卡带公司数/平均薪资/热门区县"""
        j = _home()
        regs = j["地区推荐"]
        assert len(regs) == 5
        assert [x["城市"] for x in regs] == ["苏州", "福州", "厦门", "宁波", "嘉兴"]
        assert regs[0]["岗位数"] == 2073
        nums = [x["岗位数"] for x in regs]
        assert nums == sorted(nums, reverse=True)          # Top 5 之间仍是降序
        assert sum(nums) < 8836                            # 只是子集，不是全部城市
        for x in regs:
            assert x["省份"] and x["公司数"] > 0 and x["平均薪资上限"] > 0
            assert len(x["热门区县"]) <= 3
            assert all(0 < d["数量"] <= x["岗位数"] for d in x["热门区县"])

    def test_high_salary_jobs_from_pool(self):
        """高薪岗位：必须全部来自「薪资下限 > 10000 元/月」的池子，且按薪资上限降序"""
        ids = {x["岗位ID"] for x in client.get("/api/jobs", params={"size": 100}).json()["岗位"]}
        assert ids                                            # 岗位接口可用
        for _ in range(3):
            j = _home()
            high = j["高薪岗位"]
            assert len(high) == 8
            assert all(x["薪资下限"] > 10000 for x in high), "有岗位的薪资下限没到 1 万"
            ups = [x["薪资上限"] for x in high]
            assert ups == sorted(ups, reverse=True)
            # 池子校验：随机抽出来的岗位确实存在于岗位库中
            for x in high:
                assert client.get("/api/jobs/%s" % x["岗位ID"]).status_code == 200

    def test_hot_jobs_from_pool(self):
        """热门岗位：必须全部来自「招聘者今日回复数 ≥ 20」的池子，且按回复数降序"""
        for _ in range(3):
            hot = _home()["热门岗位"]
            assert len(hot) == 8
            assert all(x["今日回复数"] >= 20 for x in hot), "有岗位的回复数没到 20"
            rep = [x["今日回复数"] for x in hot]
            assert rep == sorted(rep, reverse=True)
            for x in hot:
                assert x["招聘者"] and x["回复文案"]

    def test_both_lists_are_random_each_request(self):
        """随机性：连续 5 次请求，两组榜单至少出现 2 种不同组合（池子 1000+，不可能撞车）"""
        high_sets, hot_sets = set(), set()
        for _ in range(5):
            j = _home()
            high_sets.add(frozenset(x["岗位ID"] for x in j["高薪岗位"]))
            hot_sets.add(frozenset(x["岗位ID"] for x in j["热门岗位"]))
        assert len(high_sets) >= 2, "高薪岗位每次返回都一样，没有随机"
        assert len(hot_sets) >= 2, "热门岗位每次返回都一样，没有随机"
        # 反向：固定榜单（地区 / 热门企业）必须每次一致
        a, b = _home(), _home()
        assert [x["城市"] for x in a["地区推荐"]] == [x["城市"] for x in b["地区推荐"]]
        assert [x["公司ID"] for x in a["热门企业"]] == [x["公司ID"] for x in b["热门企业"]]

    def test_hot_companies_top10(self):
        j = _home()
        comps = j["热门企业"]
        assert len(comps) == 10
        jobs = [c["在招岗位数"] for c in comps]
        assert jobs == sorted(jobs, reverse=True)
        assert comps[0]["公司名称"] == "软通动力信息技术(集团)股份有限公司"
        assert comps[0]["在招岗位数"] == 86
        # 与公司页同一口径
        assert (client.get("/api/companies", params={"size": 1}).json()["公司"][0]["公司ID"]
                == comps[0]["公司ID"])

    def test_hot_skills(self):
        j = _home()
        assert len(j["热门技能"]) == 12
        nums = [x["数量"] for x in j["热门技能"]]
        assert nums == sorted(nums, reverse=True)

    def test_overall_consistent_with_job_stats(self):
        """跨接口一致性：首页「总体」必须与岗位页统计对得上"""
        h = _home()["总体"]
        s = client.get("/api/jobs/stats").json()["总体"]
        assert h["岗位数"] == s["岗位总数"] == 8836
        assert h["公司数"] == s["公司数"] == 4096
        assert h["城市数"] == s["城市数"] == 16
        assert h["在线岗位数"] == s["在线岗位数"]
        assert h["有回复岗位数"] == s["有回复数据岗位数"]

    def test_caliber_notes(self):
        """口径说明随接口返回（页面不展示，但接口/文档必须有）"""
        j = _home()
        assert len(j["口径说明"]) >= 5
        notes = " ".join(j["口径说明"])
        assert "来源关键词" in notes
        assert "随机抽取" in notes                    # 高薪/热门是随机抽的，必须写明
        assert "10000" in notes and "Top 5" in notes
        assert "回复数 ≥ 20" in notes and "Top 10" in notes
        assert "浏览" in notes or "投递" in notes      # 说明为什么不用"热度"
        assert j["来源"]


# ================================================================ 诚实性
class TestHomeHonesty:
    def test_no_fabricated_popularity_fields(self):
        """数据里没有浏览/投递量：接口不得返回这些字段（防"编热度"）"""
        j = _home()
        for group in ("高薪岗位", "热门岗位"):
            for x in j[group]:
                for bad in ("浏览量", "投递量", "热度", "应聘人数", "收藏量"):
                    assert bad not in x, "%s 里出现了数据中不存在的字段「%s」" % (group, bad)

    def test_job_brief_is_lightweight(self):
        """榜单卡片不该带走职位描述全文（首页体积要小）"""
        j = _home()
        for x in j["高薪岗位"] + j["热门岗位"]:
            assert "职位描述" not in x
            assert len(x["技能标签"]) <= 5


# ================================================================ 边界
class TestHomeBoundary:
    @pytest.mark.parametrize("n", [1, 3, 8, 20])
    def test_boundary_n(self, n):
        j = _home(n=n)
        assert len(j["高薪岗位"]) == n
        assert len(j["热门岗位"]) == n

    def test_boundary_n_zero_clamped(self):
        j = _home(n=0)                             # 夹到 1，而不是空列表
        assert len(j["高薪岗位"]) == 1

    def test_boundary_n_too_large_clamped(self):
        j = _home(n=999)                           # 夹到 20
        assert len(j["高薪岗位"]) == 20

    def test_boundary_n_negative_clamped(self):
        assert len(_home(n=-5)["高薪岗位"]) == 1


# ================================================================ 异常
class TestHomeAbnormal:
    def test_abnormal_bad_param_type(self):
        assert client.get("/api/home", params={"n": "abc"}).status_code == 422
