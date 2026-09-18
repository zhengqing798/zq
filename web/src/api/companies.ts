import type { JobItem } from './jobs'

/** 公司浏览（公司页）类型 —— 与 `src/api/jobs.py` 的 company_* 接口一一对应 */

export interface NameCount { 名称: string; 数量: number }

export interface CompanyItem {
  公司ID: string
  公司名称: string
  在招岗位数: number
  /** 口径：用「在招职位数」分档代理（数据里没有公司规模列） */
  规模分档: string
  城市数: number
  主要城市: string
  城市列表: NameCount[]
  区县数: number
  主要大类: string
  岗位大类: NameCount[]
  技能需求: NameCount[]
  学历要求: NameCount[]
  经验要求: NameCount[]
  薪资下限中位数: number
  薪资上限中位数: number
  最高薪资上限: number
  招聘者: { 姓名: string; 职位: string; 回复文案: string; 回复数: number }[]
  招聘者数: number
  在线岗位数: number
  有回复岗位数: number
  今日回复总数: number
  来源关键词: NameCount[]
  热招职位: { 岗位ID: string; 岗位名称: string; 薪资: string; 城市: string; 区县: string }[]
}

export interface CompanyDetail extends CompanyItem {
  在招岗位: JobItem[]
  相似公司: CompanyItem[]
}

export interface CompanyListResp {
  ok: boolean
  总数: number
  页码: number
  每页: number
  总页数: number
  公司: CompanyItem[]
  来源: string[]
}

export interface CompanyStatsResp {
  ok: boolean
  总体: {
    公司总数: number
    在招岗位总数: number
    平均每司岗位数: number
    只招1个岗位的公司数: number
    在招10个以上的公司数: number
    城市数: number
    岗位数最多公司: string
    岗位数最多公司岗位数: number
    有回复活跃的公司数: number
  }
  规模分档: (NameCount & { 说明: string })[]
  按城市: NameCount[]
  按大类: NameCount[]
  热门企业: CompanyItem[]
  最活跃企业: CompanyItem[]
  筛选项: {
    城市: string[]
    大类: string[]
    规模分档: string[]
    排序: { value: string; label: string }[]
  }
  口径说明: string[]
  来源: string[]
}
