# -*- coding: utf-8 -*-
"""zhaopin_jobs.csv 补列(岗位链接+职位描述) - SSR 方案(稳定高效)

链接: 匿名Chrome(9528)访问 /sou SSR 列表 → a.jobinfo__name 自带真实 jobdetail 链接
描述: 对已取得链接的详情页抓职位描述(未知结构自动存快照便于适配)
用法: python scripts/enrich_ssr.py --limit 3   试点
      python scripts/enrich_ssr.py             全量(长时间后台)
"""
import argparse
import csv
import random
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "raw" / "zhaopin_jobs.csv"
PROFILE = ROOT / ".zhaopin_anon"
PORT = 9528
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

CITY_CODES = {"福州": 681, "厦门": 682, "泉州": 685, "漳州": 687, "莆田": 683,
              "宁德": 690, "龙岩": 689, "三明": 684, "南平": 688,
              "温州": 655, "杭州": 653, "宁波": 654, "南昌": 691, "长沙": 749,
              "武汉": 736, "成都": 801, "西安": 854, "南京": 635, "苏州": 639,
              "济南": 702, "青岛": 703, "郑州": 719, "合肥": 664, "昆明": 831}
REAL_KW = ["Java", "Python", "前端", "后端", "测试", "算法", "运维", "数据分析",
           "C++", "嵌入式", "Android", "iOS", "网络安全", "数据库", "架构师",
           "爬虫", "Go", "PHP", ".NET", "C#", "鸿蒙", "小程序", "游戏开发",
           "机器学习", "大数据", "云计算", "DevOps", "自动化测试", "前端开发"]
HEAD_FIX = ["job_key", "岗位名称", "岗位薪资", "岗位地区", "学历要求", "经验要求",
            "技能标签", "公司名字", "来源关键词", "城市(实测)", "抓取时间",
            "岗位链接", "职位描述"]
SEL_ITEM = ".joblist-box__item"

DESC_SELECTORS = [".job_detail", ".job-intro", ".job_msg", ".job_detail_content",
                  "[class*='job-desc']", "[class*='describe']", "[class*='JobDetail']"]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def up(port=PORT):
    s = socket.socket()
    try:
        s.settimeout(1)
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        return False


def ensure_chrome():
    if not up():
        PROFILE.mkdir(parents=True, exist_ok=True)
        subprocess.Popen([CHROME, f"--remote-debugging-port={PORT}",
                          f"--user-data-dir={PROFILE}"])
        for _ in range(30):
            time.sleep(1)
            if up():
                return
        sys.exit("Chrome(9528) 启动失败")


def attach():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    o = Options()
    o.add_experimental_option("debuggerAddress", f"127.0.0.1:{PORT}")
    return webdriver.Chrome(options=o)


def norm(s):
    return re.sub(r"[·/，,、_ ]", "", s or "")


def key_of(title, company, loc):
    import hashlib
    return hashlib.md5(f"{title}|{company}|{loc}".encode()).hexdigest()[:16]


def parse_ssr_row(drv, it):
    try:
        a = it.find_element("css selector", "a.jobinfo__name")
    except Exception:
        return None
    title = a.text.strip()
    href = (a.get_attribute("href") or "").split("?")[0]
    def pick(sel):
        try:
            return it.find_element("css selector", sel).text.strip()
        except Exception:
            return ""
    comp = pick(".companyinfo__name")
    loc = pick(".jobinfo__other-info .jobinfo__other-info-item")
    return {"title": title, "company": comp, "loc": loc, "href": href}


def page_items(drv):
    return [parse_ssr_row(drv, it) for it in
            drv.find_elements("css selector", SEL_ITEM)]


