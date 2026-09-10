from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import pandas as pd
import time
import datetime
import re
from urllib.parse import quote

# ==================================================
# 全局配置
# ==================================================
CHROMEDRIVER_PATH = "chromedriver.exe"

# 城市列表：格式为 (智联城市jl代码, 城市中文名)
CITY_LIST = [
    # 福建省内 9 个
    ("682", "厦门"),
    ("681", "福州"),
    ("687", "泉州"),
    ("689", "漳州"),
    ("686", "莆田"),
    ("688", "宁德"),
    ("685", "南平"),
    ("684", "三明"),
    ("683", "龙岩"),
    # 广东省 5 个
    ("651", "深圳"),
    ("650", "广州"),
    ("654", "东莞"),
    ("656", "佛山"),
    ("657", "珠海"),
    # 浙江省 2 个
    ("671", "杭州"),
    ("673", "宁波"),
    # 江苏省 2 个
    ("663", "苏州"),
    ("661", "南京"),
    # 江西省 1 个
    ("639", "南昌"),
]

# 8 个核心关键词
KEYWORDS = ["Java", "Python", "前端", "后端", "测试", "运维", "数据分析", "算法"]

# 爬取参数
TARGET_PER_KEYWORD = 300  # 单个关键词目标条数
MAX_SCROLL_TIMES = 20  # 单关键词最多滚动次数，防止死循环
SCROLL_WAIT = 3  # 每次滚动后等待加载时间
DRAWER_WAIT = 2  # 详情抽屉弹出等待秒数
# 修改为指定保存路径
OUTPUT_CSV = r"C:\Users\王俊淇\Desktop\大四上小学期\zq\data\raw\zhaopin_jobs_full.csv"


# ==================================================
# 字段校验工具
# ==================================================
def is_valid_job_name(text: str) -> bool:
    """校验职位名称合法性，排除典型薪资格式，避免串位"""
    if not text:
        return False
    text = text.strip()
    if len(text) < 1 or len(text) > 60:
        return False
    if re.match(r"^\d+[\-~]\d+[元万千Kk]", text):
        return False
    if text in ["", " ", "面议"]:
        return False
    return True


def is_valid_salary(text: str) -> bool:
    """校验薪资合法性，必须包含薪资单位标识"""
    if not text:
        return False
    return any(unit in text for unit in ["元", "万", "K", "k", "薪"])


# ==================================================
# 浏览器初始化
# ==================================================
print("=" * 65)
print("智联招聘批量爬取工具（滚动加载版）")
print(f"覆盖城市：{len(CITY_LIST)} 个 | 关键词：{len(KEYWORDS)} 个")
print(f"单关键词目标：{TARGET_PER_KEYWORD} 条 | 滚动加载，无需翻页")
print("✅ 保留公司名称 | ✅ 中文关键词正常搜索 | ✅ 职位防串位校验")
print(f"✅ 保存路径：{OUTPUT_CSV}")
print("=" * 65)

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument("--start-maximized")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option("useAutomationExtension", False)
chrome_options.add_argument("--disable-blink-features=AutomationControlled")

driver = webdriver.Chrome(
    service=Service(executable_path=CHROMEDRIVER_PATH),
    options=chrome_options
)

print("\n请在弹出的浏览器中登录智联账号，登录完成后按回车键开始爬取...")
driver.get("https://www.zhaopin.com/")
input()
print("\n🚀 开始全量爬取...\n")

# 全局数据容器
all_jobs = []

# CSV 输出字段顺序（新增公司名称列）
FIELD_ORDER = [
    "岗位名称", "岗位薪资", "岗位地区",
    "经验要求", "学历要求", "技能标签",
    "职位描述",
    "公司名称",
    "发布者姓名", "发布者身份", "在线状态", "回复时效", "今日回复数",
    "来源关键词", "城市(实测)", "抓取时间"
]


