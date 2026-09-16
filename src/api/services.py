# -*- coding: utf-8 -*-
"""任务11 · 服务层：把已有的四类能力包成 API 可直接调用的函数

设计原则
--------
1. **不重新实现**：匹配复用 `match.py` 的 `JobIndex/match_jobs/score_pair`，检索与聚类复用
   `rag/query.py` 的 `Retriever`，对话复用 `agent.Agent`，工具类复用 `agent/tools.py`。
   这样 API 的口径与离线脚本、与 Agent 完全一致（不会出现"两套数"）。
2. **单例**：模型/索引/向量只加载一次，进程内复用（FastAPI 启动时预加载）。
3. **可溯源**：所有返回都带 `来源`，与项目"每个数字可溯源"的卖点一致。
4. **简历会话态用内存字典**（带 TTL 与条数上限）——**不引入数据库**，重启即失效，如实写在文档里。
"""
import os
import sys
import time
import uuid
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for p in (os.path.join(ROOT, "src", "agent"),
          os.path.join(ROOT, "src", "rag"),
          os.path.join(ROOT, "src", "models", "matching"),
          os.path.join(ROOT, "src", "models", "scoring"),
          HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

DIMS = ["技能", "经验", "学历", "地域", "薪资", "专业证书"]
RESUME_TTL = 2 * 3600          # 简历会话态保留 2 小时
RESUME_MAX = 200               # 最多缓存 200 份


class Services:
    """四类能力的统一入口（进程内单例）"""

    def __init__(self):
        self.t0 = time.time()
        self._matcher = None
        self._retriever = None
        self._agent = None
        self._fb = None
        self.resumes = {}          # resume_id -> {text, parsed, created}
        self.warm = {}             # 各组件的加载耗时

    # ------------------------------------------------ 懒加载单例
    def _tick(self, name, fn):
        t = time.time()
        out = fn()
        self.warm[name] = round(time.time() - t, 2)
        return out

    @property
    def matcher(self):
        if self._matcher is None:
            self._matcher = self._tick("matcher", lambda: self._build_matcher())
        return self._matcher

    def _build_matcher(self):
        import tools
        return tools._matcher()

    @property
    def retriever(self):
        if self._retriever is None:
            self._retriever = self._tick("retriever", lambda: self._build_retriever())
        return self._retriever

    def _build_retriever(self):
        from query import get_retriever
        return get_retriever()

    @property
    def agent(self):
        if self._agent is None:
            self._agent = self._tick("agent", lambda: self._build_agent())
        return self._agent

    def _build_agent(self):
        from agent import Agent
        return Agent(verbose=False)

    @property
    def features(self):
        if self._fb is None:
            self._fb = self._tick("features", lambda: self._build_fb())
        return self._fb

    def _build_fb(self):
        from score_features import PairFeatureBuilder
        return PairFeatureBuilder()

    def preload(self):
        """启动时预加载重型单例，避免首个请求等十几秒。

        匹配引擎与 RAG 检索是 /api/match、/api/chat 的必经之路，同步预加载；
        评分模型的特征构造器较重（要读 8,836 岗位并拟合 TF-IDF），放到**后台线程**预热，
        不阻塞服务启动；未就绪时 /api/score 会自动等待。
        """
        import threading
        self.matcher
        self.retriever
        threading.Thread(target=lambda: self.features, daemon=True).start()
        return self.warm

    # ------------------------------------------------ 简历会话态
    def _gc(self):
        now = time.time()
        for k in [k for k, v in self.resumes.items() if now - v["created"] > RESUME_TTL]:
            self.resumes.pop(k, None)
        if len(self.resumes) > RESUME_MAX:
            for k in sorted(self.resumes, key=lambda x: self.resumes[x]["created"])[:len(self.resumes) - RESUME_MAX]:
                self.resumes.pop(k, None)

    def put_resume(self, text, parsed):
        self._gc()
        rid = "rs_" + uuid.uuid4().hex[:12]
        self.resumes[rid] = {"text": text, "parsed": parsed, "created": time.time()}
        return rid

    def get_resume(self, rid):
        self._gc()
        return self.resumes.get(rid)

    # ------------------------------------------------ ① 简历解析
    def parse_resume(self, text=None, pdf_bytes=None, filename=None):
        _, _, _, parse_resume_text, _ = self.matcher
        warn = []
        if pdf_bytes:
            import parse_resume as PR
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            try:
                tmp.write(pdf_bytes)
                tmp.close()
                parsed = PR.parse_resume_pdf(tmp.name)
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
            raw_text = parsed.get("_原文", "")
            src = "PDF(%s, %d 页)" % (filename or "上传文件", parsed.get("PDF页数", 0))
        else:
            raw_text = text or ""
            parsed = parse_resume_text(raw_text)
            src = "粘贴文本"
        if parsed.get("解析告警"):
            warn.append(parsed["解析告警"])
        skills = [x for x in (parsed.get("技能列表") or "").split("、") if x]
        rid = self.put_resume(raw_text, parsed)
        return {
            "resume_id": rid,
            "来源": src,
            "解析字段": {k: parsed.get(k) for k in (
                "姓名", "期望岗位", "期望城市", "最高学历", "专业", "工作年限", "是否应届",
                "期望薪资", "期望薪资是否面议", "毕业院校", "毕业年份")},
            "技能列表": skills,
            "技能数": len(skills),
            "证书列表": [x for x in (parsed.get("证书列表") or "").split("、") if x],
            "未在词典的技能": [x for x in (parsed.get("技能列表_未在词典") or "").split("、") if x],
            "解析告警": warn,
        }

    # ------------------------------------------------ ② 人岗匹配
    def _resolve(self, resume_id=None, resume_text=None):
        """取简历记录（优先 resume_id，其次现解析文本）"""
        if resume_id:
            rec = self.get_resume(resume_id)
            if not rec:
                raise KeyError("resume_id 不存在或已过期（会话态保留 2 小时），请重新上传/粘贴简历")
            return rec["parsed"], rec["text"]
        if resume_text:
            _, _, _, parse_resume_text, _ = self.matcher
            return parse_resume_text(resume_text), resume_text
        raise ValueError("必须提供 resume_id 或 resume_text")

    def match(self, resume_id=None, resume_text=None, top_n=10):
        idx, match_jobs, w, _, to_record = self.matcher
        parsed, _ = self._resolve(resume_id, resume_text)
        res = to_record(parsed)
        t = time.time()
        recs, _ = match_jobs(idx, res, w["权重"], top_n=int(top_n))
        elapsed = round(time.time() - t, 3)
        return {
            "简历摘要": {"姓名": res["姓名"], "期望城市": res["城市"],
                     "学历序数": res["学历序数"], "工作年限": res["年限"],
                     "技能数": res["技能数"], "面议": res["面议"],
                     "解析告警": res.get("解析告警") or ""},
            "权重版本": w["版本"],
            "权重": w["权重"],
            "推荐数": len(recs),
            "打分范围": len(idx),
            "耗时秒": elapsed,
            "推荐": recs,
            "来源": ["任务6 人岗匹配（权重版本 %s）" % w["版本"],
                   "zhaopin_jobs_cleaned_seg.csv（%d 个岗位全量打分）" % len(idx)],
        }

    # ------------------------------------------------ ③ 评分（双口径）
    def score(self, job_id, resume_id=None, resume_text=None):
        """规则口径（六维加权，主）+ 模型口径（任务5 XGBoost，对照）"""
        idx, _, w, _, to_record = self.matcher
        parsed, _ = self._resolve(resume_id, resume_text)
        res = to_record(parsed)
        ji = int(str(job_id).upper().lstrip("J")) - 1
        if not (0 <= ji < len(idx)):
            raise IndexError("岗位ID 超出范围（有效范围 J0001 ~ J%04d）" % len(idx))
        import match as M
        cos = float(idx.sim.cosine(res["技能canon"], ji))
        total, dims, info = M.score_pair(idx, ji, res, w["权重"], cos)
        row = idx.rows[ji]

        # 模型口径
        model = {"可用": False}
        try:
            fb = self.features
            rctx = fb.resume_ctx_from_parsed(parsed)
            feats = fb.features(ji, rctx)
            model = {
                "可用": True,
                "特征": dict(zip(__import__("score_features").FEATURE_NAMES, feats)),
                "T1回归_预测总分": fb.predict(feats, "T1回归", "简历"),
                "T2分类_匹配概率": fb.predict(feats, "T2分类", "简历"),
                "是否匹配": fb.predict(feats, "T2分类", "简历") >= 65,
                "模型文件": "models/按简历_T1回归_best_XGBoost.joblib 等 4 个",
                "口径说明": "模型在任务5 用规则分作标签训练，故本质是对规则的蒸馏（任务8 实测 Spearman 0.9909）",
            }
        except Exception as e:                                   # 模型不可用不影响规则分
            model["原因"] = "%s: %s" % (type(e).__name__, e)

        return {
            "岗位": {"岗位ID": "J%04d" % (ji + 1), "岗位名称": row["岗位名称"],
                   "公司": row["公司名称"], "城市": (row["岗位地区"] or "").split()[0]
                   if (row["岗位地区"] or "").split() else "", "薪资": row["岗位薪资"],
                   "经验要求": row["经验要求"], "学历要求": row["学历要求"],
                   "技能标签": row["技能标签"]},
            "规则口径": {"总分": total, "六维分": dims, "权重版本": w["版本"],
                     "技能命中数": info["命中数"], "岗位技能要求数": info["要求数"],
                     "TF-IDF余弦": info["余弦"], "距离km": round(info["距离"], 1) if info["距离"] >= 0 else -1},
            "模型口径": model,
            "差异": (round(model["T1回归_预测总分"] - total, 2) if model.get("可用") else None),
            "来源": ["任务6 六维加权匹配（规则口径）",
                   "任务5 XGBoost 评分模型（模型口径，标签由规则生成）"],
        }

    # ------------------------------------------------ ④ 聚类画像 / 检索类工具
    def tool(self, tool_name, **kwargs):
        """直接复用 Agent 的工具实现，保证与对话口径一致"""
        import tools
        return tools.call_tool(tool_name, kwargs)

    def cluster_list(self):
        """任务7 聚类结果（按方案分组：K=9 主方案 / K=5 对照 / K=9 最大簇的二阶细分 K=8）"""
        import csv as _csv
        path = os.path.join(ROOT, "data", "processed", "岗位聚类_簇画像.csv")
        plans = {}
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in _csv.DictReader(f):
                plans.setdefault(r["方案"], []).append({
                    "簇号": r["簇号"], "簇名": r["簇名"], "岗位数": int(r["岗位数"]),
                    "占比": r["占比(%)"] + "%", "薪资中位数": r.get("薪资中位数(元)", ""),
                    "主导大类": r.get("主导大类", ""), "主要城市": r.get("主要城市", ""),
                })
        main_plan = next((k for k in plans if k.startswith("K=9")), list(plans)[0])
        return {
            "方案": list(plans),
            "主方案": main_plan,
            "簇数": len(plans[main_plan]),
            "簇": plans[main_plan],
            "各方案": plans,
            "来源": ["岗位聚类_簇画像.csv（任务7）", "岗位聚类_说明.md"],
        }

    # ------------------------------------------------ ⑤ 对话
    def chat(self, question, use_cache=True):
        t = time.time()
        rec = self.agent.ask(question, use_cache=use_cache)
        src = []
        for x in rec.get("tools", []):
            src += [s for s in (x.get("来源") or []) if s]
        tools = [{"工具": x["工具"], "参数": x.get("参数"), "结果摘要": x.get("结果摘要"),
                  "ok": x.get("ok"), "来源": x.get("来源") or []} for x in rec.get("tools", [])]
        return {
            "问题": question,
            "回答": rec["answer"],
            "来源": list(dict.fromkeys(src)),
            "工具轨迹": tools,
            "工具序列": " → ".join(x["工具"] for x in tools),
            "轮数": rec["rounds"], "耗时秒": rec["seconds"],
            "tokens": rec["tokens"], "prompt版本": rec["prompt_version"],
            "模型": rec["model"], "缓存命中": rec["cached"],
            "服务耗时秒": round(time.time() - t, 2),
        }

    # ------------------------------------------------ 健康检查
    def health(self):
        st = {"ok": True, "启动预加载耗时秒": self.warm,
              "简历会话态": {"在存": len(self.resumes), "TTL小时": RESUME_TTL / 3600,
                          "上限": RESUME_MAX, "持久化": "无（内存字典，重启失效）"}}
        try:
            idx, _, w, _, _ = self.matcher
            st["匹配引擎"] = {"就绪": True, "岗位数": len(idx), "权重版本": w["版本"]}
        except Exception as e:
            st["匹配引擎"] = {"就绪": False, "错误": str(e)}
            st["ok"] = False
        try:
            r = self.retriever
            st["RAG检索"] = {"就绪": True, "卡片数": len(r.cards), "向量维度": int(r.vecs.shape[1])}
        except Exception as e:
            st["RAG检索"] = {"就绪": False, "错误": str(e)}
            st["ok"] = False
        try:
            fb = self.features
            st["评分模型"] = {"就绪": True, "特征维度": 36,
                          "模型": sorted(os.listdir(os.path.join(ROOT, "models")))}
        except Exception as e:
            st["评分模型"] = {"就绪": False, "错误": str(e)}
        st["Agent"] = {"就绪": self._agent is not None,
                       "说明": "懒加载：首次调用 /api/chat 时构建"}
        st["进程运行秒"] = round(time.time() - self.t0, 1)
        return st


SVC = Services()
