# -*- coding: utf-8 -*-
"""任务11 · Streamlit 前端：顶部导航式布局（参考 BOSS直聘 / 智联招聘）

布局说明
--------
┌──────────────────────────────────────────────────────────────────┐
│ 🎯 系统名        [简历][职位推荐][岗位聚类][智能问答][个人中心]     登录/注册 │  ← 顶部导航
├──────────────────────────────────────────────────────────────────┤
│  页面内容（招聘网站风格：岗位卡片 + 橙色薪资 + 标签徽章）             │
└──────────────────────────────────────────────────────────────────┘

设计要点
--------
1. **通过 HTTP 调 FastAPI**（不 import 任何业务模块）——本进程不加载 BGE/torch/FAISS/模型，
   镜像可以做得很小；"前后端集成"是**真链路**（可用 Swagger / 接口测试验证）。
2. 后端地址用环境变量：本地 `http://127.0.0.1:8000`，Docker 里给 `API_BASE=http://api:8000`。
3. 无侧边栏：导航用顶部按钮，当前页用 `type="primary"` 高亮；页面切换靠 `st.session_state["page"]`。
4. 视觉：主题配置（`.streamlit/config.toml`）+ 少量 CSS（卡片/徽章/橙色薪资/导航条）。
   配色参考招聘网站：主色蓝 + **薪资橙**，岗位卡呈"标题＋薪资右对齐＋公司＋标签＋理由"。

启动：streamlit run src/web/app.py --server.port 8501
"""
import os

import altair as alt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                          # noqa: E402
import pandas as pd                                                       # noqa: E402
import requests                                                          # noqa: E402
import streamlit as st                                                   # noqa: E402

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000").rstrip("/")
DIMS = ["技能", "经验", "学历", "地域", "薪资", "专业证书"]
DIM_WEIGHT_HINT = {"技能": 0.38, "经验": 0.18, "学历": 0.12,
                   "地域": 0.16, "薪资": 0.10, "专业证书": 0.06}

for _f in ("Microsoft YaHei", "SimHei", "SimSun"):
    try:
        matplotlib.font_manager.findfont(_f, fallback_to_default=False)
        plt.rcParams["font.sans-serif"] = [_f]
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="岗位-简历人岗匹配推荐系统", page_icon="🎯",
                   layout="wide", initial_sidebar_state="collapsed")

SAMPLE = """姓名：张伟
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
2022.07-2025.06 某软件公司 测试工程师，负责接口自动化测试与压力测试

【项目经验】
使用 Python + Selenium 搭建 UI 自动化框架，覆盖 300 条用例
"""


