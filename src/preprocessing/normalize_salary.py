# -*- coding: utf-8 -*-
"""
任务3 · 追加清洗：把 `岗位薪资` 列统一成规范格式

背景：原始薪资写法五花八门（655 种），既有 `1-1.5万`、也有 `6000-8000元`、
`100-150元/天`、`20-40元/时`、`150元/次`，还有 `·13薪/·14薪` 等后缀，无法直接比较。

规范规则（统一为"月薪区间 + 元"）：
  1) 单位统一：`万` → ×10000；`千`/`k` → ×1000；`元` 原样
  2) 日薪/时薪折算为月薪：`元/天` × 21.75、`元/时` × 174（21.75 天/月 × 8 小时）
  3) 格式统一：区间写作 `10000-15000元`；单值写作 `8000元`
  4) 保留薪资月数后缀（如 `·13薪`）→ `12000-23000元·13薪`
  5) `元/次` 无法折算为月薪，保留原单位（如 `1000-2000元/次`）
  6) 数字均取整（四舍五入）

输出（原地更新 + 对照表）：
  · `data/processed/zhaopin_jobs_cleaned_seg.csv`
      - `岗位薪资` 列替换为规范格式
      - 新增 3 列：`岗位薪资(原始)`（可追溯）、`薪资下限(元/月)`、`薪资上限(元/月)`
  · `data/processed/薪资规范化对照表.csv`（原始写法 → 规范写法 + 数值 + 出现行数）

运行：python src/preprocessing/normalize_salary.py
"""
import csv
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SRC = os.path.join(ROOT, "data", "processed", "zhaopin_jobs_cleaned_seg.csv")
MAP_CSV = os.path.join(ROOT, "data", "processed", "薪资规范化对照表.csv")

DAYS_PER_MONTH = 21.75      # 月均工作日
HOURS_PER_MONTH = 174.0     # 21.75 天 × 8 小时
UNIT_FACTOR = {"月": 1.0, "日": DAYS_PER_MONTH, "时": HOURS_PER_MONTH}
SUFFIX_RE = re.compile(r"[·・]?(1[0-9]|[1-9])薪")


def split_unit(text):
    """拆出单位与后缀，返回 (主体, 单位, 后缀)"""
    t = (text or "").strip().replace(" ", "")
    suffix = ""
    m = SUFFIX_RE.search(t)
    if m:
        suffix = "·%s薪" % m.group(1)
        t = t.replace(m.group(0), "")
    unit = "月"
    for key, u in (("/天", "日"), ("/时", "时"), ("/小时", "时"), ("/次", "次")):
        if key in t:
            unit = u
            t = t.replace(key, "")
            break
    return t, unit, suffix


def parse_salary(text):
    """→ dict(min, max, unit, suffix, norm) ；无法解析返回 None"""
    body, unit, suffix = split_unit(text)
    if not body:
        return None
    nums = re.findall(r"(\d+(?:\.\d+)?)(万|千|[kK])?", body)
    # 共享单位：`1-1.5万` 表示 1万~1.5万，第一个数字没带单位时也要按"万"放大
    shared = None
    for _, u in nums:
        if u == "万":
            shared = 10000
            break
        if u in ("千", "k", "K"):
            shared = 1000
            break
    vals = []
    for n, u in nums:
        v = float(n)
        if u == "万":
            v *= 10000
        elif u in ("千", "k", "K"):
            v *= 1000
        elif shared:
            v *= shared
        vals.append(v)
    if not vals:
        return None
    if "以下" in body:
        lo, hi = 0.0, vals[0]
    elif "以上" in body:
        lo = hi = vals[0]
    else:
        lo, hi = min(vals), max(vals)

    if unit == "次":                       # 按次无法折算为月薪：保留原单位
        norm = "%d-%d元/次" % (round(lo), round(hi)) if lo != hi else "%d元/次" % round(hi)
        return {"lo": "", "hi": "", "unit": unit, "suffix": suffix, "norm": norm}

    f = UNIT_FACTOR[unit]
    lo_m, hi_m = round(lo * f), round(hi * f)
    norm = "%d-%d元" % (lo_m, hi_m) if lo_m != hi_m else "%d元" % hi_m
    return {"lo": lo_m, "hi": hi_m, "unit": unit, "suffix": suffix, "norm": norm + suffix}


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig", newline="")))
    fields = list(rows[0].keys())
    print("输入：%d 行 × %d 列" % (len(rows), len(fields)))

    mapping = {}          # 原始写法 -> 解析结果
    stats = Counter()
    unknown = []
    for r in rows:
        raw = (r.get("岗位薪资") or "").strip()
        res = mapping.get(raw)
        if res is None:
            res = parse_salary(raw)
            mapping[raw] = res
        if res is None:
            unknown.append(raw)
            stats["无法解析"] += 1
        else:
            stats[res["unit"]] += 1

    # 写回：替换 岗位薪资，并新增 3 列
    new_fields = fields + ["岗位薪资(原始)", "薪资下限(元/月)", "薪资上限(元/月)"]
    for r in rows:
        raw = (r.get("岗位薪资") or "").strip()
        res = mapping[raw]
        r["岗位薪资(原始)"] = raw
        if res is None:
            r["薪资下限(元/月)"] = ""
            r["薪资上限(元/月)"] = ""
        else:
            r["岗位薪资"] = res["norm"]
            r["薪资下限(元/月)"] = res["lo"]
            r["薪资上限(元/月)"] = res["hi"]

    with open(SRC, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=new_fields)
        w.writeheader()
        w.writerows(rows)
    print("已写回：%s（%d 行 × %d 列）" % (os.path.relpath(SRC, ROOT), len(rows), len(new_fields)))

    # 对照表
    cnt = Counter((r["岗位薪资(原始)"] or "") for r in rows)
    recs = []
    for raw, n in cnt.most_common():
        res = mapping[raw]
        recs.append([raw, res["norm"] if res else raw, res["lo"] if res else "",
                     res["hi"] if res else "", res["unit"] if res else "", n])
    with open(MAP_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["原始写法", "规范化写法", "下限(元/月)", "上限(元/月)", "原单位", "出现行数"])
        w.writerows(recs)

    print("\n=== 单位分布（行数）===")
    for k in ["月", "日", "时", "次", "无法解析"]:
        if stats[k]:
            print("  %-6s %5d 行（%.2f%%）" % (k, stats[k], stats[k] / len(rows) * 100))
    if unknown:
        print("  无法解析样例：", Counter(unknown).most_common(5))
    print("\n=== 规范化样例 ===")
    for raw, res in list(mapping.items())[:0]:
        pass
    for raw in ["1-1.5万", "1.2-2.3万·13薪", "6000-8000元", "9000-18000元·13薪",
                "100-150元/天", "20-40元/时", "18元/时", "150元/次", "1000元以下·13薪"]:
        if raw in mapping:
            res = mapping[raw]
            print("  %-18s → %s（原单位 %s）" % (raw, res["norm"] if res else "未解析",
                                              res["unit"] if res else "-"))
    print("\n对照表：%s（%d 种写法）" % (os.path.relpath(MAP_CSV, ROOT), len(recs)))


if __name__ == "__main__":
    main()
