# -*- coding: utf-8 -*-
"""任务11 · 存储层（SQLite）：用户 / 会话 / 简历 / 收藏 / 匹配历史 / 问答记录

为什么用 sqlite3
----------------
1. **Python 标准库自带**，不新增任何依赖（部署镜像不变大、机房不会因为装包失败）
2. 单文件数据库，适合"一人一机演示 + 云服务器单容器"的场景
3. 支持并发读、事务写；本系统写入量极小（用户操作级别）

安全实现（都可被审计）
----------------------
· 口令：**每用户独立随机盐 + PBKDF2-HMAC-SHA256（20 万次迭代）**，只存 hash 与 salt，**绝不存明文**
· 校验：`hmac.compare_digest` 常量时间比较，避免计时侧信道
· 会话：`secrets.token_urlsafe(32)` 随机令牌，落库并带过期时间（默认 7 天）；登出即删除
· SQL：**全部参数化查询**，无字符串拼接（防注入）
· 权限：用户带 `role`（jobseeker / employer / admin），接口层用依赖注入校验

数据库文件：`data/app.db`（**已加入 .gitignore，不入库**；首次运行时自动建表）
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DB_PATH = os.environ.get("APP_DB", os.path.join(ROOT, "data", "app.db"))

PBKDF2_ROUNDS = 200_000
TOKEN_TTL_DAYS = 7
ROLES = ("jobseeker", "employer", "admin")
ROLE_LABEL = {"jobseeker": "求职者", "employer": "企业", "admin": "管理员"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'jobseeker',
    nickname      TEXT DEFAULT '',
    phone         TEXT DEFAULT '',
    email         TEXT DEFAULT '',
    created_at    TEXT NOT NULL,
    last_login    TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resumes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    title      TEXT NOT NULL,
    text       TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS favorites (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    job_id     TEXT NOT NULL,
    job_name   TEXT DEFAULT '',
    company    TEXT DEFAULT '',
    city       TEXT DEFAULT '',
    salary     TEXT DEFAULT '',
    note       TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(user_id, job_id)
);
CREATE TABLE IF NOT EXISTS match_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    resume_title TEXT DEFAULT '',
    top_n        INTEGER DEFAULT 0,
    summary      TEXT DEFAULT '',
    result_json  TEXT DEFAULT '[]',
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    question   TEXT DEFAULT '',
    answer     TEXT DEFAULT '',
    sources    TEXT DEFAULT '[]',
    tool_seq   TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_resumes_user ON resumes(user_id);
CREATE INDEX IF NOT EXISTS idx_fav_user ON favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_match_user ON match_history(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_id);
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class DBError(Exception):
    """业务层可直接转成 400 的错误"""


# ---------------------------------------------------------------- 连接与初始化
@contextmanager
def conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with conn() as c:
        c.executescript(SCHEMA)
    return DB_PATH


def reset_db():
    """仅供测试使用：整库重建"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    return init_db()


# ---------------------------------------------------------------- 口令
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                            bytes.fromhex(salt), PBKDF2_ROUNDS)
    return h.hex(), salt


def check_password(password, password_hash, salt):
    h, _ = hash_password(password, salt)
    return hmac.compare_digest(h, password_hash)


# ---------------------------------------------------------------- 用户
def _row_user(r):
    if r is None:
        return None
    return {"id": r["id"], "username": r["username"], "role": r["role"],
            "role_label": ROLE_LABEL.get(r["role"], r["role"]),
            "nickname": r["nickname"] or "", "phone": r["phone"] or "",
            "email": r["email"] or "", "created_at": r["created_at"],
            "last_login": r["last_login"] or ""}


