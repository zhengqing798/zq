# -*- coding: utf-8 -*-
"""任务11 · 用户体系接口测试（注册/登录/鉴权/权限/个人中心）

覆盖：正常 / 边界 / 异常 三条路径。
· 使用 `TestClient`（进程内），数据库由 `tests/conftest.py` 隔离到临时文件。
· 每个用例用随机用户名，互不干扰。
"""
import os
import random
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.api.main import app                                              # noqa: E402

client = TestClient(app)
RESUME = """姓名：李四
期望岗位：Java开发工程师
期望城市：厦门
期望薪资：15000-20000元
最高学历：本科
专业：计算机科学与技术
工作年限：5年
是否应届：否

【技能特长】
Java、Spring、MySQL、Redis、Linux、Docker
"""


def rand_user():
    return "t%d" % random.randint(100000, 999999)


def register(username=None, password="pw123456", role="jobseeker", **kw):
    u = username or rand_user()
    r = client.post("/api/auth/register",
                    json={"username": u, "password": password, "role": role, **kw})
    return r, u


def token_of(username=None, password="pw123456"):
    r, u = register(username, password)
    assert r.status_code == 200, r.text
    return r.json()["token"], u


def auth(tok):
    return {"Authorization": "Bearer " + tok}


# ================================================================ 注册
class TestRegister:
    def test_normal(self):
        r, u = register(nickname="小张", phone="13800000000", email="z@example.com")
        assert r.status_code == 200
        j = r.json()
        assert j["token"] and j["expires_at"]
        assert j["用户"]["username"] == u
        assert j["用户"]["role"] == "jobseeker"
        assert j["用户"]["role_label"] == "求职者"
        assert j["用户"]["nickname"] == "小张"
        assert j["用户"]["last_login"] == ""          # 注册时还没登录过

    def test_normal_employer_role(self):
        r, _ = register(role="employer")
        assert r.status_code == 200
        assert r.json()["用户"]["role_label"] == "企业"

    def test_abnormal_duplicate(self):
        _, u = register()
        r, _ = register(username=u)
        assert r.status_code == 400
        assert "已存在" in r.json()["error"]

    @pytest.mark.parametrize("name", ["ab", "a" * 25])
    def test_abnormal_username_length(self, name):
        r, _ = register(username=name)
        assert r.status_code == 422          # Pydantic 长度约束

    def test_abnormal_username_charset(self):
        """异常：含非法字符（空格/中文）→ 400（业务层校验）"""
        r = client.post("/api/auth/register", json={"username": "bad name", "password": "pw123456"})
        assert r.status_code == 400
        assert "字母" in r.json()["error"] or "下划线" in r.json()["error"]

    def test_abnormal_short_password(self):
        r = client.post("/api/auth/register", json={"username": rand_user(), "password": "123"})
        assert r.status_code == 422

    def test_abnormal_bad_role(self):
        r = client.post("/api/auth/register",
                        json={"username": rand_user(), "password": "pw123456", "role": "boss"})
        assert r.status_code == 400
        assert "非法角色" in r.json()["error"]


# ================================================================ 登录 / 鉴权
class TestAuth:
    def test_normal_login(self):
        tok, u = token_of()
        r = client.post("/api/auth/login", json={"username": u, "password": "pw123456"})
        assert r.status_code == 200
        assert r.json()["token"]
        me = client.get("/api/auth/me", headers=auth(r.json()["token"]))
        assert me.status_code == 200
        assert me.json()["用户"]["last_login"]        # 登录后应记录时间

    def test_abnormal_wrong_password(self):
        _, u = register()
        r = client.post("/api/auth/login", json={"username": u, "password": "wrongpw"})
        assert r.status_code == 401
        assert "密码错误" in r.json()["error"]

    def test_abnormal_unknown_user(self):
        r = client.post("/api/auth/login", json={"username": "nobody_xyz", "password": "pw123456"})
        assert r.status_code == 401

    def test_abnormal_no_token(self):
        r = client.get("/api/auth/me")
        assert r.status_code == 401
        assert r.json()["error"] == "未登录"

    def test_abnormal_bad_token(self):
        r = client.get("/api/auth/me", headers=auth("not-a-real-token"))
        assert r.status_code == 401
        assert "失效" in r.json()["error"]

    def test_normal_logout_invalidates_token(self):
        tok, _ = token_of()
        assert client.get("/api/auth/me", headers=auth(tok)).status_code == 200
        assert client.post("/api/auth/logout", headers=auth(tok)).status_code == 200
        r = client.get("/api/auth/me", headers=auth(tok))
        assert r.status_code == 401                   # 登出后令牌立即失效

    def test_boundary_logout_without_token(self):
        """边界：不带令牌调登出 → 仍返回 200（幂等，不报错）"""
        assert client.post("/api/auth/logout").status_code == 200


