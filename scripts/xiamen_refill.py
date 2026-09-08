# -*- coding: utf-8 -*-
"""厦门专项补抓: 清空厦门已做组合, 重跑全部29个计算机关键词, 尽可能多抓。

用法: python scripts/xiamen_refill.py
输出: 追加到 data/raw/zhaopin_jobs.csv (job_key 去重)
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
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

import zhaopin_crawler as zc   # noqa: E402

CITY_CODE = 682
CITY_NAME = "厦门"


def main():
    state = zc.load_state()
    # 清掉厦门的所有已做组合, 使其全部重抓
    before = len(state.get("combo_done", []))
    state["combo_done"] = [c for c in state.get("combo_done", [])
                           if not c.startswith("厦门_")]
    zc.save_state(state)
    print(f"已清空厦门组合 {before - len(state['combo_done'])} 个, 重抓全部关键词", flush=True)

    zc.ensure_chrome()
    drv = zc.attach()
    try:
        ids = zc.load_ids()
        kw_list = zc.KEYWORDS + zc.EXTRA_KEYWORDS
        print(f"历史 {len(ids)} 条; 厦门关键词 {len(kw_list)} 个", flush=True)
        for kw in kw_list:
            combo = f"厦门_{kw}"
            if combo in state["combo_done"]:
                continue
            url = f"https://www.zhaopin.com/jobs?jl={CITY_CODE}&kw={quote(kw)}&kt=3"
            if not zc.open_list(drv, url):
                if zc.blocked(drv):
                    print(f"[验证] {kw} 留待后续", flush=True)
                    time.sleep(60)
                    continue
                state["combo_done"].append(combo)
                zc.save_state(state)
                print(f"[空] 厦门×{kw} 无岗位", flush=True)
                continue
            added = 0
            stable = 0
            for _ in range(zc.MAX_SCROLLS):
                rows, no_grow = zc.scroll_batch(drv, url)
                new = [r for r in rows if r.get("job_key") not in ids]
                for r in new:
                    r["来源关键词"] = kw
                    ids.add(r["job_key"])
                    zc.write_row(r)
                    added += 1
                if new:
                    stable = 0
                else:
                    stable += 1
                if no_grow and stable >= zc.STABLE_STOP:
                    break
                time.sleep(random.uniform(1.6, 3))
            state["combo_done"].append(combo)
            zc.save_state(state)
            zc.flush_pending()
            print(f"厦门×{kw}: +{added} → 累计 {len(ids)}", flush=True)
            time.sleep(random.uniform(4, 8))
        print(f"厦门补抓完成, 当前累计 {len(ids)} 条", flush=True)
    finally:
        drv.quit()


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    main()
