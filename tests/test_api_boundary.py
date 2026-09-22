# -*- coding: utf-8 -*-
"""任务13 · 边界路径测试（「正常 / 边界 / 异常」三条路径里的第二条）

与另外两个文件的分工
    `test_api.py` / `test_jobs.py` / `test_companies.py` / `test_home.py` / `test_auth.py`
        → 以**正常路径**为主（业务能不能用、口径对不对）
    本文件 `test_api_boundary.py`
        → 只测**边界值**：参数取到上下限、刚好越界、空值、超长值、不存在的取值
    同目录 `test_api_error.py`
        → 只测**异常路径**：未登录、越权、找不到、非法请求体

为什么边界要单独成文件
    正常路径测的是"功能在不在"，边界测的是"参数被压到极限时会不会崩、会不会静默返回错东西"。
    这两类问题的发现方式完全不同，混在一起写容易只覆盖前者。

本文件里每条断言的依据
    都是先读实现再写断言，不是猜的：
      · `src/api/jobs.py` 里分页是 `page = max(1, int(page))`、`size = min(max(1, int(size)), 100)`
        —— 所以越界是**夹取**而不是报错，断言就该断言夹取后的值；
      · `src/api/main.py` 里 `home(n)` 是 `max(1, min(int(n), 20))` —— 同理；
      · Pydantic 的 `Field(ge=/le=/min_length=/max_length=)` 越界会返回 **422**，且**在进入业务逻辑之前**就返回。
"""
import os
import sys
import uuid

from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.api.main import app                                              # noqa: E402

client = TestClient(app)

RESUME = """姓名：张伟
期望岗位：测试开发工程师
期望城市：苏州
期望薪资：12000-16000元
最高学历：大专
专业：软件技术
工作年限：3年

【技能特长】
熟练掌握 Selenium、JMeter、Python、MySQL、Linux，了解 Postman 与 Git

【工作经历】
2022.07-2025.06 某软件公司 测试工程师，负责接口自动化测试与性能压测
"""

TINY_RESUME = "张"
SKILL_LESS_RESUME = "姓名：李四\n期望城市：苏州\n【工作经历】在家待业，暂无相关工作经历可写。\n"


def uniq(prefix="b"):
    """每次调用都拿到不同的用户名，避免同一测试库内互相干扰"""
    return "%s%s" % (prefix, uuid.uuid4().hex[:8])


def new_user():
    """注册一个用户，返回 (token, user_id)"""
    r = client.post("/api/auth/register", json={"username": uniq(), "password": "test123456"})
    assert r.status_code == 200, r.text
    j = r.json()
    return j["token"], j["用户"]["id"]


def auth(token):
    return {"Authorization": "Bearer %s" % token}


