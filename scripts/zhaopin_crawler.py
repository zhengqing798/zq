# -*- coding: utf-8 -*-
"""智联招聘(zhaopin) 计算机岗位采集 —— SPA 滚动模式 (福建+周边 ≥1万)

路线说明(2026-09-07 实测):
  智联 /sou SSR 分页在登录态/晚间会重定向到 /jobs SPA；
  /jobs SPA 在登录后能正常渲染岗位(div.job-card), 通过滚动自动加载更多。
  本脚本采用: 打开 /jobs?jl=<城>&kw=<词> → 滚动加载 → 解析 job-card → CSV 去重。

字段: 岗位名称/薪资/地区/学历/经验/技能标签/公司/地区/抓取时间/来源关键词
反爬: 随机延时(2-5s/滚动)、验证出现自动退避、失败不硬闯、断点续传、无卡死。

运行: python scripts/zhaopin_crawler.py [--dry 1] [--deadline ...]
输出: data/raw/zhaopin_jobs.csv + data/raw/zhaopin_summary.txt
"""
import argparse
import csv
import hashlib
import json
import random
import re
import socket
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw"
PROFILE = ROOT / ".zhaopin_profile"
PORT = 9527
CSV_FILE = OUT_DIR / "zhaopin_jobs.csv"
ALT_FILE = OUT_DIR / "zhaopin_jobs_live.csv"     # 主文件被占用时的备用输出
STATE_FILE = OUT_DIR / "zhaopin_state.json"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

KEYWORDS = ["Java", "Python", "前端", "后端", "测试", "算法", "运维", "数据分析",
            "C++", "嵌入式", "Android", "iOS", "网络安全", "数据库", "架构师"]
EXTRA_KEYWORDS = ["爬虫", "Go", "PHP", ".NET", "C#", "鸿蒙", "小程序", "游戏开发",
                  "机器学习", "大数据", "云计算", "DevOps", "自动化测试", "前端开发"]

CITIES = {
    "福州": 681, "厦门": 682, "泉州": 685, "漳州": 687,
    "莆田": 683, "宁德": 690, "龙岩": 689, "三明": 684, "南平": 688,
    "温州": 655, "杭州": 653, "宁波": 654, "南昌": 691, "长沙": 749,
    "武汉": 736, "成都": 801, "西安": 854, "南京": 635, "苏州": 639,
    "济南": 702, "青岛": 703, "郑州": 719, "合肥": 664, "昆明": 831,
}
TARGET = 10000
MAX_SCROLLS = 200      # 单组合最大滚动批次数
STABLE_STOP = 3        # 连续N次滚动无新增 → 该组合结束


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


# Windows 控制台中文/emoji 兼容
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def ensure_chrome():
    s = socket.socket()
    try:
        s.settimeout(1.2)
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
            s2.settimeout(1.2)
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


def blocked(drv):
    b = body_text(drv)
    return any(k in b for k in ("访问验证", "验证中心", "拖动滑块", "请完成验证"))


def load_ids():
    ids = set()
    for p in (CSV_FILE, ALT_FILE):
        if not p.exists():
            continue
        try:
            with p.open(encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    if r.get("job_key"):
                        ids.add(r["job_key"])
        except Exception:
            pass
    return ids


_pending: list = []


def _flush_pending():
    global _pending
    if not _pending:
        return
    for path in (CSV_FILE, ALT_FILE):
        try:
            is_new = not path.exists()
            with path.open("a", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(_pending[0].keys()))
                if is_new or f.tell() == 0:
                    w.writeheader()
                for r in _pending:
                    w.writerow(r)
            _pending = []
            return
        except PermissionError:
            continue            # 主文件被 Excel 占用 → 试备用文件
        except Exception:
            continue
    # 全部被占用 → 保留缓冲, 稍后再写


def write_row(r):
    """追加行; CSV 被占用时缓冲(内存)重试, 绝不因文件锁崩溃或丢数据。"""
    global _pending
    _pending.append(r)
    _flush_pending()
    if len(_pending) % 200 == 0:
        log("  [提示] CSV 可能正被 Excel 打开, 数据在内存缓冲中(请关闭Excel)")


def flush_pending():
    _flush_pending()
    if _pending:
        log(f"  [提示] 仍有 {len(_pending)} 条缓冲未落盘(CSV被占用?)")


def save_state(st):
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"combo_done": []}


