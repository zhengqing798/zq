import random
import datetime
import pandas as pd

# ==================================================
# 基础数据池
# ==================================================
SURNAMES = ["王", "李", "张", "刘", "陈", "杨", "黄", "赵", "吴", "周", "徐", "孙", "马", "朱", "胡", "郭", "何", "高",
            "林", "罗", "郑", "梁", "谢", "宋", "唐", "许", "韩", "冯", "邓", "曹", "彭", "曾", "萧", "田", "董", "袁",
            "潘", "于", "蒋", "蔡", "余", "杜", "叶", "程", "苏", "魏", "吕", "丁", "任", "沈", "姚", "卢", "傅", "钟",
            "姜", "崔", "谭", "陆", "汪", "范", "金", "石", "廖", "贾", "夏", "韦", "方", "白", "邹", "孟", "熊", "秦",
            "邱", "江", "尹", "薛", "闫", "段", "雷", "侯", "龙", "史", "陶", "黎", "贺", "顾", "毛", "郝", "龚", "邵",
            "万", "钱", "严", "覃", "武", "戴", "莫", "孔", "向", "汤"]
MALE_NAMES = ["伟", "强", "磊", "洋", "勇", "军", "杰", "涛", "超", "明", "刚", "平", "辉", "鹏", "华", "建", "峰",
              "飞", "彬", "鑫", "博", "宇", "浩", "凯", "健", "俊", "恒", "阳", "晨", "皓", "然", "子轩", "浩然",
              "雨泽", "博文", "梓轩", "思远", "天佑", "宇泽", "俊熙"]
FEMALE_NAMES = ["芳", "娜", "敏", "静", "丽", "艳", "娟", "莉", "玲", "慧", "婷", "霞", "萍", "红", "燕", "倩", "梅",
                "琳", "丹", "雪", "璐", "颖", "佳", "妍", "茜", "悦", "雯", "瑶", "欣", "语桐", "梓涵", "思琪", "雨萱",
                "一诺", "紫涵", "佳怡", "若曦", "雨桐", "梦瑶", "安然"]

CITIES = ["厦门", "福州", "泉州", "漳州", "莆田", "宁德", "南平", "三明", "龙岩", "深圳", "广州", "东莞", "佛山",
          "珠海", "杭州", "宁波", "苏州", "南京", "南昌"]

JOB_POSITIONS = [
    "Java开发工程师", "Python开发工程师", "前端开发工程师", "后端开发工程师",
    "软件测试工程师", "运维工程师", "数据分析师", "算法工程师"
]

UNIVERSITIES = {
    "本科": ["厦门大学", "中山大学", "浙江大学", "南京大学", "东南大学", "华南理工大学", "福州大学", "南昌大学",
             "苏州大学", "南京理工大学", "暨南大学", "浙江工业大学", "厦门理工学院", "福建师范大学", "福建农林大学",
             "集美大学", "闽南师范大学", "泉州师范学院", "广东技术师范大学", "东莞理工学院", "佛山科学技术学院",
             "浙江万里学院", "苏州科技大学", "南京工程学院", "江西师范大学"],
    "专科": ["福建船政交通职业学院", "福建信息职业技术学院", "厦门海洋职业技术学院", "广东轻工职业技术学院",
             "深圳职业技术学院", "苏州职业大学", "南京工业职业技术大学", "江西交通职业技术学院", "福州职业技术学院",
             "泉州经贸职业技术学院"]
}
MAJORS = ["计算机科学与技术", "软件工程", "电子信息工程", "数据科学与大数据技术", "通信工程", "物联网工程",
          "信息管理与信息系统", "数学与应用数学", "网络工程", "数字媒体技术", "计算机应用技术", "软件技术"]

# 经验分层：(最低年限, 最高年限, 标签, 人群占比)
EXPERIENCE_GROUPS = [
    (0, 0, "应届生（无经验）", 0.25),
    (0, 1, "应届生（有实习）", 0.15),
    (1, 3, "1-3年经验", 0.30),
    (3, 5, "3-5年经验", 0.20),
    (5, 10, "5年以上经验", 0.10),
]

COMPANY_PREFIX = ["智联", "云创", "数聚", "易联", "新科", "锐捷", "信雅", "博思", "天擎", "微远", "星图", "恒信",
                  "通元", "安硕", "启明", "合众", "汇智", "卓望", "科创", "未来", "中软", "东软", "用友", "金蝶"]
