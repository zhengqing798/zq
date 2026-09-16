# -*- coding: utf-8 -*-
"""任务11 · Streamlit 前端测试（用官方 `AppTest` 无头执行页面脚本）

为什么不能只用 curl 测前端：
    Streamlit 是 JS 应用，`curl http://127.0.0.1:8501` 只能拿到外壳 HTML，
    业务渲染结果拿不到。`AppTest` 能在**无浏览器**环境下真跑一遍页面脚本并断言组件树，
    这才是"前端真的通了"的证据。

布局说明（v2：顶部导航）：
    页面由**顶部导航按钮**切换（`📄 简历 / 🎯 职位推荐 / 🏢 岗位聚类 / 💬 智能问答 / 👤 个人中心`），
    状态存在 `st.session_state["page"]`。所以用例必须先 `goto()` 切到目标页再断言。
    登录/注册表单在顶部 `st.popover` 里（AppTest 可直接访问其内部组件）。

运行：
    pytest -q tests/test_web.py              # 需要后端已启动（uvicorn ... --port 8000）

注意：
· 本测试会**真调用后端 HTTP 接口**（含注册一个随机用户），因此要求后端在运行；
  后端未启动时自动跳过（不阻塞 CI）。
· 指标卡是自定义 HTML 卡片（美化），所以断言用文本类组件而非 `st.metric`。
"""
import os
import random
import sys

import pytest
from streamlit.testing.v1 import AppTest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

APP = os.path.join(ROOT, "src", "web", "app.py")
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")

NAV = ["🏠 首页", "📄 简历", "🎯 职位推荐", "🏢 岗位聚类", "💬 智能问答"]


def backend_alive():
    try:
        import requests
        return requests.get(API_BASE + "/api/health", timeout=5).status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not backend_alive(),
                       reason="后端未启动（请先跑 scripts/run_api.ps1），跳过前端测试"),
]


def all_text(at):
    """汇总页面所有文本类组件。

    美化后正文分散在不同组件里：自定义卡片走 `markdown`，规模数字在 `caption`，
    局限提示在 `warning`，空态提示在 `info`。断言必须一起看，否则会误判。
    """
    parts = []
    for attr in ("markdown", "caption", "info", "warning", "success", "text",
                 "title", "header", "subheader"):
        for el in getattr(at, attr, []) or []:
            v = getattr(el, "value", None)
            if isinstance(v, str):
                parts.append(v)
    return "\n".join(parts)


def nav_buttons(at):
    return [b.label for b in at.button if b.label in NAV or b.label == "👤 个人中心"]


