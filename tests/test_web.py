# -*- coding: utf-8 -*-
"""任务11 · Streamlit 前端测试（用官方 `AppTest` 无头执行页面脚本）

为什么不能只用 curl 测前端：
    Streamlit 是 JS 应用，`curl http://127.0.0.1:8501` 只能拿到外壳 HTML，
    业务渲染结果拿不到。`AppTest` 能在**无浏览器**环境下真跑一遍页面脚本并断言组件树，
    这才是"前端真的通了"的证据。

运行：
    pytest -q tests/test_web.py              # 需要后端已启动（uvicorn ... --port 8000）
    pytest -q tests/test_web.py -m "not slow"

注意：
· 本测试会**真调用后端 HTTP 接口**（含注册一个随机用户），因此要求后端在运行；
  后端未启动时自动跳过（不阻塞 CI）。
· 指标卡是自定义 HTML 卡片（美化），所以断言用 `markdown` 文本而非 `st.metric`。
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
    """汇总页面所有文本类组件的内容。

    注意：美化后正文在不同组件里——自定义卡片走 `markdown`，而规模数字在 `caption`、
    局限提示在 `warning`、空态提示在 `info`。断言必须把所有文本组件一起看，否则会误判。
    """
    parts = []
    for attr in ("markdown", "caption", "info", "warning", "success", "text", "title", "header",
                 "subheader"):
        for el in getattr(at, attr, []) or []:
            v = getattr(el, "value", None)
            if isinstance(v, str):
                parts.append(v)
    return "\n".join(parts)


def all_markdown(at):
    return "\n".join(m.value for m in at.markdown)


@pytest.fixture(scope="module")
def app():
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    return at


def test_guest_mode_renders(app):
    """游客模式：四个功能页签都在，且无异常"""
    assert not app.exception, [e.value for e in app.exception]
    labels = [t.label for t in app.tabs]
    for need in ("📄 简历输入", "🎯 匹配推荐", "🏢 岗位聚类", "💬 智能问答"):
        assert need in labels
    assert "👤 个人中心" not in labels          # 未登录不显示个人中心
    assert "人岗匹配推荐系统" in all_text(app)   # 侧边栏品牌块
    # 后端状态与数据规模
    md = all_text(app)
    assert "8836" in md and "8852" in md


def test_guest_cannot_use_saved_resume(app):
    """边界：游客点「保存到我的简历」按钮应处于禁用态"""
    btns = {b.label: b for b in app.button}
    assert "💾 保存到我的简历" in btns
    assert btns["💾 保存到我的简历"].disabled is True


def test_register_and_login_flow(app):
    """正常：注册 → 自动登录 → 出现个人中心页签"""
    u = "webtest%d" % random.randint(100000, 999999)
    for ti in app.text_input:
        if ti.key == "ru":
            ti.set_value(u)
        if ti.key == "rp":
            ti.set_value("pw123456")
        if ti.key == "rn":
            ti.set_value("前端测试用户")
    app.run()
    btn = [b for b in app.button if b.label == "注册并登录"][0]
    btn.click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert app.session_state.get("token")
    assert "👤 个人中心" in [t.label for t in app.tabs]
    assert "前端测试用户" in all_text(app)

    # 未登录时游客态的两个页签
    assert "📁 我的简历" in [t.label for t in app.tabs]
    assert "还没有保存的简历" in all_text(app)


def test_parse_match_favorite_flow(app):
    """正常：解析简历 → 匹配 Top-N → 收藏岗位（一条完整业务链路）"""
    # ① 解析
    btn = [b for b in app.button if b.label == "解析这份文本"][0]
    btn.click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert app.session_state.get("resume_id", "").startswith("rs_")
    md = all_text(app)
    assert "解析结果" in md and "技能" in md

    # ② 保存到我的简历
    [b for b in app.button if "保存到我的简历" in b.label][0].click().run()
    assert not app.exception
    assert "已保存" in " ".join(s.value for s in app.success)

    # ③ 匹配
    [b for b in app.button if b.label == "开始匹配"][0].click().run()
    assert not app.exception
    result = app.session_state.get("match_result")
    assert result and result["推荐数"] >= 1
    assert result["打分范围"] == 8836
    assert result.get("已存历史") is True          # 登录后自动写入匹配历史
    md = all_text(app)
    assert "推荐岗位数" in md and "权重版本" in md
    # 每条推荐都有六维分与推荐理由
    for x in result["推荐"]:
        for d in ("技能", "经验", "学历", "地域", "薪资", "专业证书"):
            assert 0 <= x[d] <= 100
        assert x["推荐理由"]

    # ④ 收藏第一个岗位
    fav = [b for b in app.button if "收藏这个岗位" in b.label]
    assert fav, "推荐卡片上应出现收藏按钮"
    fav[0].click().run()
    assert not app.exception
    assert any("已收藏" in s.value for s in app.success)


def test_personal_center_shows_data(app):
    """正常：个人中心应能看到上面产生的简历/收藏/匹配历史"""
    md = all_text(app)
    assert "个人中心 · 概览" in md
    # 统计卡（自定义 HTML，含标签文字）
    for label in ("我的简历", "收藏岗位", "匹配次数", "提问次数"):
        assert label in md
    # 简历/收藏/历史三个子页签均在
    labels = [t.label for t in app.tabs]
    for need in ("📁 我的简历", "⭐ 我的收藏", "🕘 匹配历史", "💬 问答记录", "⚙️ 账号设置"):
        assert need in labels


def test_cluster_page(app):
    """正常：聚类页渲染出主方案、簇数、K 依据"""
    md = all_text(app)
    assert "K=9" in md
    assert "0.6735" in md and "1.0000" in md      # 轮廓系数 / ARI
    assert "统计推断" in md                        # 局限说明必须在


def test_no_errors_anywhere(app):
    """总体：任何一次交互都不应产生未捕获异常或 error 级提示"""
    assert not app.exception, [e.value for e in app.exception]
    assert not app.error, [e.value for e in app.error]
