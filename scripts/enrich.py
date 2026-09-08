# -*- coding: utf-8 -*-
"""为 zhaopin_jobs.csv 补两列: 岗位链接 + 职位描述 (试点/全量).

试点: python scripts/enrich.py --limit 20
全量: python scripts/enrich.py
机制: 按 (城市,关键词) 复现搜索页 → 滚动定位与数据行 job_key 相同的卡片 →
      精准点击岗位标题 → 新标签取得真实详情URL → 抓职位描述 → 回填。
"""
import csv
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import zhaopin_crawler as zc   # noqa: E402

CSV = ROOT / "data" / "raw" / "zhaopin_jobs.csv"
CITY_CODES = {"福州": 681, "厦门": 682, "泉州": 685, "漳州": 687, "莆田": 683,
              "宁德": 690, "龙岩": 689, "三明": 684, "南平": 688,
              "温州": 655, "杭州": 653, "宁波": 654, "南昌": 691, "长沙": 749,
              "武汉": 736, "成都": 801, "西安": 854, "南京": 635, "苏州": 639,
              "济南": 702, "青岛": 703, "郑州": 719, "合肥": 664, "昆明": 831}
REAL_KW = set(zc.KEYWORDS + zc.EXTRA_KEYWORDS)

DESC_SELECTORS = [".job_detail", ".job-intro", ".job_msg", "[class*='job-desc']",
                  "[class*='describe']", ".job_detail_content", ".tCompany_main",
                  "[class*='JobDetail']", "[class*='content'] .describtion"]


def grab_desc(drv):
    for sel in DESC_SELECTORS:
        for el in drv.find_elements("css selector", sel)[:3]:
            t = el.text.strip()
            if len(t) > 60:
                return t[:4000]
    return ""


def process_query(drv, city, kw, target):
    """打开查询并滚动, 匹配目标 job_key 的卡片, 点击取链接与描述。"""
    url = f"https://www.zhaopin.com/jobs?jl={CITY_CODES[city]}&kw={quote(kw)}&kt=3"
    if not zc.open_list(drv, url):
        return None
    for _ in range(zc.MAX_SCROLLS):
        cards = drv.find_elements("css selector", ".job-card")
        for c in cards:
            try:
                row = zc.parse_card(drv, c)
            except Exception:
                continue
            if row and row.get("job_key") == target:
                # 精准点击标题区域
                el = None
                for css in (".job-card__title-main", ".job-card__title-row"):
                    try:
                        el = c.find_element("css selector", css)
                        break
                    except Exception:
                        pass
                if not el:
                    return None
                before = drv.window_handles
                before_url = drv.current_url
                try:
                    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(drv).move_to_element(el).pause(0.2).click().perform()
                except Exception:
                    return None
                link = ""
                for _w in range(6):
                    time.sleep(0.8)
                    if len(drv.window_handles) > len(before):
                        drv.switch_to.window(drv.window_handles[-1])
                        link = drv.current_url.split("&")[0]
                        break
                    if drv.current_url != before_url:
                        link = drv.current_url.split("&")[0]
                        break
                time.sleep(2)
                if zc.blocked(drv):
                    time.sleep(60)
                desc = grab_desc(drv)
                if not desc:
                    try:
                        (ROOT / "data/raw/_detail_probe.html").write_text(
                            drv.page_source[:400000], encoding="utf-8")
                    except Exception:
                        pass
                if len(drv.window_handles) > len(before):
                    try:
                        drv.close()
                    except Exception:
                        pass
                    drv.switch_to.window(before[0])
                else:
                    try:
                        drv.get(url)
                    except Exception:
                        pass
                return {"link": link, "desc": desc}
        rows2, no_grow = zc.scroll_batch(drv, url)
        if no_grow:
            break
        time.sleep(random.uniform(1.2, 2))
    return None


def main():
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    lines = CSV.read_text(encoding="utf-8-sig").splitlines()
    head = lines[0].split(",")
    need_head = ["岗位链接", "职位描述"]
    for n in need_head:
        if n not in head:
            head.append(n)
    fieldnames = head
    recs = []
    for raw in csv.DictReader(CSV.open(encoding="utf-8-sig", newline="")):
        d = {k: raw.get(k, "") for k in fieldnames}
        recs.append(d)
    todo = [d for d in recs if not (d.get("岗位链接") or d.get("职位描述"))]
    if args.limit:
        todo = todo[: args.limit]
    print(f"共 {len(recs)} 行, 待补 {len(todo)} 行(本次处理 {len(todo)})", flush=True)

    zc.ensure_chrome()
    drv = zc.attach()
    done = 0
    try:
        for i, d in enumerate(todo):
            city = (d.get("城市(实测)") or "").split()[0]
            kw = d.get("来源关键词") or ""
            if kw not in REAL_KW or kw.startswith("厦门-") or "全岗位" in kw:
                kw = "数据分析"     # 兜底可检索词
            if city not in CITY_CODES:
                continue
            got = process_query(drv, city, kw, d.get("job_key"))
            if got:
                d["岗位链接"] = got["link"]
                d["职位描述"] = got["desc"]
                done += 1
            if (i + 1) % 20 == 0 or (args.limit and i + 1 >= len(todo)):
                with CSV.open("w", encoding="utf-8-sig", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=fieldnames)
                    w.writeheader()
                    for rr in recs:
                        w.writerow(rr)
                print(f"进度 {i + 1}/{len(todo)} 已成功 {done}", flush=True)
    finally:
        drv.quit()
    with CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for rr in recs:
            w.writerow(rr)
    print(f"完成: 本批成功 {done}", flush=True)


if __name__ == "__main__":
    main()
