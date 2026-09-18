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

    def test_region_recommendation(self):
        j = _home()
        regs = j["地区推荐"]
        assert len(regs) == 16                     # 16 个城市全覆盖
        assert regs[0]["城市"] == "苏州" and regs[0]["岗位数"] == 2073
        assert sum(x["岗位数"] for x in regs) == 8836
        for x in regs:
            assert x["省份"] and x["公司数"] > 0 and x["平均薪资上限"] > 0
            assert len(x["热门区县"]) <= 3
            assert all(0 < d["数量"] <= x["岗位数"] for d in x["热门区县"])

    def test_high_salary_jobs_sorted(self):
        j = _home()
        up = [x["薪资上限"] for x in j["高薪岗位"]]
        assert len(up) == 8
        assert up == sorted(up, reverse=True)
        assert up[0] == 200000                     # 与 /api/jobs?sort=salary_desc 同口径
        first = client.get("/api/jobs", params={"sort": "salary_desc", "size": 1}).json()["岗位"][0]
        assert j["高薪岗位"][0]["岗位ID"] == first["岗位ID"]
        # 「薪资面议」的岗位不能混进高薪榜
        assert all(x["薪资上限"] > 0 for x in j["高薪岗位"])

    def test_hot_jobs_sorted_by_recruiter_reply(self):
        j = _home()
        rep = [x["今日回复数"] for x in j["热门岗位"]]
        assert len(rep) == 8
        assert rep == sorted(rep, reverse=True)
        assert rep[0] > 0
        # 与岗位接口「回复最积极」排序的最大值一致
        top_reply = client.get("/api/jobs", params={"sort": "reply", "size": 1}).json()["岗位"][0]
        assert rep[0] == top_reply["今日回复数"]
        for x in j["热门岗位"]:
            assert x["招聘者"] and x["回复文案"]

    def test_hot_companies(self):
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
        j = _home()
        assert len(j["口径说明"]) >= 5
        assert any("来源关键词" in s for s in j["口径说明"])
        assert any("薪资上限" in s for s in j["口径说明"])
        assert any("浏览" in s or "投递" in s for s in j["口径说明"])
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
