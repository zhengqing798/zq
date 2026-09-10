# -*- coding: utf-8 -*-
"""
任务4 · 六张可视化图表（数据源：data/processed 的处理后数据）

1) 01 岗位薪资水平对比图（柱状图）      —— 各城市平均月薪
2) 02 经验要求结构分布图（堆叠柱状图）  —— 主要城市 × 经验等级占比
3) 03 核心技能需求热度图（词云）        —— 技能标签词频
4) 04 学历要求门槛分析图（饼状图）      —— 学历要求占比
5) 05 经验-薪资增长曲线图（多折线图）   —— 主要城市 经验等级 → 平均月薪
6) 06 招聘活跃企业 TOP 榜（横向柱状图） —— 公司岗位数 Top20

输出：reports/figures/ 下 6 个 HTML（可交互）+ 6 个 PNG（可直接插入报告）+ 6 个统计 CSV
"""
import csv
import os
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SEG_CSV = os.path.join(ROOT, "data", "processed", "zhaopin_jobs_cleaned_seg.csv")
CLEAN_CSV = os.path.join(ROOT, "data", "processed", "zhaopin_jobs_cleaned.csv")
OUT_DIR = os.path.join(ROOT, "reports", "figures")
os.makedirs(OUT_DIR, exist_ok=True)

ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"
WORDCLOUD_CDN = "https://cdn.jsdelivr.net/npm/echarts-wordcloud@2.1.0/dist/echarts-wordcloud.min.js"

EXPERIENCE_ORDER = ["不限/应届", "1-3年", "3-5年", "5-10年", "10年以上", "未标注/其他"]
EXP_COLORS = ["#91d5c1", "#5b8ff9", "#f6bd16", "#ff9845", "#e8684a", "#c2c8d5"]
SALARY_BAR_COLOR = "#3182bd"

# ---------------------------------------------------------------- 数据读取


def pick_source():
    """优先用清洗结果文件；若不存在（被移动/删除）则跳过该文件用分词结果文件。"""
    for p in (CLEAN_CSV, SEG_CSV):
        if os.path.exists(p):
            return p
    raise SystemExit("找不到处理后数据文件")


def load_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def city_of(region_text):
    parts = (region_text or "").replace("\u3000", " ").split()
    return parts[0] if parts else ""


def exp_bucket(text):
    t = (text or "").strip()
    if not t:
        return "未标注/其他"
    if t in ("不限", "不限经验", "接受无经验", "应届生", "应届毕业生"):
        return "不限/应届"
    if t in ("1-3年", "3-5年", "5-10年", "10年以上"):
        return t
    return "未标注/其他"


def parse_salary(text):
    """岗位薪资文本 → 折算月薪（元/月，取区间中值）。无法解析返回 None。"""
    s = (text or "").strip().replace(" ", "").replace("，", ",")
    if not s or "面议" in s:
        return None
    per = 1.0
    if "/天" in s:
        per = 21.75                      # 21.75 个工作日/月
    elif "/时" in s or "/小时" in s:
        per = 21.75 * 8
    elif "/周" in s:
        per = 4.345
    elif "/年" in s:
        per = 1 / 12
    nums = re.findall(r"(\d+(?:\.\d+)?)(万|千|[kK])?", s)
    vals = []
    for n, u in nums:
        v = float(n)
        if u == "万":
            v *= 10000
        elif u in ("千", "k", "K"):
            v *= 1000
        if v > 0:
            vals.append(v)
    if not vals:
        return None
    m = sum(vals) / len(vals) * per
    return m if 1000 <= m <= 200000 else None


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def split_tags(text):
    return [t.strip() for t in re.split(r"[|、，,\s]+", text or "") if t.strip()]


# ---------------------------------------------------------------- 输出工具


def write_csv(name, header, records):
    p = os.path.join(OUT_DIR, name)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(records)
    return p


def html_page(path, width, height, option_js, cdn_extra=""):
    tpl = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>__TITLE__</title>
<script src="__ECHARTS__"></script>
__CDN_EXTRA__
<style>
  html,body{margin:0;padding:0;background:#ffffff;overflow:hidden;
            font-family:"Microsoft YaHei","PingFang SC",sans-serif;}
  #chart{width:__W__px;height:__H__px;}
</style>
</head>
<body>
<div id="chart"></div>
<script>
  var chart = echarts.init(document.getElementById('chart'), null, {devicePixelRatio: 2});
  var option = __OPTION__;
  chart.setOption(option);
  window.addEventListener('resize', function(){ chart.resize(); });
