// 接口数据类型（对照后端 src/api/schemas.py，一一对应）
// 数据来源：8,836 个真实岗位 / 500 份简历 / 8,852 张知识卡片

export interface ApiUser {
  id: number
  username: string
  role: 'jobseeker' | 'employer' | 'admin'
  role_label: string
  nickname: string
  phone: string
  email: string
  created_at: string
  last_login: string
}

export interface TokenResp {
  ok: boolean
  token: string
  expires_at: string
  用户: ApiUser
}

export interface ParsedResume {
  resume_id: string
  来源: string
  /** 解析出的原始正文（粘贴文本原样 / PDF 文本层）：用于保存成"我的简历" */
  原文?: string
  解析字段: Record<string, string | number>
  技能列表: string[]
  技能数: number
  证书列表: string[]
  未在词典的技能: string[]
  解析告警: string[]
}

/** 一条岗位推荐（六维分 + 推荐理由） */
export interface JobRec {
  排名: number
  总分: number
  技能: number
  经验: number
  学历: number
  地域: number
  薪资: number
  专业证书: number
  岗位ID: string
  岗位名称: string
  公司: string
  城市: string
  岗位薪资: string
  经验要求: string
  学历要求: string
  技能标签: string
  技能命中数: number
  岗位技能要求数: number
  余弦分: number
  距离km: number
  推荐理由: string
}

export interface MatchResp {
  ok: boolean
  简历摘要: {
    姓名: string
    期望城市: string
    学历序数: number
    工作年限: number
    技能数: number
    面议: boolean
    解析告警: string
  }
  权重版本: string
  权重: Record<string, number>
  推荐数: number
  打分范围: number
  耗时秒: number
  推荐: JobRec[]
  来源: string[]
  已存历史?: boolean
}

export interface ScoreResp {
  ok: boolean
  岗位: Record<string, string>
  规则口径: {
    总分: number
    六维分: Record<string, number>
    权重版本: string
    技能命中数: number
    岗位技能要求数: number
    'TF-IDF余弦': number
    距离km: number
  }
  模型口径: {
    可用: boolean
    T1回归_预测总分?: number
    T2分类_匹配概率?: number
    是否匹配?: boolean
    口径说明?: string
    原因?: string
  }
  差异: number | null
  来源: string[]
}

export interface ClusterRow {
  簇号: string
  簇名: string
  岗位数: number
  占比: string
  薪资中位数: string
  主导大类: string
  主要城市: string
}

export interface ClusterListResp {
  ok: boolean
  方案: string[]
  主方案: string
  簇数: number
  簇: ClusterRow[]
  各方案: Record<string, ClusterRow[]>
  来源: string[]
}

export interface ChatResp {
  ok: boolean
  问题: string
  回答: string
  来源: string[]
  工具轨迹: { 工具: string; 参数: unknown; 结果摘要: string; ok: boolean; 来源: string[] }[]
  工具序列: string
  轮数: number
  耗时秒: number
  tokens: { prompt: number; completion: number }
  prompt版本: string
  模型: string
  缓存命中: boolean
  /** 命中缓存时：该答案的生成时间（缓存 TTL 7 天，过期会自动重新真实调用） */
  缓存时间?: string
  服务耗时秒: number
  已存历史?: boolean
}

export interface ResumeRow {
  id: number
  title: string
  字数: number
  is_default: boolean
  created_at: string
  updated_at: string
  text: string
}

export interface FavoriteRow {
  id: number
  job_id: string
  job_name: string
  company: string
  city: string
  salary: string
  note: string
  created_at: string
}

export interface MatchHistoryRow {
  id: number
  created_at: string
  resume_title: string
  top_n: number
  summary: string
  推荐: { 排名: number; 总分: number; 岗位ID: string; 岗位名称: string; 公司: string; 城市: string; 岗位薪资: string }[]
}

export interface ChatHistoryRow {
  id: number
  created_at: string
  question: string
  answer: string
  sources: string[]
  tool_seq: string
}

export interface HealthResp {
  ok: boolean
  启动预加载耗时秒: Record<string, number>
  匹配引擎: { 就绪: boolean; 岗位数: number; 权重版本: string }
  RAG检索: { 就绪: boolean; 卡片数: number; 向量维度: number }
  评分模型: { 就绪: boolean; 特征维度: number; 模型: string[] }
  Agent: { 就绪: boolean; 说明: string }
  简历会话态: Record<string, unknown>
  进程运行秒: number
}
