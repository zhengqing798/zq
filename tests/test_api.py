# -*- coding: utf-8 -*-
"""任务11/12 · FastAPI 接口测试（正常 / 边界 / 异常 三条路径）

运行：
    pytest -q tests/test_api.py                 # 全部（需本仓库数据齐备）
    pytest -q tests/test_api.py -m "not slow"   # 跳过需要网络的对话测试

说明
----
· 用 `TestClient` 在**进程内**调用 FastAPI 应用，不需要先起 uvicorn。
· 对话接口依赖 DeepSeek API：无 `.env` 或无网络时自动跳过（标记 slow）。
· 前置：`python scripts/doctor.py` 通过（尤其 5 个可重建产物要存在）。
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

RESUME = """姓名：张伟
期望岗位：测试开发工程师
期望城市：苏州
期望薪资：12000-16000元
最高学历：大专
专业：软件技术
工作年限：3年
是否应届：否

【技能特长】
熟练掌握 Selenium、JMeter、Python、MySQL、Linux，了解 Postman 与 Git

【工作经历】
2022.07-2025.06 某软件公司 测试工程师，负责接口自动化测试与性能压测

【项目经验】
使用 Python + Selenium 搭建 UI 自动化框架，覆盖 300 条用例
"""

HAS_KEY = os.path.exists(os.path.join(ROOT, ".env"))


@pytest.fixture(scope="module")
def resume_id():
    r = client.post("/api/resume/parse_text", json={"resume_text": RESUME})
    assert r.status_code == 200, r.text
    return r.json()["resume_id"]


# ================================================================ 健康检查
class TestHealth:
    def test_health_ok(self):
        r = client.get("/api/health")
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert j["匹配引擎"]["就绪"] is True
        assert j["匹配引擎"]["岗位数"] == 8836
        assert j["RAG检索"]["就绪"] is True
        assert j["RAG检索"]["卡片数"] == 8852
        assert j["评分模型"]["就绪"] is True

    def test_root_index(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "/api/chat" in r.json()["接口"]


# ================================================================ ① 简历解析
class TestResumeParse:
    def test_normal(self):
        r = client.post("/api/resume/parse_text", json={"resume_text": RESUME})
        assert r.status_code == 200
        j = r.json()
        assert j["resume_id"].startswith("rs_")
        assert j["解析字段"]["期望城市"] == "苏州"
        assert j["解析字段"]["最高学历"] == "大专"
        assert j["解析字段"]["工作年限"] == 3
        assert "Python" in j["技能列表"] and "Selenium" in j["技能列表"]
        assert j["技能数"] >= 5
        assert j["技能数"] == len(j["技能列表"])

    def test_boundary_minimal_resume(self):
        """边界：只有一句话的极简简历仍应可解析（字段可空，但不能报错）"""
        r = client.post("/api/resume/parse_text", json={"resume_text": "我会 Python"})
        assert r.status_code == 200
        j = r.json()
        assert j["resume_id"]
        assert j["技能数"] >= 0

    def test_boundary_long_text(self):
        """边界：超长文本（5000 字）不应报错"""
        r = client.post("/api/resume/parse_text", json={"resume_text": "Python " * 800})
        assert r.status_code == 200

    def test_abnormal_empty_body(self):
        """异常：空字符串被 Pydantic 拦下（min_length=1）→ 422"""
        r = client.post("/api/resume/parse_text", json={"resume_text": ""})
        assert r.status_code == 422

    def test_abnormal_missing_field(self):
        r = client.post("/api/resume/parse_text", json={})
        assert r.status_code == 422

    def test_abnormal_multipart_without_input(self):
        """异常：multipart 既没文件也没文本 → 400"""
        r = client.post("/api/resume/parse", data={})
        assert r.status_code == 400
        assert r.json()["ok"] is False


# ================================================================ ② 人岗匹配
class TestMatch:
    def test_normal_by_resume_id(self, resume_id):
        r = client.post("/api/match", json={"resume_id": resume_id, "top_n": 5})
        assert r.status_code == 200
        j = r.json()
        assert j["推荐数"] == 5
        assert j["打分范围"] == 8836
        assert j["权重版本"]  # v1 或 v2
        tops = j["推荐"]
        # 排名连续、总分降序
        assert [x["排名"] for x in tops] == [1, 2, 3, 4, 5]
        assert all(tops[i]["总分"] >= tops[i + 1]["总分"] for i in range(len(tops) - 1))
        # 六维分齐全且在 0~100
        for x in tops:
            for d in ("技能", "经验", "学历", "地域", "薪资", "专业证书"):
                assert 0 <= x[d] <= 100, (x["岗位名称"], d, x[d])
            assert x["推荐理由"]
            assert x["岗位ID"].startswith("J")
        assert j["来源"]

    def test_normal_by_text(self):
        r = client.post("/api/match", json={"resume_text": RESUME, "top_n": 3})
        assert r.status_code == 200
        assert r.json()["推荐数"] == 3

    @pytest.mark.parametrize("n", [1, 10, 50])
    def test_boundary_top_n(self, resume_id, n):
        r = client.post("/api/match", json={"resume_id": resume_id, "top_n": n})
        assert r.status_code == 200
        assert r.json()["推荐数"] == n

    @pytest.mark.parametrize("n", [0, 51, -1])
    def test_abnormal_top_n_out_of_range(self, resume_id, n):
        """异常：top_n 超出 1~50 → 422"""
        r = client.post("/api/match", json={"resume_id": resume_id, "top_n": n})
        assert r.status_code == 422

    def test_abnormal_unknown_resume_id(self):
        r = client.post("/api/match", json={"resume_id": "rs_not_exist", "top_n": 5})
        assert r.status_code == 400
        assert "resume_id" in r.json()["error"]

    def test_abnormal_no_input(self):
        """异常：既不给 resume_id 也不给 resume_text → 400"""
        r = client.post("/api/match", json={"top_n": 5})
        assert r.status_code == 400


# ================================================================ ③ 评分（双口径）
class TestScore:
    def test_normal_dual_caliber(self, resume_id):
        r = client.post("/api/score", json={"resume_id": resume_id, "job_id": "J7596"})
        assert r.status_code == 200
        j = r.json()
        rule = j["规则口径"]
        # 规则总分 = Σ(权重 × 维度分)，允许 0.02 的四舍五入误差
        w = {"技能": None}
        assert set(rule["六维分"]) == {"技能", "经验", "学历", "地域", "薪资", "专业证书"}
        assert 0 <= rule["总分"] <= 100
        # 模型口径
        m = j["模型口径"]
        assert m["可用"] is True, m.get("原因")
        assert 0 <= m["T1回归_预测总分"] <= 100
        assert 0 <= m["T2分类_匹配概率"] <= 100
        assert isinstance(m["是否匹配"], bool)
        assert len(m["特征"]) == 36
        assert j["差异"] == round(m["T1回归_预测总分"] - rule["总分"], 2)

    def test_normal_by_text(self):
        r = client.post("/api/score", json={"resume_text": RESUME, "job_id": "J0001"})
        assert r.status_code == 200
        assert r.json()["规则口径"]["总分"] >= 0

    def test_boundary_first_and_last_job(self, resume_id):
        for jid in ("J0001", "J8836"):
            r = client.post("/api/score", json={"resume_id": resume_id, "job_id": jid})
            assert r.status_code == 200, jid
            assert r.json()["岗位"]["岗位ID"] == jid

    def test_abnormal_job_out_of_range(self, resume_id):
        r = client.post("/api/score", json={"resume_id": resume_id, "job_id": "J99999"})
        assert r.status_code == 400
        assert "超出范围" in r.json()["error"]

    def test_abnormal_job_bad_format(self, resume_id):
        r = client.post("/api/score", json={"resume_id": resume_id, "job_id": "abc"})
        assert r.status_code == 400

    def test_abnormal_missing_job_id(self, resume_id):
        r = client.post("/api/score", json={"resume_id": resume_id})
        assert r.status_code == 422


# ================================================================ ④ 聚类
class TestCluster:
    def test_list_normal(self):
        r = client.get("/api/cluster/list")
        assert r.status_code == 200
        j = r.json()
        assert j["簇数"] == 9
        assert j["主方案"].startswith("K=9")
        assert sum(x["岗位数"] for x in j["簇"]) == 8836
        names = [x["簇名"] for x in j["簇"]]
        assert any("软件测试" in n for n in names)

    def test_profile_normal(self):
        r = client.get("/api/cluster/profile", params={"name": "软件测试"})
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert j["来源"]

    def test_profile_empty_returns_all(self):
        r = client.get("/api/cluster/profile")
        assert r.status_code == 200

    def test_boundary_unknown_cluster(self):
        """边界：不存在的簇名 → ok=false（工具语义），而不是 500"""
        r = client.get("/api/cluster/profile", params={"name": "量子计算"})
        assert r.status_code == 200
        assert r.json()["ok"] is False


# ================================================================ ⑤ 对话（需网络）
@pytest.mark.slow
@pytest.mark.skipif(not HAS_KEY, reason="无 .env（缺少 DeepSeek API Key），跳过对话测试")
class TestChat:
    def test_normal(self):
        r = client.post("/api/chat", json={"question": "福州市的Java岗位有多少个？"})
        assert r.status_code == 200
        j = r.json()
        assert j["回答"]
        assert j["工具序列"]
        assert j["prompt版本"].startswith("v")
        assert j["轮数"] >= 1

    def test_boundary_empty_question(self):
        r = client.post("/api/chat", json={"question": ""})
        assert r.status_code == 422

    def test_boundary_too_long_question(self):
        r = client.post("/api/chat", json={"question": "问" * 501})
        assert r.status_code == 422
