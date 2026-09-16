# -*- coding: utf-8 -*-
"""任务11 · 单对(简历, 岗位)特征构造 —— 评分 API 的「模型口径」

背景
----
任务5 训练了 XGBoost 评分模型（4 个 .joblib），但 `build_features.py` 是**批量脚本**，
只能一次算 207,640 行，**没有"给一份简历 + 一个岗位、算 36 维特征"的入口**。
本模块把它的口径抽成可复用构造器，让评分 API 能在线上调模型。

口径来源（严格对齐，不新发明）
------------------------------
· 岗位侧特征  → 复刻 `build_features.py` 第 92–117 行
· 简历侧特征  → 复刻 `build_features.py` 第 124–145 行
· 文本相似度  → 复刻 `build_features.py` 第 150–159 行（同一组 TF-IDF 拟合语料 + 点积）
· 岗位技能要求数 / 技能命中数 → 复刻 `build_labels.py` 第 227/230/394/395 行
  （注意：`岗位技能要求数` 用的是**含描述补充词**的 J_main；`技能精确命中数` 用的是
    build_features 自己的 J_plain，两者定义不同，本模块分别保留、不混用）

验证
----
    python src/api/score_features.py --validate 30
用 30 份离线简历 × 它们各自在 `匹配特征_全量样本.csv` 里的配对，逐列比对本模块算出的 36 维
特征与离线表的差异（应完全一致）。这是"线上模型口径 = 离线训练口径"的证据。
"""
import argparse
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SCORING = os.path.join(ROOT, "src", "models", "scoring")
PREP = os.path.join(ROOT, "src", "preprocessing")
for p in (SCORING, PREP):
    if p not in sys.path:
        sys.path.insert(0, p)

from build_labels import (norm_skill, load_synonyms, build_blacklist, load_csv,  # noqa: E402
                          haversine, parse_exp, EDU_ORD, MAJOR_KW, CERT_TECH, CITY_LATLON)
from build_features import job_category, num, PROVINCE, CATS                # noqa: E402

P = os.path.join(ROOT, "data", "processed")
JOBS_CSV = os.path.join(P, "zhaopin_jobs_cleaned_seg.csv")
RES_CLEAN_CSV = os.path.join(P, "简历数据_cleaned.csv")
RES_SEG_CSV = os.path.join(P, "简历数据_seg.csv")
SYN_CSV = os.path.join(P, "技能同义词表.csv")
FEAT_CSV = os.path.join(P, "匹配特征_全量样本.csv")
MODEL_DIR = os.path.join(ROOT, "models")

# 36 维特征名（顺序必须与训练时完全一致）
FEATURE_NAMES = [
    "简历技能数", "岗位技能要求数", "技能命中数", "技能精确命中数", "岗位技能标签数",
    "岗位名称与期望岗位相似度", "描述与简历文本相似度", "描述与技能特长相似度", "专业命中岗位描述",
    "简历工作年限", "是否应届", "岗位经验下限", "岗位经验上限", "岗位经验不限", "岗位经验缺失",
    "简历学历序数", "岗位学历要求序数",
    "距离km", "是否同城", "是否同省", "岗位城市岗位数", "岗位城市简历数",
    "简历期望薪资下限", "期望薪资面议", "岗位薪资下限", "岗位薪资上限", "薪资上限与期望下限比",
    "技术认证数", "通用证书数", "技术认证方向命中数",
    "岗位大类", "期望岗位大类", "岗位大类一致",
    "今日回复数", "是否在线", "同公司岗位数",
]

_CITY_HINT = re.compile(r"(北京|上海|广州|深圳|杭州|宁波|苏州|南京|福州|厦门|泉州|漳州|"
                        r"嘉兴|金华|温州|绍兴|台州|湖州|丽水|舟山|无锡|常州|徐州|南通|扬州|"
                        r"镇江|合肥|芜湖|蚌埠|马鞍山|安庆|黄山|滁州|阜阳|莆田|宁德|南平|三明|龙岩)")