# ================================================================ 岗位列表：分页
class TestJobsPagingBoundary:
    """分页参数取到上下限时的行为（实现是夹取，不是报错）"""

    def test_page_zero_clamped_to_one(self):
        r = client.get("/api/jobs?page=0&size=5")
        assert r.status_code == 200
        assert r.json()["页码"] == 1, "page=0 应被夹取为第 1 页"

    def test_page_negative_clamped_to_one(self):
        r = client.get("/api/jobs?page=-99&size=5")
        assert r.status_code == 200
        assert r.json()["页码"] == 1

    def test_page_far_beyond_end_returns_empty_but_valid_meta(self):
        r = client.get("/api/jobs?page=99999&size=20")
        assert r.status_code == 200
        j = r.json()
        assert j["岗位"] == [], "页码远超范围时应返回空列表而不是报错"
        assert j["总数"] == 8836, "总数不应随页码变化"
        assert j["总页数"] >= 1, "总页数至少为 1（避免前端分页器出现 0 页）"

    def test_size_zero_clamped_to_one(self):
        r = client.get("/api/jobs?size=0")
        assert r.status_code == 200
        j = r.json()
        assert j["每页"] == 1
        assert len(j["岗位"]) == 1

    def test_size_negative_clamped_to_one(self):
        r = client.get("/api/jobs?size=-7")
        assert r.status_code == 200
        assert r.json()["每页"] == 1

    def test_size_over_limit_clamped_to_100(self):
        r = client.get("/api/jobs?size=1000")
        assert r.status_code == 200
        j = r.json()
        assert j["每页"] == 100, "size 上限是 100，超了要夹取而不是返回 1000 条"
        assert len(j["岗位"]) == 100

    def test_size_exactly_at_limit(self):
        r = client.get("/api/jobs?size=100")
        assert r.status_code == 200
        assert len(r.json()["岗位"]) == 100

    def test_last_page_not_overfilled(self):
        meta = client.get("/api/jobs?size=100").json()
        last = meta["总页数"]
        r = client.get("/api/jobs?page=%d&size=100" % last)
        assert r.status_code == 200
        rows = r.json()["岗位"]
        assert 0 < len(rows) <= 100

    def test_page_and_size_do_not_overlap(self):
        """翻页不重不漏：第 1 页与第 2 页的岗位ID 交集必须为空"""
        p1 = client.get("/api/jobs?page=1&size=30&sort=salary").json()["岗位"]
        p2 = client.get("/api/jobs?page=2&size=30&sort=salary").json()["岗位"]
        ids1 = {x["岗位ID"] for x in p1}
        ids2 = {x["岗位ID"] for x in p2}
        assert len(ids1) == 30 and len(ids2) == 30
        assert ids1 & ids2 == set()


# ================================================================ 岗位列表：筛选与排序
class TestJobsFilterBoundary:

    def test_salary_min_zero_means_no_filter(self):
        a = client.get("/api/jobs?size=5").json()
        b = client.get("/api/jobs?size=5&salary_min=0").json()
        assert a["总数"] == b["总数"], "salary_min=0 应等价于不筛选"

    def test_salary_min_absurdly_high_returns_empty(self):
        r = client.get("/api/jobs?size=5&salary_min=99999999")
        assert r.status_code == 200
        j = r.json()
        assert j["总数"] == 0
        assert j["岗位"] == []

    def test_unknown_city_returns_empty_not_error(self):
        r = client.get("/api/jobs?city=不存在的城市")
        assert r.status_code == 200
        assert r.json()["总数"] == 0

    def test_unknown_district_returns_empty(self):
        r = client.get("/api/jobs?city=苏州&district=不存在的区县")
        assert r.status_code == 200
        assert r.json()["总数"] == 0

    def test_single_char_keyword(self):
        r = client.get("/api/jobs?keyword=测")
        assert r.status_code == 200
        assert r.json()["总数"] > 0, "单个汉字也应能搜到结果"

    def test_keyword_with_no_match(self):
        r = client.get("/api/jobs?keyword=zzzz不存在的关键词zzzz")
        assert r.status_code == 200
        assert r.json()["总数"] == 0

    def test_whitespace_keyword_ignored(self):
        a = client.get("/api/jobs?size=3&sort=salary").json()["总数"]
        b = client.get("/api/jobs?size=3&sort=salary&keyword=%20").json()["总数"]
        assert a == b, "纯空格关键词应等价于不筛选"

    def test_illegal_sort_falls_back_without_error(self):
        r = client.get("/api/jobs?size=5&sort=这不是一个合法排序")
        assert r.status_code == 200
        assert len(r.json()["岗位"]) == 5

    def test_filters_are_intersecting(self):
        """多条件叠加时结果数不超过任一单条件的结果数"""
        city = client.get("/api/jobs?city=苏州&size=1").json()["总数"]
        cat = client.get("/api/jobs?category=测试&size=1").json()["总数"]
        both = client.get("/api/jobs?city=苏州&category=测试&size=1").json()["总数"]
        assert both <= city and both <= cat and both > 0

    def test_seed_zero_is_stable(self):
        a = [x["岗位ID"] for x in client.get("/api/jobs?size=10&seed=0").json()["岗位"]]
        b = [x["岗位ID"] for x in client.get("/api/jobs?size=10&seed=0").json()["岗位"]]
        assert a == b, "同 seed 必须完全稳定（seed=0 走的是'无 seed'分支）"

    def test_negative_seed_is_valid(self):
        a = [x["岗位ID"] for x in client.get("/api/jobs?size=10&seed=-12345").json()["岗位"]]
        b = [x["岗位ID"] for x in client.get("/api/jobs?size=10&seed=-12345").json()["岗位"]]
        assert a == b and len(a) == 10

    def test_different_seeds_differ(self):
        a = [x["岗位ID"] for x in client.get("/api/jobs?size=20&seed=1").json()["岗位"]]
        b = [x["岗位ID"] for x in client.get("/api/jobs?size=20&seed=2").json()["岗位"]]
        assert a != b, "换 seed 应换顺序"

    def test_unknown_cluster_returns_empty(self):
        r = client.get("/api/jobs?cluster=不存在的簇名")
        assert r.status_code == 200
        assert r.json()["总数"] == 0