# ================================================================ 样式
def inject_css():
    st.markdown("""
<style>
/* 容器与留白 */
.block-container { padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1400px; }
header[data-testid="stHeader"] { background: transparent; height: 0; }
#MainMenu, footer { visibility: hidden; }

/* ---------- 顶部导航条 ---------- */
.navbar {
  display:flex; align-items:center; gap:10px;
  background:#fff; border:1px solid #E6EDF7; border-bottom:2px solid #EAF0FA;
  border-radius:12px; padding:10px 16px; margin-bottom:14px;
  box-shadow:0 2px 10px rgba(31,41,55,.05);
}
.brand { display:flex; align-items:center; gap:8px; }
.brand .logo {
  width:34px; height:34px; border-radius:9px; display:flex; align-items:center;
  justify-content:center; font-size:18px;
  background:linear-gradient(135deg,#2E6BE6,#00A6A7); color:#fff;
}
.brand .name { font-size:16.5px; font-weight:800; color:#16233A; line-height:1.15; }
.brand .sub  { font-size:11px; color:#8896AB; }
/* 导航按钮：扁平化，当前页高亮 */
div[data-testid="stHorizontalBlock"] .stButton > button[kind="secondary"] {
  background:transparent; border:none; color:#41506B; font-weight:600;
  padding:4px 6px; box-shadow:none;
}
div[data-testid="stHorizontalBlock"] .stButton > button[kind="secondary"]:hover {
  color:#2E6BE6; background:#F2F6FE;
}
div[data-testid="stHorizontalBlock"] .stButton > button[kind="primary"] {
  border-radius:8px; font-weight:700;
}

/* ---------- 卡片 ---------- */
.card {
  background:#fff; border:1px solid #E6EDF7; border-radius:14px; padding:16px 18px;
  box-shadow:0 2px 10px rgba(31,41,55,.05); transition:.18s;
}
.card:hover { box-shadow:0 10px 24px rgba(46,107,230,.14); transform:translateY(-2px); }

/* 岗位卡（招聘网站风格） */
.job { background:#fff; border:1px solid #E6EDF7; border-radius:14px; padding:16px 20px;
  box-shadow:0 2px 10px rgba(31,41,55,.05); transition:.18s; }
.job:hover { box-shadow:0 10px 24px rgba(46,107,230,.16); transform:translateY(-2px); }
.job .title { font-size:18px; font-weight:700; color:#16233A; }
.job .salary { font-size:19px; font-weight:800; color:#FF6A00; white-space:nowrap; }
.job .co { font-size:13.5px; color:#41506B; margin-top:6px; }
.job .meta { font-size:12.5px; color:#8896AB; margin-top:4px; }

/* 指标卡 */
.kpi { background:linear-gradient(160deg,#F7FAFF 0%,#EEF4FF 100%);
  border:1px solid #DCE7FA; border-radius:14px; padding:14px 16px; }
.kpi .v { font-size:25px; font-weight:800; color:#1B3E8F; line-height:1.25; }
.kpi .l { font-size:12.5px; color:#6B7A90; margin-top:2px; }

/* 药丸标签 */
.pill { display:inline-block; padding:2px 10px; border-radius:6px; font-size:12px;
  margin:3px 6px 0 0; border:1px solid transparent; white-space:nowrap; }
.pill-blue   { background:#EAF1FF; color:#2E6BE6; border-color:#D3E2FF; }
.pill-green  { background:#E7F8F2; color:#0E9F6E; border-color:#CBEFE1; }
.pill-orange { background:#FFF3E6; color:#D97706; border-color:#FFE2C2; }
.pill-purple { background:#F3EDFF; color:#7C4DFF; border-color:#E4D8FF; }
.pill-gray   { background:#F1F5F9; color:#5B6B7F; border-color:#E2E8F0; }
.pill-teal   { background:#E6F8F8; color:#00807F; border-color:#C7EEEE; }

/* 排名圆标 */
.rank { display:inline-flex; width:28px; height:28px; align-items:center; justify-content:center;
  border-radius:8px; color:#fff; font-weight:800; font-size:13.5px; margin-right:10px;
  background:linear-gradient(135deg,#2E6BE6,#7C4DFF); }
.rank.gold   { background:linear-gradient(135deg,#FF9A2E,#FF6A00); }
.rank.silver { background:linear-gradient(135deg,#9AA8B8,#64748B); }

.sec-title { font-size:16px; font-weight:800; color:#16233A; margin:4px 0 12px 0;
  border-left:4px solid #2E6BE6; padding-left:10px; }
.score-big { font-size:22px; font-weight:800; color:#1B3E8F; }
.score-big small { font-size:12px; color:#8896AB; font-weight:500; }

/* 表格 */
[data-testid="stDataFrame"] { border-radius:12px; overflow:hidden; border:1px solid #E6EDF7; }
[data-testid="stAlert"] { border-radius:12px; }
.stButton > button { border-radius:9px; font-weight:600; }
</style>
""", unsafe_allow_html=True)


def sec(title):
    st.markdown('<div class="sec-title">%s</div>' % title, unsafe_allow_html=True)


def kpi(col, value, label):
    col.markdown('<div class="kpi"><div class="v">%s</div><div class="l">%s</div></div>'
                 % (value, label), unsafe_allow_html=True)


def pill(text, kind="blue"):
    return '<span class="pill pill-%s">%s</span>' % (kind, text)


def sources(items, title="来源"):
    if not items:
        return
    with st.expander("📎 %s（%d 条）" % (title, len(items))):
        for s in items:
            st.markdown("- `%s`" % s)


# ================================================================ HTTP
def api(method, path, token=None, **kw):
    url = API_BASE + path
    h = kw.pop("headers", {}) or {}
    if token:
        h["Authorization"] = "Bearer " + token
    kw.setdefault("timeout", 300)
    try:
        r = requests.request(method, url, headers=h, **kw)
    except requests.exceptions.ConnectionError:
        st.error("连不上后端 `%s`。请在另一个终端启动：\n\n"
                 "```\nuvicorn src.api.main:app --host 127.0.0.1 --port 8000\n```" % API_BASE)
        st.stop()
    if r.status_code == 401:
        st.session_state.pop("token", None)
        st.session_state.pop("user", None)
        st.warning("登录已失效，请重新登录。")
        return None
    if r.status_code >= 400:
        try:
            d = r.json()
            msg = d.get("detail") if isinstance(d.get("detail"), dict) else \
                (d.get("error") or d.get("detail") or r.text)
            if isinstance(msg, dict):
                msg = msg.get("error") or str(msg)
            hint = d.get("hint") or ""
            if isinstance(d.get("detail"), dict):
                hint = d["detail"].get("hint") or hint
        except Exception:
            msg, hint = r.text, ""
        st.warning("接口返回 %d：%s%s" % (r.status_code, msg, ("\n\n提示：" + hint) if hint else ""))
        return None
    return r.json()


