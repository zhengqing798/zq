# -*- coding: utf-8 -*-
"""随机生成一份「可直接粘贴」的简历文本（演示/联调用）

为什么需要：
  · 个人中心「我的简历」是粘贴正文或上传 PDF；演示时手打一份不现实
  · 本项目已有 `scripts/jianlishengcheng.py`（500 份合成简历的生成器），
    本脚本复用它生成结构化记录，再用 `parse_resume._resume_to_paste_text()` 转成
    **与解析器完全对齐的粘贴格式**，避免格式不对导致字段解析不出来

用法：
    python scripts/make_sample_resume.py                      # 随机一份，打印并保存
    python scripts/make_sample_resume.py --out my.txt         # 指定输出文件
    python scripts/make_sample_resume.py --verify             # 额外调接口验证能解析、能匹配（需后端已启动）
"""
import argparse
import io
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src", "models", "matching"))

from jianlishengcheng import generate_single_resume                        # noqa: E402
from parse_resume import _resume_to_paste_text                             # noqa: E402

API = "http://127.0.0.1:8000"


def covered_cities():
    """岗位库覆盖的城市（取「岗位地区」第一段）——让样例简历的期望城市落在库里，匹配才有意义"""
    path = os.path.join(ROOT, "data", "processed", "zhaopin_jobs_cleaned_seg.csv")
    if not os.path.exists(path):
        return []
    import csv
    with io.open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return sorted({(r.get("岗位地区") or "").split()[0] for r in rows if (r.get("岗位地区") or "").split()})


def _clean_contact(raw):
    """把邮箱本地部分里的非 ASCII 字符去掉

    生成器的拼音表没覆盖所有汉字（例如「语」），会生成 `chen语tong99@163.com` 这种邮箱。
    样例简历要给人看，这里做一次清洗（不改生成器本身，避免影响已生成的 500 份数据）。
    """
    import re
    m = re.match(r"^([^@]+)@(.+)$", raw.get("邮箱") or "")
    if m:
        local = re.sub(r"[^A-Za-z0-9._-]", "", m.group(1)) or "resume"
        raw["邮箱"] = "%s@%s" % (local, m.group(2))
    return raw


def make_text(prefer_covered=True):
    """生成结构化记录 + 粘贴文本；期望城市尽量落在岗位库覆盖的城市里"""
    cities = covered_cities() if prefer_covered else []
    raw = _clean_contact(generate_single_resume())
    if cities:
        for _ in range(80):
            city = raw["求职意向"].split("期望城市：")[-1].split("\n")[0].strip()
            if city in cities:
                break
            raw = _clean_contact(generate_single_resume())
        else:
            # 兜底：直接改写期望城市与居住地（保证样例可匹配）
            new_city = cities[0] if cities else "厦门"
            raw["求职意向"] = raw["求职意向"].replace(
                "期望城市：" + city, "期望城市：" + new_city)
            raw["居住地"] = new_city
    return raw, _resume_to_paste_text(raw)


def verify(text):
    """调后端接口验证：解析字段 + 人岗匹配 Top5（后端没启动就跳过）"""
    def post(path, payload):
        req = urllib.request.Request(API + path, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.load(r)

    try:
        parsed = post("/api/resume/parse_text", {"resume_text": text})
    except Exception as e:
        print("\n（跳过接口验证：后端未启动？%s）" % e)
        return
    print("\n" + "=" * 72)
    print("① 解析验证（/api/resume/parse_text）")
    f = parsed["解析字段"]
    for k in ("姓名", "期望岗位", "期望城市", "最高学历", "专业", "工作年限", "是否应届", "期望薪资"):
        print("   %-6s：%s" % (k, f.get(k) if f.get(k) not in (None, "") else "（未识别）"))
    print("   识别技能 %d 项：%s" % (parsed["技能数"], "、".join(parsed["技能列表"][:12])))
    if parsed.get("未在词典的技能"):
        print("   词典外技能：%s" % "、".join(parsed["未在词典的技能"][:8]))
    if parsed.get("解析告警"):
        print("   解析告警：%s" % parsed["解析告警"])

    print("\n② 匹配验证（/api/match，Top5）")
    m = post("/api/match", {"resume_text": text, "top_n": 5})
    print("   权重版本 %s ｜ 全量打分 %.2fs ｜ 推荐 %d 个" %
          (m["权重版本"], m["耗时秒"], m["推荐数"]))
    for r in m["推荐"]:
        print("   #%d %-26s %-14s %-12s 总分 %.1f ｜ %s" %
              (r["排名"], r["岗位名称"][:26], r["公司"][:14], r["城市"], r["总分"],
               r["推荐理由"][:40]))
    print("=" * 72)


def main():
    ap = argparse.ArgumentParser(description="生成一份可直接粘贴的随机简历")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "processed", "测试简历_随机粘贴版.txt"),
                    help="保存路径（默认 data/processed/测试简历_随机粘贴版.txt）")
    ap.add_argument("--verify", action="store_true", help="额外调接口验证解析与匹配（需后端已启动）")
    ap.add_argument("--any-city", action="store_true",
                    help="期望城市允许不在岗位库覆盖范围内（默认会优先取覆盖城市）")
    a = ap.parse_args()

    raw, text = make_text(prefer_covered=not a.any_city)
    print("=" * 72)
    print("随机简历已生成（直接整段复制粘贴到「个人中心 → 我的简历」的粘贴框）")
    print("=" * 72)
    print(text)
    print("=" * 72)
    print("姓名：%s ｜ 期望岗位见上方 ｜ 技能：%s" %
          (raw["姓名"], raw["技能特长"][:60].replace("\n", " ")))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    io.open(a.out, "w", encoding="utf-8", newline="\n").write(text)
    print("已保存到：%s" % os.path.relpath(a.out, ROOT))

    if a.verify:
        verify(text)


if __name__ == "__main__":
    main()