COMPANY_SUFFIX = ["科技有限公司", "信息技术有限公司", "网络科技有限公司", "软件有限公司", "数据技术有限公司",
                  "互联网科技有限公司"]
FAMOUS_COMPANIES = ["吉比特网络", "美图公司", "亿联网络", "字节跳动（厦门分公司）", "阿里巴巴（福州分公司）",
                    "腾讯（深圳分公司）", "华为（东莞研究所）", "网易（杭州）", "小米（南京分公司）", "OPPO（东莞）",
                    "vivo（东莞）", "携程（厦门）"]

# 分岗位项目库【应届生版 + 职场版】
PROJECTS = {
    "应届生": {
        "Java开发工程师": [
            ("学生成绩管理系统（课程设计）", "实现学生信息、成绩、班级的增删改查管理", "负责后端接口开发与数据库设计",
             "完成基础功能，通过课程答辩"),
            ("校园二手交易平台（毕设）", "搭建校园闲置物品发布与交易平台", "负责用户模块、商品发布模块开发",
             "完成系统原型，获得良好成绩")
        ],
        "前端开发工程师": [
            ("个人博客系统（课程作业）", "开发个人博客前端页面，实现文章展示与评论", "负责页面布局、交互效果、接口联调",
             "完成响应式页面，兼容多浏览器"),
            ("校园社团官网（实训项目）", "为学校社团开发官方展示网站", "负责首页、新闻页、成员页开发",
             "上线后访问量累计5000+")
        ],
        "后端开发工程师": [
            ("图书管理系统后端", "实现图书借阅、归还、用户管理功能", "负责接口开发与数据库表结构设计",
             "完成核心功能，支持1000条数据量"),
            ("简单论坛系统", "实现帖子发布、回复、板块管理", "负责后端服务开发与接口文档编写", "支持百人同时在线访问")
        ],
        "软件测试工程师": [
            ("学生管理系统功能测试", "对课程设计系统进行功能测试与缺陷提交", "设计测试用例，执行黑盒测试",
             "发现并提交8个功能缺陷"),
            ("网页兼容性测试实训", "对多个网站进行浏览器兼容测试", "制定测试方案，输出测试报告", "覆盖5款主流浏览器")
        ],
        "运维工程师": [
            ("实验室服务器搭建实训", "搭建实验室Linux服务器环境", "负责系统安装、网络配置、基础服务部署",
             "完成3台服务器环境搭建"),
            ("简单监控脚本开发", "编写服务器状态监控脚本", "实现CPU、内存、磁盘使用率自动采集", "支持异常邮件告警")
        ],
        "数据分析师": [
            ("学生成绩数据分析", "对班级期末成绩进行统计分析", "数据清洗、可视化图表制作、结论输出",
             "输出分析报告，提出3点教学建议"),
            ("电商公开数据爬取分析", "采集公开电商商品数据并分析", "数据爬取、清洗、价格销量分析", "输出可视化分析图表")
        ],
        "算法工程师": [
            ("手写数字识别（课程作业）", "基于MNIST数据集实现手写数字识别", "使用CNN搭建模型，训练与调优",
             "识别准确率达到92%"),
            ("电影推荐系统（毕设）", "基于协同过滤实现简单电影推荐", "数据处理、模型实现、效果验证", "召回准确率达到75%")
        ],
        "Python开发工程师": [
            ("简单爬虫脚本开发", "爬取公开网站数据并入库", "负责反爬处理、数据清洗、SQLite存储", "日均采集数据1万条"),
            ("自动化办公脚本", "批量处理Excel表格数据", "实现数据合并、格式转换、自动统计", "提升人工效率80%")
        ]
    },
    "职场": {
        "Java开发工程师": [
            ("微服务用户中心重构", "将单体用户系统拆分为微服务架构，提升并发承载能力",
             "负责登录、注册、权限模块开发，优化数据库查询与缓存策略", "支持并发量从500提升至5000，接口响应耗时减少60%"),
            (
            "电商订单交易系统", "搭建高可用电商订单系统，支撑大促流量峰值", "负责订单创建、支付回调、库存扣减核心逻辑开发",
            "支撑日均订单量10万+，系统可用性达99.95%")
        ],
        "前端开发工程师": [
            ("电商平台前端重构", "升级旧版电商系统前端架构，提升用户体验与加载速度",
             "负责商品详情页、购物车模块开发，组件化封装公共组件", "首屏加载时间从3.2s降至1.8s，页面转化率提升12%"),
            ("企业后台管理系统", "搭建企业运营管理后台，实现业务数据可视化",
             "负责权限管理、数据报表模块开发，对接后端接口联调", "覆盖12个业务部门，运营效率提升40%")
        ],
        "后端开发工程师": [
            ("内容管理系统后端", "搭建CMS系统后端服务，支持多站点内容发布",
             "负责文章、栏目、权限模块接口开发，设计数据库表结构", "支撑8个站点同时运营，内容发布效率提升3倍"),
            ("即时通讯服务开发", "实现企业内部IM系统后端消息推送与存储", "负责消息队列、离线消息、会话管理模块开发",
             "支持万人同时在线，消息送达延迟低于100ms")
        ],
        "软件测试工程师": [
            ("电商平台功能测试", "保障电商系统上线质量，覆盖全业务流程", "设计测试用例，执行功能、回归测试，提交缺陷报告",
             "发现并修复120+缺陷，上线后线上缺陷率低于0.5%"),
            ("自动化测试框架搭建", "提升回归测试效率，减少人工重复劳动",
             "基于Selenium搭建UI自动化框架，编写核心模块测试脚本", "回归测试周期从7天缩短至2天，覆盖率达85%")
        ],
        "运维工程师": [
            ("服务器集群运维优化", "提升服务器集群稳定性，降低故障发生率",
             "负责日常巡检、故障排查，优化监控告警规则与分级策略", "服务器故障率下降60%，平均故障响应时间缩短至15分钟"),
            ("CI/CD自动化流水线", "实现代码自动化构建、测试、部署，提升发布效率",
             "基于Jenkins搭建持续集成流水线，配置Docker容器化部署", "发布周期从每周1次提升至每天3次，部署失误率降为0")
        ],
        "数据分析师": [
            ("用户行为分析看板", "构建用户行为数据体系，支撑运营决策", "负责数据清洗、指标体系搭建，输出可视化运营报表",
             "输出15+核心运营指标，支撑每月3次运营优化，用户留存率提升8%"),
            ("销售数据预测建模", "基于历史数据预测销量，指导库存与备货",
             "数据预处理，构建时间序列预测模型，输出月度预测报告", "预测准确率达89%，库存周转效率提升25%")
        ],
        "算法工程师": [
            ("个性化推荐系统", "提升内容推荐精准度，增加用户停留时长", "负责协同过滤、深度学习推荐模型开发与离线优化",
             "用户平均停留时长提升25%，点击率提升15%"),
            ("风控欺诈识别模型", "识别交易欺诈行为，降低资金损失风险", "特征工程，构建XGBoost风控模型，在线部署与迭代",
             "欺诈识别准确率达92%，每年减少损失超200万")
        ],
        "Python开发工程师": [
            ("数据采集爬虫系统", "搭建分布式爬虫平台，采集多渠道公开数据", "负责反爬策略破解、数据清洗、入库逻辑开发",
             "日均采集数据50万条，数据准确率98%以上"),
            ("自动化运维平台", "开发运维管理平台，实现服务器批量管理", "负责监控、告警、任务调度模块后端开发",
             "管理服务器200+，运维人力成本降低50%")
        ]
    }
}