# ================================================================ 个人资料 / 密码
class TestProfile:
    def test_normal_update(self):
        tok, _ = token_of()
        r = client.put("/api/user/profile", headers=auth(tok),
                       json={"nickname": "张伟", "phone": "13900000000", "email": "a@b.com"})
        assert r.status_code == 200
        u = r.json()["用户"]
        assert (u["nickname"], u["phone"], u["email"]) == ("张伟", "13900000000", "a@b.com")
        # 持久化校验：重新查一次
        again = client.get("/api/auth/me", headers=auth(tok)).json()["用户"]
        assert again["nickname"] == "张伟"

    def test_abnormal_unauthenticated(self):
        assert client.put("/api/user/profile", json={"nickname": "x"}).status_code == 401

    def test_normal_change_password(self):
        tok, u = token_of()
        r = client.put("/api/user/password", headers=auth(tok),
                       json={"old_password": "pw123456", "new_password": "newpw123"})
        assert r.status_code == 200
        # 新密码可登录、旧密码不可
        assert client.post("/api/auth/login", json={"username": u, "password": "newpw123"}).status_code == 200
        assert client.post("/api/auth/login", json={"username": u, "password": "pw123456"}).status_code == 401

    def test_abnormal_wrong_old_password(self):
        tok, _ = token_of()
        r = client.put("/api/user/password", headers=auth(tok),
                       json={"old_password": "nope", "new_password": "newpw123"})
        assert r.status_code == 400
        assert "原密码" in r.json()["error"]

    def test_abnormal_short_new_password(self):
        tok, _ = token_of()
        r = client.put("/api/user/password", headers=auth(tok),
                       json={"old_password": "pw123456", "new_password": "123"})
        assert r.status_code == 422

    def test_password_not_plaintext_in_db(self):
        """安全：数据库里不能出现明文口令"""
        tok, u = token_of(password="plaintext123")
        import sqlite3
        from src.api.db import DB_PATH
        c = sqlite3.connect(DB_PATH)
        row = c.execute("SELECT password_hash, salt FROM users WHERE username=?", (u,)).fetchone()
        c.close()
        assert row and "plaintext123" not in row[0]
        assert len(row[0]) == 64 and len(row[1]) == 32     # sha256 hex / 16 字节盐


# ================================================================ 个人中心：简历
class TestResumes:
    def test_normal_crud(self):
        tok, _ = token_of()
        r = client.post("/api/user/resumes", headers=auth(tok),
                        json={"title": "Java求职简历", "text": RESUME})
        assert r.status_code == 200
        rid = r.json()["id"]
        # 列表（第一份自动为默认）
        lst = client.get("/api/user/resumes", headers=auth(tok)).json()["简历"]
        assert len(lst) == 1 and lst[0]["is_default"] is True
        assert lst[0]["字数"] > 0
        # 再存一份 → 不抢默认
        rid2 = client.post("/api/user/resumes", headers=auth(tok),
                           json={"title": "第二份", "text": RESUME}).json()["id"]
        lst = client.get("/api/user/resumes", headers=auth(tok)).json()["简历"]
        assert len(lst) == 2
        assert sum(1 for x in lst if x["is_default"]) == 1
        # 改默认
        assert client.put("/api/user/resumes/%d/default" % rid2, headers=auth(tok)).status_code == 200
        lst = client.get("/api/user/resumes", headers=auth(tok)).json()["简历"]
        assert [x["id"] for x in lst if x["is_default"]] == [rid2]
        # 更新
        assert client.put("/api/user/resumes/%d" % rid, headers=auth(tok),
                          json={"title": "改名了"}).status_code == 200
        # 删除
        assert client.delete("/api/user/resumes/%d" % rid, headers=auth(tok)).status_code == 200
        assert len(client.get("/api/user/resumes", headers=auth(tok)).json()["简历"]) == 1

    def test_abnormal_empty_text(self):
        tok, _ = token_of()
        assert client.post("/api/user/resumes", headers=auth(tok),
                           json={"title": "空", "text": ""}).status_code == 422

    def test_abnormal_cannot_touch_others_resume(self):
        """异常：用户 A 不能改/删用户 B 的简历（越权保护）"""
        tok_a, _ = token_of()
        tok_b, _ = token_of()
        rid = client.post("/api/user/resumes", headers=auth(tok_b),
                          json={"title": "B的简历", "text": RESUME}).json()["id"]
        assert client.put("/api/user/resumes/%d" % rid, headers=auth(tok_a),
                          json={"title": "篡改"}).status_code == 400
        assert client.delete("/api/user/resumes/%d" % rid, headers=auth(tok_a)).status_code == 400
        assert client.put("/api/user/resumes/%d/default" % rid,
                          headers=auth(tok_a)).status_code == 400
        # B 的简历仍然完好
        assert len(client.get("/api/user/resumes", headers=auth(tok_b)).json()["简历"]) == 1

    def test_abnormal_unauthenticated(self):
        assert client.get("/api/user/resumes").status_code == 401


