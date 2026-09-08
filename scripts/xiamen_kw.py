# -*- coding: utf-8 -*-
"""厦门岗位采集(原语义): 用全部计算机关键词逐一搜索厦门,
来源关键词=触发该条被抓的关键词(如 java/python/数据分析/数据库…)。

写入: data/raw/zhaopin_jobs.csv (UTF-8, 固定列, 仅厦门)
用法: python scripts/xiamen_kw.py
"""
import random
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import zhaopin_crawler as zc   # noqa: E402

CITY_CODE = 682


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
        kws = zc.KEYWORDS + zc.EXTRA_KEYWORDS
        print(f"开始: 历史 {len(ids)} 条; 厦门全计算机关键词 {len(kws)} 个", flush=True)
        for kw in kws:
            url = f"https://www.zhaopin.com/jobs?jl={CITY_CODE}&kw={quote(kw)}&kt=3"
            if not zc.open_list(drv, url):
                print(f"[跳过] {kw}: 无结果/验证", flush=True)
                time.sleep(30)
                continue
            batch_new = 0
            stable = 0
            for _ in range(zc.MAX_SCROLLS):
                rows, no_grow = zc.scroll_batch(drv, url)
                n = 0
                for r in rows:
                    if r.get("job_key") in ids:
                        continue
                    r["来源关键词"] = kw          # 原语义: 用哪个词搜到记哪个词
                    ids.add(r["job_key"])
                    zc.write_row(r)
                    n += 1
                batch_new += n
                if n:
                    stable = 0
                else:
                    stable += 1
                if no_grow and stable >= 4:
                    break
                time.sleep(random.uniform(1.3, 2.2))
            print(f"厦门×{kw}: +{batch_new} → 累计 {len(ids)}", flush=True)
            time.sleep(random.uniform(2, 4))
        zc.flush_pending()
        print(f"厦门关键词抓取完成, 累计 {len(ids)} 条 (zhaopin_jobs.csv)", flush=True)
    finally:
        drv.quit()


if __name__ == "__main__":
    main()