SKILL_LIBRARY = {
    "Java开发工程师": ["Java", "SpringBoot", "MyBatis", "MySQL", "Redis", "Git", "Linux", "JVM调优", "微服务",
                       "RabbitMQ", "Docker", "SpringCloud"],
    "Python开发工程师": ["Python", "Django", "Flask", "MySQL", "MongoDB", "Redis", "爬虫", "Docker", "Git", "Linux",
                         "FastAPI", "Celery"],
    "前端开发工程师": ["HTML5", "CSS3", "JavaScript", "Vue", "React", "Element UI", "Webpack", "Axios", "移动端适配",
                       "TypeScript", "Vite", "Ant Design"],
    "后端开发工程师": ["Java", "Go", "Python", "SpringBoot", "MySQL", "PostgreSQL", "Redis", "Kafka", "Docker",
                       "微服务", "K8s", "Gin"],
    "软件测试工程师": ["功能测试", "接口测试", "性能测试", "Selenium", "JMeter", "Postman", "MySQL", "Python",
                       "缺陷管理", "测试用例设计", "Appium", "TestNG"],
    "运维工程师": ["Linux", "Shell", "Docker", "Kubernetes", "Jenkins", "Nginx", "MySQL", "Redis", "Zabbix", "网络运维",
                   "Ansible", "Prometheus"],
    "数据分析师": ["SQL", "Python", "Pandas", "Excel", "Tableau", "数据可视化", "统计学", "用户分析", "MySQL", "Hive",
                   "Power BI", "NumPy"],
    "算法工程师": ["Python", "机器学习", "深度学习", "TensorFlow", "PyTorch", "SQL", "特征工程", "推荐算法", "NLP",
                   "数据结构", "算法优化", "计算机视觉"]
}

