/** 해석 파이프라인 상태 API */
import { apiFetch } from './client'
import type { PipelineStatus } from './types'

/** GET /pipeline/status — OCR 모델·VLM provider·API 키 설정 여부 (.env 기준, 키 값은 오지 않음) */
export function getPipelineStatus(signal?: AbortSignal): Promise<PipelineStatus> {
  return apiFetch<PipelineStatus>('/pipeline/status', { signal })
}
