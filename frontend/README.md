# Frontend

Vision Welding AI 웹 프론트엔드입니다. 작업자가 휴대폰으로 접속해 부재 마킹을 촬영·업로드하고, 분석 결과를 확인·승인한 뒤 로봇용 JSON으로 내보내는 UI입니다.

지금은 **워크스페이스 기반 라우팅 + 노션형 구조에 애플 시스템 앱 느낌의 화면** 단계입니다.
모든 화면(와이어프레임 0~7)의 자리와 API 연결이 잡혀 있고, 화면마다 실제 API 데이터를 최소한으로 보여 줍니다. 디자인·세부 기능은 이 위에 채워 나가면 됩니다.

## 스택

- [React](https://react.dev/) 19 + [TypeScript](https://www.typescriptlang.org/)
- [React Router](https://reactrouter.com/) 8 — 데이터 라우터(`createBrowserRouter` + `RouterProvider`)
- [Vite](https://vite.dev/) 8 (`npm create vite@latest -- --template react-ts` 공식 템플릿 기반)
- [Oxlint](https://oxc.rs/docs/guide/usage/linter): 현재 Vite 공식 템플릿의 기본 린터
- 스타일: 순수 CSS (CSS 변수 디자인 토큰 + CSS Modules). UI 키트·상태 관리·CSS 프레임워크는 쓰지 않습니다. 디자인 원칙은 `src/index.css` 맨 위 주석 참고
- 아이콘: [Phosphor Icons](https://phosphoricons.com/) (`@phosphor-icons/react`) 한 종류만 씁니다. 크기·굵기 기본값은 `main.tsx`의 `IconContext`
- 패키지 매니저: **npm** (`package-lock.json` 커밋함)
- Node.js **22.22 이상** (React Router 8 요구 사항, CI는 Node 24)

## 실행 방법

**백엔드를 먼저 실행**해야 프론트엔드에서 API를 호출할 수 있습니다.

```bash
# 1) 백엔드 (터미널 1) — :8000  (자세한 설정은 루트 README의 '시작하기' 참고)
cd backend
python3 -m venv .venv && source .venv/bin/activate   # 처음 한 번만 생성, 이후엔 activate만
pip install -r requirements.txt
uvicorn app.main:app --reload

# 2) 프론트엔드 (터미널 2) — :5173
cd frontend
npm install
npm run dev
```

브라우저에서 <http://localhost:5173>을 열면 데모 워크스페이스(`/w/demo`)로 이동합니다.
백엔드가 꺼져 있으면 사이드바 아래에 **서버에 연결할 수 없어요**가 뜹니다. 백엔드를 켠 뒤 **다시 확인**을 누르면 됩니다 (정상일 때는 아무것도 표시하지 않습니다).

> 데모 데이터(워크스페이스 `demo`, 작업 3개)는 백엔드가 시작할 때 메모리에 올립니다. 화면에서 승인·추가·삭제한 내용은 백엔드를 재시작하면 처음 상태로 돌아갑니다.

## 라우트

노션처럼 **워크스페이스 → 프로젝트(블록) → 작업** 순서로 들어갑니다.

- **워크스페이스**: 개인(기본값) 또는 팀. 개인 워크스페이스에 팀원을 초대하면 팀 워크스페이스로 바뀝니다. 문자·기호 사전과 멤버가 워크스페이스에 속합니다.
- **프로젝트**: 블록 하나 (배 전체가 아닐 수도 있는 조립 단위). 조립 트리와 작업이 프로젝트에 속합니다.
- **표준 용접 기준**: 모든 워크스페이스가 함께 쓰는 공통(읽기 전용) 데이터.

| 경로 | 페이지 (`src/pages/`) | 와이어프레임 | 내용 |
| --- | --- | --- | --- |
| `/` | | | 지금 계정이 마지막으로 연 워크스페이스로 리다이렉트 (처음이면 `/w/demo`, 계정이 없으면 `/login`) |
| `/login` (`?mode=add`) | `LoginPage` | | 계정 고르기·계정 추가하기. 로그인 전까지 비밀번호 없이 데모 계정(`GET /users`) 중 하나로 들어감 |
| `/workspaces/new` | `NewWorkspacePage` | 0 워크스페이스 만들기 | 1단계 혼자 / 팀과 함께(기본값 개인) → 2단계 이름·설명·사전 시작 방식. 팀이면 만든 뒤 멤버 초대로 이동. **사이드바 없는 단독 화면** |
| `/w/:workspaceId` | `WorkspaceHomePage` | 1 워크스페이스 홈 | 프로젝트(블록) 타일, 확인이 필요한 작업, 최근 작업. 개인이면 팀원 초대 안내 |
| (모달, ⌘K / Ctrl+K) | `components/SearchDialog` | 2 검색 | 워크스페이스의 모든 프로젝트에서 작업 검색, Enter로 첫 결과 열기, Esc로 닫기 |
| `/w/:workspaceId/settings/preferences` | `PreferencesPage` | | 설정 > **내 설정 > 환경설정**: 계정(추가·로그아웃), 화면 모드(시스템/라이트/다크), 글씨 크기. 모든 워크스페이스 공통, 이 브라우저에만 저장 |
| `/w/:workspaceId/settings` | `WorkspaceGeneralPage` | | 설정 > **워크스페이스 > 일반**: 이름·설명, 사용 방식(개인/팀) |
| `/w/:workspaceId/settings/members` | `WorkspaceMembersPage` | | 설정 > **워크스페이스 > 멤버**: 목록·초대 (개인이면 초대 시 팀으로 전환) |
| `/w/:workspaceId/symbols` | `SymbolsPage` | 3a 문자·기호 사전 | 사전 표 + 항목 추가·삭제 (워크스페이스 공통) |
| `/w/:workspaceId/standards` | `WeldingStandardsPage` | 3c 용접 기준 (공통) | 표준 용접 기준 표 (읽기 전용) |
| `/w/:workspaceId/projects/new` | `NewProjectPage` | | 새 프로젝트(블록) |
| `/w/:workspaceId/p/:projectId` | `ProjectPage` | 1 작업 목록 | 확인 필요 안내 + 작업 목록 (이름·조립 경로·상태·용접 조건·신뢰도·날짜), 상태 필터(`?status=`) |
| `/w/:workspaceId/p/:projectId/assembly-tree` | `AssemblyTreePage` | 3b 조립 트리 | 이 블록의 조립 경로 (블록 → 대조립 → 중조립 → 소조립 → 부재) |
| `/w/:workspaceId/p/:projectId/jobs/new` | `NewJobPage` | 4 현장 촬영 = 새 작업 | 모바일 촬영(`<input type="file" accept="image/*" capture="environment">`) → 작업 생성 → 업로드 → 해석 |
| `/w/:workspaceId/p/:projectId/jobs/:jobId` | `JobResultPage` | 5 해석 결과 | 인식한 표기, 신뢰도, 추천 용접 조건, 판단 근거. 해석 전이면 '해석 시작' |
| `/w/:workspaceId/p/:projectId/jobs/:jobId/review` | `JobReviewPage` | 6 작업자 확인 | 확인할 항목, 맥락 덧붙여 다시 해석 / 직접 입력 |
| `/w/:workspaceId/p/:projectId/jobs/:jobId/summary` | `JobSummaryPage` | 7 요약본·JSON 내보내기 | 요약 → 승인 → 로봇 연계 JSON 미리보기·복사·내보내기 (승인 전이면 안내) |
| `*` | `NotFoundPage` | | 없는 주소. 워크스페이스 안(`/w/demo/...`)이면 사이드바를 유지한 채 표시 |

- `/w/:workspaceId/*` 화면은 모두 `layouts/WorkspaceLayout`(사이드바 + `<Outlet />`) 안에서 그려집니다. 레이아웃이 워크스페이스·프로젝트 목록·현재 사용자를 불러온 뒤 페이지를 그리므로, 페이지에서는 `useWorkspace()` / `useWorkspaceContext()`로 바로 꺼내 씁니다.
- `/w/:workspaceId/p/:projectId/*` 화면은 `layouts/ProjectLayout`이 주소의 프로젝트를 찾아 넘깁니다 (`useProject()`). 없는 프로젝트면 '찾을 수 없음' 화면을 보여 줍니다.
- 작업 화면 5·6·7은 `components/JobFrame`(작업 불러오기 + 위치·제목·상태 + 화면 전환 세그먼트)을 함께 씁니다. 주소의 프로젝트와 작업의 프로젝트가 다르면 맞는 주소로 옮깁니다.
- 라우트 정의는 `src/router.ts`, 화면 URL 생성은 `src/lib/paths.ts`(`paths.job(workspaceId, projectId, jobId)` 등)를 씁니다. 링크 문자열을 직접 조합하지 마세요.
- 사진 올리기·해석·작업자 확인은 백엔드 `app/pipeline.py`(1·2·3단계 패키지 통합)와 연결돼 있습니다. 해석 결과 화면의 **사진**(`components/JobPhotos`)에서 사진 추가·해석 시작·다시 해석을 하고, `components/PhotoAnnotations`가 1단계가 찾은 글자·기호 위치(`Analysis.vision`의 bbox)를 사진 위 박스로 보여 줍니다 (확률 80% 미만은 주황). 단계 패키지에 실제 모델이 아직 없으면 찾은 것이 없어 '확인 필요'가 됩니다.

### 사이드바 (노션 사이드바 구성)

- 맨 위 **워크스페이스 전환 메뉴** (노션과 같은 구성): 지금 워크스페이스, 설정·팀원 초대·계정 추가하기, 로그인한 **계정마다** 워크스페이스 목록과 새 워크스페이스, 모든 계정에서 로그아웃. 다른 계정의 워크스페이스를 누르면 그 계정으로 바뀝니다.
  - 로그인한 계정 목록과 지금 계정은 `src/lib/accounts.ts`가 브라우저에 저장하고, API 요청마다 `X-User-Id` 헤더로 보냅니다 (TODO 인증: 실제 로그인 세션으로 교체).
- 검색 ⌘K, 홈
- **작업**: 블록 목록. 펼치면 작업 목록·조립 트리. 보고 있는 블록은 자동으로 펼쳐집니다. 제목 옆 `+`로 새 블록.
- **워크스페이스**: 문자·기호 사전, 용접 기준, 설정 (`layouts/SettingsLayout`: 왼쪽에 내 설정 / 워크스페이스 묶음)
- 맨 아래 팀원 초대, 서버 연결이 끊겼을 때만 뜨는 안내

현재 화면 링크는 `NavLink`가 `aria-current="page"`를 붙여 강조합니다. 데스크톱에서는 사이드바 위쪽의 닫기 버튼(마우스를 올리면 보임)이나 **⌘\\ / Ctrl+\\**로 사이드바를 접고 펼 수 있고, 접은 상태는 브라우저에 기억합니다. **768px 미만**에서는 사이드바가 상단 바의 메뉴 버튼 뒤로 접힙니다.

## API 클라이언트

백엔드 API 계약을 그대로 옮겨 둔 타입과 함수가 `src/api/`에 있습니다. **계약이 바뀌면 `types.ts`부터 고칩니다.**

| 파일 | 내용 |
| --- | --- |
| `api/client.ts` | `apiFetch<T>()`, `ApiError`(`status`, `detail`), `isApiError(err, 501)`, `jsonInit()`, 경로 인코딩 태그 `apiPath`, `getHealth()` |
| `api/types.ts` | 계약 모델 — `User`, `Member`, `Workspace`(`kind`, `member_count`), `Project`, `SymbolEntry`, `AssemblyNode`, `Job`(`project_id`), `RobotOutput` … (필드명 snake_case, id는 문자열) |
| `api/users.ts` | `getMe` · `listUsers` (로그인 전까지 데모 계정). 다른 계정으로 보낼 때는 `client.ts`의 `asUser(userId)` |
| `api/workspaces.ts` | `listWorkspaces` · `createWorkspace` · `getWorkspace` · `updateWorkspace` · `listMembers` · `inviteMember` · `listSymbols` · `createSymbol` · `updateSymbol` · `deleteSymbol` |
| `api/projects.ts` | `listProjects` · `createProject` · `getProject` · `getAssemblyTree(workspaceId, projectId)` |
| `api/jobs.ts` | `listJobs(workspaceId, { q, status, project_id })` · `createJob` · `getJob` · `uploadJobImage`(FormData) · `listJobImages` · `jobImageUrl` · `analyzeJob` · `listAnalyses` · `reviewJob` · `approveJob` · `exportJob` |
| `api/standards.ts` | `listWeldingStandards` (공통) |

- 모든 함수의 마지막 인자는 선택 `signal?: AbortSignal`입니다. 경로 파라미터는 `encodeURIComponent`로 인코딩됩니다.
- 2xx가 아니면 `ApiError`를 던집니다. FastAPI 오류 본문의 `detail`이 문자열이면 그대로 `message`가 됩니다.
- 화면용 오류 문장은 `lib/errors.ts`의 `errorMessage(err)`, 공통 표시는 `components/Notice`의 `<ErrorNotice error={err} />`(501은 경고 톤)를 씁니다.

### 데이터 불러오기 — `useAsync`

데이터 라이브러리 없이 작은 훅 하나(`src/hooks/useAsync.ts`)로 로딩·오류 상태를 관리합니다.
deps가 바뀌거나 화면을 벗어나면 이전 요청은 `AbortSignal`로 취소됩니다.

```tsx
import { listJobs } from '../api/jobs'
import { AsyncView } from '../components/AsyncView'
import { useAsync } from '../hooks/useAsync'
import { useWorkspace } from '../hooks/useWorkspace'

export function ExamplePage() {
  const workspace = useWorkspace()
  const jobs = useAsync((signal) => listJobs(workspace.id, { status: 'needs_review' }, signal), [workspace.id])

  // 로딩·오류(다시 시도 버튼)·빈 상태는 AsyncView 가 공통 모양으로 그린다.
  return (
    <AsyncView state={jobs} isEmpty={(list) => list.length === 0} empty="작업이 없습니다.">
      {(list) => <ul>{list.map((job) => <li key={job.id}>{job.name}</li>)}</ul>}
    </AsyncView>
  )
}
```

- `jobs.reload()`: 같은 조건으로 다시 불러오기 (추가·삭제·승인 후).
- `<AsyncView keepPreviousData>`: 다시 불러오는 동안 직전 데이터를 유지해 화면 깜빡임·폼 상태를 지킵니다.
- 저장·삭제 같은 동작은 이벤트 핸들러에서 `await createJob(...)`처럼 직접 호출하고 `try/catch`로 오류를 상태에 담습니다 (`NewJobPage`, `JobSummaryPage` 참고).
- 501 여부는 `isApiError(err, 501)`로 확인합니다.

## 스타일

- `src/index.css`: 디자인 토큰(CSS 변수)과 여러 화면이 같이 쓰는 클래스 — `.page`, `.page-header`, `.btn`, `.table`, `.pill`, `.notice`, `.tabs`, `.props`, `.form`/`.field`/`.input` 등.
- 컴포넌트 전용 스타일은 `*.module.css` (예: `layouts/WorkspaceLayout.module.css`, `components/SearchDialog.module.css`).
- 디자인 토큰 (라이트 테마 기준):

  | 토큰 | 값 | 용도 |
  | --- | --- | --- |
  | `--text` / `--text-secondary` / `--text-muted` | `#37352F` / `#5F5E5B` / `#73726E` | 본문 / 보조 / 흐린 글자 |
  | `--sidebar-bg` / `--border` / `--hover` | `#F7F7F5` / `#E9E9E7` / `#EBEBE9` | 사이드바 / 구분선 / 호버 |
  | `--accent` | `#0B6BCB` | 링크·주요 버튼·포커스 |
  | `--warning-bg` / `--warning-text` | `#FAEBDD` / `#8A3F05` | 확인 필요, 501 안내 |
  | `--info-bg` / `--info-text` | `#E7F0FA` / `#0B4F94` | 승인 대기, 안내 |

  글꼴은 `'Noto Sans KR', system-ui`입니다 (웹폰트는 불러오지 않고 기기에 설치된 글꼴을 씁니다).
- 다크 모드는 시안이 없어 대비만 맞춘 대체 팔레트(`prefers-color-scheme: dark`)를 둡니다.

## API 프록시

개발 서버(`vite.config.ts`)는 `/api/*`로 들어온 요청에서 `/api`를 떼고 백엔드로 넘깁니다.

```
브라우저 → http://localhost:5173/api/workspaces/demo/jobs
Vite    → http://localhost:8000/workspaces/demo/jobs
```

- 프론트엔드 코드에서는 `src/api/`의 함수(또는 `apiFetch('/health')`)로 호출하면 `/api/...`가 자동으로 붙습니다.
- 같은 출처(origin)로 요청하므로 백엔드에 CORS 설정이 필요 없습니다.
- 백엔드 리다이렉트의 `Location`도 프록시가 `/api/...`로 바꿔 줍니다. 예: `/api/workspaces/` 요청 시 FastAPI의 끝 슬래시 리다이렉트 `http://localhost:8000/workspaces` → `/api/workspaces`. 그래서 리다이렉트된 요청도 프록시를 거칩니다.
- 기본 경로를 바꿔야 할 때는 `.env.example`을 `.env.local`로 복사해 `VITE_API_BASE_URL`을 수정합니다.
  백엔드 주소(예: `http://localhost:8000`)를 직접 넣으면 프록시를 거치지 않으므로, 이때는 백엔드에 CORS 설정이 필요합니다.

## 휴대폰에서 접속하기

`server.host: true` 설정으로 개발 서버가 같은 네트워크의 다른 기기에도 열려 있습니다.

1. PC와 휴대폰을 **같은 Wi‑Fi**에 연결합니다.
2. `npm run dev`를 실행하면 터미널에 `Network: http://<PC IP>:5173/` 주소가 표시됩니다.
   (macOS에서 직접 확인: `ipconfig getifaddr en0`)
3. 휴대폰 브라우저에서 `http://<PC IP>:5173`을 엽니다. **새 작업** 화면의 사진 영역을 누르면 카메라가 열립니다.

API 요청도 Vite 프록시를 거쳐 PC의 `localhost:8000`으로 전달되므로, 백엔드는 기본 설정(`127.0.0.1`)으로 실행해도 됩니다.
접속이 안 되면 macOS 방화벽에서 Node 들어오는 연결을 허용했는지, 공용·게스트 Wi‑Fi처럼 기기 간 통신을 막는 네트워크가 아닌지 확인하세요.

> 휴대폰 카메라 API(`getUserMedia`)는 HTTPS 또는 localhost에서만 동작합니다. 지금처럼 `<input type="file" accept="image/*" capture>`로 촬영하는 방식은 HTTP에서도 동작합니다.

## 스크립트

| 명령 | 설명 |
| --- | --- |
| `npm run dev` | 개발 서버 실행 (`:5173`, HMR, `/api` 프록시) |
| `npm run build` | 타입 체크(`tsc -b`) 후 `dist/`에 프로덕션 빌드 |
| `npm run lint` | Oxlint 검사 (경고도 실패 처리: `--deny-warnings`) |
| `npm run preview` | 빌드 결과물을 로컬에서 미리보기 (`/api` 프록시 동일하게 적용) |

CI(GitHub Actions)에서는 `frontend/`에서 `npm ci → npm run lint → npm run build` 순서로 실행합니다.

> 프로덕션 빌드를 정적 호스팅에 올릴 때는 모든 경로(`/w/...`)를 `index.html`로 돌려주는 SPA fallback 설정이 필요합니다. (`npm run dev`·`npm run preview`는 자동 처리)

## 폴더 구조

```
frontend/
├── index.html                # HTML 진입점 (lang="ko", 모바일 viewport)
├── vite.config.ts            # 개발 서버·프록시 설정
├── .env.example              # VITE_API_BASE_URL 예시
├── public/                   # 정적 파일 (favicon)
└── src/
    ├── main.tsx              # React 진입점 (RouterProvider)
    ├── router.ts             # 라우트 정의 (createBrowserRouter)
    ├── index.css             # 디자인 토큰 + 공통 클래스
    ├── env.d.ts              # import.meta.env 타입
    ├── api/                  # 백엔드 API 계약 타입 + 호출 함수
    │   ├── client.ts         #   apiFetch, ApiError, apiPath, getHealth
    │   ├── types.ts          #   계약 모델 (snake_case)
    │   ├── workspaces.ts     #   워크스페이스 · 문자/기호 사전 · 조립 트리
    │   ├── jobs.ts           #   작업 (검색·생성·업로드·분석·확인·승인·내보내기)
    │   └── standards.ts      #   표준 용접 기준 (공통)
    ├── hooks/
    │   ├── useAsync.ts       #   로딩·오류 상태 훅
    │   ├── useWorkspace.ts   #   현재 워크스페이스·프로젝트 목록·사용자 (레이아웃 Outlet context)
    │   ├── useProject.ts     #   현재 프로젝트(블록)
    │   ├── useRequiredParam.ts
    │   ├── useDebouncedValue.ts
    │   └── useObjectUrl.ts   #   사진 미리보기 URL
    ├── layouts/
    │   ├── WorkspaceLayout.tsx (+ .module.css)   # 사이드바(프로젝트 트리) + Outlet
    │   ├── ProjectLayout.tsx                     # 주소의 프로젝트를 찾아 넘김
    │   └── SettingsLayout.tsx (+ .module.css)    # 설정: 내 설정 / 워크스페이스 왼쪽 목록
    ├── components/
    │   ├── AsyncView.tsx     #   로딩·오류·빈 상태 공통 표시
    │   ├── BackendStatus.tsx #   서버 연결이 끊겼을 때만 사이드바 하단에 안내
    │   ├── JobFrame.tsx      #   작업 화면 5·6·7 공통 틀
    │   ├── JobList.tsx (+ .module.css)           # 메일 앱 같은 작업 목록
    │   ├── JobNav.tsx        #   작업 화면 전환 (세그먼트 컨트롤)
    │   ├── Notice.tsx        #   Notice, ErrorNotice
    │   ├── PageHeader.tsx    #   페이지 제목·설명 (+ 브라우저 탭 제목)
    │   ├── SearchDialog.tsx (+ .module.css)      # 검색 ⌘K 모달
    │   ├── StatusLabel.tsx   #   작업 상태 글자 (확인 필요만 주황)
    │   └── WorkspaceSwitcher.tsx (+ .module.css) # 워크스페이스 전환 메뉴
    ├── lib/
    │   ├── paths.ts          #   화면 URL 생성 (paths.job(...) 등), 마지막 워크스페이스 기억
    │   ├── accounts.ts       #   로그인한 데모 계정·지금 계정 (X-User-Id 헤더)
    │   ├── preferences.ts    #   환경설정 (화면 모드, 글씨 크기), index.html 인라인 스크립트와 같은 키
    │   ├── labels.ts         #   상태·단계·종류·이음 형태·자세 한국어 라벨
    │   ├── format.ts         #   날짜(목록용 짧은 날짜 포함)·신뢰도 표시
    │   ├── errors.ts         #   API 오류 → 화면 문장
    │   └── download.ts       #   JSON 파일 다운로드
    └── pages/                # 라우트 하나당 파일 하나 (위 '라우트' 표)
```

## 다음 작업 (TODO)

- 인증: 로그인 사용자를 승인자로 채우고, 내가 속한 워크스페이스만 보이기, 노션처럼 다른 계정 추가·전환 (지금은 데모 사용자 하나, 승인자 이름 직접 입력)
- 권한: 소유자만 설정·초대를 바꿀 수 있게 (지금은 누구나)
- 조립 트리를 도면에서 가져오기 (새 프로젝트의 조립 트리는 비어 있음)
- 문자/기호 사전 항목 수정(`updateSymbol`) UI
- 새 작업에서 같은 워크스페이스의 과거 작업 연결(`related_job_ids`) 선택
- 작업자 확인 '직접 해석'의 `values` 형식은 백엔드 재해석 구현 때 확정
- 해석이 오래 걸리게 되면(실제 모델) 진행 상태(`analyzing`) 표시와 백그라운드 처리