# -----------------------------------------------------------------解析
def guess_edu(ts):
    for t in ts:
        if re.search(r"学历不限|中专|大专|本科|硕士|博士|MBA|初中", t):
            return t
    return ""


def guess_exp(ts):
    for t in ts:
        if re.search(r"经验不限|应届|1年以下|1-3年|3-5年|5-10年|10年以上|\d+年以上", t):
            return t
    return ""


def parse_card(drv, card):
    def txt(sel):
        try:
            return card.find_element("css selector", sel).text.strip()
        except Exception:
            return ""
    title = txt(".job-card__title-main")
    salary = txt(".job-card__salary")
    tags = [x.text.strip() for x in
            card.find_elements("css selector", ".job-card__skill-tag")]
    company = txt(".job-card__company")
    loc = txt(".job-card__location")
    if not title:
        return None
    key = hashlib.md5((title + "|" + company + "|" + loc).encode()).hexdigest()[:16]
    return {
        "job_key": key,
        "岗位名称": title,
        "岗位薪资": salary,
        "岗位地区": loc,
        "学历要求": guess_edu(tags),
        "经验要求": guess_exp(tags),
        "技能标签": "|".join(t for t in tags if t not in
                          (guess_edu(tags), guess_exp(tags))),
        "公司名字": company,
        "来源关键词": "",
        "城市(实测)": loc.split()[0] if loc else "",
        "抓取时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def open_list(drv, url):
    """打开 /jobs SPA 页并等首屏; 验证时退避。"""
    drv.get(url)
    time.sleep(random.uniform(3, 5))
    for _ in range(6):
        if blocked(drv):
            log("  [验证] 退避 90s 后重试")
            time.sleep(90)
            drv.get(url)
            time.sleep(4)
        if drv.find_elements("css selector", ".job-card"):
            return True
        time.sleep(3)
    return bool(drv.find_elements("css selector", ".job-card"))


def scroll_batch(drv, url):
    """滚到底触发加载, 返回当前页 job-card 解析行(去重交由调用方)。"""
    before_h = drv.execute_script("return document.body.scrollHeight")
    drv.execute_script("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(random.uniform(2, 4))
    after_h = drv.execute_script("return document.body.scrollHeight")
    cards = drv.find_elements("css selector", ".job-card")
    rows = []
    for c in cards:
        r = parse_card(drv, c)
        if r:
            rows.append(r)
    # 无新内容(高度未变)信号
    return rows, after_h <= before_h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deadline", default="2026-09-08 07:00:00")
    ap.add_argument("--dry", type=int, default=0, help="快速验证: 厦门xJava 滚动3批")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    deadline = datetime.strptime(args.deadline, "%Y-%m-%d %H:%M:%S")
    ensure_chrome()
    drv = attach()
    ids = load_ids()
    log(f"历史 {len(ids)} 条; 目标 {TARGET}; 截止 {deadline}")

    try:
        if args.dry:
            drv.get(f"https://www.zhaopin.com/jobs?jl=682&kw=Java&kt=3")
            time.sleep(5)
            log("dry url: " + drv.current_url[:90])
            if not open_list(drv, drv.current_url):
                log("dry: 首屏无岗位")
                return
            seen = set()
            for _ in range(4):
                rows, _ = scroll_batch(drv, drv.current_url)
                for r in rows:
                    seen.add(r["job_key"])
                log(f"dry 滚动后累计卡片: {len(drv.find_elements('css selector', '.job-card'))}, "
                    f"去重键 {len(seen)}")
            log("样例: " + json.dumps(rows[0], ensure_ascii=False)[:400] if rows else "无")
            return

        state = load_state()
        # 城市可用性验证(厦门做代表即可; 后续逐城执行时按行内城市判断)
        active = {}
        log("== 城市可用性探测(每城1次Java) ==")
        for name, code in list(CITIES.items()):
            u = f"https://www.zhaopin.com/jobs?jl={code}&kw=Java&kt=3"
            if open_list(drv, u):
                cards = drv.find_elements("css selector", ".job-card")
                sample = next((parse_card(drv, c) for c in cards
                               if parse_card(drv, c)), None)
                active[name] = code
                log(f"  ✅ {name}({code}) 卡片{len(cards)}")
                time.sleep(random.uniform(4, 7))
            else:
                log(f"  ⏭ {name}({code}) 无数据")
        if not active:
            log("无可用城市, 停止")
            return
        log(f"可用城市 {len(active)} 个")

        kw_list = list(KEYWORDS)
        added_extra = False
        for pass_no in range(1, 6):
            if len(ids) >= TARGET or datetime.now() >= deadline:
                break
            if pass_no >= 3 and not added_extra:
                kw_list = list(KEYWORDS) + list(EXTRA_KEYWORDS)
                added_extra = True
                log("追加扩容关键词")
            log(f"---- 第{pass_no}轮(当前 {len(ids)}) ----")
            for name, code in active.items():
                if len(ids) >= TARGET or datetime.now() >= deadline:
                    break
                for kw in kw_list:
                    if len(ids) >= TARGET or datetime.now() >= deadline:
                        break
                    combo = f"{name}_{kw}"
                    if combo in state["combo_done"]:
                        continue
                    log(f"== {name} × {kw} 当前{len(ids)} ==")
                    url = f"https://www.zhaopin.com/jobs?jl={code}&kw={quote(kw)}&kt=3"
                    if not open_list(drv, url):
                        log("  首屏失败(可能验证/无结果), 留待下轮")
                        continue
                    # 滚动加载并收新行
                    added = 0
                    stable = 0
                    for _ in range(MAX_SCROLLS):
                        if len(ids) >= TARGET or datetime.now() >= deadline:
                            break
                        rows, no_grow = scroll_batch(drv, url)
                        new = [r for r in rows if r["job_key"] not in ids]
                        for r in new:
                            r["来源关键词"] = kw
                            ids.add(r["job_key"])
                            write_row(r)
                            added += 1
                        if new:
                            stable = 0
                        else:
                            stable += 1
                        if no_grow and stable >= STABLE_STOP:
                            break
                        time.sleep(random.uniform(2, 4))
                    log(f"  {name}/{kw} 本组合新增 {added}, 累计 {len(ids)}")
                    if added > 0 or not blocked(drv):
                        state["combo_done"].append(combo)
                    save_state(state)
                    flush_pending()
                    time.sleep(random.uniform(8, 15))
            if len(ids) < TARGET and datetime.now() < deadline:
                log(f"本轮后 {len(ids)}, 长歇10分钟")
                time.sleep(10 * 60)
            save_state(state)

        # 汇总
        flush_pending()
        dist = Counter()
        for p in (CSV_FILE, ALT_FILE):
            if not p.exists():
                continue
            try:
                with p.open(encoding="utf-8-sig") as f:
                    for rr in csv.DictReader(f):
                        dist[rr.get("城市(实测)") or "?"] += 1
            except Exception:
                pass
        log(f"== 结束: {len(ids)} 条 / 目标 {TARGET} ==")
        log("城市分布Top15: " + json.dumps(dist.most_common(15), ensure_ascii=False))
        try:
            (OUT_DIR / "zhaopin_summary.txt").write_text(
                json.dumps(dict(dist.most_common()), ensure_ascii=False, indent=1),
                encoding="utf-8")
        except Exception:
            pass
        log("达标" if len(ids) >= TARGET else "未达标(续跑: python scripts/zhaopin_crawler.py)")
    finally:
        drv.quit()


if __name__ == "__main__":
    main()