def create_user(username, password, role="jobseeker", nickname="", phone="", email=""):
    username = (username or "").strip()
    if len(username) < 3 or len(username) > 24:
        raise DBError("用户名长度需为 3~24 个字符")
    if not username.replace("_", "").isalnum():
        raise DBError("用户名只能包含字母、数字和下划线")
    if len(password or "") < 6:
        raise DBError("密码至少 6 位")
    if role not in ROLES:
        raise DBError("非法角色：%s（可选 %s）" % (role, "/".join(ROLES)))
    with conn() as c:
        if c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise DBError("用户名已存在：%s" % username)
        pw, salt = hash_password(password)
        cur = c.execute(
            "INSERT INTO users(username,password_hash,salt,role,nickname,phone,email,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (username, pw, salt, role, nickname or username, phone, email, now()))
        return _row_user(c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone())


def verify_user(username, password):
    with conn() as c:
        r = c.execute("SELECT * FROM users WHERE username=?", ((username or "").strip(),)).fetchone()
        if not r or not check_password(password or "", r["password_hash"], r["salt"]):
            return None
        c.execute("UPDATE users SET last_login=? WHERE id=?", (now(), r["id"]))
        r = c.execute("SELECT * FROM users WHERE id=?", (r["id"],)).fetchone()
        return _row_user(r)


def get_user(user_id):
    with conn() as c:
        return _row_user(c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


def update_profile(user_id, nickname=None, phone=None, email=None):
    fields, vals = [], []
    for k, v in (("nickname", nickname), ("phone", phone), ("email", email)):
        if v is not None:
            fields.append("%s=?" % k)
            vals.append(v)
    if not fields:
        raise DBError("没有要更新的字段")
    vals.append(user_id)
    with conn() as c:
        c.execute("UPDATE users SET %s WHERE id=?" % ",".join(fields), vals)
    return get_user(user_id)


def change_password(user_id, old, new):
    if len(new or "") < 6:
        raise DBError("新密码至少 6 位")
    with conn() as c:
        r = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not r:
            raise DBError("用户不存在")
        if not check_password(old or "", r["password_hash"], r["salt"]):
            raise DBError("原密码不正确")
        pw, salt = hash_password(new)
        c.execute("UPDATE users SET password_hash=?, salt=? WHERE id=?", (pw, salt, user_id))
    return True


# ---------------------------------------------------------------- 会话
def create_session(user_id, ttl_days=TOKEN_TTL_DAYS):
    token = secrets.token_urlsafe(32)
    exp = (datetime.now() + timedelta(days=ttl_days)).strftime("%Y-%m-%d %H:%M:%S")
    with conn() as c:
        c.execute("INSERT INTO sessions(token,user_id,created_at,expires_at) VALUES(?,?,?,?)",
                  (token, user_id, now(), exp))
    return token, exp


def resolve_session(token):
    """token → user（已过期则删除并返回 None）"""
    if not token:
        return None
    with conn() as c:
        r = c.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
        if not r:
            return None
        if r["expires_at"] < now():
            c.execute("DELETE FROM sessions WHERE token=?", (token,))
            return None
        return get_user(r["user_id"])


def delete_session(token):
    with conn() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))


# ---------------------------------------------------------------- 简历
def list_resumes(user_id):
    with conn() as c:
        rows = c.execute("SELECT * FROM resumes WHERE user_id=? ORDER BY is_default DESC, id DESC",
                         (user_id,)).fetchall()
    return [{"id": r["id"], "title": r["title"], "is_default": bool(r["is_default"]),
             "created_at": r["created_at"], "updated_at": r["updated_at"],
             "字数": len(r["text"] or ""), "text": r["text"]} for r in rows]


def add_resume(user_id, title, text, is_default=None):
    if not (text or "").strip():
        raise DBError("简历正文不能为空")
    title = (title or "").strip() or "未命名简历"
    with conn() as c:
        n = c.execute("SELECT COUNT(*) n FROM resumes WHERE user_id=?", (user_id,)).fetchone()["n"]
        default = 1 if (is_default is True or (is_default is None and n == 0)) else 0
        if default:
            c.execute("UPDATE resumes SET is_default=0 WHERE user_id=?", (user_id,))
        cur = c.execute("INSERT INTO resumes(user_id,title,text,is_default,created_at,updated_at) "
                        "VALUES(?,?,?,?,?,?)", (user_id, title, text, default, now(), now()))
        return cur.lastrowid


def update_resume(user_id, rid, title=None, text=None):
    with conn() as c:
        r = c.execute("SELECT * FROM resumes WHERE id=? AND user_id=?", (rid, user_id)).fetchone()
        if not r:
            raise DBError("简历不存在或无权访问")
        c.execute("UPDATE resumes SET title=?, text=?, updated_at=? WHERE id=?",
                  (title if title is not None else r["title"],
                   text if text is not None else r["text"], now(), rid))
    return True


def set_default_resume(user_id, rid):
    with conn() as c:
        r = c.execute("SELECT 1 FROM resumes WHERE id=? AND user_id=?", (rid, user_id)).fetchone()
        if not r:
            raise DBError("简历不存在或无权访问")
        c.execute("UPDATE resumes SET is_default=0 WHERE user_id=?", (user_id,))
        c.execute("UPDATE resumes SET is_default=1 WHERE id=?", (rid,))
    return True