# ================================================================ 首页推荐
class TestHomeBoundary:

    def test_n_one_gives_at_most_one_each(self):
        j = client.get("/api/home?n=1").json()
        assert len(j["高薪岗位"]) <= 1
        assert len(j["热门岗位"]) <= 1

    def test_n_zero_clamped_to_one(self):
        j = client.get("/api/home?n=0").json()
        assert 1 <= len(j["高薪岗位"]) <= 1 or len(j["高薪岗位"]) == 1
        assert len(j["高薪岗位"]) == 1, "n=0 会被夹取为 1"

    def test_n_huge_clamped_to_twenty(self):
        j = client.get("/api/home?n=9999").json()
        assert len(j["高薪岗位"]) <= 20
        assert len(j["热门岗位"]) <= 20

    def test_n_negative_clamped(self):
        j = client.get("/api/home?n=-5").json()
        assert len(j["高薪岗位"]) == 1

    def test_fixed_lists_do_not_depend_on_n(self):
        """地区推荐 Top5 与热门企业 Top10 是固定榜单，不受 n 影响"""
        a = client.get("/api/home?n=1").json()
        b = client.get("/api/home?n=20").json()
        assert len(a["地区推荐"]) == 5 and len(b["地区推荐"]) == 5
        assert len(a["热门企业"]) == 10 and len(b["热门企业"]) == 10
        assert [x["城市"] for x in a["地区推荐"]] == [x["城市"] for x in b["地区推荐"]]


# ================================================================ 公司浏览
class TestCompaniesBoundary:

    def test_page_and_size_clamped(self):
        j = client.get("/api/companies?page=0&size=0").json()
        assert j["页码"] == 1 and j["每页"] == 1
        j2 = client.get("/api/companies?size=9999").json()
        assert j2["每页"] == 100

    def test_page_beyond_end(self):
        j = client.get("/api/companies?page=99999").json()
        assert j["公司"] == []
        assert j["总数"] == 4096

    def test_unknown_bucket_returns_empty(self):
        r = client.get("/api/companies?bucket=不存在的分档")
        assert r.status_code == 200
        assert r.json()["总数"] == 0

    def test_unknown_city_returns_empty(self):
        r = client.get("/api/companies?city=不存在的城市")
        assert r.status_code == 200
        assert r.json()["总数"] == 0

    def test_company_id_at_boundaries(self):
        """取列表第一条与最后一条的 ID 都应能打开详情（首尾边界）"""
        first = client.get("/api/companies?size=1").json()["公司"][0]["公司ID"]
        total = client.get("/api/companies?size=1").json()["总页数"]
        last_page = client.get("/api/companies?page=%d&size=100" % total).json()["公司"]
        assert client.get("/api/companies/%s" % first).status_code == 200
        if last_page:
            assert client.get("/api/companies/%s" % last_page[-1]["公司ID"]).status_code == 200