</script>
</body>
</html>
"""
    extra = ""
    if cdn_extra:
        extra = '<script src="%s"></script>' % cdn_extra
    html = (tpl.replace("__TITLE__", os.path.basename(path))
               .replace("__ECHARTS__", ECHARTS_CDN)
               .replace("__CDN_EXTRA__", extra)
               .replace("__W__", str(width))
               .replace("__H__", str(height))
               .replace("__OPTION__", option_js))
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print("  HTML ->", os.path.basename(path))


def js(obj):
    """Python 结构 → JS 字面量（JSON 即可，中文不转义）。"""
    import json
    return json.dumps(obj, ensure_ascii=False)


# ------------------------------------------------------- PNG 导出（Chrome 无头）

CHART_FILES = [
    "01_岗位薪资水平对比_柱状图",
    "02_经验要求结构分布_堆叠柱状图",
    "03_核心技能需求热度_词云",
    "04_学历要求门槛分析_饼状图",
    "05_经验薪资增长曲线_多折线图",
    "06_招聘活跃企业TOP榜_横向柱状图",
    "07_岗位分布_横向柱状图",
]

EXPORT_SNIPPET = """
<script>
// 导出 PNG：先关闭动画重绘一次（无头模式虚拟时间下动画会停在起始帧），
// 再取 ECharts 的 canvas 数据（词云的绘制是异步的，必须用 getDataURL 而不是外部截图）
setTimeout(function () {
  option.animation = false;
  chart.setOption(option, true);
  setTimeout(function () {
    var url = chart.getDataURL({type: 'png', pixelRatio: 2, backgroundColor: '#ffffff'});
    var el = document.createElement('div');
    el.id = 'pngout';
    el.textContent = url;
    document.body.appendChild(el);
  }, 1200);
}, 3000);
</script>
"""


def find_chrome():
    cands = [
        os.environ.get("CHROME_PATH", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def export_png(html_path, png_path, chrome):
    """用 Chrome 无头模式打开图表页，取 ECharts 导出的 dataURL 存成 PNG。"""
    import base64
    import re as _re
    import subprocess
    import tempfile
    html = open(html_path, encoding="utf-8").read().replace("</body>", EXPORT_SNIPPET + "</body>")
    tmp = os.path.join(tempfile.gettempdir(), "dsh_chart_export.html")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    url = "file:///" + tmp.replace("\\", "/")
    res = subprocess.run([chrome, "--headless=new", "--disable-gpu",
                          "--virtual-time-budget=40000", "--dump-dom", url],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    dom = res.stdout.decode("utf-8", "replace")
    m = _re.search(r"data:image/png;base64,([A-Za-z0-9+/=]{1000,})", dom)
    if not m:
        return False
    with open(png_path, "wb") as f:
        f.write(base64.b64decode(m.group(1)))
    return True


# ---------------------------------------------------------------- 六个图表


SALARY_BINS = [
    (0, 3000, "3千以下"), (3000, 5000, "3-5千"), (5000, 8000, "5-8千"),
    (8000, 10000, "8-10千"), (10000, 15000, "10-15千"),
    (15000, 20000, "15-20千"), (20000, 10 ** 9, "20千以上"),
]


def chart1_salary_distribution(rows):
    """01 岗位薪资水平对比图（柱状图）：全部岗位薪资分档分布"""
    vals = [v for v in (parse_salary(r.get("岗位薪资")) for r in rows) if v]
    cnt = Counter()
    for v in vals:
        for lo, hi, label in SALARY_BINS:
            if lo <= v < hi:
                cnt[label] += 1
                break
    total = sum(cnt.values())
    labels = [b[2] for b in SALARY_BINS]
    counts = [cnt[l] for l in labels]
    pcts = [round(cnt[l] / total * 100, 2) for l in labels]
    write_csv("01_岗位薪资水平对比_柱状图.csv",
              ["薪资区间(元/月)", "岗位数", "占比(%)"],
              [[l, cnt[l], round(cnt[l] / total * 100, 2)] for l in labels])

    option = """
  {
    title: {
      text: '岗位薪资水平对比（全部岗位薪资分布）',
      subtext: '数据源：处理后数据 __TOTAL__ 条岗位（薪资可解析 __PARSED__ 条）｜按折算月薪分档（区间取中值，日薪/时薪已折算）｜平均 __AVG__ 元/月，中位数 __MED__ 元/月',
      left: 'center', top: 12,
      textStyle: {fontSize: 22, fontWeight: 'bold'},
      subtextStyle: {fontSize: 12, color: '#777'}
    },
    tooltip: {
      trigger: 'axis', axisPointer: {type: 'shadow'},
      formatter: function(ps) {
        var i = ps[0].dataIndex;
        return '月薪 ' + ps[0].name + '<br/>岗位数：' + ps[0].value + ' 条<br/>占比：' + __PCTS__[i] + '%';
      }
    },
    grid: {left: 90, right: 50, top: 120, bottom: 80},
    xAxis: {
      type: 'category', data: __CATS__,
      name: '月薪区间', nameLocation: 'middle', nameGap: 40, nameTextStyle: {fontSize: 12},
      axisLabel: {fontSize: 13, interval: 0},
      axisTick: {alignWithLabel: true}
    },
    yAxis: {
      type: 'value', name: '岗位数(条)', nameTextStyle: {fontSize: 12},
      axisLabel: {fontSize: 12},
      splitLine: {lineStyle: {type: 'dashed', color: '#e8e8e8'}}
    },
    series: [{
      name: '岗位数', type: 'bar', barMaxWidth: 80,
      data: __VALS__,
      itemStyle: {
        borderRadius: [4, 4, 0, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          {offset: 0, color: '#9ecae1'}, {offset: 1, color: '#3182bd'}])
      },
      label: {show: true, position: 'top', fontSize: 12,
              formatter: function(p) { return p.value + ' 条\\n' + __PCTS__[p.dataIndex] + '%'; }}
    }]
  }