# ================================================================ 个人中心：收藏
class TestFavorites:
    def test_normal_add_list_remove(self):
        tok, _ = token_of()
        r = client.post("/api/user/favorites", headers=auth(tok),
                        json={"job_id": "J7596", "note": "薪资不错"})
        assert r.status_code == 200
        assert "已收藏" in r.json()["message"]
        fs = client.get("/api/user/favorites", headers=auth(tok)).json()["收藏"]
        assert len(fs) == 1
        assert fs[0]["job_id"] == "J7596"
        assert fs[0]["job_name"] and fs[0]["company"] and fs[0]["city"]   # 岗位信息由后端补齐
        assert fs[0]["note"] == "薪资不错"
        assert client.delete("/api/user/favorites/J7596", headers=auth(tok)).status_code == 200
        assert client.get("/api/user/favorites", headers=auth(tok)).json()["收藏"] == []

    def test_abnormal_duplicate(self):
        tok, _ = token_of()
        client.post("/api/user/favorites", headers=auth(tok), json={"job_id": "J0001"})
        r = client.post("/api/user/favorites", headers=auth(tok), json={"job_id": "J0001"})
        assert r.status_code == 400
        assert "已在收藏夹" in r.json()["error"]

    def test_abnormal_job_out_of_range(self):
        tok, _ = token_of()
        r = client.post("/api/user/favorites", headers=auth(tok), json={"job_id": "J99999"})
        assert r.status_code == 400
        assert "超出范围" in r.json()["error"]

    def test_abnormal_remove_not_exists(self):
        tok, _ = token_of()
        assert client.delete("/api/user/favorites/J0001", headers=auth(tok)).status_code == 400

    def test_abnormal_unauthenticated(self):
        assert client.get("/api/user/favorites").status_code == 401


# ================================================================ 个人中心：历史与统计
class TestHistoryAndStats:
    def test_normal_match_saves_history(self):
        tok, _ = token_of()
        r = client.post("/api/match", headers=auth(tok),
                        json={"resume_text": RESUME, "top_n": 3})
        assert r.status_code == 200
        assert r.json()["已存历史"] is True
        hs = client.get("/api/user/matches", headers=auth(tok)).json()["历史"]
        assert len(hs) == 1
        assert hs[0]["top_n"] == 3
        assert len(hs[0]["推荐"]) == 3
        assert hs[0]["推荐"][0]["岗位名称"]

    def test_normal_guest_match_no_history(self):
        """游客匹配：不写历史，也不报错"""
        r = client.post("/api/match", json={"resume_text": RESUME, "top_n": 2})
        assert r.status_code == 200
        assert r.json().get("已存历史") is None

    def test_normal_saved_resume_match(self):
        tok, _ = token_of()
        rid = client.post("/api/user/resumes", headers=auth(tok),
                          json={"title": "Java简历", "text": RESUME}).json()["id"]
        r = client.post("/api/match", headers=auth(tok),
                        json={"saved_resume_id": rid, "top_n": 3})
        assert r.status_code == 200
        assert r.json()["推荐数"] == 3
        hs = client.get("/api/user/matches", headers=auth(tok)).json()["历史"]
        assert hs[0]["resume_title"] == "Java简历"

    def test_abnormal_saved_resume_requires_login(self):
        r = client.post("/api/match", json={"saved_resume_id": 1, "top_n": 3})
        assert r.status_code == 400
        assert "需先登录" in r.json()["error"]

    def test_abnormal_saved_resume_not_owned(self):
        tok_a, _ = token_of()
        tok_b, _ = token_of()
        rid = client.post("/api/user/resumes", headers=auth(tok_b),
                          json={"title": "B的", "text": RESUME}).json()["id"]
        r = client.post("/api/match", headers=auth(tok_a),
                        json={"saved_resume_id": rid, "top_n": 3})
        assert r.status_code == 400
        assert "无权" in r.json()["error"] or "不存在" in r.json()["error"]

    def test_normal_stats(self):
        tok, _ = token_of()
        client.post("/api/user/resumes", headers=auth(tok), json={"title": "r", "text": RESUME})
        client.post("/api/user/favorites", headers=auth(tok), json={"job_id": "J0002"})
        client.post("/api/match", headers=auth(tok), json={"resume_text": RESUME, "top_n": 2})
        s = client.get("/api/user/stats", headers=auth(tok)).json()["统计"]
        assert s["简历数"] == 1 and s["收藏岗位数"] == 1 and s["匹配次数"] == 1
        assert s["提问次数"] == 0

    def test_abnormal_stats_unauthenticated(self):
        assert client.get("/api/user/stats").status_code == 401


# ================================================================ 权限控制
class TestPermissions:
    def test_abnormal_jobseeker_forbidden_admin_api(self):
        """异常：求职者访问管理员接口 → 403（并给出所需角色提示）"""
        tok, _ = token_of()
        r = client.get("/api/admin/users", headers=auth(tok))
        assert r.status_code == 403
        assert "无权访问" in r.json()["error"]
        assert "管理员" in r.json()["hint"]

    def test_normal_admin_can_access(self):
        r, _ = register(role="admin")
        tok = r.json()["token"]
        j = client.get("/api/admin/users", headers=auth(tok))
        assert j.status_code == 200
        assert j.json()["用户数"] >= 1

    def test_abnormal_admin_api_unauthenticated(self):
        assert client.get("/api/admin/users").status_code == 401