TOKEN = lambda: st.session_state.get("token")                                   # noqa: E731
USER = lambda: st.session_state.get("user") or {}                               # noqa: E731
LOGGED = lambda: bool(st.session_state.get("token"))                            # noqa: E731


# ================================================================ 图表
def radar(dims, title="六维得分"):
    labels = DIMS
    vals = [float(dims.get(d, 0)) for d in labels]
    ang = [i / len(labels) * 2 * 3.1415926 for i in range(len(labels))]
    ang += ang[:1]
    vals += vals[:1]
    fig = plt.figure(figsize=(3.4, 3.4), dpi=120)
    ax = fig.add_subplot(111, polar=True)
    ax.plot(ang, vals, "o-", linewidth=2.2, color="#2E6BE6", markersize=4)
    ax.fill(ang, vals, alpha=0.20, color="#2E6BE6")
    ax.set_xticks(ang[:-1])
    ax.set_xticklabels(labels, fontsize=10.5, color="#37475E")
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=7, color="#A9B4C4")
    ax.grid(color="#E6EDF7")
    ax.spines["polar"].set_color("#E6EDF7")
    ax.set_title(title, fontsize=11, pad=16, color="#16233A")
    fig.tight_layout()
    return fig


def dim_bar_altair(dims):
    df = pd.DataFrame({"维度": DIMS, "分数": [float(dims.get(d, 0)) for d in DIMS]})
    base = alt.Chart(df).encode(
        y=alt.Y("维度:N", sort=DIMS, axis=alt.Axis(title=None, labelFontSize=12)),
        x=alt.X("分数:Q", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(title=None)),
    )
    bars = base.mark_bar(cornerRadius=6, height=18).encode(
        color=alt.Color("分数:Q", scale=alt.Scale(scheme="blues"), legend=None))
    text = base.mark_text(align="left", dx=4, fontSize=12, color="#37475E").encode(
        text=alt.Text("分数:Q", format=".1f"))
    return (bars + text).properties(height=180).configure_view(stroke=None)


def cluster_donut(rows):
    df = pd.DataFrame(rows)
    df["占比数值"] = df["占比"].str.rstrip("%").astype(float)
    df.loc[df["占比数值"] < 4, "簇名"] = df.loc[df["占比数值"] < 4, "簇名"].str.slice(0, 10) + "…"
    return alt.Chart(df).mark_arc(innerRadius=70, cornerRadius=4).encode(
        theta=alt.Theta("占比数值:Q"),
        color=alt.Color("簇名:N", scale=alt.Scale(scheme="tableau20"), legend=alt.Legend(title="簇")),
        tooltip=["簇名", "岗位数", "占比"],
    ).properties(height=330)


# ================================================================ 顶部导航
inject_css()

if "page" not in st.session_state:
    st.session_state["page"] = "resume"

NAV = [("📄 简历", "resume"), ("🎯 职位推荐", "match"),
       ("🏢 岗位聚类", "cluster"), ("💬 智能问答", "chat")]
if LOGGED():
    NAV.append(("👤 个人中心", "me"))