"""
    option = (option.replace("__CATS__", js(labels))
                    .replace("__VALS__", js(counts))
                    .replace("__PCTS__", js(pcts))
                    .replace("__TOTAL__", str(len(rows)))
                    .replace("__PARSED__", str(total))
                    .replace("__AVG__", str(int(round(sum(vals) / len(vals)))))
                    .replace("__MED__", str(int(median(vals)))))
    html_page(os.path.join(OUT_DIR, "01_岗位薪资水平对比_柱状图.html"), 1400, 820, option)


def chart2_experience_stack(rows):
    """02 经验要求结构分布图（堆叠柱状图）：全部岗位 × 经验等级 → 学历构成"""
    levels = ["不限/应届", "1-3年", "3-5年", "5-10年", "10年以上"]
    edu_order = ["本科", "大专", "硕士", "中专/中技", "高中", "博士"]
    table = {lv: Counter() for lv in levels}
    for r in rows:
        lv = exp_bucket(r.get("经验要求"))
        if lv not in table:
            continue
        edu = (r.get("学历要求") or "").strip()
        if not edu:
            continue                      # 学历未标注（清空值）不参与结构图
        table[lv][edu] += 1

    records = []
    for lv in levels:
        tot = sum(table[lv].values())
        for edu in edu_order:
            records.append([lv, edu, table[lv][edu],
                            round(table[lv][edu] / tot * 100, 2) if tot else 0])
    write_csv("02_经验要求结构分布_堆叠柱状图.csv",
              ["经验要求", "学历要求", "岗位数", "占该经验等级比例(%)"], records)

    valid = sum(sum(table[lv].values()) for lv in levels)
    cats = ["%s\n(%d条)" % (lv, sum(table[lv].values())) for lv in levels]
    series = []
    for i, edu in enumerate(edu_order):
        vals, cnts = [], []
        for lv in levels:
            tot = sum(table[lv].values())
            vals.append(round(table[lv][edu] / tot * 100, 2) if tot else 0)
            cnts.append(table[lv][edu])
        series.append({"name": edu, "type": "bar", "stack": "总量",
                       "barMaxWidth": 110, "data": vals, "cnt": cnts,
                       "itemStyle": {"color": EXP_COLORS[i]},
                       "emphasis": {"focus": "series"},
                       "label": {"show": True, "fontSize": 12, "color": "#fff",
                                 "formatter": "{c}%"}})
    option = """
  {
    title: {
      text: '经验要求结构分布（全部岗位）',
      subtext: '数据源：处理后数据 __TOTAL__ 条岗位中，经验要求与学历要求均有效的 __VALID__ 条｜按经验等级统计其学历构成（100% 堆叠）',
      left: 'center', top: 12,
      textStyle: {fontSize: 22, fontWeight: 'bold'},
      subtextStyle: {fontSize: 12, color: '#777'}
    },
    tooltip: {
      trigger: 'axis', axisPointer: {type: 'shadow'},
      formatter: function(ps) {
        var s = ps[0].name.replace('\\n', ' ');
        var out = s + '<br/>';
        for (var i = 0; i < ps.length; i++) {
          out += ps[i].marker + ps[i].seriesName + '：' + ps[i].value + '%（'
               + __CNTS__[ps[i].seriesIndex][ps[i].dataIndex] + ' 条）<br/>';
        }
        return out;
      }
    },
    legend: {top: 96, itemWidth: 16, itemHeight: 11, textStyle: {fontSize: 13}},
    grid: {left: 80, right: 50, top: 150, bottom: 80},
    xAxis: {type: 'category', data: __CATS__,
            axisLabel: {fontSize: 13, interval: 0, lineHeight: 18},
            name: '经验要求', nameLocation: 'middle', nameGap: 62, nameTextStyle: {fontSize: 12}},
    yAxis: {type: 'value', max: 100, name: '占比(%)', nameTextStyle: {fontSize: 12},
            axisLabel: {fontSize: 12, formatter: '{value}%'},
            splitLine: {lineStyle: {type: 'dashed', color: '#e8e8e8'}}},
    series: __SERIES__
  }