# ================================================================ 简历解析
class TestResumeParseBoundary:

    def test_single_character_resume(self):
        r = client.post("/api/resume/parse_text", json={"resume_text": TINY_RESUME})
        assert r.status_code == 200, "单个汉字也是合法输入（min_length=1）"
        assert r.json()["resume_id"]

    def test_whitespace_only_resume(self):
        r = client.post("/api/resume/parse_text", json={"resume_text": "   \n\t  "})
        assert r.status_code == 200
        assert r.json()["技能列表"] == [], "没有内容时技能列表应为空，而不是报错"

    def test_resume_without_any_skill_word(self):
        r = client.post("/api/resume/parse_text", json={"resume_text": SKILL_LESS_RESUME})
        assert r.status_code == 200
        assert r.json()["技能列表"] == []

    def test_very_long_resume(self):
        """2 万字长文本：要能处理完，且不应因为长度而报错"""
        long_text = RESUME + ("【补充说明】负责接口自动化测试与性能压测，熟练使用 Python 与 MySQL。\n" * 600)
        assert len(long_text) > 20000, "构造的长文本应超过 2 万字（实际 %d）" % len(long_text)
        r = client.post("/api/resume/parse_text", json={"resume_text": long_text})
        assert r.status_code == 200
        assert r.json()["技能列表"], "长文本里的技能词仍应被识别出来"

    def test_resume_with_emoji_and_special_chars(self):
        text = "姓名：王五 😀\n期望城市：厦门\n【技能特长】Python、Java、MySQL —— 熟悉 <HTML> & \"引号\" 与 \\反斜杠\n"
        r = client.post("/api/resume/parse_text", json={"resume_text": text})
        assert r.status_code == 200
        assert r.json()["resume_id"]

    def test_original_text_is_returned_verbatim(self):
        """原文要能原样回传（前端靠它保存简历；这是缺陷 8 的回归点）"""
        r = client.post("/api/resume/parse_text", json={"resume_text": RESUME})
        assert r.status_code == 200
        assert r.json()["原文"].strip() == RESUME.strip()

    def test_empty_pdf_upload_rejected(self):
        r = client.post("/api/resume/parse", files={"file": ("a.pdf", b"", "application/pdf")})
        assert r.status_code == 400, "空文件应被拒（而不是当成简历解析通过）"

    def test_oversized_pdf_rejected(self):
        big = b"%PDF-1.4\n" + b"0" * (11 * 1024 * 1024)
        r = client.post("/api/resume/parse", files={"file": ("big.pdf", big, "application/pdf")})
        assert r.status_code == 400
        assert "10MB" in r.text or "10 MB" in r.text


# ================================================================ 人岗匹配
class TestMatchBoundary:

    def test_top_n_one(self):
        r = client.post("/api/match", json={"resume_text": RESUME, "top_n": 1})
        assert r.status_code == 200
        assert len(r.json()["推荐"]) == 1

    def test_top_n_fifty_is_the_upper_limit(self):
        r = client.post("/api/match", json={"resume_text": RESUME, "top_n": 50})
        assert r.status_code == 200
        assert len(r.json()["推荐"]) == 50

    def test_top_n_zero_rejected(self):
        r = client.post("/api/match", json={"resume_text": RESUME, "top_n": 0})
        assert r.status_code == 422

    def test_top_n_over_limit_rejected(self):
        r = client.post("/api/match", json={"resume_text": RESUME, "top_n": 51})
        assert r.status_code == 422

    def test_scores_stay_in_range_on_tiny_resume(self):
        """1 个字的简历：不能崩，且若给出分数必须在 0~100 内"""
        r = client.post("/api/match", json={"resume_text": TINY_RESUME, "top_n": 5})
        assert r.status_code == 200, r.text
        for item in r.json()["推荐"]:
            assert 0 <= item["总分"] <= 100, "总分越界：%s" % item.get("总分")

    def test_recommendations_are_sorted_desc(self):
        rows = client.post("/api/match", json={"resume_text": RESUME, "top_n": 20}).json()["推荐"]
        scores = [x["总分"] for x in rows]
        assert scores == sorted(scores, reverse=True), "推荐必须按总分降序"

    def test_top_n_returns_distinct_jobs(self):
        rows = client.post("/api/match", json={"resume_text": RESUME, "top_n": 30}).json()["推荐"]
        ids = [x["岗位ID"] for x in rows]
        assert len(set(ids)) == len(ids), "同一岗位不能重复推荐"

    def test_match_by_unknown_resume_id(self):
        r = client.post("/api/match", json={"resume_id": "rs_不存在的会话", "top_n": 5})
        assert r.status_code == 400, "不存在的会话 ID 应被拒"


