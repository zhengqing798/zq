/** 首页推荐（`GET /api/home`）类型 —— 与 `src/api/jobs.py::JobStore.home()` 对应 */
import type { NameCount } from './jobs'
import type { CompanyItem } from './companies'

export interface HomeJob {
  岗位ID: string
  岗位名称: string
  公司: string
  公司ID: string
  城市: string
  区县: string
  薪资: string
  薪资下限: number
  薪资上限: number
  岗位大类: string
  经验要求: string
  学历要求: string
  技能标签: string[]
  是否在线: number
  今日回复数: number
  回复文案: string
  招聘者: string
  招聘者职位: string
  同公司岗位数: number
}

export interface HomeCategory {
  分类: string
  岗位数: number
  在线岗位数: number
  公司数: number
  平均薪资上限: number
  热门技能: string[]
  示例岗位: HomeJob[]
}

export interface HomeRegion {
  城市: string
  省份: string
  岗位数: number
  公司数: number
  平均薪资上限: number
  在线岗位数: number
  热门区县: NameCount[]
}

export interface HomeResp {
  ok: boolean
  热门分类: HomeCategory[]
  地区推荐: HomeRegion[]
  高薪岗位: HomeJob[]
  热门岗位: HomeJob[]
  热门企业: CompanyItem[]
  热门技能: NameCount[]
  总体: {
    岗位数: number
    公司数: number
    城市数: number
    在线岗位数: number
    有回复岗位数: number
  }
  口径说明: string[]
  来源: string[]
}
