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
TARGET = 10_000
MAX_SCROLLS = 200      # 单组合最大滚动批次数
STABLE_STOP = 3        # 连续N次滚动无新增 → 该组合结束
# 抓取顺序: 福建省内优先(厦门→漳州→泉州→宁德→龙岩→三明→南平→莆田, 福州已基本完成放最后), 再周边
FUJIAN_ORDER = ["厦门", "漳州", "泉州", "宁德", "龙岩", "三明", "南平", "莆田", "福州"]


def city_order(active):
    """按福建省内优先排序可抓城市。"""
    others = [k for k in active if k not in FUJIAN_ORDER]
    return FUJIAN_ORDER + others


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
    if _pending and len(_pending) % 300 == 0:
        log(f"  [提示] CSV 正被占用, {len(_pending)} 条在内存缓冲(请关闭Excel/WPS)")


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
        "岗位链接": "",
        "职位描述": "",
    }


def open_list(drv, url):
    """打开 /jobs SPA 页并等首屏; 验证时退避。"""
    drv.get(url)
    time.sleep(random.uniform(2.5, 3.5))
    for _ in range(4):
        if blocked(drv):
            log("  [验证] 退避 90s 后重试")
            time.sleep(90)
            drv.get(url)
            time.sleep(3)
        if drv.find_elements("css selector", ".job-card"):
            return True
        time.sleep(2.5)
    return bool(drv.find_elements("css selector", ".job-card"))


def scroll_batch(drv, url):
    """滚到底触发加载, 返回当前页 job-card 解析行(去重交由调用方)。"""
    before_h = drv.execute_script("return document.body.scrollHeight")
    drv.execute_script("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(random.uniform(1.6, 2.6))
    after_h = drv.execute_script("return document.body.scrollHeight")
    cards = drv.find_elements("css selector", ".job-card")
    rows = []
    for c in cards:
        try:
            r = parse_card(drv, c)
            if r:
                rows.append(r)
        except Exception:
            continue            # 单卡片异常不影响整体
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
    log(f"历史 {len(ids)} 条(无自停上限); 截止 {deadline}")

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
        # 城市可用性: 优先用缓存(避免每次重启重扫约5分钟)
        if state.get("active_cities"):
            active = {k: int(v) for k, v in state["active_cities"].items()}
            log(f"使用缓存城市 {len(active)} 个")
        else:
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
                    time.sleep(random.uniform(3, 5))
                else:
                    log(f"  ⏭ {name}({code}) 无数据")
            if not active:
                log("无可用城市, 停止")
                return
            state["active_cities"] = {k: str(v) for k, v in active.items()}
            save_state(state)
        log(f"可用城市 {len(active)} 个")

        kw_list = list(KEYWORDS)
        added_extra = False
        for pass_no in range(1, 6):
            if datetime.now() >= deadline:
                break
            if not added_extra:
                kw_list = list(KEYWORDS) + list(EXTRA_KEYWORDS)
                added_extra = True
                log("关键词: 主批+扩容全部启用(优先福建全量组合)")
            log(f"---- 第{pass_no}轮(当前 {len(ids)}) ----")
            city_seq = [c for c in city_order(active) if c in active]
            # 第三轮起若已无未做组合 → 提前结束(避免空转长歇)
            if pass_no >= 3:
                undone = any(f"{c}_{kw}" not in state["combo_done"]
                             for c in city_seq for kw in kw_list)
                if not undone:
                    log("所有组合已穷尽, 提前结束")
                    break
            for name in city_seq:
                code = active[name]
                if datetime.now() >= deadline:
                    break
                for kw in kw_list:
                    if datetime.now() >= deadline:
                        break
                    combo = f"{name}_{kw}"
                    if combo in state["combo_done"]:
                        continue
                    log(f"== {name} × {kw} 当前{len(ids)} ==")
                    url = f"https://www.zhaopin.com/jobs?jl={code}&kw={quote(kw)}&kt=3"
                    if not open_list(drv, url):
                        if blocked(drv):
                            log("  验证中... 该组合留待下轮")
                        else:
                            log("  该组合无岗位, 标记完成(避免反复重试)")
                            state["combo_done"].append(combo)
                            save_state(state)
                        continue
                    # 滚动加载并收新行
                    added = 0
                    stable = 0
                    for _ in range(MAX_SCROLLS):
                        if datetime.now() >= deadline:
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
                    log(f"  {name}/{kw} 本组合新增 {added}, 累计 {len(ids)}")
                    if added > 0 or not blocked(drv):
                        state["combo_done"].append(combo)
                    save_state(state)
                    flush_pending()
                    time.sleep(random.uniform(5, 9))
            if datetime.now() < deadline:
                log(f"本轮后 {len(ids)}, 长歇10分钟后继续(自动穷尽组合/至截止)")
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
        log(f"== 结束: 共抓 {len(ids)} 条(无1万自停, 因截止时间或组合穷尽停止) ==")
        log("城市分布Top15: " + json.dumps(dist.most_common(15), ensure_ascii=False))
        try:
            (OUT_DIR / "zhaopin_summary.txt").write_text(
                json.dumps(dict(dist.most_common()), ensure_ascii=False, indent=1),
                encoding="utf-8")
        except Exception:
            pass
        log("如需继续, 可稍后重跑: python scripts/zhaopin_crawler.py (自动去重续抓)")
    finally:
        drv.quit()


if __name__ == "__main__":
    _dl = datetime.strptime("2026-09-08 07:00:00", "%Y-%m-%d %H:%M:%S")
    while datetime.now() < _dl:
        try:
            main()
            log("本次运行正常结束")
            break
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log(f"[自动重启] 异常({type(e).__name__}: {str(e)[:120]}), 30秒后自动续跑")
            time.sleep(30)
