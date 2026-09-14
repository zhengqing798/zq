# -*- coding: utf-8 -*-
"""
任务6 · 步骤5：人岗匹配主流程（简历 → 六维加权匹配分 → Top-N 推荐 + 推荐理由）

输入：任意简历（粘贴文本 / PDF / 已有的 500 份离线简历之一）
输出：
  · Top-N 岗位推荐（含 6 个维度分项得分 + 自然语言推荐理由）
  · `--sample N` 时另出 `data/processed/匹配推荐_样例结果.csv`（N 份简历 × Top10）

口径（与任务5 标签同源，权重见 `data/processed/匹配权重表.csv`）：
  匹配分 = w技能·技能分 + w经验·经验分 + w学历·学历分 + w地域·地域分 + w薪资·薪资分 + w专业证书·专业证书分
  · 技能分 = 0.6 × (0.7×岗位技能覆盖率 + 0.3×简历技能利用率) + 0.4 × (TF-IDF 余弦 × 100)
    （融合口径的定稿依据见《技能相似度_口径对比报告》）
  · 其余五维直接复用任务5 的算分函数，保证"离线标签口径 = 线上匹配口径"一致
  · 权重带版本号（v1 = 任务5 口径），改权重只需改 `匹配权重表.csv`

运行示例
  python src/models/matching/match.py --resume-id R001 --top 10
  python src/models/matching/match.py --text "…简历正文…" --top 5
  python src/models/matching/match.py --pdf 简历.pdf --top 10
  python src/models/matching/match.py --sample 5          # 样例结果落盘
"""
import argparse
import csv
import os
import sys
import time

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "preprocessing"))
sys.path.insert(0, os.path.join(ROOT, "src", "models", "scoring"))
from build_labels import (load_csv, load_synonyms, build_blacklist, build_jobs, build_resumes,  # noqa: E402
                          norm_skill, skill_score, exp_score, edu_score, geo_score, sal_score,
                          pc_score, haversine, EDU_ORD)
from parse_resume import build_skill_dict, parse_resume_text, parse_resume_pdf              # noqa: E402
from skill_similarity import SkillSim, W_COVER, W_COS                                       # noqa: E402

P = os.path.join(ROOT, "data", "processed")
JOBS_CSV = os.path.join(P, "zhaopin_jobs_cleaned_seg.csv")
RES_CLEAN_CSV = os.path.join(P, "简历数据_cleaned.csv")
RES_SEG_CSV = os.path.join(P, "简历数据_seg.csv")
WEIGHTS_CSV = os.path.join(P, "匹配权重表.csv")
OUT_SAMPLE = os.path.join(P, "匹配推荐_样例结果.csv")
DIMS = ["技能", "经验", "学历", "地域", "薪资", "专业证书"]
EDU_NAME = {0: "初中", 1: "高中", 2: "中专", 3: "大专", 4: "本科", 5: "硕士", 6: "博士", -1: "不限"}


# ---------------------------------------------------------------- 权重

def load_weights(version=None):
    rows = load_csv(WEIGHTS_CSV)
    if version:
        rows = [r for r in rows if r["版本"] == version]
    if not rows:
        raise SystemExit("权重表里没有版本 %s（可用：%s）" %
                         (version, "、".join(r["版本"] for r in load_csv(WEIGHTS_CSV))))
    w = rows[-1]
    out = {d: float(w[d]) for d in DIMS}
    s = sum(out.values())
    if abs(s - 1.0) > 1e-6:
        raise SystemExit("权重之和 %.4f ≠ 1（版本 %s），请检查 匹配权重表.csv" % (s, w["版本"]))
    return {"版本": w["版本"], "权重": out, "说明": w["说明"]}


# ---------------------------------------------------------------- 岗位索引（一次建好，多次复用）

