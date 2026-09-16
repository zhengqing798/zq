# -*- coding: utf-8 -*-
"""pytest 全局配置

1. **隔离测试数据库**：把 `APP_DB` 指到临时目录，避免测试污染真实的 `data/app.db`。
   必须在导入 `src.api.*` 之前设置，所以放在 conftest.py（pytest 会最先加载它）。
2. **显式建表**：`TestClient(app)` 不会触发 FastAPI 的 startup 事件（表是在 startup 里建的），
   所以这里直接调 `db.init_db()`，保证任何测试都能拿到 users/sessions/... 表。
3. 每次会话开始时清空该测试库，保证用例之间互不干扰。
"""
import os
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_TEST_DB = os.path.join(tempfile.gettempdir(), "zq_test_app.db")
os.environ["APP_DB"] = _TEST_DB
for _suffix in ("", "-journal", "-wal"):
    try:
        os.remove(_TEST_DB + _suffix)
    except OSError:
        pass

from src.api import db as _db          # noqa: E402  必须在设置 APP_DB 之后导入

_db.init_db()