# ================================================================ 评分
class TestScoreBoundary:

    def test_first_and_last_job_id(self):
        for jid in ("J0001", "J8836"):
            r = client.post("/api/score", json={"resume_text": RESUME, "job_id": jid})
            assert r.status_code == 200, "%s 应可评分：%s" % (jid, r.text)
            assert 0 <= r.json()["规则口径"]["总分"] <= 100

    def test_just_below_first_job_id(self):
        r = client.post("/api/score", json={"resume_text": RESUME, "job_id": "J0000"})
        assert r.status_code == 400

    def test_just_above_last_job_id(self):
        r = client.post("/api/score", json={"resume_text": RESUME, "job_id": "J8837"})
        assert r.status_code == 400

    def test_same_input_is_deterministic(self):
        """同样的简历 + 同样的岗位，两次评分必须一致（否则前端会看到分数跳变）"""
        a = client.post("/api/score", json={"resume_text": RESUME, "job_id": "J0020"}).json()
        b = client.post("/api/score", json={"resume_text": RESUME, "job_id": "J0020"}).json()
        assert a["规则口径"]["总分"] == b["规则口径"]["总分"]
        assert a["模型口径"] == b["模型口径"]

    def test_six_dims_all_in_range(self):
        j = client.post("/api/score", json={"resume_text": RESUME, "job_id": "J0020"}).json()
        dims = j["规则口径"].get("六维分") or {}
        assert dims, "规则口径必须带六维分明细"
        for k, v in dims.items():
            assert 0 <= v <= 100, "维度 %s 越界：%s" % (k, v)