with st.container():
    c_logo, c_nav, c_user = st.columns([2.6, 6.4, 2.4], vertical_alignment="center")
    with c_logo:
        st.markdown(
            '<div class="brand"><div class="logo">🎯</div>'
            '<div><div class="name">人岗匹配推荐</div>'
            '<div class="sub">岗位-简历智能匹配系统</div></div></div>',
            unsafe_allow_html=True)
    with c_nav:
        nav_cols = st.columns(len(NAV))
        for i, (label, key) in enumerate(NAV):
            if nav_cols[i].button(label, key="nav_%s" % key, width="stretch",
                                  type=("primary" if st.session_state["page"] == key else "secondary")):
                st.session_state["page"] = key
                st.rerun()
    with c_user:
        if LOGGED():
            u = USER()
            with st.popover("👤 %s" % (u.get("nickname") or u.get("username")), width="stretch"):
                st.markdown("**%s**  %s" % (u.get("nickname") or u.get("username"),
                                           pill(u.get("role_label", ""), "purple")),
                            unsafe_allow_html=True)
                st.caption("账号：%s" % u.get("username"))
                st.caption("上次登录：%s" % (u.get("last_login") or "首次"))
                if st.button("个人中心", width="stretch"):
                    st.session_state["page"] = "me"
                    st.rerun()
                if st.button("退出登录", width="stretch"):
                    api("POST", "/api/auth/logout", token=TOKEN())
                    for k in ("token", "user", "parsed", "resume_id", "matched",
                              "match_result", "chat_result"):
                        st.session_state.pop(k, None)
                    st.session_state["page"] = "resume"
                    st.rerun()
        else:
            with st.popover("登录 / 注册", width="stretch"):
                t1, t2 = st.tabs(["登录", "注册"])
                with t1:
                    lu = st.text_input("用户名", key="lu")
                    lp = st.text_input("密码", type="password", key="lp")
                    if st.button("登录", type="primary", width="stretch"):
                        j = api("POST", "/api/auth/login", json={"username": lu, "password": lp})
                        if j:
                            st.session_state["token"] = j["token"]
                            st.session_state["user"] = j["用户"]
                            st.rerun()
                with t2:
                    ru = st.text_input("用户名（3~24 位字母/数字/下划线）", key="ru")
                    rp = st.text_input("密码（至少 6 位）", type="password", key="rp")
                    rn = st.text_input("昵称（可选）", key="rn")
                    rr = st.selectbox("角色", ["求职者", "企业（预留）"], index=0, key="rr")
                    if st.button("注册并登录", type="primary", width="stretch"):
                        j = api("POST", "/api/auth/register",
                                json={"username": ru, "password": rp, "nickname": rn,
                                      "role": "jobseeker" if rr.startswith("求职") else "employer"})
                        if j:
                            st.session_state["token"] = j["token"]
                            st.session_state["user"] = j["用户"]
                            st.rerun()

page = st.session_state["page"]

# 后端状态：只在"简历"页顶部用一行小字提示，不占导航
if "health" not in st.session_state:
    st.session_state["health"] = api("GET", "/api/health", token=TOKEN())
h = st.session_state.get("health") or {}
if not h.get("ok"):
    st.error("后端未就绪，请先启动 FastAPI（`scripts/run_api.ps1`）")

# ================================================================ 📄 简历
if page == "resume":
    sec("简历输入：粘贴文本 或 上传 PDF")
    st.caption("两条通路**共用同一个解析器**，结果可验证——这是任务6 的设计契约。")
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        text = st.text_area("粘贴简历正文", value=st.session_state.get("resume_text", SAMPLE),
                            height=300)
        b1, b2 = st.columns(2)
        if b1.button("解析这份文本", type="primary", width="stretch"):
            j = api("POST", "/api/resume/parse_text", json={"resume_text": text}, token=TOKEN())
            if j:
                st.session_state.update({"resume_id": j["resume_id"], "resume_text": text,
                                         "parsed": j, "matched": False})
                st.success("解析完成，会话 ID：`%s`" % j["resume_id"])
        if b2.button("💾 保存到我的简历", width="stretch", disabled=not LOGGED(),
                     help="登录后可保存，供个人中心与后续匹配复用"):
            j = api("POST", "/api/user/resumes", token=TOKEN(),
                    json={"title": (st.session_state.get("parsed", {}) or {}).get("解析字段", {})
                          .get("期望岗位") or "我的简历", "text": text})
            if j:
                st.success("已保存（id=%s），可在 **👤 个人中心** 查看" % j["id"])
    with c2:
        up = st.file_uploader("或上传 PDF 简历（一份 PDF = 一份简历）", type=["pdf"])
        if up is not None and st.button("解析这份 PDF", width="stretch"):
            j = api("POST", "/api/resume/parse", token=TOKEN(),
                    files={"file": (up.name, up.getvalue(), "application/pdf")})
            if j:
                st.session_state.update({"resume_id": j["resume_id"], "parsed": j, "matched": False})
                st.success("PDF 解析完成，会话 ID：`%s`" % j["resume_id"])
        st.info("PDF 通路会做**文本质量检测**：可打印字符占比 <60% 时告警"
                "（扫描件或字体缺 ToUnicode 映射），提示改用粘贴文本。")

    p = st.session_state.get("parsed")
    if p:
        st.divider()
        sec("解析结果")
        f = p["解析字段"]
        cols = st.columns(4)
        for c, (k, v) in zip(cols, [("姓名", f.get("姓名") or "（未识别）"),
                                    ("期望岗位", f.get("期望岗位") or "—"),
                                    ("期望城市", f.get("期望城市") or "—"),
                                    ("工作年限", "%s 年" % f.get("工作年限", "—"))]):
            kpi(c, v, k)
        st.write("")
        st.markdown("**技能（%d 项）**：%s" % (p["技能数"],
                                          " ".join(pill(s, "blue") for s in p["技能列表"]) or "—"),
                    unsafe_allow_html=True)
        if p.get("未在词典的技能"):
            st.markdown("**词典外技能**：%s" % " ".join(pill(s, "gray")
                                                   for s in p["未在词典的技能"]),
                        unsafe_allow_html=True)
        if p.get("解析告警"):
            st.warning("解析告警：" + "；".join(p["解析告警"]))
        with st.expander("全部解析字段"):
            st.json(f)
        st.info("下一步 → 点顶部 **🎯 职位推荐** 看匹配结果。")
    else:
        st.info("粘贴一份简历后点「解析这份文本」，或直接上传 PDF。"
                "示例文本已预填，可直接点解析体验。")