"""
    option = (option.replace("__CATS__", js(cats))
                    .replace("__SERIES__", js(series))
                    .replace("__CNTS__", js([s["cnt"] for s in series]))
                    .replace("__TOTAL__", str(len(rows)))
                    .replace("__VALID__", str(valid)))
    html_page(os.path.join(OUT_DIR, "02_经验要求结构分布_堆叠柱状图.html"), 1400, 820, option)



def chart3_skill_wordcloud(rows, top_n=150):
    """03 核心技能需求热度图（词云）：技能标签词频"""
    cnt = Counter()
    for r in rows:
        for t in split_tags(r.get("技能标签")):
            cnt[t] += 1
    top = cnt.most_common(top_n)
    write_csv("03_核心技能需求热度_词云.csv",
              ["技能关键词", "出现岗位数", "占全部岗位比例(%)"],
              [[w, n, round(n / len(rows) * 100, 2)] for w, n in top])
    data = [{"name": w, "value": n} for w, n in top]
    option = """
  {
    title: {
      text: '核心技能需求热度词云',
      subtext: '数据源：处理后数据 __TOTAL__ 条岗位的"技能标签"字段（共出现 __KINDS__ 个技能词，图中展示 Top__TOPN__）｜字越大表示需求该技能的岗位越多',
      left: 'center', top: 10,
      textStyle: {fontSize: 22, fontWeight: 'bold'},
      subtextStyle: {fontSize: 12, color: '#777'}
    },
    tooltip: {
      show: true,
      formatter: function(p) { return p.name + '：' + p.value + ' 个岗位'; }
    },
    series: [{
      type: 'wordCloud',
      shape: 'circle',
      left: 20, top: 110, width: 1360, height: 750,
      sizeRange: [14, 72],
      rotationRange: [-45, 45],
      rotationStep: 45,
      gridSize: 8,
      drawOutOfBound: false,
      textStyle: {
        fontFamily: '"Microsoft YaHei", sans-serif',
        fontWeight: 'bold',
        color: function() {
          var cs = ['#3182bd','#6baed6','#9ecae1','#4292c6','#08519c','#f6bd16',
                    '#ff9845','#e8684a','#5b8ff9','#5ad8a6','#945fb9','#269a99'];
          return cs[Math.floor(Math.random() * cs.length)];
        }
      },
      emphasis: {textStyle: {shadowBlur: 10, shadowColor: '#999'}},
      data: __DATA__
    }]
  }
"""
    option = (option.replace("__DATA__", js(data))
                    .replace("__TOTAL__", str(len(rows)))
                    .replace("__KINDS__", str(len(cnt)))
                    .replace("__TOPN__", str(len(top))))
    html_page(os.path.join(OUT_DIR, "03_核心技能需求热度_词云.html"), 1400, 900, option,
              cdn_extra=WORDCLOUD_CDN)


def chart4_education_pie(rows):
    """04 学历要求门槛分析图（饼状图）：不含学历未标注（已清空值）"""
    cnt = Counter((r.get("学历要求") or "").strip() for r in rows)
    blank = cnt.pop("", 0)
    order = ["本科", "大专", "硕士", "中专/中技", "高中", "博士"]
    items = [(k, cnt[k]) for k in order if k in cnt]
    for k, v in cnt.items():
        if k not in order:
            items.append((k, v))
    valid = sum(v for _, v in items)
    write_csv("04_学历要求门槛分析_饼状图.csv",
              ["学历要求", "岗位数", "占比(%)"],
              [[k, v, round(v / valid * 100, 2)] for k, v in items])
    data = [{"name": k, "value": v} for k, v in items]
    option = """
  {
    title: {
      text: '学历要求门槛分析',
      subtext: '数据源：处理后数据 __TOTAL__ 条岗位的"学历要求"字段｜已剔除未标注（原本为非学历值、已被清空）__BLANK__ 条，占比按有效 __VALID__ 条计算',
      left: 'center', top: 12,
      textStyle: {fontSize: 22, fontWeight: 'bold'},
      subtextStyle: {fontSize: 12, color: '#777'}
    },
    tooltip: {trigger: 'item', formatter: '{b}<br/>岗位数：{c}<br/>占比：{d}%'},
    legend: {orient: 'vertical', left: 60, top: 'middle', itemWidth: 14, itemHeight: 12,
             textStyle: {fontSize: 13}},
    color: ['#3182bd', '#6baed6', '#9ecae1', '#5ad8a6', '#f6bd16', '#ff9845'],
    series: [{
      name: '学历要求', type: 'pie',
      radius: ['34%', '62%'], center: ['62%', '56%'],
      avoidLabelOverlap: true,
      itemStyle: {borderColor: '#fff', borderWidth: 2},
      label: {fontSize: 13, formatter: '{b}\\n{c} 条（{d}%）'},
      labelLine: {length: 16, length2: 16},
      emphasis: {label: {fontSize: 15, fontWeight: 'bold'},
                 itemStyle: {shadowBlur: 12, shadowColor: 'rgba(0,0,0,.25)'}},
      data: __DATA__
    }]
  }