# ==================================================
# 单卡片提取函数（新增公司名称提取）
# ==================================================
def extract_single_card(card, city_name, keyword) -> dict:
    """提取单张职位卡片的完整数据"""
    try:
        # ---------- 1. 职位名称（4层兜底 + 校验） ----------
        job_name = ""
        name_selectors = [
            ".job-card__title-main",
            ".vue-clamp__text",
            ".job-card__title-clamp",
            ".job-card__title",
        ]
        for sel in name_selectors:
            try:
                t = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if is_valid_job_name(t):
                    job_name = t
                    break
            except:
                continue

        if not job_name:
            try:
                title_row = card.find_element(By.CSS_SELECTOR, ".job-card__title-row").text.strip()
                for line in title_row.split("\n"):
                    line = line.strip()
                    if is_valid_job_name(line):
                        job_name = line
                        break
            except:
                pass

        if not job_name:
            try:
                card_lines = [l.strip() for l in card.text.strip().split("\n") if l.strip()]
                for line in card_lines[:5]:
                    if is_valid_job_name(line) and not is_valid_salary(line):
                        job_name = line
                        break
            except:
                pass

        # ---------- 2. 薪资 ----------
        salary = ""
        try:
            t = card.find_element(By.CSS_SELECTOR, ".job-card__salary").text.strip()
            if is_valid_salary(t):
                salary = t
        except:
            pass

        # ---------- 3. 地区 ----------
        location = ""
        try:
            location = card.find_element(By.CSS_SELECTOR, ".job-card__location").text.strip()
        except:
            pass

        # ---------- 4. 公司名称（新增） ----------
        company_name = ""
        try:
            company_name = card.find_element(By.CSS_SELECTOR, ".job-card__company").text.strip()
        except:
            pass

        # ---------- 5. 标签拆分（学历、经验、技能） ----------
        skill_tags = card.find_elements(By.CSS_SELECTOR, ".job-card__skill-tag")
        education = skill_tags[0].text.strip() if len(skill_tags) >= 1 else ""
        experience = skill_tags[1].text.strip() if len(skill_tags) >= 2 else ""
        skills = "|".join([e.text.strip() for e in skill_tags[2:]]) if len(skill_tags) > 2 else ""

        # ---------- 6. 点击卡片弹出详情抽屉 ----------
        try:
            card.click()
            time.sleep(DRAWER_WAIT)
        except:
            pass

        # ---------- 7. 职位描述 ----------
        job_desc = ""
        desc_selectors = ["[class*='desc']", ".job-detail__desc", ".drawer-content"]
        for sel in desc_selectors:
            try:
                desc_eles = driver.find_elements(By.CSS_SELECTOR, sel)
                for ele in desc_eles:
                    t = ele.text.strip()
                    if len(t) > 50:
                        job_desc = t
                        break
                if job_desc:
                    break
            except:
                continue

        # ---------- 8. 发布者信息 ----------
        publisher_name = ""
        publisher_role = ""
        online_status = ""
        reply_time = ""
        reply_count = ""

        try:
            pub_box = driver.find_element(By.CSS_SELECTOR, "[class*='publisher']")
            pub_lines = [l.strip() for l in pub_box.text.strip().split("\n") if l.strip()]

            for line in pub_lines:
                if "在线" in line:
                    online_status = line
                elif "分钟前回复" in line or "小时前回复" in line:
                    reply_time = line
                elif "今日回复" in line:
                    reply_count = line
                elif any(role in line for role in ["HR", "主管", "经理", "总监"]):
                    publisher_role = line
                elif len(line) <= 12 and not any(k in line for k in ["在线", "回复", "今日", "HR", "主管"]):
                    publisher_name = line
        except:
            pass

        # ---------- 组装数据（新增公司名称字段） ----------
        return {
            "岗位名称": job_name,
            "岗位薪资": salary,
            "岗位地区": location,
            "经验要求": experience,
            "学历要求": education,
            "技能标签": skills,
            "职位描述": job_desc,
            "公司名称": company_name,
            "发布者姓名": publisher_name,
            "发布者身份": publisher_role,
            "在线状态": online_status,
            "回复时效": reply_time,
            "今日回复数": reply_count,
            "来源关键词": keyword,
            "城市(实测)": city_name,
            "抓取时间": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        }
    except Exception:
        return None


