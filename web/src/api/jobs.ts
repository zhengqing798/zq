// 岗位浏览（首页）类型
export interface JobItem {
  岗位ID: string
  岗位名称: string
  公司: string
  城市: string
  区县: string
  省份: string
  地区: string
  薪资: string
  薪资下限: number
  薪资上限: number
  经验要求: string
  学历要求: string
  技能标签: string[]
  技能标签原文: string
  职位描述?: string
  岗位大类: string
  一级簇名: string
  二级簇名: string
  今日回复数: number
  是否在线: number
  /** 模拟 BOSS直聘「招聘者」行所需字段（全部来自真实数据） */
  招聘者: string
  招聘者职位: string
  在线状态: string
  回复文案: string
  来源关键词: string
  同公司岗位数: number
}

export interface JobListResp {
  ok: boolean
  总数: number
  页码: number
  每页: number
  总页数: number
  岗位: JobItem[]
  来源: string[]
}

export interface NameCount { 名称: string; 数量: number }

export interface JobStatsResp {
  ok: boolean
  总体: {
    岗位总数: number
    公司数: number
    城市数: number
    省份数: number
    平均薪资上限: number
    薪资下限中位数: number
    薪资上限中位数: number
    在线岗位数: number
    区县数: number
    有招聘者职位数: number
    有回复数据岗位数: number
  }
  按城市: NameCount[]
  按大类: NameCount[]
  按学历: NameCount[]
  按经验: NameCount[]
  按簇: NameCount[]
  热门技能: NameCount[]
  热门搜索: NameCount[]
  按城市区县: Record<string, NameCount[]>
  分类导航: { 大类: string; 数量: number; 子职位: NameCount[] }[]
  筛选项: {
    城市: string[]
    大类: string[]
    学历: string[]
    省份: string[]
    排序: { value: string; label: string }[]
  }
  来源: string[]
}