"""
    option = (option.replace("__DATA__", js(data))
                    .replace("__TOTAL__", str(len(rows)))
                    .replace("__BLANK__", str(blank))
                    .replace("__VALID__", str(valid)))
    html_page(os.path.join(OUT_DIR, "04_学历要求门槛分析_饼状图.html"), 1200, 800, option)


CITY_COLORS = [
    "#3182bd", "#5ad8a6", "#f6bd16", "#945fb9", "#ff9845", "#1e9493",
    "#ff99c3", "#269a99", "#9270ca", "#9ecae1", "#c76f3c", "#6dc8ec",
    "#b5a642", "#c05b8b", "#7cb342", "#d4a5a5",
]


def chart5_experience_salary_lines(rows, top_cities=6, min_n=10):
    """05 经验-薪资增长曲线图（多折线图）：岗位数最多的主要城市"""
    city_cnt = Counter(city_of(r.get("岗位地区")) for r in rows)
    cities = [c for c, _ in city_cnt.most_common(top_cities) if c]   # 主要城市
    buckets = ["不限/应届", "1-3年", "3-5年", "5-10年", "10年以上"]
    agg = defaultdict(list)     # (city, bucket) -> [salary]
    allagg = defaultdict(list)
    for r in rows:
        v = parse_salary(r.get("岗位薪资"))
        if not v:
            continue
        b = exp_bucket(r.get("经验要求"))
        if b not in buckets:
            continue
        c = city_of(r.get("岗位地区"))
        if c in cities:
            agg[(c, b)].append(v)
        allagg[b].append(v)

    records = []
    series = []
    for i, c in enumerate(cities):
        vals, ns = [], []
        for b in buckets:
            vs = agg.get((c, b), [])
            ns.append(len(vs))
            vals.append(round(sum(vs) / len(vs), 0) if len(vs) >= min_n else None)
        records.append([c] + [("" if v is None else int(v)) for v in vals])
        series.append({"name": c, "type": "line", "smooth": True, "symbolSize": 6,
                       "connectNulls": False, "data": vals, "n": ns,
                       "itemStyle": {"color": CITY_COLORS[i % len(CITY_COLORS)]},
                       "lineStyle": {"width": 2},
                       "emphasis": {"focus": "series", "lineStyle": {"width": 5}}})
    all_vals = [round(sum(allagg[b]) / len(allagg[b]), 0) if allagg[b] else None for b in buckets]
    records.append(["全部城市平均"] + [("" if v is None else int(v)) for v in all_vals])
    write_csv("05_经验薪资增长曲线_多折线图.csv",
              ["城市"] + ["%s平均月薪(元)" % b for b in buckets], records)

    series.append({"name": "全部城市平均", "type": "line", "smooth": True, "symbolSize": 10,
                   "data": all_vals, "lineStyle": {"width": 4, "type": "dashed"},
                   "itemStyle": {"color": "#333333"}, "z": 10,
                   "n": [len(allagg[b]) for b in buckets]})
    option = """
  {
    title: {
      text: '经验-薪资增长曲线（多折线 · 主要城市）',
      subtext: '数据源：处理后数据 __TOTAL__ 条岗位｜取岗位数最多的 __NCITY__ 个城市：__CITYLIST__｜按"经验要求"等级的平均月薪（元/月），样本 <__MINN__ 条的组合不显示；黑色虚线为全部城市平均',
      left: 'center', top: 12,
      textStyle: {fontSize: 22, fontWeight: 'bold'},
      subtextStyle: {fontSize: 12, color: '#777'}
    },
    tooltip: {
      trigger: 'axis',
      formatter: function(ps) {
        var out = ps[0].axisValue + '<br/>';
        for (var i = 0; i < ps.length; i++) {
          if (ps[i].value === null || ps[i].value === undefined) continue;
          var n = __NS__[ps[i].seriesIndex][ps[i].dataIndex];
          out += ps[i].marker + ps[i].seriesName + '：' + ps[i].value + ' 元/月（' + n + ' 条）<br/>';
        }
        return out;
      }
    },
    legend: {top: 92, left: 'center', itemWidth: 18, itemHeight: 10,
             itemGap: 18, textStyle: {fontSize: 13}},
    grid: {left: 90, right: 70, top: 165, bottom: 80},
    xAxis: {type: 'category', boundaryGap: false, data: __CATS__,
            axisLabel: {fontSize: 13}, name: '经验要求', nameLocation: 'middle', nameGap: 36,
            nameTextStyle: {fontSize: 12}},
    yAxis: {type: 'value', name: '平均月薪(元)', nameTextStyle: {fontSize: 12},
            min: function(v) { return Math.max(0, Math.floor(v.min / 1000) * 1000 - 1000); },
            axisLabel: {fontSize: 12, formatter: function(v){ return (v/1000) + 'k'; }},
            splitLine: {lineStyle: {type: 'dashed', color: '#e8e8e8'}}},
    series: __SERIES__
  }