def fetch_ssr_pages(drv, city, kw, seen_link):
    """抓某 城市×关键词 SSR 全部分页, 返回链接命中集合(基于标题+公司匹配)。"""
    from selenium.webdriver.common.by import By
    url = f"https://www.zhaopin.com/sou/jl{CITY_CODES[city]}?kw={quote(kw)}&kt=3"
    drv.get(url)
    time.sleep(4)
    cur = drv.current_url
    base = re.sub(r"/p\d+(\?|$)", "/p{page}\\1", cur)
    if "{page}" not in base:
        return set()
    hit = set()
    for page in range(1, 400):
        drv.get(base.format(page=page))
        time.sleep(random.uniform(1.2, 2))
        items = drv.find_elements(By.CSS_SELECTOR, SEL_ITEM)
        if not items:
            break
        for it in items:
            r = parse_ssr_row(drv, it)
            if not r or not r["href"]:
                continue
            seen_link.setdefault((norm(r["title"]), norm(r["company"])), r["href"])
        time.sleep(random.uniform(1.5, 2.5))
    return hit


def grab_desc(drv):
    for sel in DESC_SELECTORS:
        for el in drv.find_elements("css selector", sel)[:3]:
            t = el.text.strip()
            if len(t) > 60:
                return t[:4000]
    return ""


def fill_desc(drv, link, out_snap):
    try:
        drv.get(link)
        time.sleep(2.5)
        desc = grab_desc(drv)
        if not desc:
            try:
                out_snap.write_text(drv.page_source[:400000], encoding="utf-8")
            except Exception:
                pass
        return desc
    except Exception:
        return ""


def main():
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    recs = list(csv.DictReader(CSV.open(encoding="utf-8-sig", newline="")))
    need_cols = ["岗位链接", "职位描述"]
    for c in need_cols:
        if c not in recs[0]:
            for r in recs:
                r[c] = ""
    todo = [r for r in recs if not (r.get("岗位链接") and r.get("职位描述"))]
    if args.limit:
        todo = todo[: args.limit]
    log(f"共 {len(recs)} 行, 待补 {len(todo)} 行")

    ensure_chrome()
    drv = attach()
    snap = ROOT / "data" / "raw" / "_desc_probe.html"
    done_link = done_desc = 0
    try:
        # 按 (城市,来源关键词) 分组批量扫SSR收集链接
        groups = {}
        for r in todo:
            city = (r.get("城市(实测)") or "").split()[0]
            kw = r.get("来源关键词") or ""
            if kw not in REAL_KW or kw.startswith("厦门-") or "全岗位" in kw:
                kw = "Java" if city not in ("杭州", "厦门") else "数据分析"
            groups.setdefault((city, kw), []).append(r)
        log(f"查询组数: {len(groups)}")
        for (city, kw), rows in groups.items():
            if city not in CITY_CODES:
                continue
            try:
                link_map = {}
                fetch_ssr_pages(drv, city, kw, link_map)
            except Exception as e:
                log(f"组 {city}/{kw} 异常 {type(e).__name__}, 跳过")
                continue
            for r in rows:
                k = (norm(r.get("岗位名称") or ""), norm(r.get("公司名字") or ""))
                if k in link_map:
                    r["岗位链接"] = link_map[k]
                    done_link += 1
            log(f"组 {city}/{kw}: {len(rows)}行, 命中链接 {sum(1 for r in rows if r.get('岗位链接'))}")
        log(f"链接阶段完成: 命中 {done_link}/{len(todo)}")
        # 描述阶段
        for i, r in enumerate(todo, 1):
            if r.get("岗位链接") and not r.get("职位描述"):
                d = fill_desc(drv, r["岗位链接"], snap)
                if d:
                    r["职位描述"] = d
                    done_desc += 1
            if i % 30 == 0 or (args.limit and i >= len(todo)):
                persist(recs)
                log(f"进度 {i}/{len(todo)}, 描述成功 {done_desc}")
        persist(recs)
        log(f"完成: 链接 {done_link}, 描述 {done_desc}")
    finally:
        drv.quit()


def persist(recs):
    tmp = CSV.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(recs[0].keys()))
        w.writeheader()
        for r in recs:
            w.writerow(r)
    tmp.replace(CSV)


if __name__ == "__main__":
    main()
