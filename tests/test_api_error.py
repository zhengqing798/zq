# -*- coding: utf-8 -*-
"""任务13 · 异常路径测试（「正常 / 边界 / 异常」三条路径里的第三条）

与另外两个文件的分工
    `test_api.py` 等   → 正常路径（功能能不能用、口径对不对）
    `test_api_boundary.py` → 边界路径（参数取到上下限、刚好越界、空值、超长）
    本文件             → 异常路径（未登录 / 越权 / 找不到 / 请求体非法 / 业务规则拒绝）

异常路径要回答的三个问题
    1. **该拦的拦住了吗**：没登录、越权、非法参数，有没有被拒绝（状态码对不对）；
    2. **拒绝的方式一致吗**：错误体是不是统一的 `{"ok","error","hint"}`（见缺陷 15）；
    3. **拒绝信息说人话吗**：前端会把 `error` 直接弹给用户，不能是英文堆栈或纯代码。

关于状态码约定（如实记录本项目的选择）
    本项目把"资源找不到"统一表达为 **400 + 明确的 error 文案**，而不是 404：
    `GET /api/jobs/J9999` → `400 {"error": "岗位不存在：J9999（有效范围 J0001 ~ J8836）"}`。
    这样做的好处是错误信息里直接带正确范围，对使用者更友好；代价是与 REST 惯例不完全一致。
    测试里如实断言这个约定，而不是硬套 404。
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

RESUME = "姓名：张伟\n期望城市：苏州\n【技能特长】Python、MySQL、Selenium\n"


def uniq(prefix="e"):
    return "%s%s" % (prefix, uuid.uuid4().hex[:8])


def new_user(role=None):
    """注册一个用户，返回 (token, user_id)"""
    body = {"username": uniq(), "password": "test123456"}
    if role:
        body["role"] = role
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["用户"]["id"]


def auth(token):
    return {"Authorization": "Bearer %s" % token}


# ---------------------------------------------------------------- 统一错误体的断言工具
def assert_error_shape(r, status):
    """断言状态码 + 统一错误体结构（这是缺陷 15 的回归点）"""
    assert r.status_code == status, "期望 %s，实际 %s：%s" % (status, r.status_code, r.text[:200])
    j = r.json()
    assert j.get("ok") is False, "错误体里 ok 必须是 false：%s" % j
    assert isinstance(j.get("error"), str) and j["error"].strip(), \
        "错误体必须有一句人能读懂的 error：%s" % j
    # 不能把 Python 异常类名/堆栈直接甩给用户
    for bad in ("Traceback", "Error: ", "Exception", "TypeError", "KeyError"):
        assert bad not in j["error"], "error 里出现了内部异常细节：%s" % j["error"]
    return j


# ================================================================ 未登录（401）
NEED_LOGIN_GET = [
    "/api/auth/me",
    "/api/user/stats",
    "/api/user/resumes",
    "/api/user/favorites",
    "/api/user/matches",
    "/api/user/chats",
    "/api/admin/users",
]

NEED_LOGIN_POST = [
    ("/api/user/resumes", {"title": "t", "text": RESUME}),
    ("/api/user/favorites", {"job_id": "J0001"}),
]


class TestUnauthorized:
    """所有需要登录的接口，不带令牌时必须 401 且错误体统一"""

    def test_all_protected_get_endpoints_reject_anonymous(self):
        for path in NEED_LOGIN_GET:
            r = client.get(path)
            j = assert_error_shape(r, 401)
            assert "登录" in j["error"] or "令牌" in j["error"], \
                "%s 的 401 提示不明确：%s" % (path, j["error"])

    def test_all_protected_post_endpoints_reject_anonymous(self):
        for path, body in NEED_LOGIN_POST:
            r = client.post(path, json=body)
            assert_error_shape(r, 401)

    def test_protected_put_and_delete_reject_anonymous(self):
        assert_error_shape(client.put("/api/user/profile", json={"nickname": "x"}), 401)
        assert_error_shape(client.put("/api/user/password",
                                      json={"old_password": "a", "new_password": "b" * 6}), 401)
        assert_error_shape(client.put("/api/user/resumes/1", json={"title": "x"}), 401)
        assert_error_shape(client.put("/api/user/resumes/1/default"), 401)
        assert_error_shape(client.delete("/api/user/resumes/1"), 401)
        assert_error_shape(client.delete("/api/user/favorites/J0001"), 401)

    def test_garbage_token_rejected(self):
        # 注意：HTTP 头只能是 ASCII（latin-1），塞中文会先在 httpx 层抛
        # UnicodeEncodeError，测不到后端。所以这里用 ASCII 的乱码令牌。
        r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token-xyz"})
        assert_error_shape(r, 401)

    def test_tampered_token_rejected(self):
        """真令牌改掉最后一个字符 → 必须失效（不能因为前缀一样就放行）"""
        token, _ = new_user()
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        assert tampered != token
        r = client.get("/api/auth/me", headers=auth(tampered))
        assert_error_shape(r, 401)

    def test_empty_bearer_rejected(self):
        for value in ("Bearer", "Bearer ", "  ", "Bearer    "):
            r = client.get("/api/auth/me", headers={"Authorization": value})
            assert_error_shape(r, 401)

    def test_token_invalid_after_logout(self):
        token, _ = new_user()
        assert client.get("/api/auth/me", headers=auth(token)).status_code == 200
        assert client.post("/api/auth/logout", headers=auth(token)).status_code == 200
        assert_error_shape(client.get("/api/auth/me", headers=auth(token)), 401)

    def test_public_endpoints_still_open(self):
        """异常路径也不能把该开放的接口一起关了"""
        for path in ("/api/health", "/api/home", "/api/jobs?size=1", "/api/companies?size=1",
                     "/api/cluster/list", "/api/jobs/J0001"):
            assert client.get(path).status_code == 200, "%s 不该需要登录" % path


# ================================================================ 越权（403 / 400）
class TestForbidden:

    def test_jobseeker_cannot_read_admin_users(self):
        token, _ = new_user()
        j = assert_error_shape(client.get("/api/admin/users", headers=auth(token)), 403)
        assert "无权" in j["error"] or "权限" in j["error"]

    def test_employer_cannot_read_admin_users(self):
        """企业角色是预留的，同样不能看用户列表"""
        token, _ = new_user(role="employer")
        assert_error_shape(client.get("/api/admin/users", headers=auth(token)), 403)

    def test_admin_can_read_admin_users(self):
        token, _ = new_user(role="admin")
        r = client.get("/api/admin/users", headers=auth(token))
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_cannot_edit_another_users_resume(self):
        a_token, _ = new_user()
        b_token, _ = new_user()
        client.post("/api/user/resumes", json={"title": "A的简历", "text": RESUME}, headers=auth(a_token))
        rid = client.get("/api/user/resumes", headers=auth(a_token)).json()["简历"][0]["id"]

        # B 拿着 A 的 rid 去改 / 删 / 设默认，都必须被拒
        j = assert_error_shape(client.put("/api/user/resumes/%d" % rid,
                                          json={"title": "被改了"}, headers=auth(b_token)), 400)
        assert "无权" in j["error"] or "不存在" in j["error"]
        assert_error_shape(client.put("/api/user/resumes/%d/default" % rid, headers=auth(b_token)), 400)
        assert_error_shape(client.delete("/api/user/resumes/%d" % rid, headers=auth(b_token)), 400)
        assert_error_shape(client.put("/api/user/resumes/%d" % rid,
                                      json={"title": "被改了"}, headers=auth(b_token)), 400)

        # 关键：A 的简历一个字都没被改掉
        rows = client.get("/api/user/resumes", headers=auth(a_token)).json()["简历"]
        assert len(rows) == 1 and rows[0]["title"] == "A的简历"

    def test_cannot_use_another_users_saved_resume_for_matching(self):
        a_token, _ = new_user()
        b_token, _ = new_user()
        client.post("/api/user/resumes", json={"title": "A", "text": RESUME}, headers=auth(a_token))
        rid = client.get("/api/user/resumes", headers=auth(a_token)).json()["简历"][0]["id"]
        r = client.post("/api/match", json={"saved_resume_id": rid, "top_n": 5}, headers=auth(b_token))
        assert_error_shape(r, 400)

    def test_saved_resume_requires_login(self):
        a_token, _ = new_user()
        client.post("/api/user/resumes", json={"title": "A", "text": RESUME}, headers=auth(a_token))
        rid = client.get("/api/user/resumes", headers=auth(a_token)).json()["简历"][0]["id"]
        r = client.post("/api/match", json={"saved_resume_id": rid, "top_n": 5})
        assert_error_shape(r, 400)


# ================================================================ 找不到（本项目统一用 400）
class TestNotFound:
    """本项目把"资源不存在"统一表达为 400 + 明确文案，而不是 404（见文件头说明）"""

    def test_job_id_out_of_range(self):
        for jid in ("J9999", "J0000", "J8837"):
            j = assert_error_shape(client.get("/api/jobs/%s" % jid), 400)
            assert "岗位不存在" in j["error"]
        # 边界内的两端必须仍然可用，避免"为了拦异常把正常范围也拦了"
        assert client.get("/api/jobs/J0001").status_code == 200
        assert client.get("/api/jobs/J8836").status_code == 200

    def test_job_id_not_a_valid_format(self):
        j = assert_error_shape(client.get("/api/jobs/abc"), 400)
        assert "岗位不存在" in j["error"]

    def test_company_id_not_found(self):
        j = assert_error_shape(client.get("/api/companies/C99999999"), 400)
        assert "公司不存在" in j["error"]

    def test_company_id_garbage(self):
        assert_error_shape(client.get("/api/companies/不是公司ID"), 400)

    def test_unknown_api_path_uses_unified_error_body(self):
        """路由没匹配上 → 404，而且**也**要是统一错误体（缺陷 15 的一部分）"""
        j = assert_error_shape(client.get("/api/这个接口不存在"), 404)
        assert "Not Found" in j["error"] or "不存在" in j["error"]

    def test_wrong_method_uses_unified_error_body(self):
        """方法不允许 → 405，同样要统一错误体"""
        r = client.post("/api/health")
        assert_error_shape(r, 405)

    def test_match_with_unknown_resume_id(self):
        assert_error_shape(client.post("/api/match", json={"resume_id": "rs_不存在", "top_n": 5}), 400)

    def test_score_with_unknown_resume_id(self):
        assert_error_shape(
            client.post("/api/score", json={"resume_id": "rs_不存在", "job_id": "J0020"}), 400)


# ================================================================ 参数非法（422）
class TestValidationError:
    """422 的响应体必须也走统一错误体 —— 缺陷 15 的回归点"""

    def test_unified_error_body_for_422(self):
        r = client.post("/api/chat", json={"question": "问" * 501})
        j = assert_error_shape(r, 422)
        assert "校验" in j["error"] or "参数" in j["error"]
        assert "question" in j["error"], "错误信息要指出是哪个字段错了：%s" % j["error"]
        assert "500" in j["error"], "错误信息要带上正确范围：%s" % j["error"]
        assert "校验明细" in j, "保留原始明细便于排查"

    def test_422_error_body_is_not_raw_pydantic_json(self):
        """回归：前端会把 error 直接弹给用户，不能是英文 JSON 串"""
        j = client.post("/api/match", json={"resume_text": RESUME, "top_n": 99}).json()
        assert not j["error"].lstrip().startswith("[")
        assert "Input should be" not in j["error"]

    def test_missing_body_fields(self):
        # 缺 resume_text
        assert_error_shape(client.post("/api/resume/parse_text", json={}), 422)
        # 缺 job_id
        assert_error_shape(client.post("/api/score", json={"resume_text": RESUME}), 422)
        # 缺 question
        assert_error_shape(client.post("/api/chat", json={}), 422)
        # 缺 job_id（收藏）
        assert_error_shape(client.post("/api/user/favorites", json={},
                                       headers=auth(new_user()[0])), 422)

    def test_wrong_types(self):
        assert_error_shape(client.get("/api/jobs?page=abc"), 422)
        assert_error_shape(client.get("/api/jobs?salary_min=abc"), 422)
        assert_error_shape(client.get("/api/jobs?size=1.5"), 422)
        assert_error_shape(client.get("/api/home?n=abc"), 422)
        assert_error_shape(client.get("/api/companies?page=abc"), 422)

    def test_bad_json_body(self):
        r = client.post("/api/resume/parse_text", content="{不是合法JSON",
                         headers={"Content-Type": "application/json"})
        assert_error_shape(r, 422)

    def test_missing_content_type(self):
        r = client.post("/api/chat", content="question=abc")
        assert_error_shape(r, 422)

    def test_parse_endpoint_without_any_input(self):
        """既没上传文件也没给 resume_text → 400（业务侧主动校验，不是 422）"""
        j = assert_error_shape(client.post("/api/resume/parse"), 400)
        assert "resume_text" in j["error"] or "PDF" in j["error"]

    def test_history_wrong_element_type(self):
        r = client.post("/api/chat", json={"question": "测试", "history": [{"role": 1}]})
        assert_error_shape(r, 422)


# ================================================================ 业务规则拒绝
class TestBusinessErrors:

    def test_duplicate_username_rejected(self):
        name = uniq()
        assert client.post("/api/auth/register",
                           json={"username": name, "password": "123456"}).status_code == 200
        j = assert_error_shape(client.post("/api/auth/register",
                                           json={"username": name, "password": "123456"}), 400)
        assert "已存在" in j["error"] or "存在" in j["error"]

    def test_login_with_unknown_user(self):
        j = assert_error_shape(client.post("/api/auth/login",
                                           json={"username": uniq(), "password": "123456"}), 401)
        assert "用户名或密码错误" in j["error"]

    def test_login_with_wrong_password(self):
        token, _ = new_user()
        me = client.get("/api/auth/me", headers=auth(token)).json()["用户"]
        j = assert_error_shape(client.post("/api/auth/login",
                                           json={"username": me["username"],
                                                 "password": "错误的密码"}), 401)
        assert "用户名或密码错误" in j["error"], "不能泄露'用户存在但密码错'"

    def test_change_password_with_wrong_old_password(self):
        token, _ = new_user()
        j = assert_error_shape(client.put("/api/user/password",
                                          json={"old_password": "错误的原密码",
                                                "new_password": "newpass123"},
                                          headers=auth(token)), 400)
        assert "原密码" in j["error"] or "密码" in j["error"]

    def test_favorite_job_id_out_of_range(self):
        token, _ = new_user()
        for jid in ("J0000", "J8837"):
            j = assert_error_shape(client.post("/api/user/favorites", json={"job_id": jid},
                                               headers=auth(token)), 400)
            assert "范围" in j["error"] or "超出" in j["error"]

    def test_favorite_job_id_garbage(self):
        token, _ = new_user()
        assert_error_shape(client.post("/api/user/favorites", json={"job_id": "Java工程师"},
                                       headers=auth(token)), 400)

    def test_resume_id_not_an_integer(self):
        token, _ = new_user()
        assert_error_shape(client.delete("/api/user/resumes/abc", headers=auth(token)), 422)

    def test_delete_resume_that_does_not_exist(self):
        token, _ = new_user()
        assert_error_shape(client.delete("/api/user/resumes/999999", headers=auth(token)), 400)

    def test_match_without_any_resume_source(self):
        """/api/match 既不给 resume_id 也不给 resume_text → 明确拒绝，不能返回一堆瞎推荐"""
        r = client.post("/api/match", json={"top_n": 5})
        assert r.status_code in (400, 422), "实际 %s：%s" % (r.status_code, r.text[:200])
        assert r.json()["ok"] is False

    def test_score_without_any_resume_source(self):
        r = client.post("/api/score", json={"job_id": "J0020"})
        assert r.status_code in (400, 422), "实际 %s：%s" % (r.status_code, r.text[:200])
        assert r.json()["ok"] is False


# ================================================================ 错误体一致性（跨类型）
class TestErrorShapeConsistency:
    """不管哪一类错误，客户端都应该只需处理一种错误体结构"""

    def test_all_error_classes_share_one_shape(self):
        token, _ = new_user()
        cases = [
            ("未登录 401", client.get("/api/auth/me")),
            ("越权 403", client.get("/api/admin/users", headers=auth(token))),
            ("找不到 404", client.get("/api/不存在")),
            ("方法不对 405", client.post("/api/health")),
            ("参数非法 422", client.post("/api/chat", json={"question": ""})),
            ("业务拒绝 400", client.get("/api/jobs/J9999")),
            ("登录失败 401", client.post("/api/auth/login",
                                        json={"username": "nobody", "password": "x"})),
        ]
        for name, r in cases:
            assert r.status_code >= 400, "%s 不该成功" % name
            j = r.json()
            assert j.get("ok") is False, "%s 的 ok 不是 false：%s" % (name, j)
            assert isinstance(j.get("error"), str) and j["error"], \
                "%s 缺少可读的 error 字段：%s" % (name, j)
            assert "detail" not in j or "error" in j, \
                "%s 仍在用裸 detail 结构：%s" % (name, j)