"""
    option = (option.replace("__CATS__", js(buckets))
                    .replace("__SERIES__", js(series))
                    .replace("__NS__", js([s["n"] for s in series]))
                    .replace("__TOTAL__", str(len(rows)))
                    .replace("__NCITY__", str(len(cities)))
                    .replace("__CITYLIST__", "、".join(cities))
                    .replace("__MINN__", str(min_n)))
    html_page(os.path.join(OUT_DIR, "05_经验薪资增长曲线_多折线图.html"), 1400, 860, option)


def chart6_top_companies(rows, top_n=20):
    """06 招聘活跃企业 TOP 榜（横向柱状图）"""
    cnt = Counter((r.get("公司名称") or "").strip() for r in rows)
    cnt.pop("", None)
    top = cnt.most_common(top_n)
    write_csv("06_招聘活跃企业TOP榜_横向柱状图.csv",
              ["排名", "公司名称", "在招岗位数", "占全部岗位比例(%)"],
              [[i + 1, c, n, round(n / len(rows) * 100, 2)] for i, (c, n) in enumerate(top)])
    names = [c for c, _ in top][::-1]
    vals = [n for _, n in top][::-1]
    option = """
  {
    title: {
      text: '招聘活跃企业 TOP__TOPN__',
      subtext: '数据源：处理后数据 __TOTAL__ 条岗位的"公司名称"字段（共 __COMPANIES__ 家企业）｜按在招岗位数排名',
      left: 'center', top: 12,
      textStyle: {fontSize: 22, fontWeight: 'bold'},
      subtextStyle: {fontSize: 12, color: '#777'}
    },
    tooltip: {
      trigger: 'axis', axisPointer: {type: 'shadow'},
      formatter: function(ps) {
        return ps[0].name + '<br/>在招岗位：' + ps[0].value + ' 个（占全部岗位 '
             + (ps[0].value / __TOTAL__ * 100).toFixed(2) + '%）';
      }
    },
    grid: {left: 260, right: 90, top: 110, bottom: 50},
    xAxis: {type: 'value', name: '在招岗位数', nameTextStyle: {fontSize: 12},
            axisLabel: {fontSize: 12},
            splitLine: {lineStyle: {type: 'dashed', color: '#e8e8e8'}}},
    yAxis: {type: 'category', data: __NAMES__,
            axisLabel: {fontSize: 12, width: 240, overflow: 'truncate'},
            axisTick: {show: false}},
    series: [{
      name: '在招岗位数', type: 'bar', barMaxWidth: 22,
      data: __VALS__,
      itemStyle: {
        borderRadius: [0, 4, 4, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          {offset: 0, color: '#9ecae1'}, {offset: 1, color: '#2171b5'}])
      },
      label: {show: true, position: 'right', fontSize: 12, formatter: '{c} 个'}
    }]
  }
