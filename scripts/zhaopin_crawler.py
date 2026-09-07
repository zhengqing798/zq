# -*- coding: utf-8 -*-
"""智联招聘(zhaopin) 计算机岗位采集 —— 福建+周边, ≥1万, 低频率整夜跑

运行: python scripts/zhaopin_crawler.py            (默认跑到 07:00 或 1万条)
      python scripts/zhaopin_crawler.py --dry 1    (快速验证: 单城单关键词1页)
      python scripts/zhaopin_crawler.py --deadline "2026-09-08 07:00:00"

要点
----
- 接管 9527 真实 Chrome(配置 .zhaopin_profile, 自动启动)
- 请求/翻页全部低频率(随机 4-8s/页), 空页自动退避重试, 绝不硬闯验证
- 城市运行时验证(关键词页有本城岗位才算可用), 逐 城x关键词 抓取去重
- 断点续传: 已入库 job_id 自动跳过
输出: data/raw/zhaopin_jobs.csv
"""
import argparse
import csv
import json
import random
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw"
PROFILE = ROOT / ".zhaopin_profile"
PORT = 9527
CSV_FILE = OUT_DIR / "zhaopin_jobs.csv"
STATE_FILE = OUT_DIR / "zhaopin_state.json"

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# 计算机相关关键词
KEYWORDS = ["Java", "Python", "前端", "后端", "测试", "算法", "运维", "数据分析",
            "C++", "嵌入式", "Android", "iOS", "网络安全", "数据库", "架构师"]

# 城市: 名称->候选代码(运行时以关键词首页验证取用)
CITIES = {
    # 福建
    "福州": [681], "厦门": [682], "泉州": [685], "漳州": [687],
    "莆田": [683, 690], "宁德": [690, 683], "龙岩": [689, 690],
    "三明": [684, 689], "南平": [688, 684],
    # 周边
    "温州": [655, 682], "宁波": [654, 655], "杭州": [653, 654],
    "南昌": [691, 653], "长沙": [749, 691], "武汉": [736, 749],
    "成都": [801, 736], "西安": [854, 801], "南京": [635, 854],
    "苏州": [639, 635], "济南": [702, 639], "青岛": [703, 702],
    "郑州": [719, 703], "合肥": [664, 719], "昆明": [831, 664],
}
TARGET = 10000
SEL_ITEM = ".joblist-box__item"
MAX_PAGE = 400      # 单组合页数上限


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def ensure_chrome():
    import socket
    s = socket.socket()
    try:
        s.connect(("127.0.0.1", PORT))
        s.close()
        return
    except Exception:
        pass
    PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([CHROME, f"--remote-debugging-port={PORT}",
                      f"--user-data-dir={PROFILE}", "--window-size=1500,1100"])
    for _ in range(30):
        time.sleep(1)
        try:
            s2 = socket.socket()
            s2.connect(("127.0.0.1", PORT))
            s2.close()
            return
        except Exception:
            continue
    sys.exit("Chrome 调试端口启动失败")


def attach():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    o = Options()
    o.add_experimental_option("debuggerAddress", f"127.0.0.1:{PORT}")
    return webdriver.Chrome(options=o)


def body_text(drv):
    try:
        return drv.find_element("tag name", "body").text
    except Exception:
        return ""


def load_ids():
    ids = set()
    if CSV_FILE.exists():
        try:
            with CSV_FILE.open(encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    if r.get("job_id"):
                        ids.add(r["job_id"])
        except Exception:
            pass
    return ids


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"combo_done": []}