# 证书池【基础证书 + 职业证书】
CERT_BASIC = ["计算机二级", "英语四级", "英语六级", "计算机一级"]
CERT_PROFESSIONAL = ["软件设计师（中级）", "系统架构设计师", "PMP项目管理专业人士", "阿里云ACP云计算认证", "华为HCIA认证",
                     "MySQL数据库认证", "红帽RHCE认证", "软考中级"]


# ==================================================
# 工具函数
# ==================================================
def generate_phone():
    prefixes = ["130", "131", "132", "133", "134", "135", "136", "137", "138", "139", "150", "151", "152", "153", "155",
                "156", "157", "158", "159", "180", "181", "182", "183", "184", "185", "186", "187", "188", "189", "177",
                "176"]
    return random.choice(prefixes) + "".join(random.choice("0123456789") for _ in range(8))


def generate_email(name_py):
    suffixes = ["@163.com", "@qq.com", "@gmail.com", "@126.com", "@outlook.com"]
    num = "".join(random.choice("0123456789") for _ in range(random.randint(2, 4)))
    return f"{name_py}{num}{random.choice(suffixes)}"


def generate_wechat(name_py):
    if random.random() > 0.5:
        return f"wx_{name_py}_{random.randint(100, 999)}"
    else:
        return generate_phone()


def get_name_pinyin(name):
    pinyin_map = {
        '王': 'wang', '李': 'li', '张': 'zhang', '刘': 'liu', '陈': 'chen', '杨': 'yang', '黄': 'huang',
        '赵': 'zhao', '吴': 'wu', '周': 'zhou', '徐': 'xu', '孙': 'sun', '马': 'ma', '朱': 'zhu',
        '胡': 'hu', '郭': 'guo', '何': 'he', '高': 'gao', '林': 'lin', '罗': 'luo', '郑': 'zheng',
        '梁': 'liang', '谢': 'xie', '宋': 'song', '唐': 'tang', '许': 'xu', '韩': 'han', '冯': 'feng',
        '邓': 'deng', '曹': 'cao', '彭': 'peng', '曾': 'zeng', '萧': 'xiao', '田': 'tian', '董': 'dong',
        '袁': 'yuan', '潘': 'pan', '于': 'yu', '蒋': 'jiang', '蔡': 'cai', '余': 'yu', '杜': 'du',
        '叶': 'ye', '程': 'cheng', '苏': 'su', '魏': 'wei', '吕': 'lv', '丁': 'ding', '任': 'ren',
        '沈': 'shen', '姚': 'yao', '卢': 'lu', '傅': 'fu', '钟': 'zhong', '姜': 'jiang', '崔': 'cui',
        '谭': 'tan', '陆': 'lu', '汪': 'wang', '范': 'fan', '金': 'jin', '石': 'shi', '廖': 'liao',
        '贾': 'jia', '夏': 'xia', '韦': 'wei', '方': 'fang', '白': 'bai', '邹': 'zou', '孟': 'meng',
        '熊': 'xiong', '秦': 'qin', '邱': 'qiu', '江': 'jiang', '尹': 'yin', '薛': 'xue', '闫': 'yan',
        '段': 'duan', '雷': 'lei', '侯': 'hou', '龙': 'long', '史': 'shi', '陶': 'tao', '黎': 'li',
        '贺': 'he', '顾': 'gu', '毛': 'mao', '郝': 'hao', '龚': 'gong', '邵': 'shao', '万': 'wan',
        '钱': 'qian', '严': 'yan', '覃': 'qin', '武': 'wu', '戴': 'dai', '莫': 'mo', '孔': 'kong',
        '向': 'xiang', '汤': 'tang',
        '伟': 'wei', '强': 'qiang', '磊': 'lei', '洋': 'yang', '勇': 'yong', '军': 'jun', '杰': 'jie',
        '涛': 'tao', '超': 'chao', '明': 'ming', '刚': 'gang', '平': 'ping', '辉': 'hui', '鹏': 'peng',
        '华': 'hua', '建': 'jian', '峰': 'feng', '飞': 'fei', '彬': 'bin', '鑫': 'xin', '博': 'bo',
        '宇': 'yu', '浩': 'hao', '凯': 'kai', '健': 'jian', '俊': 'jun', '恒': 'heng', '阳': 'yang',
        '晨': 'chen', '皓': 'hao', '然': 'ran', '轩': 'xuan', '泽': 'ze', '文': 'wen',
        '熙': 'xi', '思': 'si', '远': 'yuan', '佑': 'you',
        '芳': 'fang', '娜': 'na', '敏': 'min', '静': 'jing', '丽': 'li', '艳': 'yan', '娟': 'juan',
        '莉': 'li', '玲': 'ling', '慧': 'hui', '婷': 'ting', '霞': 'xia', '萍': 'ping', '红': 'hong',
        '燕': 'yan', '倩': 'qian', '梅': 'mei', '琳': 'lin', '丹': 'dan', '雪': 'xue', '璐': 'lu',
        '颖': 'ying', '佳': 'jia', '妍': 'yan', '茜': 'xi', '悦': 'yue', '雯': 'wen', '瑶': 'yao',
        '欣': 'xin', '桐': 'tong', '涵': 'han', '琪': 'qi', '萱': 'xuan', '诺': 'nuo', '怡': 'yi',
        '曦': 'xi', '梦': 'meng', '安': 'an'
    }
    res = ""
    for c in name:
        res += pinyin_map.get(c, c)
    return res