def delete_resume(user_id, rid):
    with conn() as c:
        cur = c.execute("DELETE FROM resumes WHERE id=? AND user_id=?", (rid, user_id))
        if cur.rowcount == 0:
            raise DBError("简历不存在或无权访问")
        left = c.execute("SELECT id FROM resumes WHERE user_id=? ORDER BY id LIMIT 1",
                         (user_id,)).fetchone()
        if left:
            c.execute("UPDATE resumes SET is_default=1 WHERE id=?", (left["id"],))
    return True


# ---------------------------------------------------------------- 收藏
def list_favorites(user_id):
    with conn() as c:
        rows = c.execute("SELECT * FROM favorites WHERE user_id=? ORDER BY id DESC",
                         (user_id,)).fetchall()
    return [dict(r) for r in rows]


def add_favorite(user_id, job_id, job_name="", company="", city="", salary="", note=""):
    with conn() as c:
        try:
            c.execute("INSERT INTO favorites(user_id,job_id,job_name,company,city,salary,note,created_at)"
                      " VALUES(?,?,?,?,?,?,?,?)",
                      (user_id, job_id, job_name, company, city, salary, note, now()))
        except sqlite3.IntegrityError:
            raise DBError("该岗位已在收藏夹中（%s）" % job_id)
    return True


def delete_favorite(user_id, job_id):
    with conn() as c:
        cur = c.execute("DELETE FROM favorites WHERE user_id=? AND job_id=?", (user_id, job_id))
        if cur.rowcount == 0:
            raise DBError("收藏不存在或无权访问")
    return True


# ---------------------------------------------------------------- 历史
def add_match(user_id, resume_title, top_n, summary, recs):
    with conn() as c:
        c.execute("INSERT INTO match_history(user_id,resume_title,top_n,summary,result_json,created_at)"
                  " VALUES(?,?,?,?,?,?)",
                  (user_id, resume_title, int(top_n), summary,
                   json.dumps(recs, ensure_ascii=False), now()))
    return True


def list_matches(user_id, limit=20):
    with conn() as c:
        rows = c.execute("SELECT * FROM match_history WHERE user_id=? ORDER BY id DESC LIMIT ?",
                         (user_id, limit)).fetchall()
    out = []
    for r in rows:
        recs = json.loads(r["result_json"] or "[]")
        out.append({"id": r["id"], "created_at": r["created_at"], "resume_title": r["resume_title"],
                    "top_n": r["top_n"], "summary": r["summary"],
                    "推荐": [{"排名": x.get("排名"), "总分": x.get("总分"),
                             "岗位ID": x.get("岗位ID"), "岗位名称": x.get("岗位名称"),
                             "公司": x.get("公司"), "城市": x.get("城市"),
                             "岗位薪资": x.get("岗位薪资")} for x in recs]})
    return out


def add_chat(user_id, question, answer, sources, tool_seq):
    with conn() as c:
        c.execute("INSERT INTO chat_history(user_id,question,answer,sources,tool_seq,created_at)"
                  " VALUES(?,?,?,?,?,?)",
                  (user_id, question, answer, json.dumps(sources, ensure_ascii=False),
                   tool_seq or "", now()))
    return True


def list_chats(user_id, limit=20):
    with conn() as c:
        rows = c.execute("SELECT * FROM chat_history WHERE user_id=? ORDER BY id DESC LIMIT ?",
                         (user_id, limit)).fetchall()
    return [{"id": r["id"], "created_at": r["created_at"], "question": r["question"],
             "answer": r["answer"], "sources": json.loads(r["sources"] or "[]"),
             "tool_seq": r["tool_seq"]} for r in rows]


# ---------------------------------------------------------------- 个人中心概览
def user_stats(user_id):
    with conn() as c:
        g = lambda sql: c.execute(sql, (user_id,)).fetchone()[0]      # noqa: E731
        return {
            "简历数": g("SELECT COUNT(*) FROM resumes WHERE user_id=?"),
            "收藏岗位数": g("SELECT COUNT(*) FROM favorites WHERE user_id=?"),
            "匹配次数": g("SELECT COUNT(*) FROM match_history WHERE user_id=?"),
            "提问次数": g("SELECT COUNT(*) FROM chat_history WHERE user_id=?"),
        }


def list_users(limit=100):
    with conn() as c:
        rows = c.execute("SELECT * FROM users ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_row_user(r) for r in rows]


if __name__ == "__main__":
    p = init_db()
    print("数据库就绪：%s" % p)
    with conn() as c:
        for t in ("users", "sessions", "resumes", "favorites", "match_history", "chat_history"):
            n = c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
            print("   %-16s %d 行" % (t, n))