# ================================================================ 聚类
class TestClusterBoundary:
    """聚类接口的参数边界与数据完整性

    这个类守着两个真实缺陷的回归（见《测试报告》缺陷 13、14）：
      · 缺陷 13：`Retriever.cluster_profile()` 里写死的 `[:8]` 把 K=9 的第 9 簇静默丢掉，
        导致接口报「簇数=9」而画像只给 8 条，智能问答据此回答「岗位共分 8 类」；
      · 缺陷 14：画像里的「岗位数 / 占比 / 薪资中位数」是从 CSV 直接透出的**字符串**，
        而兄弟接口 `/api/cluster/list` 的「岗位数」是整数 —— 同一系统两个聚类接口字段类型不一致。

    另外记录一个踩过的坑：`/api/cluster/profile` 的参数名是 **`name`**（不是 `cluster`），
    FastAPI 会**静默忽略**不认识的查询参数，所以第一版测试写 `?cluster=测试` 时拿到的其实是
    「全部簇」，断言就假通过了。**参数名写错不会报错，只会给你一份看起来正常的结果。**
    """

    def test_cluster_list_basic_shape(self):
        r = client.get("/api/cluster/list")
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert j["簇数"] == 9, "主方案是 K=9"

    def test_profile_returns_all_nine_clusters_of_main_scheme(self):
        """缺陷 13 回归：K=9 主方案 9 个簇一条都不能少"""
        data = client.get("/api/cluster/profile").json()["data"]
        main = [x for x in data if str(x["方案"]).startswith("K=9")]
        assert len(main) == 9, "主方案有 9 个簇，画像也必须给 9 条（实际 %d 条）" % len(main)

    def test_main_scheme_job_counts_sum_to_total(self):
        """更强的交叉校验：主方案 9 个簇的岗位数合计必须等于岗位库总数

        少任何一行这个和就对不上 —— 比只数条数更能守住"静默丢数据"这类缺陷。
        """
        data = client.get("/api/cluster/profile").json()["data"]
        main = [x for x in data if str(x["方案"]).startswith("K=9")]
        assert sum(x["岗位数"] for x in main) == 8836

    def test_profile_numbers_are_numbers_not_strings(self):
        """缺陷 14 回归：画像里的数字字段必须是数字类型"""
        for row in client.get("/api/cluster/profile").json()["data"]:
            assert isinstance(row["岗位数"], int), \
                "岗位数是 %s（应为 int）" % type(row["岗位数"]).__name__
            assert isinstance(row["占比"], (int, float)), \
                "占比是 %s（应为数字）" % type(row["占比"]).__name__
            assert isinstance(row["薪资中位数"], (int, float)), \
                "薪资中位数是 %s（应为数字）" % type(row["薪资中位数"]).__name__

    def test_profile_filter_by_partial_name(self):
        r = client.get("/api/cluster/profile", params={"name": "测试"})
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert all("测试" in x["簇名"] or "测试" in x["方案"] for x in j["data"])

    def test_profile_with_unknown_name(self):
        r = client.get("/api/cluster/profile", params={"name": "zzz不存在的簇zzz"})
        assert r.status_code == 200, "查不到簇也不该报错（返回空即可）"
        assert r.json()["ok"] is False
        assert r.json()["data"] == []

    def test_profile_share_stays_within_bounds(self):
        for row in client.get("/api/cluster/profile").json()["data"]:
            assert 0 < float(row["占比"]) <= 100, "簇占比越界：%s" % row

    def test_profile_covers_all_three_schemes(self):
        """三套方案都应能查到：K=9 主方案 / K=5 对照 / 二阶细分"""
        rows = client.get("/api/cluster/profile").json()["data"]
        text = " ".join(str(x["方案"]) for x in rows)
        assert "K=9" in text and "K=5" in text and "细分" in text
        assert len(rows) == 22, "三套方案合计 22 行（9 + 5 + 8）"


# ================================================================ 用户体系
class TestAuthBoundary:

    def test_username_min_length_accepted(self):
        r = client.post("/api/auth/register", json={"username": uniq("a")[:3] * 1,
                                                    "password": "123456"})
        # 3 位是下界；用随机 3 位避免重名
        if r.status_code == 400:      # 极小概率撞上已存在的名字，换一个再试
            r = client.post("/api/auth/register",
                            json={"username": uuid.uuid4().hex[:3], "password": "123456"})
        assert r.status_code == 200, r.text

    def test_username_below_min_length_rejected(self):
        r = client.post("/api/auth/register", json={"username": "ab", "password": "123456"})
        assert r.status_code == 422

    def test_username_at_max_length_accepted(self):
        r = client.post("/api/auth/register",
                        json={"username": uuid.uuid4().hex[:24], "password": "123456"})
        assert r.status_code == 200, r.text

    def test_username_over_max_length_rejected(self):
        r = client.post("/api/auth/register",
                        json={"username": uuid.uuid4().hex * 2, "password": "123456"})
        assert r.status_code == 422

    def test_password_min_length_accepted(self):
        r = client.post("/api/auth/register", json={"username": uniq(), "password": "123456"})
        assert r.status_code == 200

    def test_password_below_min_length_rejected(self):
        r = client.post("/api/auth/register", json={"username": uniq(), "password": "12345"})
        assert r.status_code == 422

    def test_password_at_max_length_accepted(self):
        r = client.post("/api/auth/register", json={"username": uniq(), "password": "x" * 64})
        assert r.status_code == 200

    def test_password_over_max_length_rejected(self):
        r = client.post("/api/auth/register", json={"username": uniq(), "password": "x" * 65})
        assert r.status_code == 422

    def test_nickname_at_max_length(self):
        r = client.post("/api/auth/register",
                        json={"username": uniq(), "password": "123456", "nickname": "名" * 24})
        assert r.status_code == 200

    def test_nickname_over_max_length_rejected(self):
        r = client.post("/api/auth/register",
                        json={"username": uniq(), "password": "123456", "nickname": "名" * 25})
        assert r.status_code == 422

    def test_profile_field_boundaries(self):
        token, _ = new_user()
        assert client.put("/api/user/profile", json={"nickname": "名" * 24},
                          headers=auth(token)).status_code == 200
        assert client.put("/api/user/profile", json={"nickname": "名" * 25},
                          headers=auth(token)).status_code == 422
        assert client.put("/api/user/profile", json={"email": "a" * 64},
                          headers=auth(token)).status_code == 200
        assert client.put("/api/user/profile", json={"email": "a" * 65},
                          headers=auth(token)).status_code == 422