# ================================================================ 🎯 职位推荐
elif page == "match":
    sec("职位推荐：对全量 8,836 个岗位逐对打分，返回 Top-N")
    saved = []
    if LOGGED():
        jr = api("GET", "/api/user/resumes", token=TOKEN())
        saved = (jr or {}).get("简历", [])
    if not st.session_state.get("resume_id") and not saved:
        st.warning("请先在 **📄 简历** 页解析一份简历，或登录后在个人中心保存简历。")
    else:
        c1, c2, c3 = st.columns([1.6, 1, 1])
        src_label = c1.radio("使用哪份简历", ["本次解析的简历"] + ["📁 %s" % r["title"] for r in saved],
                             horizontal=True, label_visibility="collapsed")
        top_n = c2.slider("返回条数", 1, 20, 5)
        if c3.button("开始匹配", type="primary", width="stretch"):
            body = {"top_n": top_n}
            if src_label.startswith("📁"):
                i = [k for k, r in enumerate(saved) if "📁 %s" % r["title"] == src_label][0]
                body["saved_resume_id"] = saved[i]["id"]
            else:
                body["resume_id"] = st.session_state.get("resume_id")
            j = api("POST", "/api/match", token=TOKEN(), json=body)
            if j:
                st.session_state["matched"] = True
                st.session_state["match_result"] = j

        j = st.session_state.get("match_result") if st.session_state.get("matched") else None
        if j:
            st.write("")
            cols = st.columns(4)
            for c, (v, l) in zip(cols, [(j["推荐数"], "推荐岗位数"),
                                        ("%s 个" % j["打分范围"], "打分范围"),
                                        (j["权重版本"], "权重版本"),
                                        ("%.2f s" % j["耗时秒"], "打分耗时")]):
                kpi(c, v, l)
            src = j["简历摘要"]
            st.caption("简历：%s ｜ 期望城市 %s ｜ 学历序数 %s ｜ %s 年经验 ｜ 技能 %d 项%s"
                       % (src["姓名"], src["期望城市"] or "—", src["学历序数"], src["工作年限"],
                          src["技能数"], " ｜ ✅ 已存入匹配历史" if j.get("已存历史") else ""))
            sources(j["来源"])
            st.write("")
            for x in j["推荐"]:
                rk = "gold" if x["排名"] == 1 else ("silver" if x["排名"] == 2 else "")
                st.markdown('<div class="job">', unsafe_allow_html=True)
                a, b = st.columns([3, 1.5], gap="large")
                with a:
                    st.markdown(
                        '<div style="display:flex;justify-content:space-between;align-items:baseline">'
                        '<div class="title"><span class="rank %s">%d</span>%s</div>'
                        '<div class="salary">%s</div></div>'
                        % (rk, x["排名"], x["岗位名称"], x["岗位薪资"] or "薪资面议"),
                        unsafe_allow_html=True)
                    st.markdown(
                        '<div class="co">%s</div><div class="meta">%s</div>'
                        % (x["公司"],
                           " ｜ ".join([x["城市"] or "—", x["经验要求"] or "经验不限",
                                      x["学历要求"] or "学历不限",
                                      "匹配度 %.1f 分" % x["总分"]])),
                        unsafe_allow_html=True)
                    st.markdown("".join([pill("技能命中 %s/%s" % (x["技能命中数"],
                                                             x["岗位技能要求数"]), "blue"),
                                         pill("TF-IDF 余弦 %s" % x["余弦分"], "teal"),
                                         pill("距离 %s km" % x["距离km"], "gray"),
                                         pill("岗位ID %s" % x["岗位ID"], "gray")]),
                                unsafe_allow_html=True)
                    st.markdown("**推荐理由**：%s" % x["推荐理由"])
                    if LOGGED():
                        if st.button("⭐ 收藏", key="fav_%s" % x["岗位ID"]):
                            r = api("POST", "/api/user/favorites", token=TOKEN(),
                                    json={"job_id": x["岗位ID"]})
                            if r:
                                st.success(r.get("message", "已收藏"))
                with b:
                    st.pyplot(radar({d: x[d] for d in DIMS}, ""))
                with st.expander("六维分明细"):
                    st.altair_chart(dim_bar_altair({d: x[d] for d in DIMS}), width="stretch")
                st.markdown('</div>', unsafe_allow_html=True)
                st.write("")

    with st.expander("⚠️ 已知局限（如实说明）"):
        st.markdown("- **无人工金标**：真值都由规则生成，不能宣称「准确率 X%」\n"
                    "- **简历侧为合成数据**（500 份），岗位侧 8,836 条为真实抓取\n"
                    "- **只覆盖 16 城 / 4 省**（闽浙苏皖）\n"
                    "- **`经验要求` 字段 24.69% 错位**，系统按「信息缺失」处理\n"
                    "- **模型口径是规则的蒸馏**（任务8 实测 Spearman 0.9909）")

