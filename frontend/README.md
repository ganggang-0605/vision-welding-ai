# Frontend

Vision Welding AI 웹 프론트엔드입니다. 작업자가 휴대폰으로 접속해 부재 마킹을 촬영·업로드하고, 분석 결과를 확인하고 JSON으로 내보내는 UI가 들어갈 자리입니다.
지금은 초기 세팅 단계라 앱 셸과 백엔드 연결 표시(`/api/health`)만 있습니다.

## 스택

- [React](https://react.dev/) 19 + [TypeScript](https://www.typescriptlang.org/)
- [Vite](https://vite.dev/) 8 (`npm create vite@latest -- --template react-ts` 공식 템플릿 기반)
- [Oxlint](https://oxc.rs/docs/guide/usage/linter): 현재 Vite 공식 템플릿의 기본 린터
- 패키지 매니저: **npm** (`package-lock.json` 커밋함)
- Node.js `^20.19.0` 또는 `>=22.12.0` (Vite 8 요구 사항)

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

브라우저에서 <http://localhost:5173>을 열면 백엔드 서버가 **연결됨**으로 표시됩니다.
백엔드가 꺼져 있으면 **연결 안 됨**으로 표시되고, 백엔드를 켠 뒤 **다시 확인** 버튼을 누르면 됩니다.

## API 프록시

개발 서버(`vite.config.ts`)는 `/api/*`로 들어온 요청에서 `/api`를 떼고 백엔드로 넘깁니다.

```
브라우저 → http://localhost:5173/api/health
Vite    → http://localhost:8000/health
```

- 프론트엔드 코드에서는 항상 `/api/...`로 호출합니다. 예: `fetch('/api/health')`, `apiFetch('/health')`
- 같은 출처(origin)로 요청하므로 백엔드에 CORS 설정이 필요 없습니다.
- 백엔드 리다이렉트의 `Location`도 프록시가 `/api/...`로 바꿔 줍니다. 예: `/api/workspaces/` 요청 시 FastAPI의 끝 슬래시 리다이렉트 `http://localhost:8000/workspaces` → `/api/workspaces`. 그래서 리다이렉트된 요청도 프록시를 거칩니다.
- API 호출 헬퍼는 `src/api/client.ts`에 있습니다 (`apiFetch<T>()`, `getHealth()`).
- 기본 경로를 바꿔야 할 때는 `.env.example`을 `.env.local`로 복사해 `VITE_API_BASE_URL`을 수정합니다.
  백엔드 주소(예: `http://localhost:8000`)를 직접 넣으면 프록시를 거치지 않으므로, 이때는 백엔드에 CORS 설정이 필요합니다.

## 휴대폰에서 접속하기

`server.host: true` 설정으로 개발 서버가 같은 네트워크의 다른 기기에도 열려 있습니다.

1. PC와 휴대폰을 **같은 Wi‑Fi**에 연결합니다.
2. `npm run dev`를 실행하면 터미널에 `Network: http://<PC IP>:5173/` 주소가 표시됩니다.
   (macOS에서 직접 확인: `ipconfig getifaddr en0`)
3. 휴대폰 브라우저에서 `http://<PC IP>:5173`을 엽니다.

API 요청도 Vite 프록시를 거쳐 PC의 `localhost:8000`으로 전달되므로, 백엔드는 기본 설정(`127.0.0.1`)으로 실행해도 됩니다.
접속이 안 되면 macOS 방화벽에서 Node 들어오는 연결을 허용했는지, 공용·게스트 Wi‑Fi처럼 기기 간 통신을 막는 네트워크가 아닌지 확인하세요.

> 휴대폰 카메라 API(`getUserMedia`)는 HTTPS 또는 localhost에서만 동작합니다. `<input type="file" accept="image/*" capture>`로 촬영하는 방식은 HTTP에서도 동작합니다.

## 스크립트

| 명령 | 설명 |
| --- | --- |
| `npm run dev` | 개발 서버 실행 (`:5173`, HMR, `/api` 프록시) |
| `npm run build` | 타입 체크(`tsc -b`) 후 `dist/`에 프로덕션 빌드 |
| `npm run lint` | Oxlint 검사 (경고도 실패 처리: `--deny-warnings`) |
| `npm run preview` | 빌드 결과물을 로컬에서 미리보기 (`/api` 프록시 동일하게 적용) |

CI(GitHub Actions)에서는 `frontend/`에서 `npm ci → npm run lint → npm run build` 순서로 실행합니다.

## 폴더 구조

```
frontend/
├── index.html            # HTML 진입점 (lang="ko", 모바일 viewport)
├── vite.config.ts        # 개발 서버·프록시 설정
├── .env.example          # VITE_API_BASE_URL 예시
├── public/               # 정적 파일 (favicon)
└── src/
    ├── main.tsx          # React 진입점
    ├── App.tsx           # 앱 셸
    ├── index.css         # 전역 스타일 (라이트/다크)
    ├── env.d.ts          # import.meta.env 타입
    ├── api/client.ts     # API 호출 헬퍼
    └── components/
        └── BackendStatus.tsx   # 백엔드 연결 표시
```