"""
    option = (option.replace("__NAMES__", js(names))
                    .replace("__VALS__", js(vals))
                    .replace("__TOTAL__", str(len(rows)))
                    .replace("__TOPN__", str(top_n))
                    .replace("__COMPANIES__", str(len(cnt))))
    html_page(os.path.join(OUT_DIR, "06_招聘活跃企业TOP榜_横向柱状图.html"), 1300, 900, option)


# 岗位大类归并规则（按顺序匹配，先命中先归类）
# 说明：原始岗位名称有 6000+ 种（其中 5000+ 只出现 1 次），直接画图无法阅读，
#       因此按关键词归并为 16 个岗位大类；未命中任何规则的归入"其他"。
JOB_CATEGORY_RULES = [
    ("质量管理类", ["质量", "品质", "品控", "品管", "质检", "检测", "化验", "计量", "测量", "三坐标",
                "实验室", "qc", "qa", "qe", "cqe", "sqe", "检验", "体系", "审核"]),
    ("测试类", ["测试", "test"]),
    ("运维与支持类", ["运维", "网络", "安全", "系统管理员", "系统工程师", "it工程师", "it专员", "it经理",
                  "it主管", "it支持", "信息技术", "信息化", "mes", "erp", "sap", "oa",
                  "技术支持", "实施工程", "实施顾问", "售后", "helpdesk", "dba"]),
    ("算法与人工智能类", ["算法", "机器学习", "深度学习", "人工智能", "ai", "nlp", "计算机视觉", "视觉",
                    "数据挖掘", "推荐", "大模型", "智能", "agent"]),
    ("数据分析类", ["数据", "经营分析", "etl", "bi", "报表", "统计"]),
    ("前端与移动端类", ["前端", "web", "h5", "小程序", "android", "ios", "移动端", "客户端", "ui开发"]),
    ("软件开发类", ["开发", "软件", "程序员", "架构", "全栈", "java", "python", "c++", "c#", ".net",
                "golang", "php", "node", "后端", "服务端", "嵌入式", "驱动", "固件", "上位机"]),
    ("硬件与制造类", ["硬件", "电子", "电工", "电路", "pcb", "射频", "电气", "电力", "通信", "自动化", "仪表",
                 "机械", "结构", "模具", "工艺", "设备", "制造", "生产", "工业", "材料", "焊接", "装配",
                 "数控", "光电", "光学", "半导体", "芯片", "机电", "研发", "调试", "维修", "仿真",
                 "可靠性", "厂务", "中试", "制冷", "轴承", "pe工程师", "技术员"]),
    ("产品与项目类", ["产品经理", "产品专员", "项目经理", "项目管理", "项目专员", "pmo", "需求分析", "产品运营"]),
    ("设计类", ["设计", "美工", "视觉设计", "平面", "视频剪辑", "视频制作", "剪辑师", "摄影师", "动画"]),
    ("运营与市场类", ["运营", "市场", "推广", "seo", "sem", "新媒体", "电商", "客服", "销售", "商务",
                 "渠道", "bd", "导购", "店长", "招商", "外贸业务"]),
    ("金融与风控类", ["催收", "风控", "信贷", "证券", "投资", "基金", "保险", "银行", "理财", "金融", "担保"]),
    ("财务类", ["财务", "会计", "出纳", "审计", "税务", "成本", "结算"]),
    ("人事行政类", ["人事", "人力资源", "hr", "招聘", "薪酬", "绩效", "行政", "助理", "文员", "前台",
                 "后勤", "秘书", "管培", "储备干部"]),
    ("教育与培训类", ["教师", "讲师", "培训", "教育", "教练", "助教", "教研"]),
    ("医药生物类", ["医药", "护理", "临床", "生物", "药学", "医疗", "健康"]),
    ("供应链与物流类", ["物流", "仓储", "仓库", "采购", "供应链", "订单", "跟单", "关务", "计划员", "调度"]),
]
OTHER_CATEGORY = "其他"


def job_category(title):
    """把岗位名称归入岗位大类（未命中规则 → 其他）"""
    t = (title or "").strip().lower()
    for cat, kws in JOB_CATEGORY_RULES:
        for kw in kws:
            if kw in t:
                return cat
    return OTHER_CATEGORY


def chart7_job_distribution(rows, top_titles=10):
    """07 岗位分布图（横向柱状图）：按岗位大类 + 高频具体岗位名称"""
    total = len(rows)
    cat_cnt = Counter(job_category(r.get("岗位名称")) for r in rows)
    titles_by_cat = defaultdict(Counter)
    for r in rows:
        t = (r.get("岗位名称") or "").strip()
        titles_by_cat[job_category(t)][t] += 1

    # 高频具体岗位名称（合并大小写差异：java开发工程师 / Java开发工程师）
    norm_title = Counter()
    for r in rows:
        t = re.sub(r"\s+", "", (r.get("岗位名称") or "").strip())
        if t:
            norm_title[t.lower()] += 1
    display = {}
    for r in rows:
        t = re.sub(r"\s+", "", (r.get("岗位名称") or "").strip())
        display.setdefault(t.lower(), t)
    top_t = [(display[k], v) for k, v in norm_title.most_common(top_titles)]

    cats_sorted = cat_cnt.most_common()
    write_csv("07_岗位分布_横向柱状图.csv",
              ["岗位大类", "岗位数", "占比(%)", "该类高频岗位（Top3）"],
              [[c, n, round(n / total * 100, 2),
                "、".join("%s(%d)" % (t, v) for t, v in titles_by_cat[c].most_common(3))]
               for c, n in cats_sorted])

    cats = [c for c, _ in cats_sorted][::-1]            # 反向：最大值显示在最上方
    vals = [n for _, n in cats_sorted][::-1]
    tips = []
    for c in cats:
        ex = "、".join("%s（%d）" % (t, v) for t, v in titles_by_cat[c].most_common(3))
        tips.append(ex or "—")
    t_names = [t for t, _ in top_t][::-1]
    t_vals = [v for _, v in top_t][::-1]

    option = """
  {
    title: {
      text: '岗位分布（按岗位大类 + 高频岗位）',
      subtext: '数据源：处理后数据 __TOTAL__ 条岗位｜原始岗位名称 __KINDS__ 种（__ONCE__ 种仅出现 1 次），按关键词归并为 __NCAT__ 个岗位大类',
      left: 'center', top: 12,
      textStyle: {fontSize: 22, fontWeight: 'bold'},
      subtextStyle: {fontSize: 12, color: '#777'}
    },
    tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'},
      formatter: function(ps) {
        var i = ps[0].dataIndex;
        if (ps[0].seriesIndex === 0) {
          return '<b>' + ps[0].name + '</b><br/>岗位数：' + ps[0].value + '（'
               + (ps[0].value / __TOTAL__ * 100).toFixed(2) + '%）<br/>高频岗位：' + __TIPS__[i];
        }
        return '<b>' + ps[0].name + '</b><br/>岗位数：' + ps[0].value + '（'
             + (ps[0].value / __TOTAL__ * 100).toFixed(2) + '%）';
      }
    },
    grid: [{left: 150, right: 90, top: 110, bottom: 60, width: '42%'},
           {left: '58%', right: 70, top: 110, bottom: 60}],
    xAxis: [
      {type: 'value', gridIndex: 0, name: '岗位数', nameTextStyle: {fontSize: 11},
       axisLabel: {fontSize: 11}, splitLine: {lineStyle: {type: 'dashed', color: '#e8e8e8'}}},
      {type: 'value', gridIndex: 1, name: '岗位数', nameTextStyle: {fontSize: 11},
       axisLabel: {fontSize: 11}, splitLine: {lineStyle: {type: 'dashed', color: '#e8e8e8'}}}
    ],
    yAxis: [
      {type: 'category', gridIndex: 0, data: __CATS__,
       axisLabel: {fontSize: 12}, axisTick: {show: false}},
      {type: 'category', gridIndex: 1, data: __TNAMES__,
       axisLabel: {fontSize: 11, width: 150, overflow: 'truncate'}, axisTick: {show: false}}
    ],
    series: [
      {name: '岗位大类', type: 'bar', xAxisIndex: 0, yAxisIndex: 0, barMaxWidth: 22,
       data: __VALS__,
       itemStyle: {borderRadius: [0, 4, 4, 0],
         color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
           {offset: 0, color: '#9ecae1'}, {offset: 1, color: '#2171b5'}])},
       label: {show: true, position: 'right', fontSize: 11,
               formatter: function(p) { return p.value + '（' + (p.value / __TOTAL__ * 100).toFixed(1) + '%）'; }}},
      {name: '高频岗位名称', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, barMaxWidth: 16,
       data: __TVALS__,
       itemStyle: {borderRadius: [0, 4, 4, 0],
         color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
           {offset: 0, color: '#ffd591'}, {offset: 1, color: '#fa8c16'}])},
       label: {show: true, position: 'right', fontSize: 11, formatter: '{c}'}}
    ]
  }