class JobIndex:
    def __init__(self):
        jobs_raw = load_csv(JOBS_CSV)
        clean = load_csv(RES_CLEAN_CSV)
        seg = load_csv(RES_SEG_CSV)
        terms, syn, pool_norm = build_skill_dict(write=False)
        black, indus, _ = build_blacklist(jobs_raw)
        pool_plain = {norm_skill(x) for s in seg for x in (s["技能词"] or "").split("、") if x}
        self.terms = terms
        self.jobs = build_jobs(jobs_raw, syn, black, indus, pool_plain)
        self.resumes = build_resumes(clean, seg, syn)
        self.sim = SkillSim(self.jobs, terms)
        self.rows = jobs_raw
        self._dist = {}

    def distance(self, city_a, city_b):
        if not city_a or not city_b:
            return -1.0
        if city_a == city_b:
            return 0.0
        k = (city_a, city_b)
        if k not in self._dist:
            self._dist[k] = haversine(city_a, city_b)
        return self._dist[k]

    def __len__(self):
        return len(self.jobs)


def resume_record_from_parsed(parsed):
    """把解析器输出转成与离线简历记录同结构的对象（供算分函数直接使用）"""
    skills = [x for x in (parsed.get("技能列表") or "").split("、") if x]
    canon = {norm_skill(x) for x in skills}
    lo = parsed.get("期望薪资下限(元/月)") or ""
    return {
        "姓名": parsed.get("姓名") or "（未识别）",
        "城市": parsed.get("期望城市") or "",
        "学历序数": EDU_ORD.get(parsed.get("最高学历") or "", 3),
        "年限": int(parsed.get("工作年限") or 0),
        "应届": parsed.get("是否应届") == "是",
        "期望下限": int(lo) if str(lo).strip().isdigit() else None,
        "面议": parsed.get("期望薪资是否面议") == "是",
        "专业": parsed.get("专业") or "",
        "证书": [x for x in (parsed.get("证书列表") or "").split("、") if x],
        "技能数": len(canon),
        "技能canon": canon,
        "技能plain": canon,
        "解析告警": parsed.get("解析告警", ""),
    }


# ---------------------------------------------------------------- 单对打分

def score_pair(idx, job_i, res, w, cos):
    """→ (总分, {维度: 分}, 说明)；w 是 {维度: 权重}，cos 是该简历对 job_i 的 TF-IDF 余弦分（预先批量算好）"""
    job = idx.jobs[job_i]
    # ① 技能：覆盖率口径 + TF-IDF 余弦 融合
    hit_set = res["技能canon"] & job["J"]
    cover, cov, util = skill_score(len(hit_set), len(job["J"]), max(res["技能数"], 1))
    skill = round(W_COVER * cover + W_COS * cos, 2)
    # ②–⑥ 复用任务5 的算分函数
    exp = exp_score(res["年限"], job["exp_kind"], job["exp_lo"])
    edu = edu_score(job["edu"], res["学历序数"])
    d = idx.distance(res["城市"], job["城市"])
    geo = geo_score(d) if d >= 0 else 60.0
    sal = sal_score(res["期望下限"], res["面议"], job["sal_lo"], job["sal_hi"])
    pc, prof, cert = pc_score(job["kw"], res["专业"], res["证书"])
    dims = {"技能": skill, "经验": exp, "学历": edu, "地域": geo, "薪资": sal, "专业证书": pc}
    total = round(sum(w[d] * dims[d] for d in DIMS), 2)
    info = {
        "命中技能": "、".join(idx.terms.get(c, c) for c in sorted(hit_set)[:6]) or "无",
        "命中数": len(hit_set), "要求数": len(job["J"]), "余弦": round(cos, 1),
        "覆盖率": round(cov, 1) if cov is not None else None,
        "距离": d, "经验type": job["exp_kind"], "经验下限": job["exp_lo"], "经验上限": job["exp_hi"],
        "专业命中": prof, "证书项": cert,
    }
    return total, dims, info