def goto(at, label):
    """点击顶部导航切页（会触发 st.rerun）"""
    btns = [b for b in at.button if b.label == label]
    assert btns, "找不到导航按钮：%s（当前有：%s）" % (label, [b.label for b in at.button])
    btns[0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def click(at, label_contains):
    btns = [b for b in at.button if label_contains in (b.label or "")]
    assert btns, "找不到按钮：%s（当前有：%s）" % (label_contains, [b.label for b in at.button])
    btns[0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


@pytest.fixture(scope="module")
def app():
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    return at


# ================================================================ 顶部导航 / 游客态
def test_top_nav_layout(app):
    """正常：顶部导航渲染出五个功能入口（含首页；无侧边栏、无 Hero 大标题）"""
    assert not app.exception, [e.value for e in app.exception]
    assert nav_buttons(app) == NAV
    assert "👤 个人中心" not in [b.label for b in app.button]   # 未登录不显示
    assert app.session_state.get("page") == "home"              # 默认落在首页
    md = all_text(app)
    assert "人岗匹配推荐" in md                                  # 左上角品牌
    assert "全部结论可溯源" not in md                            # 已删除的副标题不应存在
    assert "8,836" in md or "8836" in md          # 首页显示岗位总数


def test_guest_cannot_save_resume(app):
    """边界：游客的「保存到我的简历」按钮应为禁用态（需先切到简历页）"""
    goto(app, "📄 简历")
    btns = {b.label: b for b in app.button}
    assert "💾 保存到我的简历" in btns
    assert btns["💾 保存到我的简历"].disabled is True


def test_page_switch_keeps_no_error(app):
    """正常：四个导航页都能切换且不报错"""
    for label in NAV:
        goto(app, label)
        assert not app.error, [e.value for e in app.error]
    goto(app, "📄 简历")


# ================================================================ 注册 / 登录
def test_register_and_login(app):
    """正常：顶部弹出层注册 → 自动登录 → 出现个人中心入口"""
    u = "webtest%d" % random.randint(100000, 999999)
    for ti in app.text_input:
        if ti.key == "ru":
            ti.set_value(u)
        if ti.key == "rp":
            ti.set_value("pw123456")
        if ti.key == "rn":
            ti.set_value("前端测试用户")
    app.run()
    click(app, "注册并登录")
    assert app.session_state.get("token")
    assert "👤 个人中心" in [b.label for b in app.button]
    assert "前端测试用户" in all_text(app)


# ================================================================ 简历 → 匹配 → 收藏
def test_parse_resume(app):
    """正常：简历页解析文本，并保存到个人中心"""
    goto(app, "📄 简历")
    click(app, "解析这份文本")
    assert app.session_state.get("resume_id", "").startswith("rs_")
    md = all_text(app)
    assert "解析结果" in md
    assert "技能" in md

    click(app, "保存到我的简历")
    assert any("已保存" in s.value for s in app.success)


def test_match_and_favorite(app):
    """正常：职位推荐页匹配 Top-N → 收藏岗位（完整业务链路）"""
    goto(app, "🎯 职位推荐")
    click(app, "开始匹配")
    result = app.session_state.get("match_result")
    assert result and result["推荐数"] >= 1
    assert result["打分范围"] == 8836
    assert result.get("已存历史") is True            # 登录后自动写匹配历史
    for x in result["推荐"]:
        for d in ("技能", "经验", "学历", "地域", "薪资", "专业证书"):
            assert 0 <= x[d] <= 100
        assert x["推荐理由"]
    md = all_text(app)
    assert "推荐岗位数" in md and "权重版本" in md
    assert "已存入匹配历史" in md

    click(app, "⭐ 收藏")
    assert any("已收藏" in s.value for s in app.success)


def test_cluster_page(app):
    """正常：岗位聚类页渲染主方案、簇数与定 K 指标"""
    goto(app, "🏢 岗位聚类")
    md = all_text(app)
    assert "K=9" in md
    assert "0.6735" in md and "1.0000" in md          # 轮廓系数 / ARI
    assert "岗位聚类" in md                            # 页面标题
    assert app.dataframe, "簇明细表应渲染为 dataframe"   # 表格内容不在 markdown 里


def test_chat_page_renders(app):
    """正常：智能问答页渲染输入框与示例问题（不真提问，避免依赖外网）

    注意：「工具轨迹」展开项只在**提问成功之后**才渲染，所以这里只断言页面骨架。
    """
    goto(app, "💬 智能问答")
    md = all_text(app)
    assert "智能问答" in md
    assert "福州市的Java岗位有多少个" in md
    assert "厦门有哪些 Java 开发岗位" in md          # 示例问题列表


# ================================================================ 个人中心
def test_personal_center(app):
    """正常：个人中心显示概览统计与五个子页签"""
    goto(app, "👤 个人中心")
    md = all_text(app)
    assert "个人中心" in md
    for label in ("我的简历", "收藏岗位", "匹配次数", "提问次数"):
        assert label in md
    labels = [t.label for t in app.tabs]
    for need in ("📁 我的简历", "⭐ 我的收藏", "🕘 匹配历史", "💬 问答记录", "⚙️ 账号设置"):
        assert need in labels
    assert not app.error, [e.value for e in app.error]


def test_no_errors_anywhere(app):
    """总体：任何一次交互都不应产生未捕获异常或 error 级提示"""
    assert not app.exception, [e.value for e in app.exception]
    assert not app.error, [e.value for e in app.error]
