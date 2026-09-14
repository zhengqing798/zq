# -*- coding: utf-8 -*-
"""
任务4 · 数据看板（Dashboard）生成脚本

把 `reports/figures/` 里生成的全部可视化图片汇总成一个 HTML 看板，每张图配：
  · 看点（一句话）
  · 数据结论（关键数字，均来自对应图的 CSV）
  · 对系统的启示
并附「交互版」链接（指向同名的 ECharts HTML，可悬浮查看明细）。

输出：reports/数据看板.html（自包含，双击即可打开；图片用相对路径引用 figures/）
运行：python src/analysis/build_dashboard.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "reports", "数据看板.html")

KPI = [
    ("原始采集岗位", "12,355", "条（清洗后 8,836）"),
    ("覆盖城市 / 省份", "16 / 4", "福建·浙江·江苏·安徽"),
    ("月薪中位数 / 平均", "7,671 / 8,392", "元/月（P25-P75：6,006-10,000）"),
    ("技能词 / 企业数", "4,327 / 4,096", "词云已剔除福利与行业词"),
    ("可用简历", "500", "份（结构化 47 列 + 分词 20 列）"),
    ("匹配评分模型", "XGBoost", "T1 MAE 0.827 ｜ T2 NDCG@10 0.867（主口径）"),
]

SECTIONS = [
    ("一、薪资水平与结构", "钱：这批岗位给多少钱、经验能涨多少", [
        ("01_岗位薪资水平对比_柱状图", "岗位薪资水平对比（柱状图）",
         "全部岗位薪资落在哪些档位",
         ["5-8 千是最大档：**42.81%**（3,781 条）；8-10 千 19.43%、10-15 千 24.10%",
          "3 千以下仅 1.00%，15 千以上合计 5.19%",
          "平均 **8,392** 元 / 中位数 **7,671** 元（均值>中位数 → 右偏）"],
         ["薪资宜分层展示（&lt;8千 / 8-15千 / 15千+），不要只报一个平均数",
          "薪资匹配用**区间重叠度**而不是精确相等",
          "薪资不作硬门槛：中位数说明大量岗位薪资接近，用它筛人会误杀"]),
        ("11_薪资统计_直方图与分位数", "全部岗位薪资统计（直方图 + 累计分布 + 分位数）",
         "中位数、平均数、分位数到底差多少",
         ["**中位数 7,671 元** vs **平均数 8,392 元**，差 **721 元（9.4%）**，分布明显右偏",
          "累计曲线：50% ≤7,671、**75% ≤10,000**、90% ≤12,000 元",
          "P25-P75 区间 = **6,006-10,000 元**；最大值 80,004 元（极端值）"],
         ["描述市场行情用**中位数**，薪资预期给 **P25-P75 区间**更稳",
          "&gt;P90（12,000 元）的岗位只占 10%，做薪资预测要标注置信度低",
          "极端值建议截断，避免影响模型与展示"]),
        ("05_经验薪资增长曲线_多折线图", "经验-薪资增长曲线（多折线图）",
         "多干几年能多拿多少、哪个城市给得高",
         ["全部城市平均：1-3年 **7,752** → 3-5年 **8,834** → 5-10年 **9,941** → 10年以上 **12,579** 元（累计 **+62%**）",
          "苏州全程最高（10 年以上 **15,705**），福州起点最低（7,558）",
          "湖州 13,065、宁波 12,768、厦门 12,586、福州 11,436"],
         ["经验是**薪资的核心解释变量**，且 5-10 年后加速 → 既要作门槛也要进打分公式",
          "可按「经验档 × 城市」给简历推导参考薪资区间",
          "跨城市推荐时做期望值校正（如福州→苏州约 +10%）"]),
    ]),
    ("二、岗位与人才需求结构", "岗位：招什么岗、要什么学历经验、要什么技能", [
        ("07_岗位分布_横向柱状图", "岗位分布（岗位大类 + 高频岗位）",
         "这批数据到底在招哪些岗位",
         ["18 个岗位大类中前三：**质量管理 18.19%**、软件开发 13.98%、运维与支持 12.22%",
          "具体岗位 Top：质量工程师 152、测试工程师 67、质量经理 62、软件工程师 54",
          "原始岗位名称 **6,037 种**，其中 **5,196 种只出现 1 次**"],
         ["聚类（任务7）可直接借用这 18 个大类作为簇命名依据",
          "匹配时先按「期望岗位 → 岗位大类」粗筛，候选从 8,836 压到千级再精排",
          "岗位名称归一化仍有优化空间（「其他」占 10.4%）"]),
        ("03_核心技能需求热度_词云", "核心技能需求热度（词云）",
         "市场上最缺什么技能",
         ["剔除 434 种非技能标签后保留 **4,327 个技能词**",
          "Top：**QE 390、Python 349、QC 327、Java 318、QA 280、C++ 270、MySQL 228、Spring 224**",
          "两条主线：软件开发栈 + 质量管理/检验（IQC/IPQC/功能测试）"],
         ["技能是**区分力最强**的维度（单特征 AUC 0.94~0.95）",
          "任务6 直接用 Top-N 技术词构建核心技能词典做加权余弦",
          "QE/QC/QA 属岗位职能缩写，建议单列，不混入「技能命中数」"]),
        ("02_经验要求结构分布_堆叠柱状图", "经验要求结构分布（堆叠柱状图）",
         "企业要几年经验、学历门槛怎么随经验变化",
         ["**3-5 年 2,708 条 + 1-3 年 2,441 条 = 77.4%**，10 年以上仅 117 条",
          "学历构成随经验升高「本科化」：1-3年 48.55% → 5-10年 **65.87%** → 10年以上 **68.38%**",
          "同期大专占比从 41.01% 降到 29.91%"],
         ["经验匹配按**等级差值**给分，而不是二值判断",
          "5 年以上岗位若简历是大专，匹配分应适度下调（本科占比近 70%）",
          "按经验等级做分层召回：应届→1-3年岗，3年+→3-5年岗"]),
        ("04_学历要求门槛分析_饼状图", "学历要求门槛分析（饼状图）",
         "学历门槛有多高",
         ["**本科 55.75% + 大专 34.25% = 90.0%**；硕士 4.27%、中专/中技 2.93%、高中 2.21%、博士 0.59%",
          "硕士及以上门槛岗位合计仅 **4.86%**",
          "大专简历可覆盖 **42.2%** 岗位，本科可覆盖 **95.4%**"],
         ["学历是第三条硬筛选线（地域→经验→学历）",
          "「学历超出要求」不扣分；但硕士门槛岗位不要推给本科简历（当前数据无正样本）",
          "推荐结果里显示「学历门槛：满足/超出」提升可解释性"]),
    ]),
    ("三、企业与招聘活跃度", "谁在招、谁回得快", [
        ("06_招聘活跃企业TOP榜_横向柱状图", "招聘活跃企业 TOP20（横向柱状图）",
         "哪些公司在大量招人",
         ["共 **4,096 家企业**；第一名软通动力 86 个岗位，仅占全部岗位 **0.97%**",
          "其后：三一集团 72、外企德科 36、厦门睿云联 33、宁波信泰 29、鑫锡软件 27、新大陆支付 27",
          "头部以「软件外包/IT 服务 + 制造业龙头」为主"],
         ["推荐列表需**公司维度去重**（同公司最多 1~3 条），否则易被活跃雇主刷屏",
          "头部企业可做重点校企/岗位数据补充",
          "招聘集中度低（长尾）→ 不能只靠少数大公司做推荐"]),
        ("10_回复积极企业TOP20_横向柱状图", "回复积极企业 TOP20（横向柱状图）",
         "哪些公司回消息最快（求职者体验）",
         ["口径说明：`回复时效` 字段 **99.83% 为空**，因此以 `今日回复数` 为准（非空 52.3%）",
          "在招岗位 ≥5 个的 **360 家**公司中，Top：厦门睿云联 **84.7**、外企德科 81.8、软通动力 81.1、福州云之景 71.3",
          "对照：厦门亿联（25 岗）、中电福富（26 岗）回复数据覆盖率为 **0** → 得分 0 / 2.3"],
         ["「雇主响应度」可作推荐排序的软性加分项",
          "必须区分**「无回复数据」与「回复少」**：47.7% 岗位缺该字段，应显示「暂无数据」",
          "采集侧建议优先补齐 `回复时效` 字段"]),
    ]),
    ("四、地域分布", "在哪：岗位集中在哪些省份和城市", [
        ("中国地图_岗位数量分布", "中国各省岗位数量分布（地图）",
         "这批岗位分布在全国哪些地方",
         ["仅 4 个省级区域有数据：**福建 3,553（40.21%）、浙江 2,656（30.06%）、江苏 2,073（23.46%）、安徽 554（6.27%）**",
          "其余 30 个省级区域为 0（地图上为最浅色）",
          "这正是采集策略（福建为主 + 长三角补充）的直接投影"],
         ["训练与推荐都应**限定在四省范围内**，范围外必须提示「暂无岗位数据」",
          "扩大覆盖只需补城市坐标并重跑采集，模型与流水线不用改",
          "解释了为什么 300km 门槛会把广东、江西的简历全部排除出正样本"]),
        ("福建省地图_岗位数量分布", "福建省各市岗位数量分布（地图）",
         "福建省内岗位集中在哪",
         ["**福州 1,173（33.01%）+ 厦门 1,169（32.90%）双核**，合计约全省 2/3",
          "泉州 594、漳州 235、莆田 138、南平 99、龙岩 87、三明 58，**宁德 0**",
          "山区市（南平/龙岩/三明）岗位稀少，跨市求职是常态"],
         ["福建简历优先从**福州、厦门**召回（300km 内密度最高）",
          "距离应作**加权项**而非仅二值门槛：同城 &gt; 邻近市（厦门↔漳州）&gt; 跨省",
          "宁德等「有求职者无岗位」城市需「周边城市推荐」兜底"]),
    ]),
    ("五、评分模型（任务5）", "分：匹配分怎么算、模型学到什么、可信到什么程度", [
        ("12_模型对比_柱状图", "模型指标对比（2 口径 × 2 任务 × 各对照实验）",
         "四个面板里，XGBoost 全胜",
         ["**T1 回归**（主口径测试集 MAE，越低越好）：XGBoost **0.827**、随机森林 1.175、SVR 2.057、线性回归 4.755、均值基线 8.711",
          "**T2 二分类**（阈值 ≥65，正样本 16.6%，PR-AUC 越高越好）：XGBoost **0.965**、随机森林 0.949、逻辑回归/LinearSVC 0.746、随机基线 0.181",
          "两个任务 × 两个划分口径，最优模型都是 **XGBoost**（按验证集指标选出，测试集不参与选择）"],
         ["线上打分直接用 XGBoost；线性模型只适合做可解释性对照",
          "规则里含阈值与比值关系（经验缺口比例、距离分档、薪资比）→ **强非线性**，必须用树模型",
          "正样本仅 16.6%，**不报准确率**，用 PR-AUC 与排序指标（P@10 / MRR@10 / NDCG@10）衡量"]),
        ("13_预测vs真实_散点图", "预测值 vs 真实值（纯净标签 / 噪声标签）",
         "特征几乎能还原规则；模型已打到噪声下限",
         ["左图**纯净标签**（无噪声）：MAE **0.370**、R² **0.997** —— 这是「特征充分性上界」，说明特征足以还原六维规则",
          "右图**噪声标签**（最终标签，10% 配对加噪）：MAE **0.827**",
          "0.827 ≈ 0.370（模型残差）+ **0.48**（噪声贡献 = 10%×E|N(0,6)|），即模型已达噪声天花板"],
         ["不要再靠调参把 MAE 往下压：那 0.48 分是标签自带的噪声，不是模型能力问题",
          "标签由六维加权规则生成（蒸馏），指标反映**对规则的拟合程度**，不等于对真实人岗匹配的判断力",
          "模型泛化能力要看「仅 3 个文本相似度特征」那组对照（MAE 7.906、PR-AUC 0.380）"]),
        ("14_残差分布_直方图", "残差分布（4 个回归模型）",
         "线性回归的长尾会把 65 分判定线两侧搞混",
         ["XGBoost 残差集中在 **±1 分**内；随机森林 ±3 分；SVR 与线性回归尾部拖到 **±10 分以上**（纵轴对数）",
          "**65 分是匹配/不匹配的判定线**，残差大的模型在这条线附近误判率显著更高",
          "排序指标印证：NDCG@10 XGBoost **0.867** vs 线性回归 0.568"],
         ["推荐列表排序对残差敏感，**选模型要看排序指标**，不能只看 MAE",
          "对 60–70 分区间（临界带）的候选，产品上建议标注「临界」并提示人工复核"]),
        ("15_特征重要性Top15_横向柱状图", "特征重要性 Top15（XGBoost 回归）",
         "经验与地域主导，技能只排第 10",
         ["Top4：**是否应届 0.217**、**是否同城 0.189**、**简历工作年限 0.132**、距离km 0.089",
          "「岗位经验缺失」（A2 字段错位标记）排第 5（0.073）—— 有 **2,182 个岗位（24.69%）** 的经验要求不可用",
          "**技能命中数只排第 10（0.022）**；技能分均值 4.13/100，对总分平均贡献约 **1.2 分**（名义权重 0.30）"],
         ["⚠ **更正**：本看板前面「技能是区分力最强的维度」的说法，在任务5 实测中**不成立** —— 合成简历只有 74 个技能词，与真实岗位标签重叠极低，且岗位技能标签质量差",
          "要让技能真正起作用，需先**扩充简历技能词表**或启用技能同义词库（宽松档已备好、默认未启用）",
          "地域维度区分度有限（简历居住地与期望城市 100% 一致），方差只来自岗位城市"]),
        ("16_分类PR曲线_折线图", "分类 PR 曲线（4 个分类模型）",
         "推荐列表前几名几乎不推错，但覆盖有限",
         ["主口径测试集（正样本 18.1%）：XGBoost AP **0.965**、随机森林 0.949、逻辑回归/LinearSVC 0.746、随机基线 0.181",
          "排序质量：**P@10 = 0.671**、R@10 = 0.525、**MRR@10 = 0.911**、**NDCG@10 = 0.867**",
          "按岗位口径（冷启动）NDCG@10 达 0.952，但该口径下简历在训练集出现过 → 属乐观偏差"],
         ["首页给 **5–10 个推荐位**最合适（P@10 0.671）；要覆盖更多正样本就得牺牲精确率（R@10 仅 0.525）",
          "对外汇报统一用**主口径**（测试集是完全陌生的简历），指标更保守可信",
          "模型文件：<code>models/按简历_T1回归_best_XGBoost.joblib</code>、<code>models/按简历_T2分类_best_XGBoost.joblib</code>"]),
    ]),
]


def build_html():
    cards = "\n".join(
        '<div class="kpi"><div class="kpi-label">%s</div><div class="kpi-value">%s</div>'
        '<div class="kpi-sub">%s</div></div>' % (a, b, c) for a, b, c in KPI)

    sec_html = []
    fig_no = 0
    for title, sub, figs in SECTIONS:
        blocks = []
        for name, fig_title, highlight, facts, tips in figs:
            fig_no += 1
            facts_html = "".join("<li>%s</li>" % f for f in facts)
            tips_html = "".join("<li>%s</li>" % t for t in tips)
            png = "figures/%s.png" % name
            html_link = "figures/%s.html" % name
            has_html = os.path.exists(os.path.join(ROOT, "reports", "figures", name + ".html"))
            blocks.append("""
      <div class="card">
        <div class="card-head">
          <span class="badge">图 %d</span>
          <h3>%s</h3>
          <span class="hl">%s</span>
        </div>
        <img src="%s" alt="%s" loading="lazy">
        <div class="explain">
          <div class="col"><h4>数据结论</h4><ul>%s</ul></div>
          <div class="col"><h4>对匹配/推荐系统的启示</h4><ul>%s</ul></div>
        </div>
        %s
      </div>""" % (fig_no, fig_title, highlight, png, fig_title, facts_html, tips_html,
                   ('<div class="links">交互版（可悬浮查看明细）：<a href="%s" target="_blank">打开 %s.html</a></div>'
                    % (html_link, name)) if has_html else ""))
        sec_html.append("""
    <section>
      <h2>%s</h2>
      <p class="sec-sub">%s</p>%s
    </section>""" % (title, sub, "".join(blocks)))

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>岗位-简历人岗匹配推荐系统 · 数据看板</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; background:#f5f7fa; color:#22303f;
         font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif; line-height:1.65; }
  header { background:linear-gradient(135deg,#0b3d91,#2171b5 60%,#2f9e6b);
           color:#fff; padding:34px 5vw 28px; }
  header h1 { margin:0 0 6px; font-size:26px; letter-spacing:.5px; }
  header p { margin:2px 0; font-size:13px; opacity:.92; }
  .kpis { display:flex; flex-wrap:wrap; gap:14px; margin-top:20px; }
  .kpi { background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.28);
         border-radius:10px; padding:12px 16px; min-width:170px; }
  .kpi-label { font-size:12px; opacity:.9; }
  .kpi-value { font-size:22px; font-weight:700; margin:2px 0; }
  .kpi-sub { font-size:11px; opacity:.85; }
  main { padding:26px 5vw 60px; }
  section { margin-bottom:34px; }
  h2 { font-size:20px; margin:0 0 4px; padding-left:12px; border-left:5px solid #2171b5; }
  .sec-sub { margin:0 0 16px 17px; color:#5b6b7c; font-size:13px; }
  .card { background:#fff; border-radius:12px; padding:18px 20px 16px; margin-bottom:20px;
          box-shadow:0 2px 12px rgba(16,42,67,.07); }
  .card-head { display:flex; flex-wrap:wrap; align-items:baseline; gap:10px; margin-bottom:10px; }
  .card-head h3 { margin:0; font-size:16px; }
  .badge { background:#e8f1fb; color:#2171b5; border-radius:6px; padding:1px 8px; font-size:12px; font-weight:700; }
  .hl { color:#7a8b9a; font-size:12px; }
  .card img { width:100%; height:auto; border:1px solid #eef2f6; border-radius:8px; background:#fff; }
  .explain { display:flex; flex-wrap:wrap; gap:18px; margin-top:12px; }
  .col { flex:1 1 320px; }
  .col h4 { margin:0 0 6px; font-size:13px; color:#2171b5; }
  .col ul { margin:0; padding-left:20px; font-size:13px; color:#33475b; }
  .col li { margin-bottom:4px; }
  .col b, .col strong { color:#0b3d91; }
  .links { margin-top:10px; font-size:12px; color:#7a8b9a; }
  .links a { color:#2171b5; }
  footer { background:#0b3d91; color:#dbe7f5; padding:22px 5vw; font-size:12px; }
  footer b { color:#fff; }
  code { background:#eef2f6; padding:1px 5px; border-radius:4px; font-size:12px; }
</style>
</head>
<body>
<header>
  <h1>岗位-简历人岗匹配推荐系统 · 数据看板</h1>
  <p>行业大数据分析实践（23大数据班）｜数据源：智联招聘公开岗位信息（采集 12,355 条 → 清洗后 8,836 条）</p>
  <p>本看板汇总任务3–任务5 生成的全部可视化图片与结论；每张图均可打开交互版查看明细数据。</p>
  <div class="kpis">__KPIS__</div>
</header>
<main>__SECTIONS__
</main>
<footer>
  <p><b>数据口径</b>：地域以 <code>岗位地区</code> 首个城市词为准；薪资为月薪（区间取中值，日薪×21.75、时薪×8×21.75），可解析率 99.97%；技能 = <code>技能标签</code> ∪ 职位描述分词中命中技能词典（74 项技术词）的词汇。</p>
  <p><b>生成方式</b>：<code>python src/analysis/job_charts.py</code>（图1~7、10、11）｜<code>python src/analysis/map_job_distribution.py</code>（图8、9）｜<code>python src/models/scoring/model_charts.py</code>（图12~16 模型评估图）｜本看板 <code>python src/analysis/build_dashboard.py</code>。</p>
  <p><b>数据文件</b>：<code>reports/figures/*.csv</code>（每张图的数据）｜<code>data/processed/</code>（清洗、分词、薪资规范化数据与模型评估结果）｜<code>docs/可视化分析报告.md</code>（业务图文字版）｜<code>docs/评分模型文档.md</code>（任务5 模型文字版：标签口径、36 特征、划分、全部指标与局限）。</p>
</footer>
</body>
</html>
"""
    html = html.replace("__KPIS__", cards).replace("__SECTIONS__", "".join(sec_html))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("看板已生成:", os.path.relpath(OUT, ROOT))
    print("图片数量:", fig_no, "｜文件大小: %.1f KB" % (os.path.getsize(OUT) / 1024))
    return fig_no


if __name__ == "__main__":
    build_html()