def build_reasons(dims, job, res, info, w):
    """推荐理由：取「权重×得分」贡献最大的 3 项做亮点，再给出最低的 1 项作为提醒"""
    contrib = sorted(dims.items(), key=lambda kv: -w[kv[0]] * kv[1])
    lines = []
    for dim, sc in contrib[:3]:
        if dim == "技能":
            lines.append("技能命中 %d/%d（%s）" % (info["命中数"], info["要求数"], info["命中技能"])
                         if info["要求数"] else "岗位未给出技能要求")
        elif dim == "经验":
            if info["经验type"] == "missing":
                lines.append("岗位经验要求未能解析（按信息缺失中性处理）")
            elif info["经验type"] == "unlimited":
                lines.append("岗位经验不限")
            else:
                lines.append("经验满足（要求 %s-%s 年，你有 %s 年）" % (info["经验下限"], info["经验上限"], res["年限"])
                             if res["年限"] >= (info["经验下限"] or 0)
                             else "经验不足（要求 ≥%s 年，你有 %s 年）" % (info["经验下限"], res["年限"]))
        elif dim == "学历":
            req = EDU_NAME.get(job["edu"], "不限") if job["edu"] is not None else "不限"
            lines.append("学历满足（要求%s，你%s）" % (req, EDU_NAME.get(res["学历序数"], "?")))
        elif dim == "地域":
            lines.append("同城（%s）" % job["city" if "city" in job else "城市"] if info["距离"] == 0
                         else ("地域信息不全" if info["距离"] < 0
                               else "%s → %s 约 %.0fkm" % (res["城市"], job["城市"], info["距离"])))
        elif dim == "薪资":
            lines.append("岗位上限 %s ≥ 期望下限 %s" % (job["sal_hi"] or "缺失", res["期望下限"] or "未填写")
                         if (job["sal_hi"] and res["期望下限"]) else "薪资信息不全（按中性处理）")
        else:
            lines.append("专业命中岗位描述" if info["专业命中"] >= 100 else
                         ("技术认证方向相关" if info["证书项"] >= 100 else "专业/证书为通用匹配"))
    low = min(dims.items(), key=lambda kv: kv[1])       # 提醒项取「原始得分最低」的维度（更直观）
    return "；".join(lines) + "。｜提醒：" + _low_text(low[0], dims, job, res, info)


def _low_text(dim, dims, job, res, info):
    if dim == "技能":
        return "技能匹配度最低（命中 %d/%d）" % (info["命中数"], info["要求数"])
    if dim == "经验":
        return "经验是短板（岗位要求未能解析）" if info["经验type"] == "missing" \
            else "经验是短板（要求 ≥%s 年，你有 %s 年）" % (info["经验下限"], res["年限"])
    if dim == "学历":
        return "学历低于要求（要求%s，你%s）" % (EDU_NAME.get(job["edu"], "不限"), EDU_NAME.get(res["学历序数"], "?"))
    if dim == "地域":
        return "跨城（约 %.0fkm）" % info["距离"] if info["距离"] and info["距离"] > 0 else "地域信息不足"
    if dim == "薪资":
        return "岗位薪资上限低于期望（%s < %s）" % (job["sal_hi"] or "缺失", res["期望下限"] or "未填写")
    return "专业/证书与岗位方向关联弱"


# ---------------------------------------------------------------- 主流程

def match_jobs(idx, res, w, top_n=10):
    n = len(idx.jobs)
    cos_arr = idx.sim.cosine_all(res["技能canon"])      # 一次矩阵乘算完全部岗位的余弦（避免逐对重算）
    out = []
    for i in range(n):
        total, dims, info = score_pair(idx, i, res, w, cos_arr[i])
        out.append((total, i, dims, info))
    out.sort(key=lambda x: -x[0])
    recs = []
    for rank, (total, i, dims, info) in enumerate(out[:top_n], 1):
        job = idx.jobs[i]
        r = idx.rows[i]
        recs.append({
            "排名": rank, "总分": total, **{d: dims[d] for d in DIMS},
            "岗位ID": job["id"], "岗位名称": job["名称"], "公司": r["公司名称"],
            "城市": job["城市"], "岗位薪资": r["岗位薪资"], "经验要求": r["经验要求"],
            "学历要求": r["学历要求"], "技能标签": r["技能标签"],
            "技能命中数": info["命中数"], "岗位技能要求数": info["要求数"],
            "余弦分": info["余弦"], "距离km": round(info["距离"], 1) if info["距离"] >= 0 else -1,
            "推荐理由": build_reasons(dims, job, res, info, w),
        })
    return recs, out


