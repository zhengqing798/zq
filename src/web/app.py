# -*- coding: utf-8 -*-
"""任务11 · Streamlit 前端：上传简历 → 匹配 → 推荐 → 对话

设计要点
--------
1. **通过 HTTP 调 FastAPI**（不 import 任何业务模块）——所以本进程很轻，不加载 BGE/torch/FAISS，
   镜像可以做得很小；同时"前后端集成"是**真链路**（可用 curl/接口测试验证）。
2. 后端地址用环境变量：本地 `http://127.0.0.1:8000`，Docker 里给 `API_BASE=http://api:8000`。
3. 每个结论都展示 `来源`，与项目"每个数字可溯源"的口径一致；局限说明固定放在侧边栏与各页底部。

启动：
    streamlit run src/web/app.py --server.port 8501
    一键脚本：scripts/run_web.ps1
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                          # noqa: E402
import requests                                                          # noqa: E402
import streamlit as st                                                   # noqa: E402

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000").rstrip("/")
DIMS = ["技能", "经验", "学历", "地域", "薪资", "专业证书"]
DIM_WEIGHT_HINT = {"技能": 0.38, "经验": 0.18, "学历": 0.12, "地域": 0.16, "薪资": 0.10, "专业证书": 0.06}

for _f in ("Microsoft YaHei", "SimHei", "SimSun"):
    try:
        matplotlib.font_manager.findfont(_f, fallback_to_default=False)
        plt.rcParams["font.sans-serif"] = [_f]
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="岗位-简历人岗匹配推荐系统", page_icon="🎯", layout="wide")

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
2022.07-2025.06 某软件公司 测试工程师，负责接口自动化测试与性能压测

【项目经验】
使用 Python + Selenium 搭建 UI 自动化框架，覆盖 300 条用例
"""


# ---------------------------------------------------------------- HTTP 封装
def api(method, path, **kw):
    url = API_BASE + path
    kw.setdefault("timeout", 300)
    try:
        r = requests.request(method, url, **kw)
    except requests.exceptions.ConnectionError:
        st.error("连不上后端 `%s`。请先在另一个终端启动：\n\n"
                 "```\nuvicorn src.api.main:app --host 127.0.0.1 --port 8000\n```" % API_BASE)
        st.stop()
    if r.status_code >= 400:
        try:
            d = r.json()
            msg = d.get("error") or d.get("detail") or r.text
            hint = d.get("hint") or ""
        except Exception:
            msg, hint = r.text, ""
        st.warning("接口返回 %d：%s%s" % (r.status_code, msg, ("\n\n提示：" + hint) if hint else ""))
        return None
    return r.json()


def sources(items, title="来源"):
    if not items:
        return
    with st.expander("📎 %s（%d 条）" % (title, len(items))):
        for s in items:
            st.markdown("- `%s`" % s)


def dim_bars(dims):
    """六维分：用进度条展示（比雷达图更直观，且无字体问题）"""
    for d in DIMS:
        v = float(dims.get(d, 0))
        c1, c2 = st.columns([1, 5])
        c1.markdown("**%s** <span style='color:#888;font-size:12px'>w=%.2f</span>"
                    % (d, DIM_WEIGHT_HINT.get(d, 0)), unsafe_allow_html=True)
        c2.progress(min(max(v / 100.0, 0.0), 1.0), text="%.1f 分" % v)


def radar(dims, title="六维得分"):
    labels = DIMS
    vals = [float(dims.get(d, 0)) for d in labels]
    ang = [i / len(labels) * 2 * 3.1415926 for i in range(len(labels))]
    ang += ang[:1]
    vals += vals[:1]
    fig = plt.figure(figsize=(3.6, 3.6), dpi=110)
    ax = fig.add_subplot(111, polar=True)
    ax.plot(ang, vals, "o-", linewidth=2, color="#2E6BE6")
    ax.fill(ang, vals, alpha=0.22, color="#2E6BE6")
    ax.set_xticks(ang[:-1])
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=7, color="#999")
    ax.set_title(title, fontsize=11, pad=14)
    fig.tight_layout()
    return fig


def limitations():
    with st.expander("⚠️ 已知局限（如实说明）"):
        st.markdown(
            "- **无人工金标**：评分/匹配/检索的真值都由规则生成，不能宣称「准确率 X%」\n"
            "- **简历侧为合成数据**：500 份简历是合成的，岗位侧 8,836 条为真实抓取\n"
            "- **只覆盖 16 城 / 4 省**（福建、浙江、江苏、安徽），其他城市查不到不等于没有岗位\n"
            "- **`经验要求` 字段 24.69% 错位**（2,182 个岗位），系统按「信息缺失」处理\n"
            "- **无公司维度检索**：只有公司名称，没有公司 ID/规模/回复行为字段\n"
            "- **模型口径是规则的蒸馏**：任务5 模型用规则分作标签训练，任务8 实测 Spearman 0.9909")


