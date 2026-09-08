# -*- coding: utf-8 -*-
"""厦门全量扫库(无关键词)+计算机岗位过滤: 抓取关键词搜索未覆盖的岗位。

用法: python scripts/xiamen_full.py
输出: 追加到 data/raw/zhaopin_jobs.csv (来源关键词='厦门全岗位', job_key 去重)
"""
import random
import re
import sys
import time
from urllib.parse import quote

from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import zhaopin_crawler as zc   # noqa: E402

CITY_CODE = 682
CITY_NAME = "厦门"

# 计算机相关标题/标签特征词
TECH = re.compile(
    r"java|python|\.net|php|c\+\+|c#|golang|javascript|vue|react|node|前端|后端|"
    r"开发|测试|算法|运维|数据|大数据|嵌入式|android|ios|鸿蒙|小程序|网络安全|"
    r"信息安全|数据库|云计算|架构|机器学习|深度学习|人工智能|ai|自动化|软件|"
    r"程序员|爬虫|全栈|产品|研发", re.I)


def is_tech(row):
    text = " ".join([row.get("岗位名称") or "", row.get("技能标签") or "",
                     row.get("公司名字") or ""])
    return bool(TECH.search(text))


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
        print(f"历史 {len(ids)} 条; 开始厦门全量扫库...", flush=True)
        url = f"https://www.zhaopin.com/jobs?jl={CITY_CODE}&kt=3"
        zc.open_list(drv, url)
        added = 0
        stable = 0
        for batch in range(1, zc.MAX_SCROLLS * 2 + 1):
            rows, no_grow = zc.scroll_batch(drv, url)
            for r in rows:
                if r.get("job_key") in ids:
                    continue
                if not is_tech(r):
                    continue
                r["来源关键词"] = "厦门全岗位(计算机过滤)"
                ids.add(r["job_key"])
                zc.write_row(r)
                added += 1
            if added > 0:
                stable = 0
            else:
                stable += 1
            if batch % 20 == 0:
                print(f"  滚动{batch}批, 本批累计新增 {added}, 总 {len(ids)}", flush=True)
            if no_grow and stable >= zc.STABLE_STOP:
                print(f"  连续{stable}批无新增, 结束", flush=True)
                break
            time.sleep(random.uniform(1.4, 2.4))
        zc.flush_pending()
        print(f"厦门全量扫库完成: 新增计算机岗位 {added} 条 → 总累计 {len(ids)}", flush=True)
    finally:
        drv.quit()


if __name__ == "__main__":
    main()