def write_row(r):
    with CSV_FILE.open("a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(r.keys()))
        if f.tell() == 0:
            w.writeheader()
        w.writerow(r)


def parse_page(drv):
    """解析 sou 搜索页 .joblist-box__item 岗位行。"""
    from selenium.webdriver.common.by import By
    rows = []
    for it in drv.find_elements(By.CSS_SELECTOR, SEL_ITEM):
        try:
            a = it.find_element(By.CSS_SELECTOR, "a.jobinfo__name")
        except Exception:
            continue
        href = (a.get_attribute("href") or "").split("?")[0]
        m = re.search(r"/jobdetail/([A-Z0-9]+)\.htm", href or "")
        jid = m.group(1) if m else ""
        def pick(sel):
            try:
                return it.find_element(By.CSS_SELECTOR, sel).text.strip()
            except Exception:
                return ""
        salary = pick(".jobinfo__salary")
        loc = pick(".jobinfo__other-info .jobinfo__other-info-item")
        tags = []
        try:
            for t in it.find_elements(By.CSS_SELECTOR, ".jobinfo__tag .joblist-box__item-tag"):
                tags.append(t.text.strip())
        except Exception:
            pass
        comp = pick(".companyinfo__name")
        ctags = []
        try:
            for t in it.find_elements(By.CSS_SELECTOR,
                                      ".companyinfo__tag .joblist-box__item-tag"):
                ctags.append(t.text.strip())
        except Exception:
            pass
        rows.append({
            "job_id": jid,
            "岗位名称": a.text.strip(),
            "岗位薪资": salary,
            "岗位地区": loc,
            "岗位标签": "|".join(tags),
            "公司名字": comp,
            "公司信息": "|".join(ctags),
            "来源关键词": "",
            "抓取时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    return rows


def canonical_page(drv, url):
    """访问查询URL并返回其规范化分页基址(含kw编码路径), 例如 .../sou/jl682/kwXXX/p1?kt=3"""
    drv.get(url)
    time.sleep(4)
    cur = drv.current_url
    m = re.search(r"(.+?)/p(\d+)(\?.*)?$", cur)
    if m:
        return cur
    return cur  # 兜底直接返回


def city_of(row):
    loc = row.get("岗位地区") or ""
    return loc.split("·")[0].split(" ")[0].strip()


def combo_url(city_code, kw):
    return (f"https://www.zhaopin.com/sou/jl{city_code}"
            f"?kw={quote(kw)}&kt=3")


def fetch_list(drv, url):
    """抓取一页; 空页/验证时退避重试。返回(rows, ok)"""
    drv.get(url)
    time.sleep(random.uniform(4, 6))
    from selenium.webdriver.common.by import By
    for attempt in range(3):
        body = body_text(drv)
        if any(k in body for k in ("访问验证", "验证中心", "拖动滑块")):
            log(f"  [验证] 页面要求验证, 退避 {60*(attempt+1)}s 后自动继续")
            time.sleep(60 * (attempt + 1))
            drv.get(url)
            time.sleep(4)
            continue
        items = drv.find_elements(By.CSS_SELECTOR, SEL_ITEM)
        if items:
            return parse_page(drv), True
        if attempt < 2:
            time.sleep(30 * (attempt + 1))
    return [], False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deadline", default="2026-09-08 07:00:00")
    ap.add_argument("--dry", type=int, default=0, help="仅验证: 厦门xJava 1页")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    deadline = datetime.strptime(args.deadline, "%Y-%m-%d %H:%M:%S")

    ensure_chrome()
    drv = attach()
    ids = load_ids()
    log(f"已载入历史 {len(ids)} 条; 目标 {TARGET}; 截止 {deadline}")

    try:
        if args.dry:
            url = combo_url(682, "Java")
            drv.get(url)
            time.sleep(5)
            log("dry URL: " + drv.current_url[:120])
            rows, _ = parse_page(drv), True
            log(f"dry 行数: {len(rows)}")
            if rows:
                log("样例: " + json.dumps(rows[0], ensure_ascii=False)[:300])
            return

        state = load_state()
        # 先验证并挑选可用城市代码
        active = {}
        log("== 城市代码验证 ==")
        for name, codes in CITIES.items():
            for code in codes:
                if len(ids) >= TARGET:
                    break
                u = combo_url(code, "Java")
                drv.get(u)
                time.sleep(random.uniform(3, 5))
                rows, _ = parse_page(drv), True
                city = ""
                for r in rows:
                    c = city_of(r)
                    if c:
                        city = c
                        break
                if rows and (name in city or city in name):
                    active[name] = code
                    log(f"  ✅ {name} = jl{code} (样例区:{city})")
                    break
                time.sleep(random.uniform(2, 4))
        if not active:
            log("没有可用城市, 停止")
            return
        log(f"可用城市: {list(active.items())}")

        # 逐 城市x关键词 抓取(多轮直到达标/截止)
        pass_no = 0
        while pass_no < 4:
            pass_no += 1
            if len(ids) >= TARGET or datetime.now() >= deadline:
                break
            log(f"---- 第 {pass_no} 轮开始(当前 {len(ids)}) ----")
            for name, code in list(active.items()):
                if len(ids) >= TARGET or datetime.now() >= deadline:
                    break
                for kw in KEYWORDS:
                    if len(ids) >= TARGET or datetime.now() >= deadline:
                        break
                    combo = f"{name}_{code}_{kw}"
                    if combo in state["combo_done"]:
                        continue
                    log(f"== {name}({code}) × {kw} 当前{len(ids)} ==")
                    # 规范基址(含kw编码路径)
                    drv.get(combo_url(code, kw))
                    time.sleep(4)
                    cur = drv.current_url
                    base = re.sub(r"/p\d+(\?|$)", "/p{page}\\1", cur)
                    if "{page}" not in base:
                        base = cur.rstrip("/") + "/p{page}"
                    got_any = False
                    first_page_done = False
                    for page in range(1, MAX_PAGE + 1):
                        if len(ids) >= TARGET or datetime.now() >= deadline:
                            break
                        url = base.format(page=page)
                        rows, ok = fetch_list(drv, url)
                        if page == 1:
                            first_page_done = bool(ok)     # 首页能正常出(空)才算该组合真完成过
                        new = [r for r in rows if r.get("job_id") and r["job_id"] not in ids]
                        for r in new:
                            r["来源关键词"] = kw
                            r["城市(实测)"] = city_of(r) or name
                            ids.add(r["job_id"])
                            write_row(r)
                        if new:
                            got_any = True
                        log(f"  {name}/{kw} p{page}: +{len(new)} 条 → 累计{len(ids)}")
                        if not rows:
                            break                      # 空页即该组合(当前)结束
                        time.sleep(random.uniform(4, 8))
                    # 首页正常渲染过(有数据或真无结果)才标记完成, 否则视为风控留待下轮
                    if first_page_done:
                        state["combo_done"].append(combo)
                    save_state(state)
                    time.sleep(random.uniform(5, 10))
            if len(ids) < TARGET and datetime.now() < deadline:
                log(f"本轮后 {len(ids)}, 长歇 20 分钟后继续")
                time.sleep(20 * 60)
            save_state(state)

        log(f"== 结束: 共 {len(ids)} 条 (目标 {TARGET}) ==")
    finally:
        drv.quit()


if __name__ == "__main__":
    main()