# ---------------------------------------------------------------- 侧边栏
with st.sidebar:
    st.markdown("## 🎯 人岗匹配推荐系统")
    st.caption("行业大数据分析实践 · 23大数据班 · 任务11 前后端集成")
    st.markdown("后端：`%s`" % API_BASE)
    if st.button("🔄 检查后端状态", width="stretch"):
        st.session_state["health"] = api("GET", "/api/health")
    if "health" not in st.session_state:
        st.session_state["health"] = api("GET", "/api/health")
    h = st.session_state.get("health") or {}
    if h.get("ok"):
        st.success("后端就绪")
        me = h.get("匹配引擎", {})
        rg = h.get("RAG检索", {})
        sc = h.get("评分模型", {})
        st.metric("岗位库", "%s 个" % me.get("岗位数", "—"))
        st.metric("知识库卡片", "%s 张" % rg.get("卡片数", "—"))
        st.metric("匹配权重版本", me.get("权重版本", "—"))
        st.caption("评分模型：%s ｜ 特征 36 维" % ("就绪" if sc.get("就绪") else "未就绪"))
        with st.expander("预加载耗时 / 组件详情"):
            st.json(h, expanded=False)
    else:
        st.error("后端未就绪")
    st.divider()
    st.caption("每个结论都带 `来源`，可逐条回溯到报告或数据文件。")

st.title("岗位-简历人岗匹配推荐系统")
st.caption("上传/粘贴简历 → 六维匹配打分 → Top-N 推荐 → 智能问答（全部带来源）")

tab1, tab2, tab3, tab4 = st.tabs(["📄 ① 简历输入", "🎯 ② 匹配推荐", "🏢 ③ 岗位聚类", "💬 ④ 智能问答"])

# ================================================================ ① 简历输入
with tab1:
    st.subheader("简历输入：粘贴文本 或 上传 PDF")
    st.caption("两条通路**共用同一个解析器**，结果可验证——这是任务6 的设计契约。")
    c1, c2 = st.columns([3, 2])
    with c1:
        text = st.text_area("粘贴简历正文", value=st.session_state.get("resume_text", SAMPLE), height=320)
        if st.button("解析这份文本", type="primary"):
            j = api("POST", "/api/resume/parse_text", json={"resume_text": text})
            if j:
                st.session_state["resume_id"] = j["resume_id"]
                st.session_state["resume_text"] = text
                st.session_state["parsed"] = j
                st.success("解析完成，会话 ID：`%s`" % j["resume_id"])
    with c2:
        up = st.file_uploader("或上传 PDF 简历（一份 PDF = 一份简历）", type=["pdf"])
        if up is not None and st.button("解析这份 PDF"):
            j = api("POST", "/api/resume/parse",
                    files={"file": (up.name, up.getvalue(), "application/pdf")})
            if j:
                st.session_state["resume_id"] = j["resume_id"]
                st.session_state["parsed"] = j
                st.success("PDF 解析完成，会话 ID：`%s`" % j["resume_id"])
        st.info("PDF 通路会做**文本质量检测**：可打印字符占比 <60% 时告警"
                "（扫描件或字体缺 ToUnicode 映射），提示改用粘贴文本。")

    p = st.session_state.get("parsed")
    if p:
        st.divider()
        st.markdown("#### 解析结果")
        m1, m2, m3, m4 = st.columns(4)
        f = p["解析字段"]
        m1.metric("姓名", f.get("姓名") or "（未识别）")
        m2.metric("期望岗位", (f.get("期望岗位") or "—")[:12])
        m3.metric("期望城市", f.get("期望城市") or "—")
        m4.metric("工作年限", "%s 年" % f.get("工作年限", "—"))
        st.markdown("**技能（%d 项）**：%s" % (p["技能数"], "、".join(p["技能列表"]) or "—"))
        if p.get("解析告警"):
            st.warning("解析告警：" + "；".join(p["解析告警"]))
        with st.expander("全部解析字段"):
            st.json(f)
        st.info("下一步 → 切到 **🎯 匹配推荐** 页看 Top-N 岗位。")