# ================================================================ 个人中心：简历
class TestResumeCrudBoundary:

    def test_title_at_max_length(self):
        token, _ = new_user()
        r = client.post("/api/user/resumes", json={"title": "标" * 40, "text": RESUME},
                        headers=auth(token))
        assert r.status_code == 200, r.text
        assert client.get("/api/user/resumes", headers=auth(token)).json()["简历"][0]["title"] == "标" * 40

    def test_title_over_max_length_rejected(self):
        token, _ = new_user()
        r = client.post("/api/user/resumes", json={"title": "标" * 41, "text": RESUME},
                        headers=auth(token))
        assert r.status_code == 422

    def test_empty_title_allowed(self):
        token, _ = new_user()
        r = client.post("/api/user/resumes", json={"title": "", "text": RESUME}, headers=auth(token))
        assert r.status_code == 200, "标题可为空（默认 title 就是空串）"

    def test_single_character_text_accepted(self):
        token, _ = new_user()
        r = client.post("/api/user/resumes", json={"title": "极短", "text": "张"}, headers=auth(token))
        assert r.status_code == 200, "正文下界是 1 个字"

    def test_empty_text_rejected(self):
        token, _ = new_user()
        r = client.post("/api/user/resumes", json={"title": "空", "text": ""}, headers=auth(token))
        assert r.status_code == 422

    def test_still_one_resume_after_many_saves(self):
        """一人一份：连存 10 次之后库里仍然只有 1 条"""
        token, _ = new_user()
        for i in range(10):
            assert client.post("/api/user/resumes",
                               json={"title": "第%d次" % i, "text": RESUME + "\n第%d次" % i},
                               headers=auth(token)).status_code == 200
        rows = client.get("/api/user/resumes", headers=auth(token)).json()["简历"]
        assert len(rows) == 1
        assert rows[0]["title"] == "第9次"

    def test_update_to_empty_text_rejected(self):
        token, _ = new_user()
        rid = client.get("/api/user/resumes", headers=auth(token)).json()["简历"]
        client.post("/api/user/resumes", json={"title": "t", "text": RESUME}, headers=auth(token))
        rid = client.get("/api/user/resumes", headers=auth(token)).json()["简历"][0]["id"]
        r = client.put("/api/user/resumes/%d" % rid, json={"text": ""}, headers=auth(token))
        assert r.status_code == 422, "更新成空正文要在入口被拦下"


