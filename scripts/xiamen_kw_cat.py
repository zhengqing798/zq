# -*- coding: utf-8 -*-
"""厦门岗位采集(类别限定) - 关键词驱动版: 逐词滚动抓取并标注类别,
追加写入 data/raw/zhaopin_jobs.csv(UTF-8, 固定列, 与原表一致).

用法: python scripts/xiamen_kw_cat.py
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

CAT_A = re.compile(
    r"java|python|\.net|php|c\+\+|c#|golang|javascript|vue|react|node|前端|后端|"
    r"工程师|技术|研发|开发|软件|硬件|嵌入式|android|ios|鸿蒙|小程序|网络|通信|"
    r"物联网|信息安全|数据库|云计算|数据|算法|机器学习|深度学习|人工智能|架构|"
    r"爬虫|全栈|实施|产品|服务端|客户端", re.I)
CAT_B = re.compile(r"运维|测试|qa|质量保障|技术支持|实施工程师", re.I)


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
        kws = zc.KEYWORDS + zc.EXTRA_KEYWORDS
        added = {"互联网/通信及硬件": 0, "运维/测试": 0}
        print(f"开始: 历史 {len(ids)} 条; 厦门 关键词 {len(kws)} 个", flush=True)
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
                    cat = cat_of(r)
                    if not cat:
                        continue
                    r["来源关键词"] = f"厦门-{cat}"
                    ids.add(r["job_key"])
                    zc.write_row(r)
                    added[cat] += 1
                    n += 1
                batch_new += n
                if n:
                    stable = 0
                else:
                    stable += 1
                if no_grow and stable >= 4:
                    break
                time.sleep(random.uniform(1.3, 2.2))
            print(f"厦门×{kw}: +{batch_new} "
                  f"(A:{added['互联网/通信及硬件']} B:{added['运维/测试']}) → 累计{len(ids)}",
                  flush=True)
            time.sleep(random.uniform(2, 4))
        zc.flush_pending()
        print(f"完成: A+{added['互联网/通信及硬件']}, B+{added['运维/测试']}; "
              f"累计 {len(ids)} 条(zhaopin_jobs.csv)", flush=True)
    finally:
        drv.quit()


if __name__ == "__main__":
    main()