# ================================================================ ② 匹配推荐
with tab2:
    st.subheader("人岗匹配：对全量 8,836 个岗位逐对打分，返回 Top-N")
    rid = st.session_state.get("resume_id")
    if not rid:
        st.warning("请先在 **📄 简历输入** 页解析一份简历。")
    else:
        c1, c2 = st.columns([1, 4])
        top_n = c1.slider("返回条数", 1, 20, 5)
        if c2.button("开始匹配", type="primary") or st.session_state.get("matched"):
            j = api("POST", "/api/match", json={"resume_id": rid, "top_n": top_n})
            if j:
                st.session_state["matched"] = True
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("推荐岗位数", j["推荐数"])
                m2.metric("打分范围", "%s 个岗位" % j["打分范围"])
                m3.metric("权重版本", j["权重版本"])
                m4.metric("打分耗时", "%.2f s" % j["耗时秒"])
                src = j["简历摘要"]
                st.caption("简历：%s ｜ 期望城市 %s ｜ 学历序数 %s ｜ %s 年经验 ｜ 技能 %d 项"
                           % (src["姓名"], src["期望城市"] or "—", src["学历序数"],
                              src["工作年限"], src["技能数"]))
                sources(j["来源"])
                st.divider()
                for x in j["推荐"]:
                    with st.container(border=True):
                        a, b = st.columns([3, 2])
                        with a:
                            st.markdown("### %d. %s ｜ **%.2f 分**" % (x["排名"], x["岗位名称"], x["总分"]))
                            st.markdown("🏢 %s ｜ 📍 %s ｜ 💰 %s ｜ 🎓 %s ｜ 🧭 %s"
                                        % (x["公司"], x["城市"], x["岗位薪资"],
                                           x["学历要求"] or "—", x["经验要求"] or "—"))
                            st.markdown("**推荐理由**：%s" % x["推荐理由"])
                            st.caption("岗位ID `%s` ｜ 技能命中 %s/%s ｜ TF-IDF 余弦 %s ｜ 距离 %s km"
                                       % (x["岗位ID"], x["技能命中数"], x["岗位技能要求数"],
                                          x["余弦分"], x["距离km"]))
                        with b:
                            st.pyplot(radar({d: x[d] for d in DIMS}, "六维得分"), width="stretch")
                        with st.expander("六维分明细"):
                            dim_bars({d: x[d] for d in DIMS})
                st.caption("已展示 %d 条中的全部；打分口径为六维加权（技能 = 覆盖率 0.6 + TF-IDF 余弦 0.4）"
                           % len(j["推荐"]))
        limitations()

# ================================================================ ③ 岗位聚类
with tab3:
    st.subheader("岗位聚类画像（任务7：K-Means 定 K=9）")
    j = api("GET", "/api/cluster/list")
    if j:
        m1, m2, m3 = st.columns(3)
        m1.metric("主方案", j["主方案"])
        m2.metric("簇数", j["簇数"])
        m3.metric("覆盖岗位", "%d 个" % sum(x["岗位数"] for x in j["簇"]))
        st.caption("定 K 依据：轮廓系数峰值 **0.6735**（K=9），肘部法指向 K=5，"
                   "ARI = **1.0000**（换随机种子结果一致）。")
        st.dataframe(j["簇"], width="stretch", hide_index=True)
        if j.get("各方案") and len(j["方案"]) > 1:
            with st.expander("其他方案（对照 / 二阶细分）"):
                pick = st.selectbox("方案", j["方案"], index=min(2, len(j["方案"]) - 1))
                st.dataframe(j["各方案"][pick], width="stretch", hide_index=True)
        sources(j["来源"])
        st.divider()
        st.markdown("#### 查某个簇的画像")
        name = st.text_input("簇名关键词", value="软件测试",
                             help="例如：软件测试 / 算法 / 后端 / 质量检验")
        if st.button("查询簇画像"):
            r = api("GET", "/api/cluster/profile", params={"name": name})
            if r:
                st.markdown("**%s**" % r.get("summary", ""))
                for d in (r.get("data") or []):
                    with st.container(border=True):
                        st.markdown("**%s** ｜ 规模 %s ｜ 占比 %s ｜ 薪资中位数 %s"
                                    % (d.get("簇名") or "—", d.get("岗位数") or "—",
                                       d.get("占比") or "—", d.get("薪资中位数") or "—"))
                        st.caption("主导大类 %s ｜ 主要城市 %s"
                                   % (d.get("主导大类") or "—", d.get("主要城市") or "—"))
                        if d.get("高频技能Top8"):
                            st.caption("高频技能：" + str(d["高频技能Top8"])[:160])
                sources(r.get("来源"))
        st.warning("簇名是**统计推断**（主导大类 + 特征技能 lift + 关键词规则），未做人工逐簇确认；"
                   "最大簇占 51.45%，已做二阶细分（K=8）。")

# ================================================================ ④ 智能问答
with tab4:
    st.subheader("Agent 智能问答（Function Calling + 9 工具）")
    st.caption("问题 → DeepSeek 选工具 → 本地工具执行 → 带来源的中文回答；最多 6 轮、12 次工具调用。")
    q = st.text_input("问点什么", value="福州市的Java岗位有多少个？")
    c1, c2 = st.columns([1, 1])
    ask = c1.button("提问", type="primary")
    nocache = c2.checkbox("忽略缓存（强制真实调用，较慢）", value=False)
    if ask and q.strip():
        with st.spinner("正在调用工具与模型…"):
            j = api("POST", "/api/chat", json={"question": q, "use_cache": not nocache})
        if j:
            st.markdown(j["回答"])
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("工具序列", j["工具序列"] or "（未调用）")
            m2.metric("轮数", j["轮数"])
            m3.metric("耗时", "%.1f s" % j["耗时秒"])
            m4.metric("缓存", "命中" if j["缓存命中"] else "未命中")
            st.caption("Prompt 版本 `%s` ｜ 模型 `%s` ｜ tokens %s"
                       % (j["prompt版本"], j["模型"], j["tokens"]))
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
    limitations()

st.divider()
st.caption("岗位-简历人岗匹配推荐系统 ｜ 任务11 前后端集成（Streamlit 前端 + FastAPI 后端）"
           " ｜ 后端接口文档：`%s/docs`" % API_BASE)