# ================================================================ 🏢 岗位聚类
elif page == "cluster":
    sec("岗位聚类画像（任务7：K-Means 定 K=9）")
    j = api("GET", "/api/cluster/list", token=TOKEN())
    if j:
        cols = st.columns(4)
        for c, (v, l) in zip(cols, [(j["主方案"], "主方案"),
                                    (j["簇数"], "簇数"),
                                    ("%d 个" % sum(x["岗位数"] for x in j["簇"]), "覆盖岗位"),
                                    ("0.6735 / 1.0000", "轮廓系数 / ARI")]):
            kpi(c, v, l)
        st.caption("定 K 依据：轮廓系数峰值 **0.6735**（K=9），肘部法指向 K=5（已在文档说明取舍）；"
                   "ARI = **1.0000**（换随机种子结果一致）。")
        a, b = st.columns([1.25, 1], gap="large")
        with a:
            st.altair_chart(cluster_donut(j["簇"]), width="stretch")
        with b:
            st.dataframe(pd.DataFrame(j["簇"])[["簇名", "岗位数", "占比", "薪资中位数"]],
                         width="stretch", hide_index=True, height=330)
        if j.get("各方案") and len(j["方案"]) > 1:
            with st.expander("其他方案（K=5 对照 / 「其他」巨簇的二阶细分 K=8）"):
                pick = st.selectbox("方案", j["方案"], index=min(2, len(j["方案"]) - 1))
                st.dataframe(pd.DataFrame(j["各方案"][pick]), width="stretch", hide_index=True)
        sources(j["来源"])
        st.divider()
        sec("查某个簇的画像")
        c1, c2 = st.columns([3, 1])
        name = c1.text_input("簇名关键词", value="软件测试", label_visibility="collapsed",
                             help="例如：软件测试 / 算法 / 后端 / 质量检验")
        if c2.button("查询", type="primary", width="stretch"):
            st.session_state["cluster_profile"] = api("GET", "/api/cluster/profile",
                                                      token=TOKEN(), params={"name": name})
        r = st.session_state.get("cluster_profile")
        if r:
            st.markdown("**%s**" % r.get("summary", ""))
            for d in (r.get("data") or []):
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown("**%s** ｜ 规模 %s ｜ 占比 %s ｜ 薪资中位数 %s"
                            % (d.get("簇名") or "—", d.get("岗位数") or "—",
                               d.get("占比") or "—", d.get("薪资中位数") or "—"))
                st.caption("主导大类 %s ｜ 主要城市 %s" % (d.get("主导大类") or "—",
                                                     d.get("主要城市") or "—"))
                if d.get("高频技能Top8"):
                    st.caption("高频技能：" + str(d["高频技能Top8"])[:160])
                st.markdown('</div>', unsafe_allow_html=True)
            sources(r.get("来源"))
        st.warning("簇名是**统计推断**（主导大类 + 特征技能 lift + 关键词规则），未做人工逐簇确认；"
                   "最大簇占 51.45%，已做二阶细分（K=8）。")