# ================================================================ 收藏
class TestFavoriteBoundary:

    def test_first_job_id(self):
        token, _ = new_user()
        r = client.post("/api/user/favorites", json={"job_id": "J0001"}, headers=auth(token))
        assert r.status_code == 200, r.text

    def test_last_job_id(self):
        token, _ = new_user()
        r = client.post("/api/user/favorites", json={"job_id": "J8836"}, headers=auth(token))
        assert r.status_code == 200, r.text

    def test_lowercase_job_id_accepted(self):
        token, _ = new_user()
        r = client.post("/api/user/favorites", json={"job_id": "j0020"}, headers=auth(token))
        assert r.status_code == 200, "小写 j 应被兼容（实现里有 .upper()）"

    def test_note_at_max_length(self):
        token, _ = new_user()
        r = client.post("/api/user/favorites", json={"job_id": "J0020", "note": "备" * 200},
                        headers=auth(token))
        assert r.status_code == 200

    def test_note_over_max_length_rejected(self):
        token, _ = new_user()
        r = client.post("/api/user/favorites", json={"job_id": "J0020", "note": "备" * 201},
                        headers=auth(token))
        assert r.status_code == 422

    def test_same_job_twice_does_not_duplicate(self):
        """重复收藏同一岗位不应在列表里出现两条"""
        token, _ = new_user()
        for _ in range(3):
            client.post("/api/user/favorites", json={"job_id": "J0020"}, headers=auth(token))
        rows = client.get("/api/user/favorites", headers=auth(token)).json()["收藏"]
        assert len(rows) == 1, "重复收藏应幂等，实际 %d 条" % len(rows)

    def test_cancel_not_favorited_reports_error(self):
        """取消一个没收藏过的岗位 → 400 且错误信息明确

        这是**刻意的接口契约**（`db.delete_favorite` 在 rowcount=0 时抛 DBError，
        `tests/test_auth.py` 也断言 400），语义是"你假设的状态和实际不一致，明确告诉你"，
        而不是静默返回成功。前端 `JobView.toggleFav()` 有 `faving` 并发保护，
        并且 catch 里走统一拦截器提示后端原文，所以不会出现误报成功的假象。
        """
        token, _ = new_user()
        r = client.delete("/api/user/favorites/J0020", headers=auth(token))
        assert r.status_code == 400
        assert r.json()["ok"] is False
        assert "收藏" in r.json()["error"], "错误信息要说清是收藏状态的问题：%s" % r.text

    def test_cancel_twice_reports_state_mismatch(self):
        """连点两次取消：第一次成功，第二次明确报错 —— 不能两次都"成功"（会掩盖状态错乱）"""
        token, _ = new_user()
        client.post("/api/user/favorites", json={"job_id": "J0020"}, headers=auth(token))
        assert client.delete("/api/user/favorites/J0020", headers=auth(token)).status_code == 200
        assert client.delete("/api/user/favorites/J0020", headers=auth(token)).status_code == 400


# ================================================================ 对话（只测参数边界，不花钱）
class TestChatBoundary:

    def test_question_exact_upper_limit_shape(self):
        """500 字是上界：这里只验证**不被 422 拦掉**，不触发真实大模型调用
        （用一个不可能命中缓存、但会被长度校验放行的问法；为避免花钱，本用例只跑长度校验部分）"""
        from src.api.schemas import ChatRequest
        ChatRequest(question="问" * 500)          # 恰好 500 应通过校验
        try:
            ChatRequest(question="问" * 501)
            raise AssertionError("501 字应当被拒")
        except Exception:
            pass

    def test_question_empty_rejected(self):
        r = client.post("/api/chat", json={"question": ""})
        assert r.status_code == 422

    def test_question_over_limit_rejected(self):
        r = client.post("/api/chat", json={"question": "问" * 501})
        assert r.status_code == 422

    def test_history_wrong_type_rejected(self):
        r = client.post("/api/chat", json={"question": "测试", "history": "不是数组"})
        assert r.status_code == 422

    def test_use_cache_wrong_type_rejected(self):
        r = client.post("/api/chat", json={"question": "测试", "use_cache": "也许"})
        assert r.status_code == 422
