# vision-welding-ai

[![CI](https://github.com/ganggang-0605/vision-welding-ai/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ganggang-0605/vision-welding-ai/actions/workflows/ci.yml)

**AI 기반 용접 작업 분석 서비스** — PAC 해커톤

선박 블록의 부재 표기 정보를 촬영하면 AI가 노이즈를 제거하고 시각 정보를 문자·기호로 나눠 인식한 뒤,
도메인 DB(문자/기호 · 조립 경로 · 용접 기준)와 결합해 최적의 용접 조건을 판별합니다.
다계층 신뢰도 검증과 작업자 확인을 거쳐 승인된 결과를 요약 저장하고, 로봇 연계용 JSON으로 출력합니다.

![표기 정보 해석 프로세스](docs/images/pipeline.webp)

## 주요 기능

서비스는 **워크스페이스 단위**로 동작합니다. 워크스페이스(조선소·공정 하나)마다 작업, 문자/기호 사전, 조립 트리를 따로 가지며
검색·내보내기도 워크스페이스 안에서 이뤄집니다. **표준 용접 기준**만 모든 워크스페이스가 공유하는 공통(읽기 전용) 데이터입니다.

1. **워크스페이스 & 문자/기호 체계 등록** — 조선소·공정별 자체 문자/기호 체계를 직접 등록·수정해 어떤 현장이든 이식
   (새 워크스페이스는 빈 사전으로 시작하거나 기존 워크스페이스의 사전을 복사)
2. **작업 생성 & 이미지 입력** — 작업 단위로 이미지를 촬영·첨부, 같은 워크스페이스의 과거 작업과 연결
3. **표기 정보 해석**
   - **[1단계] 시각 인식**: 전처리(노이즈·오염·스크래치 제거) → 문자는 OCR, 기호·그림은 YOLO
   - **[2단계] DB 기반 맥락 해석**: VLM이 1단계 결과를 용접 기준 DB · 문자/기호 DB · 조립 경로 DB와 대조
   - **[3단계] 신뢰도 산출 & 판단 근거**: 시각 인식 / DB 정합성 / VLM 추론 신뢰도
4. **작업자 확인** — 기준치 미달 시 유사 문자 후보·DB 불일치 항목 제시 → 맥락 추가·재해석 또는 직접 해석
5. **작업 결과 관리** — 이름·날짜·해석 결과 검색, 로봇 제어·용접 프로그램용 JSON 내보내기

## 조립 경로 (블록 → 대조립 → 중조립 → 소조립 → 부재)

![조립 트리](docs/images/assembly-tree.webp)

데모 워크스페이스(`demo`)의 조립 트리 — [`data/seed/workspaces/demo/assembly_tree.csv`](data/seed/workspaces/demo/assembly_tree.csv)

| node_id | parent_id | level | path |
| --- | --- | --- | --- |
| A1 | – | BLOCK | A1 |
| L1 | A1 | LARGE | A1/L1 |
| M2 | L1 | MID | A1/L1/M2 |
| S1 | M2 | SUB | A1/L1/M2/S1 |
| S2 | M2 | SUB | A1/L1/M2/S2 |
| P-1 | S1 | PART | A1/L1/M2/S1/P-1 |
| P-2 | S1 | PART | A1/L1/M2/S1/P-2 |
| P-3 | S2 | PART | A1/L1/M2/S2/P-3 |

## 신뢰도

| 구분 | 측정 대상 | 근거 |
| --- | --- | --- |
| 시각 인식 | 글자/기호의 시각적 모호성 | OCR/YOLO 출력 확률, 전처리 보정 강도, OCR↔VLM 교차 검증 일치도 (0~100%) |
| DB 정합성 | 맥락 일치도 | 문자/기호 사전 규칙, 조립 트리 내 부재 존재 여부, 표준 용접 기준과의 충돌 여부 |
| VLM 추론 | VLM 해석 정확도 | 출력 토큰 확률, 다중 추론 일관성 |

## 적용 모델

| 단계 | 모델 |
| --- | --- |
| 전처리 | Retinexformer(조도), OpenCV(시점), SIHR(반사) |
| 인식 | PaddleOCR · TrOCR(문자), YOLO(기호·그림) |
| VLM | Qwen3-VL · InternVL(로컬), Gemini · GPT · Claude(상용) |

## API (워크스페이스 기반)

백엔드 기준 경로입니다. 프론트엔드 개발 서버에서는 앞에 `/api` 를 붙입니다 (예: `GET /api/workspaces`).
요청·응답은 JSON(필드명 snake_case, id 는 문자열, 시각은 UTC ISO 8601)이며 스키마는 [`backend/app/schemas.py`](backend/app/schemas.py)와 `/docs` 를 참고하세요.

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/health` | 상태 확인 → `{"status": "ok"}` |
| GET | `/workspaces` | 워크스페이스 목록 |
| POST | `/workspaces` | 워크스페이스 생성 (201). `dictionary_source`: `empty`(기본) \| `copy` + `copy_from_workspace_id` → 해당 사전 복사 |
| GET | `/workspaces/{workspace_id}` | 워크스페이스 조회 |
| GET · POST | `/workspaces/{workspace_id}/symbols` | 문자/기호 사전 목록 · 항목 추가 (201) |
| PATCH · DELETE | `/workspaces/{workspace_id}/symbols/{symbol_id}` | 항목 부분 수정 · 삭제 (204) |
| GET | `/workspaces/{workspace_id}/assembly-tree` | 조립 트리 노드 목록 |
| GET | `/workspaces/{workspace_id}/jobs?q=&status=` | 작업 검색 — `q`: 이름·조립 경로·표기 원문/해석(대소문자 무시), `status` 필터(빈 값이면 전체), 최신순 |
| POST | `/workspaces/{workspace_id}/jobs` | 작업 생성 (201, 상태 `draft`). `related_job_ids` 는 같은 워크스페이스의 작업만 (아니면 422) |
| GET | `/workspaces/{workspace_id}/jobs/{job_id}` | 작업 조회 |
| POST | `/workspaces/{workspace_id}/jobs/{job_id}/images` | 이미지 업로드 (multipart `file`) — **501 미구현** |
| POST | `/workspaces/{workspace_id}/jobs/{job_id}/analyze` | 표기 정보 해석 — **501 미구현** |
| POST | `/workspaces/{workspace_id}/jobs/{job_id}/review` | 작업자 확인 (`reinterpret` \| `manual`) — **501 미구현** |
| POST | `/workspaces/{workspace_id}/jobs/{job_id}/approve` | 승인 `{"approved_by": "..."}` → `approved`. `awaiting_approval`·`needs_review` 가 아니면 409 |
| GET | `/workspaces/{workspace_id}/jobs/{job_id}/export` | 로봇 연계 JSON ([`schemas/robot_output.schema.json`](schemas/robot_output.schema.json)). 승인 전이면 409 |
| GET | `/welding-standards` | 표준 용접 기준 (공통, 읽기 전용) |

- 작업 상태: `draft` → `analyzing` → `needs_review`(신뢰도 기준 미달) / `awaiting_approval` → `approved`
- 없는 워크스페이스의 하위 경로는 모두 404, 다른 워크스페이스의 작업 id 로 요청해도 404 입니다. 오류 본문은 `{"detail": "..."}` (422 는 FastAPI 기본 형식).
- **저장소는 임시 인메모리**([`backend/app/store.py`](backend/app/store.py))라 서버를 재시작하면 시드 상태(데모 워크스페이스 `demo`)로 돌아갑니다. 실제 DB(SQLAlchemy)로 교체 예정입니다.
- 인증·멤버 관리는 아직 없습니다 (TODO).

## 디렉터리 구조

```
backend/
  app/
    api/            # REST API (FastAPI) — workspaces · jobs · standards
    schemas.py      # API 스키마 (Pydantic) — 프론트엔드와 공유하는 계약
    store.py        # 임시 인메모리 저장소 (실제 DB 로 교체 예정)
    pipeline/
      preprocess/   # [1단계] 전처리
      recognition/  # [1단계] OCR / YOLO
      context/      # [2단계] DB 대조 + VLM 맥락 해석
      confidence/   # [3단계] 신뢰도 산출
      run.py        # 파이프라인 진입점
    db/             # 조립 트리 / 문자·기호 / 용접 기준 DB
    export/         # 로봇 연계 JSON
  tests/
data/seed/
  welding_standards.csv   # 표준 용접 기준 (공통)
  workspaces/demo/        # 데모 워크스페이스 (workspace.json, 문자/기호 사전, 조립 트리, 데모 작업)
schemas/            # 로봇 출력 JSON 스키마
frontend/           # UI (React + Vite + TypeScript)
docs/               # 기획 문서·이미지
```

## 시작하기

### 백엔드

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env
uvicorn app.main:app --reload
```

http://localhost:8000/docs 에서 Swagger UI로 API를 바로 호출해 볼 수 있습니다.
시작 시 데모 워크스페이스 `demo`("데모 조선소 · 1도크")와 데모 작업 3건이 시드됩니다.

테스트: `cd backend && python -m pytest -q`

### 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

http://localhost:5173 에서 열립니다. 백엔드(http://localhost:8000)를 먼저 띄워 두면 개발 서버가
`/api/*` 요청을 백엔드로 프록시합니다 (예: `fetch('/api/health')` → `GET http://localhost:8000/health`).

### CI

`main` 브랜치 push와 모든 PR에서 GitHub Actions([`.github/workflows/ci.yml`](.github/workflows/ci.yml))가 실행됩니다.

- **backend** (Python 3.12): `pip install -r requirements.txt` → `python -m pytest -q`
- **frontend** (Node 24): `npm ci` → `npm run lint` → `npm run build`

Actions 탭에서 수동 실행(`workflow_dispatch`)도 가능합니다.
