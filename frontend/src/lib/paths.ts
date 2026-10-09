/** 화면 URL 생성기. 링크는 문자열을 직접 조합하지 말고 여기서 만든다 (경로 파라미터 인코딩 포함). */
import { generatePath } from 'react-router'

/** 마지막으로 연 워크스페이스가 없을 때 처음 여는 워크스페이스 (백엔드 시드 데이터) */
export const DEFAULT_WORKSPACE_ID = 'demo'

/** 계정마다 따로 기억한다 (노션처럼 계정을 바꾸면 그 계정에서 보던 워크스페이스로). */
const lastWorkspaceKey = (accountId: string) => `vwa:last-workspace:${accountId}`

/** 그 계정이 마지막으로 연 워크스페이스 id. 없거나 브라우저 저장소를 못 쓰면 undefined. */
export function readLastWorkspaceId(accountId: string): string | undefined {
  try {
    return localStorage.getItem(lastWorkspaceKey(accountId)) ?? undefined
  } catch {
    return undefined
  }
}

export function rememberWorkspaceId(accountId: string, workspaceId: string): void {
  try {
    localStorage.setItem(lastWorkspaceKey(accountId), workspaceId)
  } catch {
    // 사파리 개인 정보 보호 모드 등: 기억하지 못해도 동작에는 문제없다.
  }
}

export type ProcessStage = 'vision' | 'context' | 'confidence'

type W = { workspaceId: string }
type P = W & { projectId: string }
type J = P & { jobId: string }

export const paths = {
  login: (mode?: 'add') => (mode ? `/login?mode=${mode}` : '/login'),
  newWorkspace: () => '/workspaces/new',
  workspaceHome: (workspaceId: string) => generatePath('/w/:workspaceId', { workspaceId } satisfies W),
  /** 설정 > 워크스페이스 > 일반 (이름·설명·개인/팀) */
  settings: (workspaceId: string) => generatePath('/w/:workspaceId/settings', { workspaceId } satisfies W),
  /** 설정 > 워크스페이스 > 멤버 (목록·초대) */
  members: (workspaceId: string) => generatePath('/w/:workspaceId/settings/members', { workspaceId } satisfies W),
  /** 설정 > 내 설정 > 환경설정 (화면 모드·글씨 크기, 모든 워크스페이스 공통) */
  preferences: (workspaceId: string) =>
    generatePath('/w/:workspaceId/settings/preferences', { workspaceId } satisfies W),
  symbols: (workspaceId: string) => generatePath('/w/:workspaceId/symbols', { workspaceId } satisfies W),
  standards: (workspaceId: string) => generatePath('/w/:workspaceId/standards', { workspaceId } satisfies W),
  newProject: (workspaceId: string) => generatePath('/w/:workspaceId/projects/new', { workspaceId } satisfies W),

  project: (workspaceId: string, projectId: string) =>
    generatePath('/w/:workspaceId/p/:projectId', { workspaceId, projectId } satisfies P),
  assemblyTree: (workspaceId: string, projectId: string) =>
    generatePath('/w/:workspaceId/p/:projectId/assembly-tree', { workspaceId, projectId } satisfies P),
  newJob: (workspaceId: string, projectId: string) =>
    generatePath('/w/:workspaceId/p/:projectId/jobs/new', { workspaceId, projectId } satisfies P),

  job: (workspaceId: string, projectId: string, jobId: string) =>
    generatePath('/w/:workspaceId/p/:projectId/jobs/:jobId', { workspaceId, projectId, jobId } satisfies J),
  jobReview: (workspaceId: string, projectId: string, jobId: string) =>
    generatePath('/w/:workspaceId/p/:projectId/jobs/:jobId/review', { workspaceId, projectId, jobId } satisfies J),
  /** 해석 과정: 1 시각 인식(vision) · 2 DB 기반 맥락 해석(context) · 3 신뢰도 산출(confidence). stage 를 빼면 1단계 */
  jobProcess: (workspaceId: string, projectId: string, jobId: string, stage?: ProcessStage) =>
    generatePath('/w/:workspaceId/p/:projectId/jobs/:jobId/process/:stage?', { workspaceId, projectId, jobId, stage }),
  jobSummary: (workspaceId: string, projectId: string, jobId: string) =>
    generatePath('/w/:workspaceId/p/:projectId/jobs/:jobId/summary', { workspaceId, projectId, jobId } satisfies J),
}