def print_table(res, recs, version, n_jobs, elapsed):
    print("\n简历：%s ｜ 期望岗位 %s ｜ 期望城市 %s ｜ 学历序数 %s ｜ 工作年限 %s ｜ 技能 %d 项 ｜ 面议 %s"
          % (res["姓名"], res.get("期望岗位") or "—", res["城市"] or "—", res["学历序数"],
             res["年限"], res["技能数"], "是" if res["面议"] else "否"))
    if res.get("解析告警"):
        print("解析告警：%s" % res["解析告警"])
    print("权重版本 %s ｜ 全量 %d 个岗位逐个打分耗时 %.2fs（课程要求 <3s）" % (version, n_jobs, elapsed))
    print("-" * 132)
    print("%-4s %-6s %-26s %-8s %-6s %-6s %-6s %-6s %-6s %-6s" %
          ("排名", "总分", "岗位名称", "城市", "技能", "经验", "学历", "地域", "薪资", "专证"))
    print("-" * 132)
    for r in recs:
        print("%-4d %-6.1f %-26s %-8s %-6.1f %-6.1f %-6.1f %-6.1f %-6.1f %-6.1f" %
              (r["排名"], r["总分"], r["岗位名称"][:26], r["城市"], r["技能"], r["经验"], r["学历"],
               r["地域"], r["薪资"], r["专业证书"]))
    print("-" * 132)
    for r in recs[:3]:
        print("  #%d %s ｜ %s" % (r["排名"], r["岗位名称"][:26], r["推荐理由"]))


def sample_output(idx, weights, n=5):
    """取 n 份离线简历跑 Top10 并落盘"""
    w = weights["权重"]
    clean = load_csv(RES_CLEAN_CSV)
    idxs = list(range(0, len(idx.resumes), max(1, len(idx.resumes) // n)))[:n]
    rows = []
    for i in idxs:
        res = dict(idx.resumes[i])
        res["期望岗位"] = clean[i].get("期望岗位", "")
        res["解析告警"] = ""
        recs, _ = match_jobs(idx, res, w, top_n=10)
        for r in recs:
            rows.append({"简历ID": "R%03d" % (i + 1), "简历姓名": res["姓名"],
                         "期望岗位": res["期望岗位"], "期望城市": res["城市"], **r})
    with open(OUT_SAMPLE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("输出：%s（%d 份简历 × Top10 = %d 行）" % (os.path.relpath(OUT_SAMPLE, ROOT), len(idxs), len(rows)))


def main():
    ap = argparse.ArgumentParser(description="人岗匹配：Top-N 推荐 + 推荐理由")
    ap.add_argument("--text", help="粘贴简历文本")
    ap.add_argument("--pdf", help="简历 PDF 路径")
    ap.add_argument("--resume-id", help="用离线 500 份简历之一，如 R001")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--weights", help="权重版本，默认取最新")
    ap.add_argument("--sample", type=int, help="跑 N 份离線简历并落盘样例结果")
    a = ap.parse_args()
    weights = load_weights(a.weights)
    print("权重版本 %s：%s" % (weights["版本"], weights["说明"]))
    t0 = time.time()
    idx = JobIndex()
    print("岗位索引就绪：%d 个岗位（建索引 %.1fs）" % (len(idx), time.time() - t0))

    if a.sample:
        sample_output(idx, weights, a.sample)
        return
    if a.pdf:
        parsed = parse_resume_pdf(a.pdf)
        print("PDF 解析完成：%s" % (parsed.get("解析告警") or "无告警"))
    elif a.text:
        parsed = parse_resume_text(a.text)
    elif a.resume_id:
        k = int(a.resume_id.lstrip("Rr")) - 1
        clean = load_csv(RES_CLEAN_CSV)
        parsed = {"姓名": clean[k]["姓名"], "期望城市": clean[k]["期望城市"], "期望岗位": clean[k]["期望岗位"],
                  "最高学历": clean[k]["最高学历"], "工作年限": clean[k]["工作年限"],
                  "是否应届": clean[k]["是否应届"], "期望薪资下限(元/月)": clean[k]["期望薪资下限(元/月)"],
                  "期望薪资是否面议": clean[k]["期望薪资是否面议"], "专业": clean[k]["专业"],
                  "技能列表": clean[k]["技能列表"], "证书列表": clean[k]["证书列表"], "解析告警": ""}
    else:
        ap.print_help()
        return
    res = resume_record_from_parsed(parsed)
    res["期望岗位"] = parsed.get("期望岗位", "")
    t1 = time.time()
    recs, _ = match_jobs(idx, res, weights["权重"], a.top)
    print_table(res, recs, weights["版本"], len(idx), time.time() - t1)


if __name__ == "__main__":
    main()
