# -*- coding: utf-8 -*-
"""厦门岗位采集(类别限定): ①互联网/通信及硬件 ②运维/测试; 写入 zhaopin_jobs.csv。

用法: python scripts/xiamen_categories.py
"""
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import zhaopin_crawler as zc   # noqa: E402

CITY_CODE = 682
CAT_A = re.compile(
    r"java|python|\.net|php|c\+\+|c#|golang|javascript|vue|react|node|前端|后端|"
    r"开发|软件|硬件|嵌入式|android|ios|鸿蒙|小程序|网络|通信|物联网|信息安全|"
    r"数据库|云计算|数据|算法|机器学习|深度学习|人工智能|架构|全栈|爬虫|产品经理", re.I)
CAT_B = re.compile(r"运维|测试|实施|技术支持|devops|qa|质量保障", re.I)


def cat_of(row):
    t = " ".join([row.get("岗位名称") or "", row.get("技能标签") or ""])
    if CAT_B.search(t):
        return "运维/测试"
    if CAT_A.search(t):
        return "互联网/通信及硬件"
    return ""


def main():
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    zc.ensure_chrome()
    drv = zc.attach()
    try:
        ids = zc.load_ids()
        print(f"历史 {len(ids)} 条; 厦门两类岗位扫库开始", flush=True)
        url = f"https://www.zhaopin.com/jobs?jl={CITY_CODE}&kt=3"
        zc.open_list(drv, url)
        added = { "互联网/通信及硬件": 0, "运维/测试": 0 }
        stable = 0
        for batch in range(1, zc.MAX_SCROLLS * 2 + 1):
            rows, no_grow = zc.scroll_batch(drv, url)
            batch_new = 0
            for r in rows:
                if r.get("job_key") in ids:
                    continue
                cat = cat_of(r)
                if not cat:
                    continue
                r["来源关键词"] = f"厦门-{cat}"
                ids.add(r["job_key"])
                zc.write_row(r)
                added[cat] += 1
                batch_new += 1
            if batch_new:
                stable = 0
            else:
                stable += 1
            if batch % 20 == 0:
                print(f"  滚动{batch}批 | 新增 A:{added['互联网/通信及硬件']} "
                      f"B:{added['运维/测试']} | 总{len(ids)}", flush=True)
            if no_grow and stable >= zc.STABLE_STOP:
                print("  列表已穷尽(连续无新增)", flush=True)
                break
            time.sleep(random.uniform(1.4, 2.6))
        zc.flush_pending()
        print(f"完成: 互联网/通信及硬件 +{added['互联网/通信及硬件']} 条, "
              f"运维/测试 +{added['运维/测试']} 条; 累计 {len(ids)} 条 (zhaopin_jobs.csv)", flush=True)
    finally:
        drv.quit()


if __name__ == "__main__":
    main()