class PairFeatureBuilder:
    """把「一份简历 + 一个岗位」算成 36 维特征（与离线特征表同口径）"""

    def __init__(self, verbose=False):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.verbose = verbose
        self.jobs_raw = load_csv(JOBS_CSV)
        self.clean = load_csv(RES_CLEAN_CSV)
        self.seg = load_csv(RES_SEG_CSV)
        self.syn, _, _ = load_synonyms(SYN_CSV)
        self.black, self.indus, _ = build_blacklist(self.jobs_raw)
        self.pool_plain = {norm_skill(x) for s in self.seg
                           for x in (s["技能词"] or "").split("、") if x}

        # ---------------- 岗位侧（复刻 build_features 92–117 + build_labels 220–230）----------------
        self.job_rows = []
        for r in self.jobs_raw:
            parts = (r["岗位地区"] or "").strip().split()
            city = parts[0] if parts else ""
            tags = [t.strip() for t in (r["技能标签"] or "").split("|") if t.strip()]
            tnorm = [(t, norm_skill(t)) for t in tags]
            text = ((r["岗位名称"] or "") + " " + (r["职位描述"] or "")).lower()
            kind, lo, hi = parse_exp(r["经验要求"])
            desc_tokens = {norm_skill(t) for t in (r["描述分词"] or "").split() if t.strip()}
            desc_plain = {t for t in desc_tokens if t in self.pool_plain}
            desc_syn = {self.syn.get(t, t) for t in desc_plain}
            self.job_rows.append({
                "city": city, "province": PROVINCE.get(city, ""), "cat": job_category(r["岗位名称"]),
                "n_tags": len(tags),
                "edu": EDU_ORD.get((r["学历要求"] or "").strip(), -1),
                "exp_kind": kind, "exp_lo": lo if lo is not None else -1,
                "exp_hi": hi if hi is not None else -1,
                "sal_lo": num(r["薪资下限(元/月)"]), "sal_hi": num(r["薪资上限(元/月)"]),
                "kw": {k for kws in list(MAJOR_KW.values()) + list(CERT_TECH.values())
                       for k in kws if k in text},
                "reply": int(re.search(r"\d+", r["今日回复数"] or "").group())
                if re.search(r"\d+", r["今日回复数"] or "") else -1,
                "online": 1 if "在线" in (r["在线状态"] or "") else 0,
                "company": (r["公司名称"] or "").strip(),
                "name": (r["岗位名称"] or "").strip(),
                "desc_tokens": (r["描述分词"] or ""),
                # 精确命中口径（build_features 的 J_plain，不含描述补充词）
                "J_plain": {n for _, n in tnorm if n not in self.black and n not in self.indus},
                # 技能要求集合口径（build_labels 的 J_main，含描述补充词）
                "J": {self.syn.get(n, n) for _, n in tnorm
                      if n not in self.black and n not in self.indus} | desc_syn,
            })
        self.job_city_cnt = Counter(j["city"] for j in self.job_rows)
        self.comp_cnt = Counter(j["company"] for j in self.job_rows if j["company"])

        # ---------------- 简历侧（500 份离线，用于语料统计与 TF-IDF 拟合）----------------
        self.res_rows = [self._res_row(c, s) for c, s in zip(self.clean, self.seg)]
        self.res_city_cnt = Counter(r["city"] for r in self.res_rows)

        # ---------------- TF-IDF（与 build_features 同一拟合语料）----------------
        self.title_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), min_df=2)
        self.title_vec.fit([j["name"] for j in self.job_rows] +
                           [r["exp_pos"] for r in self.res_rows])
        self.text_vec = TfidfVectorizer(token_pattern=r"\S+", min_df=2)
        self.text_vec.fit([j["desc_tokens"] for j in self.job_rows] +
                          [r["text"] for r in self.res_rows])
        self.JT = self.title_vec.transform([j["name"] for j in self.job_rows])
        self.JD = self.text_vec.transform([j["desc_tokens"] for j in self.job_rows])
        if verbose:
            print("  PairFeatureBuilder 就绪：岗位 %d ｜ 简历 %d ｜ 词表 %d/%d"
                  % (len(self.job_rows), len(self.res_rows),
                     len(self.title_vec.vocabulary_), len(self.text_vec.vocabulary_)))

    # ---------------- 简历记录 ----------------
    def _res_row(self, c, s):
        skills_raw = [x for x in (s["技能词"] or "").split("、") if x]
        certs = [x for x in (s["证书"] or "").split("、") if x]
        return {
            "city": (c["期望城市"] or "").strip(), "cat": job_category(c["期望岗位"]),
            "years": int(c["工作年限"] or 0), "fresh": 1 if c["是否应届"] == "是" else 0,
            "edu": EDU_ORD.get((c["最高学历"] or "").strip(), 3),
            "sal_lo": num(c["期望薪资下限(元/月)"]),
            "nego": 1 if c["期望薪资是否面议"] == "是" else 0,
            "major": (c["专业"] or "").strip(),
            "n_skills": len(skills_raw),
            "skills_canon": {self.syn.get(norm_skill(x), norm_skill(x)) for x in skills_raw},
            "skills_plain": {norm_skill(x) for x in skills_raw},
            "n_cert_tech": sum(1 for x in certs if x in CERT_TECH),
            "n_cert_gen": sum(1 for x in certs if x not in CERT_TECH),
            "certs": certs,
            "cert_kw": {k for x in certs if x in CERT_TECH for k in CERT_TECH[x]},
            "major_kw": MAJOR_KW.get((c["专业"] or "").strip(), [(c["专业"] or "").strip().lower()]),
            "exp_pos": (c["期望岗位"] or "").strip(),
            "text": " ".join(x for x in [(s["项目经验_分词"] or ""), (s["工作经历_分词"] or ""),
                                         (s["个人简介_分词"] or "")] if x),
            "skill_text": (s["技能特长_分词"] or ""),
        }

    def resume_ctx_from_parsed(self, parsed):
        """把 parse_resume 的输出转成简历侧上下文（新粘贴简历走这条）"""
        skills_raw = [x for x in (parsed.get("技能列表") or "").split("、") if x]
        certs = [x for x in (parsed.get("证书列表") or "").split("、") if x]
        lo = str(parsed.get("期望薪资下限(元/月)") or "").strip()
        major = (parsed.get("专业") or "").strip()
        # 文本列在线分词（与离线 resume_seg 同一 jieba 词典：先补词典再切）
        seg = {}
        try:
            import jieba
            from resume_seg import tokenize
            dict_csv = os.path.join(P, "技能词典_匹配用.csv")
            if os.path.exists(dict_csv):
                for r in load_csv(dict_csv):
                    w = (r.get("技能") or "").strip()
                    if w:
                        jieba.add_word(w, freq=10 ** 7)
            for key, raw_key in (("skill_text", "技能特长"), ("proj", "项目经验"),
                                 ("work", "工作经历"), ("intro", "个人简介")):
                # tokenize 返回 list，需拼成空格分隔（与离线分词列同形）
                seg[key] = " ".join(tokenize(parsed.get(raw_key) or ""))
        except Exception:
            for key, raw_key in (("skill_text", "技能特长"), ("proj", "项目经验"),
                                 ("work", "工作经历"), ("intro", "个人简介")):
                seg[key] = " ".join((parsed.get(raw_key) or "").split())
        return {
            "city": (parsed.get("期望城市") or "").strip(),
            "cat": job_category(parsed.get("期望岗位")),
            "years": int(parsed.get("工作年限") or 0),
            "fresh": 1 if parsed.get("是否应届") == "是" else 0,
            "edu": EDU_ORD.get((parsed.get("最高学历") or "").strip(), 3),
            "sal_lo": int(lo) if lo.isdigit() else -1,
            "nego": 1 if parsed.get("期望薪资是否面议") == "是" else 0,
            "major": major,
            "n_skills": len(skills_raw),
            "skills_canon": {self.syn.get(norm_skill(x), norm_skill(x)) for x in skills_raw},
            "skills_plain": {norm_skill(x) for x in skills_raw},
            "n_cert_tech": sum(1 for x in certs if x in CERT_TECH),
            "n_cert_gen": sum(1 for x in certs if x not in CERT_TECH),
            "certs": certs,
            "cert_kw": {k for x in certs if x in CERT_TECH for k in CERT_TECH[x]},
            "major_kw": MAJOR_KW.get(major, [major.lower()]),
            "exp_pos": (parsed.get("期望岗位") or "").strip(),
            "text": " ".join(x for x in [seg.get("proj"), seg.get("work"), seg.get("intro")] if x),
            "skill_text": seg.get("skill_text", ""),
        }

    # ---------------- 单对特征 ----------------
    def features(self, job_i, res):
        j = self.job_rows[job_i]
        rt = self.title_vec.transform([res["exp_pos"] or ""])
        rd = self.text_vec.transform([res["text"] or ""])
        rs = self.text_vec.transform([res["skill_text"] or ""])
        sim_title = float(self.JT[job_i].multiply(rt).sum())
        sim_text = float(self.JD[job_i].multiply(rd).sum())
        sim_skill = float(self.JD[job_i].multiply(rs).sum())
        d = self._dist(res["city"], j["city"])
        vals = {
            "简历技能数": res["n_skills"], "岗位技能要求数": len(j["J"]),
            "技能命中数": len(res["skills_canon"] & j["J"]),
            "技能精确命中数": len(res["skills_plain"] & j["J_plain"]),
            "岗位技能标签数": j["n_tags"],
            "岗位名称与期望岗位相似度": round(sim_title, 4),
            "描述与简历文本相似度": round(sim_text, 4),
            "描述与技能特长相似度": round(sim_skill, 4),
            "专业命中岗位描述": 1 if any(k in j["kw"] for k in res["major_kw"]) else 0,
            "简历工作年限": res["years"], "是否应届": res["fresh"],
            "岗位经验下限": j["exp_lo"], "岗位经验上限": j["exp_hi"],
            "岗位经验不限": 1 if j["exp_kind"] == "unlimited" else 0,
            "岗位经验缺失": 1 if j["exp_kind"] == "missing" else 0,
            "简历学历序数": res["edu"], "岗位学历要求序数": j["edu"],
            "距离km": float(d) if d >= 0 else -1.0,
            "是否同城": 1 if res["city"] == j["city"] else 0,
            "是否同省": 1 if (j["province"] and j["province"] == PROVINCE.get(res["city"], "")) else 0,
            "岗位城市岗位数": self.job_city_cnt.get(j["city"], 0),
            "岗位城市简历数": self.res_city_cnt.get(j["city"], 0),
            "简历期望薪资下限": res["sal_lo"], "期望薪资面议": res["nego"],
            "岗位薪资下限": j["sal_lo"], "岗位薪资上限": j["sal_hi"],
            "薪资上限与期望下限比": round(j["sal_hi"] / res["sal_lo"], 3)
            if (j["sal_hi"] > 0 and res["sal_lo"] and res["sal_lo"] > 0) else -1.0,
            "技术认证数": res["n_cert_tech"], "通用证书数": res["n_cert_gen"],
            "技术认证方向命中数": sum(1 for x in res["certs"]
                                      if x in CERT_TECH and any(k in j["kw"] for k in CERT_TECH[x])),
            "岗位大类": CATS.index(j["cat"]), "期望岗位大类": CATS.index(res["cat"]),
            "岗位大类一致": 1 if j["cat"] == res["cat"] else 0,
            "今日回复数": j["reply"], "是否在线": j["online"],
            "同公司岗位数": self.comp_cnt.get(j["company"], 0),
        }
        return [vals[n] for n in FEATURE_NAMES]

    _dist_cache = {}

    def _dist(self, a, b):
        if not a or not b:
            return -1.0
        if a == b:
            return 0.0
        k = (a, b)
        if k not in self._dist_cache:
            self._dist_cache[k] = haversine(a, b) if (a in CITY_LATLON and b in CITY_LATLON) else -1.0
        return self._dist_cache[k]

    # ---------------- 模型加载与预测 ----------------
    _MODELS = {}

    def model_path(self, task, group):
        return os.path.join(MODEL_DIR, "按%s_%s_best_XGBoost.joblib" % (group, task))

    def predict(self, feats, task="T1回归", group="简历"):
        """task: T1回归(预测总分) / T2分类(是否匹配)。group: 简历(主口径) / 岗位"""
        import joblib
        key = (task, group)
        if key not in self._MODELS:
            self._MODELS[key] = joblib.load(self.model_path(task, group))
        m = self._MODELS[key]
        X = np.asarray([feats], dtype=float)
        if task == "T1回归":
            return round(float(m.predict(X)[0]), 2)
        p = float(m.predict_proba(X)[0][1])
        return round(p * 100, 2)

    def sha(self):
        import hashlib
        h = hashlib.md5()
        for p in sorted(os.listdir(MODEL_DIR)):
            h.update(p.encode())
            h.update(open(os.path.join(MODEL_DIR, p), "rb").read())
        return h.hexdigest()[:12]


