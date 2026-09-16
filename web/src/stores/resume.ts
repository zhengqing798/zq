import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { MatchResp, ParsedResume } from '../api/types'

/**
 * 跨页面共享的"本次简历"状态：简历页解析 → 职位推荐页匹配。
 * 也可来自个人中心保存的简历（savedId）。
 */
export const useResumeStore = defineStore('resume', () => {
  const resumeId = ref<string>('')            // 会话 ID（后端内存态）
  const text = ref<string>('')                 // 简历正文
  const parsed = ref<ParsedResume | null>(null)
  const savedId = ref<number | null>(null)     // 个人中心里保存的简历 id
  const savedTitle = ref<string>('')
  const matchResult = ref<MatchResp | null>(null)

  function setParsed(p: ParsedResume, raw: string) {
    parsed.value = p
    resumeId.value = p.resume_id
    text.value = raw
    savedId.value = null
    savedTitle.value = ''
  }
  function useSaved(id: number, title: string, body: string) {
    savedId.value = id
    savedTitle.value = title
    text.value = body
    resumeId.value = ''
    parsed.value = null
  }
  function canMatch() {
    return !!resumeId.value || !!savedId.value || !!text.value
  }

  return { resumeId, text, parsed, savedId, savedTitle, matchResult, setParsed, useSaved, canMatch }
})