def calc_graduation_year(exp_years):
    current_year = datetime.datetime.now().year
    return current_year - int(exp_years) - 4


# ==================================================
# 单份简历生成
# ==================================================
def generate_single_resume():
    # 1. 基本信息
    gender = random.choice(["男", "女"])
    surname = random.choice(SURNAMES)
    name = surname + random.choice(MALE_NAMES if gender == "男" else FEMALE_NAMES)
    name_py = get_name_pinyin(name)

    phone = generate_phone()
    email = generate_email(name_py)
    wechat = generate_wechat(name_py)
    city = random.choice(CITIES)

    # 2. 求职岗位
    target_job = random.choice(JOB_POSITIONS)

    # 3. 经验分层抽样
    exp_group = random.choices(
        EXPERIENCE_GROUPS,
        weights=[g[3] for g in EXPERIENCE_GROUPS],
        k=1
    )[0]
    exp_min, exp_max, exp_label, _ = exp_group
    exp_years = random.randint(exp_min, exp_max)
    graduation_year = calc_graduation_year(exp_years)

    # 4. 学历匹配：零经验大专概率更高，经验越久本科概率越高
    if exp_label == "应届生（无经验）":
        edu_type = random.choices(["本科", "专科"], weights=[0.4, 0.6])[0]
    elif exp_label == "应届生（有实习）":
        edu_type = random.choices(["本科", "专科"], weights=[0.6, 0.4])[0]
    elif exp_label == "1-3年经验":
        edu_type = random.choices(["本科", "专科"], weights=[0.65, 0.35])[0]
    else:
        edu_type = random.choices(["本科", "专科"], weights=[0.8, 0.2])[0]

    school = random.choice(UNIVERSITIES[edu_type])
    major = random.choice(MAJORS)
    core_courses = random.sample(
        ["数据结构", "计算机网络", "操作系统", "数据库原理", "Java程序设计", "Python编程", "机器学习", "软件工程",
         "数字信号处理", "算法设计与分析"], 4)

    education_text = f"{school} | {major} | {edu_type}\n毕业时间：{graduation_year}年6月\n核心课程：{'、'.join(core_courses)}"

    # 5. 个人简介
    if exp_label == "应届生（无经验）":
        intro = f"{edu_type}{major}专业应届毕业生，掌握{random.choice(SKILL_LIBRARY[target_job])}、{random.choice(SKILL_LIBRARY[target_job])}基础技能，完成过课程设计与毕业项目，具备基础代码编写能力与问题排查思路，学习能力强，做事认真踏实，期望从事{target_job}相关工作。"
    elif exp_label == "应届生（有实习）":
        intro = f"{edu_type}{major}专业应届毕业生，有{exp_years}段{target_job}实习经验，掌握{random.choice(SKILL_LIBRARY[target_job])}技术栈，参与过实习项目开发，具备良好的代码规范与团队协作意识，能够快速上手业务，期望正式入职发展。"
    elif exp_label == "1-3年经验":
        intro = f"{exp_years}年{target_job}工作经验，精通{random.choice(SKILL_LIBRARY[target_job])}、{random.choice(SKILL_LIBRARY[target_job])}技术栈，参与过完整项目迭代，能够独立完成模块开发与问题排查，注重代码质量与开发效率，具备良好的沟通协作能力。"
    elif exp_label == "3-5年经验":
        intro = f"{exp_years}年{target_job}从业经验，精通{random.choice(SKILL_LIBRARY[target_job])}技术架构，主导过中型项目从0到1落地，擅长技术方案设计与性能优化，曾推动核心模块技术重构，带来显著效率提升，具备跨部门协作与项目推进能力。"
    else:
        intro = f"{exp_years}年{target_job}资深经验，精通全链路技术架构，具备团队技术规划与方案设计能力，主导过多个大型项目重构与升级，在高并发/系统稳定性领域有深厚积累，能够带领团队攻克技术难题，驱动业务技术升级。"

    # 6. 工作/实习经历
    work_experience = ""
    if exp_label == "应届生（无经验）":
        # 无经验：不写工作经历，写校园实践
        work_experience = f"【校园实践】\n    · 参与学校计算机协会技术部，负责协会网站日常维护\n    · 协助老师完成实验室设备管理与系统环境搭建\n    · 参与班级课程设计小组，担任后端开发角色"
    else:
        work_count = 1 if exp_years <= 1 else 2 if exp_years <= 4 else 3
        current_end_year = datetime.datetime.now().year

        for i in range(work_count):
            if random.random() > 0.7 and i == 0:
                company = random.choice(FAMOUS_COMPANIES)
            else:
                company = random.choice(COMPANY_PREFIX) + random.choice(COMPANY_SUFFIX)

            work_duration = max(1, exp_years // work_count) if exp_years > 0 else random.randint(3, 8)
            start_year = current_end_year - work_duration
            work_time = f"{start_year}年{random.randint(1, 12)}月 - {current_end_year}年{random.randint(1, 12)}月"
            if i == 0:
                work_time = f"{start_year}年{random.randint(1, 12)}月 - 至今"

            # 职位：实习还是正式
            position = f"{target_job}（实习）" if exp_label == "应届生（有实习）" else target_job

            duties = [
                f"负责公司{target_job}相关业务的开发与维护，参与需求评审",
                f"承担分配模块的编码、测试与优化工作，保障系统稳定运行",
                f"对接产品、测试团队，跟进需求落地与缺陷修复",
                f"编写开发文档，沉淀技术规范，协助新人熟悉业务"
            ]
            duty_text = "\n    · ".join(random.sample(duties, random.randint(2, 3)))

            work_experience += f"【{company}】 {position}\n{work_time}\n    · {duty_text}\n\n"
            current_end_year = start_year

        work_experience = work_experience.strip()

    # 7. 项目经验
    project_type = "应届生" if "应届生" in exp_label else "职场"
    project_count = 1 if exp_label == "应届生（无经验）" else 2 if "应届生" in exp_label else 3
    available_projects = PROJECTS[project_type][target_job]
    selected_projects = random.sample(available_projects, min(project_count, len(available_projects)))

    project_text = ""
    for proj_name, proj_target, proj_duty, proj_result in selected_projects:
        project_text += f"■ {proj_name}\n  项目目标：{proj_target}\n  个人职责：{proj_duty}\n  项目成果：{proj_result}\n\n"
    project_text = project_text.strip()

    # 8. 技能特长 + 证书
    # 技能数量：应届生少，职场多
    if "应届生" in exp_label:
        skill_count = random.randint(4, 7)
    else:
        skill_count = random.randint(6, 10)
    skills = random.sample(SKILL_LIBRARY[target_job], min(skill_count, len(SKILL_LIBRARY[target_job])))

    # 证书：0-3个随机，应届生基础证书多，职场职业证书多
    cert_list = []
    cert_num = random.choices([0, 1, 2, 3], weights=[0.2, 0.4, 0.3, 0.1])[0]

    if cert_num > 0:
        if "应届生" in exp_label:
            # 应届生多基础证书
            cert_pool = CERT_BASIC + random.sample(CERT_PROFESSIONAL, 2)
            cert_list = random.sample(cert_pool, cert_num)
        else:
            # 职场混合证书
            cert_pool = CERT_BASIC + CERT_PROFESSIONAL
            cert_list = random.sample(cert_pool, cert_num)

    cert_text = "、".join(cert_list) if cert_list else "无"
    skill_text = f"专业技能：{'、'.join(skills)}\n相关证书：{cert_text}"

    # 9. 自我评价
    if exp_label == "应届生（无经验）":
        self_evaluation = f"应届毕业，具备扎实的专业基础知识与学习能力，能够快速掌握新技术；工作态度认真负责，有耐心，注重细节；具备良好的团队意识与沟通能力，能够积极配合团队完成任务；期望在工作中积累经验，快速成长。"
    elif exp_label == "应届生（有实习）":
        self_evaluation = f"有实习经验，熟悉开发基本流程，具备基础的项目实践能力；学习能力强，能够快速上手新业务新技术；工作踏实，责任心强，善于沟通协作，能够高效完成分配的工作任务。"
    elif exp_label == "1-3年经验":
        self_evaluation = f"拥有{exp_years}年实际工作经验，技术功底扎实，熟悉完整开发流程；具备较强的问题解决能力，能够独立排查并解决常见技术问题；工作认真负责，注重团队协作，能够高效推进项目落地；持续学习，保持技术敏感度。"
    else:
        self_evaluation = f"拥有{exp_years}年行业经验，技术视野开阔，具备方案设计与项目把控能力；逻辑清晰，善于定位并解决复杂技术问题；具备良好的团队管理与跨部门沟通能力，能够推动技术优化与业务落地；责任心强，追求技术与业务的平衡发展。"

    # 10. 求职意向
    job_intention = f"期望岗位：{target_job}\n期望城市：{city}\n期望行业：互联网/信息技术/软件服务\n期望薪资：面议"

    return {
        "姓名": name,
        "性别": gender,
        "手机号": phone,
        "邮箱": email,
        "微信号": wechat,
        "居住地": city,
        "求职意向": job_intention,
        "个人简介": intro,
        "教育经历": education_text,
        "工作/实践经历": work_experience,
        "项目经验": project_text,
        "技能特长": skill_text,
        "自我评价": self_evaluation
    }


# ==================================================
# 批量生成保存
# ==================================================
if __name__ == "__main__":
    print("正在生成500份真实随机简历...")
    resume_list = []

    for i in range(500):
        resume = generate_single_resume()
        resume_list.append(resume)
        if (i + 1) % 100 == 0:
            print(f"已生成 {i + 1}/500 份")

    # 保存到指定路径（CSV格式）
    save_path = r"C:\Users\王俊淇\Desktop\大四上小学期\zq\data\raw\随机简历500份.csv"
    df = pd.DataFrame(resume_list)
    df.to_csv(save_path, index=False, encoding="utf-8-sig")

    # 人群分布统计
    exp_dist = df["个人简介"].apply(lambda x:
                                    "应届生（无经验）" if "应届毕业生，掌握" in x
                                    else "应届生（有实习）" if "应届毕业生，有" in x
                                    else "1-3年经验" if "1-3年" in x
                                    else "3-5年经验" if "3-5年" in x
                                    else "5年以上经验"
                                    ).value_counts().to_dict()

    print(f"\n✅ 生成完成！共500份简历")
    print(f"文件保存路径：{save_path}")
    print(f"\n📊 人群分布统计：")
    for k, v in exp_dist.items():
        print(f"  {k}：{v} 人")
    print(
        f"\n包含字段：姓名、性别、手机号、邮箱、微信号、居住地、求职意向、个人简介、教育经历、工作/实践经历、项目经验、技能特长、自我评价")