# ---------------------------------------------------------------- 自验证
def validate(n_resumes=30):
    """用离线简历复算特征，与 匹配特征_全量样本.csv 逐列比对"""
    from build_labels import load_csv as _lc
    b = PairFeatureBuilder(verbose=True)
    table = _lc(FEAT_CSV)
    by_res = defaultdict(list)
    for r in table:
        by_res[r["简历ID"]].append(r)
    ids = sorted(by_res)[:n_resumes]
    print("\n验证：%d 份离线简历 × 其全部候选配对，逐列比对 36 维特征" % len(ids))
    diff_cols = Counter()
    total = same = 0
    for rid in ids:
        res = b.res_rows[int(rid[1:]) - 1]
        for r in by_res[rid]:
            ji = int(r["岗位ID"][1:]) - 1
            got = b.features(ji, res)
            for name, g in zip(FEATURE_NAMES, got):
                total += 1
                exp = r[name]
                try:
                    e = float(exp) if str(exp).strip() != "" else None
                except ValueError:
                    e = None
                if e is None or abs(float(g) - e) > 1e-6:
                    diff_cols[name] += 1
                else:
                    same += 1
    print("  比对单元格：%d ｜ 一致：%d（%.4f%%）" % (total, same, 100.0 * same / max(total, 1)))
    if diff_cols:
        print("  ⚠️ 有差异的列：")
        for k, v in diff_cols.most_common():
            print("     %-22s 差异 %d 处" % (k, v))
    else:
        print("  ✅ 36 维特征与离线特征表完全一致（线上模型口径 = 离线训练口径）")
    return not diff_cols


def main():
    ap = argparse.ArgumentParser(description="单对特征构造器自检")
    ap.add_argument("--validate", type=int, metavar="N", help="用 N 份离线简历验证一致性")
    a = ap.parse_args()
    if a.validate:
        ok = validate(a.validate)
        sys.exit(0 if ok else 1)
    b = PairFeatureBuilder(verbose=True)
    res = b.res_rows[0]
    f = b.features(0, res)
    print("\n示例：简历 R001 × 岗位 J0001")
    for n, v in zip(FEATURE_NAMES, f):
        print("   %-22s %s" % (n, v))
    print("\n模型预测（简历口径）：T1 回归总分 = %s ｜ T2 匹配概率 = %s%%"
          % (b.predict(f, "T1回归"), b.predict(f, "T2分类")))


if __name__ == "__main__":
    main()