# ================================================================ 💬 智能问答
elif page == "chat":
    sec("智能问答（Agent · Function Calling + 9 工具）")
    st.caption("问题 → DeepSeek 选工具 → 本地工具执行 → 带来源的中文回答；最多 6 轮、12 次工具调用。")
    c1, c2, c3 = st.columns([4, 1.1, 1.4])
    q = c1.text_input("问点什么", value="福州市的Java岗位有多少个？", label_visibility="collapsed")
    nocache = c2.checkbox("忽略缓存", value=False, help="勾选则强制真实调用（较慢）")
    if c3.button("提问", type="primary", width="stretch") and q.strip():
        with st.spinner("正在调用工具与模型…"):
            j = api("POST", "/api/chat", token=TOKEN(),
                    json={"question": q, "use_cache": not nocache})
        if j:
            st.session_state["chat_result"] = j
    j = st.session_state.get("chat_result")
    if j:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(j["回答"])
        st.markdown('</div>', unsafe_allow_html=True)
        cols = st.columns(4)
        for c, (v, l) in zip(cols, [(j["工具序列"] or "（未调用）", "工具序列"),
                                    (j["轮数"], "轮数"),
                                    ("%.1f s" % j["耗时秒"], "耗时"),
                                    ("命中" if j["缓存命中"] else "未命中", "缓存")]):
            kpi(c, v, l)
        st.caption("Prompt 版本 `%s` ｜ 模型 `%s` ｜ tokens %s%s"
                   % (j["prompt版本"], j["模型"], j["tokens"],
                      " ｜ ✅ 已存入问答记录" if j.get("已存历史") else ""))
        sources(j["来源"])
        with st.expander("工具轨迹（每一步查了什么）"):
            for t in j["工具轨迹"]:
                st.markdown("- **%s**（ok=%s）：%s" % (t["工具"], t["ok"], t.get("结果摘要")))
                st.caption("参数：`%s`" % t.get("参数"))
    with st.expander("可以试试这些问题"):
        for s in ["福州市的Java岗位有多少个？",
                  "厦门有哪些 Java 开发岗位？顺便说下厦门整体的薪资水平。",
                  "岗位可以分成哪几类？软件测试类岗位大概是什么样的？",
                  "薪资是用中位数还是平均数描述更合适？",
                  "匹配系统给一份简历打分要多久？",
                  "帮我看看北京有没有合适的岗位，我想投字节跳动。"]:
            st.markdown("- %s" % s)

