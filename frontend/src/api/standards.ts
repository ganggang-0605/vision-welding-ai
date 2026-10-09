/** 표준 용접 기준 API — 모든 워크스페이스가 공유하는 읽기 전용 공식 기준 */
import { apiFetch } from './client'
import type { WeldingStandard } from './types'

/** GET /welding-standards */
export function listWeldingStandards(signal?: AbortSignal): Promise<WeldingStandard[]> {
  return apiFetch<WeldingStandard[]>('/welding-standards', { signal })
}