# ==================================================
# 单关键词滚动加载提取
# ==================================================
def extract_keyword_jobs(city_code, city_name, keyword, target):
    """单个关键词滚动加载，直到达到目标条数或无更多数据"""
    # 初始搜索页（仅第一页，靠滚动加载更多）
    encoded_kw = quote(keyword, encoding="utf-8")
    url = f"https://www.zhaopin.com/jobs?jl={city_code}&kw={encoded_kw}&p=1"

    try:
        driver.get(url)
    except Exception as e:
        print(f"    ⚠️ 页面加载失败：{str(e)[:30]}，跳过")
        return []

    time.sleep(2)

    # 初始滚动触发懒加载
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(2)

    result = []
    last_card_count = 0
    no_new_count = 0  # 连续无新数据次数
    scroll_count = 0  # 滚动次数

    while len(result) < target and scroll_count < MAX_SCROLL_TIMES and no_new_count < 2:
        # 滚动到底部加载更多
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_WAIT)
        scroll_count += 1

        # 获取当前所有卡片
        try:
            job_cards = driver.find_elements(By.CSS_SELECTOR, ".job-card")
        except:
            job_cards = []

        current_count = len(job_cards)

        # 没有新卡片，累计计数
        if current_count <= last_card_count:
            no_new_count += 1
            continue
        else:
            no_new_count = 0

        # 只提取新增的卡片（增量提取，避免重复）
        new_cards = job_cards[last_card_count:current_count]
        for card in new_cards:
            if len(result) >= target:
                break
            item = extract_single_card(card, city_name, keyword)
            if item:
                result.append(item)

        last_card_count = current_count
        print(f"    已加载 {current_count} 条卡片，已提取 {len(result)} 条", end="\r")

    # 截取到目标条数
    if len(result) > target:
        result = result[:target]

    print()  # 换行
    return result


# ==================================================
# 主爬取流程
# ==================================================
if __name__ == "__main__":
    total_city = len(CITY_LIST)

    for city_idx, (city_code, city_name) in enumerate(CITY_LIST):
        print(f"\n{'=' * 60}")
        print(f"【{city_idx + 1}/{total_city}】当前城市：{city_name}")
        print(f"{'=' * 60}")

        city_total = 0
        for kw_idx, kw in enumerate(KEYWORDS):
            print(f"\n  [{kw_idx + 1}/{len(KEYWORDS)}] 关键词：{kw}")

            # 单个关键词滚动加载提取
            kw_jobs = extract_keyword_jobs(city_code, city_name, kw, TARGET_PER_KEYWORD)
            print(f"    完成，共提取 {len(kw_jobs)} 条", end=" | ")

            all_jobs.extend(kw_jobs)
            city_total += len(kw_jobs)

            # 每个关键词爬完立即保存到指定路径
            df = pd.DataFrame(all_jobs, columns=FIELD_ORDER)
            df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
            print(f"已保存，累计 {len(all_jobs)} 条")

            time.sleep(1)

        print(f"\n  ✅ {city_name} 爬取完成，本城市累计 {city_total} 条")

    # ========== 最终统计 ==========
    print("\n" + "=" * 65)
    print("🎉 全部爬取完成")
    print(f"✅ 最终总条数：{len(all_jobs)} 条")
    print(f"✅ 结果文件：{OUTPUT_CSV}")

    # 数据质量自检（新增公司名称缺失统计）
    name_empty = df["岗位名称"].astype(str).str.strip().isin(["", "nan"]).sum()
    name_error = df[df["岗位名称"] == df["岗位薪资"]].shape[0]
    company_empty = df["公司名称"].astype(str).str.strip().isin(["", "nan"]).sum()
    desc_empty = df["职位描述"].astype(str).str.strip().isin(["", "nan"]).sum()

    print(f"\n📊 数据质量自检：")
    print(f"  职位名称缺失：{name_empty} 条")
    print(f"  名称薪资串位：{name_error} 条")
    print(f"  公司名称缺失：{company_empty} 条")
    print(f"  职位描述缺失：{desc_empty} 条")
    print("=" * 65)

    input("\n按回车键关闭浏览器...")
    try:
        driver.quit()
    except:
        pass