# ================================================================ 👤 个人中心
elif page == "me" and LOGGED():
    j = api("GET", "/api/user/stats", token=TOKEN())
    if j:
        s = j["统计"]
        sec("个人中心")
        cols = st.columns(4)
        for c, (v, l) in zip(cols, [(s["简历数"], "我的简历"), (s["收藏岗位数"], "收藏岗位"),
                                    (s["匹配次数"], "匹配次数"), (s["提问次数"], "提问次数")]):
            kpi(c, v, l)
        st.caption("账号：%s ｜ 角色：%s ｜ 注册时间：%s"
                   % (j["用户"]["username"], j["用户"]["role_label"], j["用户"]["created_at"]))

    sub = st.tabs(["📁 我的简历", "⭐ 我的收藏", "🕘 匹配历史", "💬 问答记录", "⚙️ 账号设置"])

    with sub[0]:
        jr = api("GET", "/api/user/resumes", token=TOKEN()) or {}
        rs = jr.get("简历", [])
        if not rs:
            st.info("还没有保存的简历。到 **📄 简历** 页粘贴简历后点「保存到我的简历」。")
        for r in rs:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns([4, 1, 1, 1])
            c1.markdown("**%s** %s" % (r["title"], pill("默认", "green") if r["is_default"] else ""),
                        unsafe_allow_html=True)
            c1.caption("更新于 %s ｜ 约 %s 字" % (r["updated_at"], r["字数"]))
            if c2.button("用这份匹配", key="use_%d" % r["id"]):
                st.session_state["match_result"] = api("POST", "/api/match", token=TOKEN(),
                                                       json={"saved_resume_id": r["id"], "top_n": 5})
                st.session_state["matched"] = True
                st.session_state["page"] = "match"
                st.rerun()
            if not r["is_default"] and c3.button("设为默认", key="def_%d" % r["id"]):
                api("PUT", "/api/user/resumes/%d/default" % r["id"], token=TOKEN())
                st.rerun()
            if c4.button("删除", key="del_%d" % r["id"]):
                api("DELETE", "/api/user/resumes/%d" % r["id"], token=TOKEN())
                st.rerun()
            with st.expander("查看/编辑正文"):
                nt = st.text_input("标题", value=r["title"], key="t_%d" % r["id"])
                nx = st.text_area("正文", value=r["text"], height=200, key="x_%d" % r["id"])
                if st.button("保存修改", key="up_%d" % r["id"]):
                    api("PUT", "/api/user/resumes/%d" % r["id"], token=TOKEN(),
                        json={"title": nt, "text": nx})
                    st.success("已保存")
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    with sub[1]:
        jf = api("GET", "/api/user/favorites", token=TOKEN()) or {}
        fs = jf.get("收藏", [])
        if not fs:
            st.info("还没有收藏。到 **🎯 职位推荐** 页点岗位卡上的「⭐ 收藏」。")
        else:
            df = pd.DataFrame(fs)[["job_id", "job_name", "company", "city", "salary", "note",
                                   "created_at"]]
            df.columns = ["岗位ID", "岗位名称", "公司", "城市", "薪资", "备注", "收藏时间"]
            st.dataframe(df, width="stretch", hide_index=True)
            st.write("")
            c1, c2 = st.columns([3, 1])
            pick = c1.selectbox("取消收藏", ["%s ｜ %s" % (f["job_id"], f["job_name"]) for f in fs],
                                label_visibility="collapsed")
            if c2.button("取消收藏", width="stretch"):
                api("DELETE", "/api/user/favorites/%s" % pick.split(" ｜ ")[0], token=TOKEN())
                st.rerun()

    with sub[2]:
        jm = api("GET", "/api/user/matches", token=TOKEN()) or {}
        hs = jm.get("历史", [])
        if not hs:
            st.info("还没有匹配记录。登录后使用 **🎯 职位推荐** 会自动保存。")
        for h in hs:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("**%s** ｜ %s ｜ Top-%s ｜ 简历：%s"
                        % (h["created_at"], h["summary"], h["top_n"], h["resume_title"]))
            st.markdown("".join(pill("#%s %s（%.1f 分）" % (x["排名"], x["岗位名称"], x["总分"] or 0),
                                     "blue" if (x["排名"] or 9) <= 3 else "gray")
                                for x in h["推荐"]), unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    with sub[3]:
        jc = api("GET", "/api/user/chats", token=TOKEN()) or {}
        cs = jc.get("历史", [])
        if not cs:
            st.info("还没有问答记录。登录后使用 **💬 智能问答** 会自动保存。")
        for c in cs:
            with st.expander("%s ｜ %s %s" % (c["created_at"], c["question"],
                                              "（%s）" % c["tool_seq"] if c["tool_seq"] else "")):
                st.markdown(c["answer"][:1200])
                sources(c["sources"])

    with sub[4]:
        u = USER()
        sec("修改个人资料")
        a, b, c = st.columns(3)
        nn = a.text_input("昵称", value=u.get("nickname", ""))
        np_ = b.text_input("手机号", value=u.get("phone", ""))
        ne = c.text_input("邮箱", value=u.get("email", ""))
        if st.button("保存资料", type="primary"):
            r = api("PUT", "/api/user/profile", token=TOKEN(),
                    json={"nickname": nn, "phone": np_, "email": ne})
            if r:
                st.session_state["user"] = r["用户"]
                st.success("资料已更新")
        st.divider()
        sec("修改密码")
        p1, p2, p3 = st.columns(3)
        po = p1.text_input("原密码", type="password")
        pn = p2.text_input("新密码（至少 6 位）", type="password")
        pc = p3.text_input("确认新密码", type="password")
        if st.button("修改密码"):
            if pn != pc:
                st.warning("两次输入的新密码不一致")
            else:
                r = api("PUT", "/api/user/password", token=TOKEN(),
                        json={"old_password": po, "new_password": pn})
                if r:
                    st.success(r.get("message", "已修改"))
        st.divider()
        st.caption("说明：口令以 **PBKDF2-HMAC-SHA256（20 万次迭代 + 每用户随机盐）** 存储，"
                   "不保存明文；登录令牌有效期 7 天，退出即失效。")

st.divider()
st.caption("岗位-简历人岗匹配推荐系统 ｜ 任务11 前后端集成（Streamlit 前端 + FastAPI 后端）"
           " ｜ 接口文档 `%s/docs` ｜ 数据：8,836 岗位 / 500 简历 / 8,852 知识卡片" % API_BASE)
