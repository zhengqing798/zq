# -*- coding: utf-8 -*-
"""任务11 · 公司浏览（公司页）接口测试

覆盖 `/api/companies/stats`、`/api/companies`（分页/筛选/排序）、`/api/companies/{id}` 的正常/边界/异常。

数据来源：`data/processed/zhaopin_jobs_cleaned_seg.csv`
          —— 8,836 个岗位按「公司名称」去重得到 **4,096 家公司**（无空值）。

口径说明（与页面提示、文档一致）：
· 数据里**没有**「行业 / 规模 / 融资阶段」列，接口**不返回**这三个字段；
· 「规模分档」用该公司的**在招职位数**代理（1 / 2-4 / 5-9 / 10-49 / 50 以上）。
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


# ================================================================ 公司统计
class TestCompanyStats:
    def test_normal(self):
        r = client.get("/api/companies/stats")
        assert r.status_code == 200
        j = r.json()
        o = j["总体"]
        assert o["公司总数"] == 4096
        assert o["在招岗位总数"] == 8836          # 与岗位页同一批数据
        assert o["平均每司岗位数"] == 2.16
        assert o["城市数"] == 16
        assert o["只招1个岗位的公司数"] == 2481
        assert o["在招10个以上的公司数"] == 88
        assert o["岗位数最多公司"] == "软通动力信息技术(集团)股份有限公司"
        assert o["岗位数最多公司岗位数"] == 86
        assert j["来源"]

    def test_size_buckets_sum_to_total(self):
        """口径校验：规模分档必须能不重不漏地覆盖全部公司"""
        j = client.get("/api/companies/stats").json()
        assert [x["名称"] for x in j["规模分档"]] == ["1个", "2-4个", "5-9个", "10-49个", "50个以上"]
        assert sum(x["数量"] for x in j["规模分档"]) == 4096
        assert [x["数量"] for x in j["规模分档"]] == [2481, 1255, 272, 86, 2]

    def test_no_fabricated_fields(self):
        """诚实性校验：接口不得输出数据里不存在的行业/规模/融资字段"""
        j = client.get("/api/companies/stats").json()
        c = j["热门企业"][0]
        for k in ("行业", "规模", "融资阶段", "公司规模", "员工人数"):
            assert k not in c, "数据里没有「%s」列，不应凭空出现" % k
        assert c["规模分档"] and "在招职位数" in j["规模分档"][0]["说明"]

    def test_caliber_notes_present(self):
        """口径说明必须随接口返回（页面要如实展示）"""
        j = client.get("/api/companies/stats").json()
        assert len(j["口径说明"]) >= 4
        assert any("代理" in s for s in j["口径说明"])
        assert any("行业/规模/融资" in s for s in j["口径说明"])

    def test_hot_and_active_lists(self):
        j = client.get("/api/companies/stats").json()
        assert len(j["热门企业"]) == 20
        assert len(j["最活跃企业"]) == 10
        jobs = [x["在招岗位数"] for x in j["热门企业"]]
        assert jobs == sorted(jobs, reverse=True)
        reply = [x["今日回复总数"] for x in j["最活跃企业"]]
        assert reply == sorted(reply, reverse=True)

    def test_city_category_counts_may_overlap(self):
        """口径校验：「按城市/按大类」是「有在招职位的公司数」，同一公司可计入多处，故合计大于总数"""
        j = client.get("/api/companies/stats").json()
        assert len(j["按城市"]) == 16
        assert len(j["按大类"]) == 9
        assert sum(x["数量"] for x in j["按城市"]) > 4096
        assert any("大于公司总数" in s for s in j["口径说明"])

    def test_consistent_with_job_stats(self):
        """跨接口一致性：公司页与岗位页的「公司数」必须是同一个数"""
        assert (client.get("/api/companies/stats").json()["总体"]["公司总数"]
                == client.get("/api/jobs/stats").json()["总体"]["公司数"] == 4096)


# ================================================================ 公司列表与分页
class TestCompanyList:
    def test_normal_first_page(self):
        r = client.get("/api/companies", params={"page": 1, "size": 20})
        assert r.status_code == 200
        j = r.json()
        assert j["总数"] == 4096
        assert j["总页数"] == 205
        assert len(j["公司"]) == 20
        assert j["公司"][0]["公司名称"] == "软通动力信息技术(集团)股份有限公司"
        assert j["公司"][0]["在招岗位数"] == 86
        for k in ("公司ID", "公司名称", "在招岗位数", "规模分档", "主要城市", "主要大类",
                  "薪资下限中位数", "薪资上限中位数", "招聘者数", "热招职位", "城市列表"):
            assert k in j["公司"][0], k

    def test_card_has_no_internal_rows(self):
        """实现细节：卡片不能把该公司全部岗位（内部 _rows）带出来，否则列表接口过大"""
        j = client.get("/api/companies", params={"size": 100}).json()
        for c in j["公司"]:
            assert "_rows" not in c and "在招岗位" not in c

    def test_boundary_last_page(self):
        j = client.get("/api/companies", params={"page": 205, "size": 20}).json()
        assert len(j["公司"]) == 4096 - 204 * 20 == 16

    @pytest.mark.parametrize("size", [1, 50, 100])
    def test_boundary_page_size(self, size):
        r = client.get("/api/companies", params={"size": size})
        assert r.status_code == 200 and len(r.json()["公司"]) == size

    def test_boundary_size_capped(self):
        j = client.get("/api/companies", params={"size": 500}).json()
        assert j["每页"] == 100

    def test_boundary_page_beyond_end(self):
        j = client.get("/api/companies", params={"page": 99999}).json()
        assert j["公司"] == []

    def test_abnormal_bad_param_type(self):
        assert client.get("/api/companies", params={"page": "abc"}).status_code == 422


# ================================================================ 筛选与排序
class TestCompanyFilter:
    def test_filter_city(self):
        j = client.get("/api/companies", params={"city": "厦门", "size": 5}).json()
        assert j["总数"] == 498
        for c in j["公司"]:
            assert any(x["名称"] == "厦门" for x in c["城市列表"])

    def test_filter_category(self):
        j = client.get("/api/companies", params={"category": "测试", "size": 5}).json()
        assert j["总数"] == 921
        for c in j["公司"]:
            assert any(x["名称"] == "测试" for x in c["岗位大类"])

    def test_filters_combined(self):
        j = client.get("/api/companies", params={"city": "厦门", "category": "测试", "size": 5}).json()
        assert j["总数"] == 135

    def test_filter_bucket(self):
        """正常：规模分档筛选与统计里的一致（50 个以上只有 2 家）"""
        j = client.get("/api/companies", params={"bucket": "50个以上"}).json()
        assert j["总数"] == 2
        assert all(c["规模分档"] == "50个以上" for c in j["公司"])
        assert j["公司"][0]["在招岗位数"] == 86

    def test_filter_keyword(self):
        j = client.get("/api/companies", params={"keyword": "软通", "size": 5}).json()
        assert j["总数"] >= 1
        assert all("软通" in c["公司名称"] for c in j["公司"])

    def test_filter_no_match(self):
        assert client.get("/api/companies", params={"city": "北京"}).json()["总数"] == 0

    def test_sort_jobs_desc(self):
        j = client.get("/api/companies", params={"sort": "jobs_desc", "size": 10}).json()
        assert [c["在招岗位数"] for c in j["公司"]] == sorted(
            [c["在招岗位数"] for c in j["公司"]], reverse=True)

    def test_sort_salary_desc(self):
        j = client.get("/api/companies", params={"sort": "salary_desc", "size": 10}).json()
        med = [c["薪资上限中位数"] for c in j["公司"]]
        assert med == sorted(med, reverse=True)
        assert med[0] > 0

    def test_sort_reply_desc(self):
        j = client.get("/api/companies", params={"sort": "reply_desc", "size": 10}).json()
        rep = [c["今日回复总数"] for c in j["公司"]]
        assert rep == sorted(rep, reverse=True)
        assert rep[0] > 0

    def test_sort_name(self):
        j = client.get("/api/companies", params={"sort": "name", "size": 10}).json()
        names = [c["公司名称"] for c in j["公司"]]
        assert names == sorted(names)

    def test_sort_unknown_falls_back(self):
        j = client.get("/api/companies", params={"sort": "not-a-sort"}).json()
        assert j["总数"] == 4096
        assert j["公司"][0]["在招岗位数"] == 86          # 回落到「在招职位最多」

    def test_filter_unknown_bucket(self):
        """边界：不存在的分档 → 空结果而不是报错"""
        j = client.get("/api/companies", params={"bucket": "999个"}).json()
        assert j["总数"] == 0 and j["公司"] == []


# ================================================================ 公司详情
class TestCompanyDetail:
    JOB_ID = "C1875D776"          # 软通动力信息技术(集团)股份有限公司（在招 86 个）

    def test_normal_by_id(self):
        r = client.get("/api/companies/%s" % self.JOB_ID)
        assert r.status_code == 200
        j = r.json()
        assert j["公司名称"] == "软通动力信息技术(集团)股份有限公司"
        assert j["在招岗位数"] == 86
        assert len(j["在招岗位"]) == 86                 # 详情要给出**全部**在招岗位
        assert all(x["公司"] == j["公司名称"] for x in j["在招岗位"])
        assert j["技能需求"] and j["岗位大类"] and j["招聘者"]
        for k in ("岗位ID", "岗位名称", "薪资", "城市", "区县"):
            assert k in j["在招岗位"][0], k

    def test_normal_by_name(self):
        """兼容用公司名直接查（URL 建议用 ID，避免中文编码坑）"""
        r = client.get("/api/companies/三一集团有限公司")
        assert r.status_code == 200
        assert r.json()["在招岗位数"] == 72

    def test_job_ids_are_reachable(self):
        """重要：详情页列出的岗位必须真的能点进岗位详情（岗位ID 可查）"""
        j = client.get("/api/companies/%s" % self.JOB_ID).json()
        ids = [x["岗位ID"] for x in j["在招岗位"][:5]]
        assert ids
        for jid in ids:
            assert client.get("/api/jobs/%s" % jid).status_code == 200

    def test_similar_companies(self):
        j = client.get("/api/companies/%s" % self.JOB_ID).json()
        assert 0 < len(j["相似公司"]) <= 6
        for c in j["相似公司"]:
            assert c["公司ID"] != self.JOB_ID
            assert c["主要城市"] == j["主要城市"] and c["主要大类"] == j["主要大类"]

    def test_normal_single_job_company(self):
        """边界：只招 1 个岗位的公司（占 60.6%）也要能打开详情"""
        cid = client.get("/api/companies", params={"bucket": "1个", "size": 1}).json()["公司"][0]["公司ID"]
        j = client.get("/api/companies/%s" % cid).json()
        assert j["在招岗位数"] == 1 and len(j["在招岗位"]) == 1

    def test_abnormal_not_exists(self):
        r = client.get("/api/companies/C00000000")
        assert r.status_code == 400
        assert "不存在" in r.json()["error"]

    def test_abnormal_empty_name(self):
        assert client.get("/api/companies/%20").status_code == 400


# ================================================================ 跨接口总量对账
class TestCompanyJobConsistency:
    def test_company_job_counts_sum_to_total(self):
        """对账：所有公司的「在招岗位数」之和 == 岗位总数 8,836"""
        total = 0
        for page in range(1, 42):                  # 4,096 / 100 = 41 页取完
            for c in client.get("/api/companies", params={"page": page, "size": 100}).json()["公司"]:
                total += c["在招岗位数"]
        assert total == 8836

    def test_same_company_count_as_jobs(self):
        """对账：某公司的「在招岗位数」应与岗位接口按公司名检索的条数一致"""
        j = client.get("/api/companies", params={"keyword": "三一集团", "size": 1}).json()["公司"][0]
        cid = j["公司ID"]
        detail = client.get("/api/companies/%s" % cid).json()
        cnt = 0
        for page in range(1, 5):
            cnt += len([x for x in client.get("/api/jobs",
                                              params={"keyword": j["公司名称"], "page": page,
                                                      "size": 100}).json()["岗位"]
                        if x["公司"] == j["公司名称"]])
        assert cnt == len(detail["在招岗位"]) == j["在招岗位数"]
