# -*- coding: utf-8 -*-
"""
任务4 · 地域分布可视化：中国地图（各省岗位数）+ 福建省地图（各市岗位数）

数据来源：data/processed/zhaopin_jobs_cleaned.csv（清洗后 8,836 行）
统计口径：取"岗位地区"字段的第一个词作为城市（如"厦门 思明 莲前"→厦门），
         再按《城市→省份》映射表汇总到省；没有数据的省份/城市记为 0。
输出：reports/figures/ 下的 2 个 HTML 地图 + 2 个统计 CSV
"""
import csv
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_CSV = os.path.join(ROOT, "data", "processed", "zhaopin_jobs_cleaned.csv")
OUT_DIR = os.path.join(ROOT, "reports", "figures")
os.makedirs(OUT_DIR, exist_ok=True)

# 城市 → 省份（覆盖数据中出现的全部 16 个城市）
CITY2PROV = {
    "苏州": "江苏省", "福州": "福建省", "厦门": "福建省", "宁波": "浙江省",
    "嘉兴": "浙江省", "湖州": "浙江省", "泉州": "福建省", "滁州": "安徽省",
    "漳州": "福建省", "安庆": "安徽省", "莆田": "福建省", "丽水": "浙江省",
    "南平": "福建省", "龙岩": "福建省", "三明": "福建省", "舟山": "浙江省",
}

# 中国地图 GeoJSON（阿里 DataV）中的 34 个省级区域名称
CHINA_REGIONS = [
    "北京市", "天津市", "河北省", "山西省", "内蒙古自治区", "辽宁省", "吉林省",
    "黑龙江省", "上海市", "江苏省", "浙江省", "安徽省", "福建省", "江西省",
    "山东省", "河南省", "湖北省", "湖南省", "广东省", "广西壮族自治区", "海南省",
    "重庆市", "四川省", "贵州省", "云南省", "西藏自治区", "陕西省", "甘肃省",
    "青海省", "宁夏回族自治区", "新疆维吾尔自治区", "台湾省", "香港特别行政区",
    "澳门特别行政区",
]

# 福建省地图 GeoJSON（350000_full）中的 9 个地级市
FUJIAN_CITIES = ["福州市", "厦门市", "莆田市", "三明市", "泉州市",
                 "漳州市", "南平市", "龙岩市", "宁德市"]

COLOR_RAMP = ["#f7fbff", "#deebf7", "#c6dbef", "#9ecae1", "#6baed6", "#3182bd"]


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def city_of(region_text):
    parts = (region_text or "").replace("\u3000", " ").split()
    return parts[0] if parts else ""


def count_jobs(rows):
    city = Counter()
    unknown = Counter()
    for r in rows:
        c = city_of(r.get("岗位地区"))
        if c in CITY2PROV:
            city[c] += 1
        else:
            unknown[c] += 1
    prov = Counter()
    for c, n in city.items():
        prov[CITY2PROV[c]] += n
    return city, prov, unknown


def write_csv(path, header, records):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(records)


def js_data(pairs):
    return ",\n            ".join(
        "{ name: '%s', value: %d }" % (n, v) for n, v in pairs)