"""
    option = (option.replace("__CATS__", js(cats))
                    .replace("__VALS__", js(vals))
                    .replace("__TIPS__", js(tips))
                    .replace("__TNAMES__", js(t_names))
                    .replace("__TVALS__", js(t_vals))
                    .replace("__TOTAL__", str(total))
                    .replace("__KINDS__", str(len(set((r.get("岗位名称") or "").strip() for r in rows))))
                    .replace("__ONCE__", str(sum(1 for v in Counter(
                        (r.get("岗位名称") or "").strip() for r in rows).values() if v == 1)))
                    .replace("__NCAT__", str(len(cats))))
    html_page(os.path.join(OUT_DIR, "07_岗位分布_横向柱状图.html"), 1500, 900, option)
    return cats_sorted


def main():
    src = pick_source()
    rows = load_rows(src)
    print("数据源:", os.path.relpath(src, ROOT), "｜行数:", len(rows))
    salary_ok = sum(1 for r in rows if parse_salary(r.get("岗位薪资")))
    print("薪资可解析:", salary_ok, "/", len(rows))
    print("生成图表：")
    chart1_salary_distribution(rows)
    chart2_experience_stack(rows)
    chart3_skill_wordcloud(rows)
    chart4_education_pie(rows)
    chart5_experience_salary_lines(rows)
    chart6_top_companies(rows)
    cats = chart7_job_distribution(rows)
    print("  岗位大类分布:", ", ".join("%s %d(%.1f%%)" % (c, n, n / len(rows) * 100)
                                       for c, n in cats))
    print("输出目录:", OUT_DIR)

    if "--no-png" not in sys.argv:
        chrome = find_chrome()
        if not chrome:
            print("未找到 Chrome，跳过 PNG 导出（HTML 已生成，可用浏览器打开后另存为图片）")
        else:
            print("导出 PNG（Chrome 无头模式）：")
            for name in CHART_FILES:
                ok = export_png(os.path.join(OUT_DIR, name + ".html"),
                                os.path.join(OUT_DIR, name + ".png"), chrome)
                print("  %s -> %s" % (name, "OK" if ok else "失败"))


if __name__ == "__main__":
    main()