def build_china_html(prov_counter, total, out_path):
    data = [(p, prov_counter.get(p, 0)) for p in CHINA_REGIONS]
    max_value = max(v for _, v in data) or 1
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>中国各省份岗位数量分布</title>
    <!-- 引入 ECharts CDN -->
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            width: 100vw; height: 100vh; background: #f5f7fa;
            display: flex; flex-direction: column; align-items: center;
            justify-content: center; font-family: "Microsoft YaHei", sans-serif;
        }
        h2 { color: #333; margin-bottom: 8px; }
        p.sub { color: #666; font-size: 13px; margin-bottom: 12px; }
        #map-container {
            width: 90%; height: 85%; background: #fff;
            border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        }
    </style>
</head>
<body>
    <h2>中国各省份岗位数量分布</h2>
    <p class="sub">数据来源：data/processed/zhaopin_jobs_cleaned.csv（清洗后 __TOTAL__ 条岗位）｜ 统计字段：岗位地区 ｜ 颜色越深岗位数越多，无数据省份记为 0</p>
    <div id="map-container"></div>

    <script>
        const myChart = echarts.init(document.getElementById('map-container'));

        // 各省岗位数量（按"岗位地区"字段汇总，无数据为 0）
        const mapData = [
            __DATA__
        ];

        const maxValue = __MAX__;

        fetch('https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json')
            .then(response => response.json())
            .then(chinaJson => {
                echarts.registerMap('china', chinaJson);

                const option = {
                    tooltip: {
                        trigger: 'item',
                        formatter: function(params) {
                            const v = (params.value === undefined || params.value === null) ? 0 : params.value;
                            const pct = (v / __TOTAL__ * 100).toFixed(2);
                            return `${params.name}<br/>岗位数量：${v}<br/>占比：${pct}%`;
                        }
                    },
                    visualMap: {
                        min: 0,
                        max: maxValue,
                        left: 'left',
                        bottom: '5%',
                        text: ['多', '少'],
                        calculable: true,
                        inRange: { color: __RAMP__ }
                    },
                    series: [
                        {
                            name: '岗位数量',
                            type: 'map',
                            map: 'china',
                            roam: true,
                            label: {
                                show: true,
                                fontSize: 8,
                                color: '#333',
                                formatter: function(params) {
                                    const v = (params.value === undefined || params.value === null) ? 0 : params.value;
                                    return `${params.name}\\n${v}`;
                                }
                            },
                            itemStyle: {
                                borderWidth: 0.5,
                                borderColor: '#ffffff',
                                areaColor: '#f7fbff'
                            },
                            emphasis: {
                                label: { color: '#fff', fontSize: 12 },
                                itemStyle: { areaColor: '#f46d43' }
                            },
                            data: mapData
                        }
                    ]
                };

                myChart.setOption(option);
            })
            .catch(function(err) {
                document.getElementById('map-container').innerHTML =
                    '<p style="padding:40px;color:#c00">地图 GeoJSON 加载失败（需要联网访问 geo.datav.aliyun.com）：' + err + '</p>';
            });

        window.addEventListener('resize', () => { myChart.resize(); });
    </script>
</body>
</html>
"""
    html = (html.replace("__DATA__", js_data(data))
                .replace("__MAX__", str(max_value))
                .replace("__TOTAL__", str(total))
                .replace("__RAMP__", str(COLOR_RAMP).replace("'", '"')))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


def build_fujian_html(city_counter, total, out_path):
    data = []
    for c in FUJIAN_CITIES:
        data.append((c, city_counter.get(c[:-1], 0)))
    max_value = max(v for _, v in data) or 1
    fj_total = sum(v for _, v in data)
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>福建省各市岗位数量分布</title>
    <!-- 引用ECharts在线CDN（无需本地echarts.min.js文件，适配实验环境） -->
    <script src="https://cdn.bootcdn.net/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
    <style>
        html,body,#main{ padding: 0px; margin: 0px; height: 100%; overflow: hidden; }
        #tip {
            position: absolute; left: 20px; top: 12px; color: #666;
            font-size: 13px; font-family: "Microsoft YaHei", sans-serif;
        }
    </style>
</head>
<body>
<div id="main"></div>
<div id="tip">数据来源：data/processed/zhaopin_jobs_cleaned.csv（清洗后 __TOTAL__ 条岗位，其中福建省 __FJTOTAL__ 条）｜ 颜色越深岗位数越多，无数据城市记为 0</div>
<script type="text/javascript">
    // 各市岗位数量（按"岗位地区"字段汇总，无数据为 0）
    var mapData = [
        __DATA__
    ];

    var maxValue = __MAX__;

    // 加载福建省地图JSON数据（使用实验相关接口）
    $.get("https://geo.datav.aliyun.com/areas_v3/bound/350000_full.json", function(map) {
        var myChart = echarts.init(document.getElementById('main'));
        echarts.registerMap("fujian", map);

        var option = {
            title: {
                text: '福建省各市岗位数量分布',
                left: 'center',
                top: 12,
                textStyle: { fontSize: 20, fontWeight: 'bold' }
            },
            tooltip: {
                trigger: 'item',
                formatter: function(params) {
                    var v = (params.value === undefined || params.value === null) ? 0 : params.value;
                    var pct = (v / __FJTOTAL__ * 100).toFixed(2);
                    return params.name + '<br/>岗位数量：' + v + '<br/>占福建省比例：' + pct + '%';
                }
            },
            visualMap: {
                min: 0,
                max: maxValue,
                left: 'left',
                bottom: '5%',
                text: ['多', '少'],
                calculable: true,
                inRange: { color: __RAMP__ }
            },
            series: [
                {
                    name: '岗位数量',
                    map: "fujian",
                    type: "map",
                    aspectScale: 1.2,
                    selectedMode: 'single',
                    hoverable: true,
                    roam: true,
                    label: {
                        show: true,
                        fontSize: 11,
                        color: '#333',
                        formatter: function(params) {
                            var v = (params.value === undefined || params.value === null) ? 0 : params.value;
                            return params.name + '\\n' + v;
                        }
                    },
                    itemStyle: {
                        borderWidth: 1,
                        borderColor: '#ffffff',
                        areaColor: '#f7fbff'
                    },
                    emphasis: {
                        label: { color: '#fff', fontSize: 13 },
                        itemStyle: { areaColor: '#f46d43', borderColor: '#ff6600', borderWidth: 2 }
                    },
                    data: mapData
                }
            ]
        };

        myChart.setOption(option);
        window.addEventListener('resize', function() { myChart.resize(); });
    }).fail(function() {
        document.getElementById('main').innerHTML =
            '<p style="padding:40px;color:#c00">地图 GeoJSON 加载失败（需要联网访问 geo.datav.aliyun.com）</p>';
    });
</script>
</body>
</html>
"""
    html = (html.replace("__DATA__", js_data(data))
                .replace("__MAX__", str(max_value))
                .replace("__TOTAL__", str(total))
                .replace("__FJTOTAL__", str(fj_total))
                .replace("__RAMP__", str(COLOR_RAMP).replace("'", '"')))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return fj_total


def main():
    rows = read_rows(SRC_CSV)
    total = len(rows)
    city, prov, unknown = count_jobs(rows)

    print("总行数(清洗后):", total)
    print("未识别城市:", dict(unknown) if unknown else "无")
    print("覆盖行数校验:", sum(prov.values()) + sum(unknown.values()), "/", total)

    # 1) 中国地图：各省岗位数
    prov_records = sorted(((p, prov.get(p, 0)) for p in CHINA_REGIONS),
                          key=lambda x: -x[1])
    write_csv(os.path.join(OUT_DIR, "中国各省岗位数量.csv"),
              ["省份", "岗位数量", "占比(%)"],
              [[p, n, round(n / total * 100, 2)] for p, n in prov_records])
    build_china_html(prov, total, os.path.join(OUT_DIR, "中国地图_岗位数量分布.html"))

    # 2) 福建省地图：各市岗位数
    fj_records = sorted(((c[:-1], city.get(c[:-1], 0)) for c in FUJIAN_CITIES),
                        key=lambda x: -x[1])
    fj_total = sum(n for _, n in fj_records)
    write_csv(os.path.join(OUT_DIR, "福建省各市岗位数量.csv"),
              ["城市", "岗位数量", "占福建省比例(%)"],
              [[c, n, round(n / fj_total * 100, 2) if fj_total else 0]
               for c, n in fj_records])
    build_fujian_html(city, total, os.path.join(OUT_DIR, "福建省地图_岗位数量分布.html"))

    print("非零省份:", dict(prov.most_common()))
    print("福建省各市:", dict(fj_records))
    print("输出目录:", OUT_DIR)


if __name__ == "__main__":
    main()
