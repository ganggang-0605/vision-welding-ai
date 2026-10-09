# vision-welding-ai

[![CI](https://github.com/ganggang-0605/vision-welding-ai/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ganggang-0605/vision-welding-ai/actions/workflows/ci.yml)

**AI 기반 용접 작업 분석 서비스** — PAC 해커톤

선박 블록의 부재 표기 정보를 촬영하면 AI가 노이즈를 제거하고 시각 정보를 문자·기호로 나눠 인식한 뒤,
도메인 DB(문자/기호 · 조립 경로 · 용접 기준)와 결합해 최적의 용접 조건을 판별한다.
다계층 신뢰도 검증과 작업자 확인을 거쳐 승인된 결과를 요약 저장하고, 로봇 연계용 JSON으로 출력한다.

![표기 정보 해석 프로세스](docs/images/pipeline.webp)

## 주요 기능

서비스는 Notion 처럼 **워크스페이스 단위**로 동작한다. 워크스페이스(조선소·공정 하나)는 **개인**(기본) 또는 **팀**이며,
개인 워크스페이스에 멤버를 초대하면 팀 워크스페이스로 바뀐다. 워크스페이스 안에는 블록(배 전체가 아닐 수도 있는 조립 단위) 하나를 뜻하는 **프로젝트**가 있고,
**조립 트리와 작업은 프로젝트에 속한다**. **문자/기호 사전**은 워크스페이스 단위로 프로젝트들이 함께 쓰고,
**표준 용접 기준**은 모든 워크스페이스가 공유하는 공통(읽기 전용) 데이터다. 검색·내보내기는 워크스페이스 안에서 이뤄진다.

1. **워크스페이스 & 문자/기호 체계 등록** — 조선소·공정별 자체 문자/기호 체계를 직접 등록·수정해 어떤 현장이든 이식
   (새 워크스페이스는 빈 사전으로 시작하거나 기존 워크스페이스의 사전을 복사)
2. **작업 생성 & 이미지 입력** — 프로젝트(블록)를 골라 작업 단위로 이미지들을 촬영·첨부, 같은 워크스페이스의 과거 작업과 연결
3. **표기 정보 해석**
   - **[1단계] 시각 인식**: 전처리(노이즈·오염·스크래치 제거) → 문자는 OCR, 기호·그림은 YOLO
   - **[2단계] DB 기반 맥락 해석**: VLM이 1단계 결과를 용접 기준 DB · 문자/기호 DB · 조립 경로 DB와 대조
   - **[3단계] 신뢰도 산출 & 판단 근거**: 시각 인식 / DB 정합성 / VLM 추론 신뢰도
4. **작업자 확인** — 기준치 미달 시 유사 문자 후보·DB 불일치 항목 제시 → 맥락 추가·재해석 또는 직접 해석
5. **작업 결과 관리** — 이름·날짜·해석 결과 검색, 로봇 제어·용접 프로그램용 JSON 내보내기

## 조립 경로 (블록 → 대조립 → 중조립 → 소조립 → 부재)

![조립 트리](docs/images/assembly-tree.webp)

데모 워크스페이스(`demo`) A1 블록(`block_a1`)의 조립 트리 — [`data/seed/workspaces/demo/projects/block_a1/assembly_tree.csv`](data/seed/workspaces/demo/projects/block_a1/assembly_tree.csv)

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

## 셀 형태와 각장 (PAC 과제)

과제는 셀 블록 사진에서 **셀 좌·우 끝의 형태**를 판별하고, **수기 각장 표기 F·V·S**를 읽어 셀 타입에 매핑하는 것이다.

| 항목 | 값 | 계약 (`backend/app/schemas.py`) |
| --- | --- | --- |
| 셀 형태 | `slit`, `slot`, `collar_front`(앞 Collar), `collar_back`(뒤 Collar), `scallop`. 한쪽에 여러 개가 겹칠 수 있음 (예: 앞 Collar + Scallop) | `Job.cell = {left: [...], right: [...]}` (판별 전이면 `null`) |
| 수기 각장 | `F` 3F 용접장 각장, `V` 2F 용접장 각장, `S` 스티프너 각장 + 숫자(mm). 예: `F5.5` | `Job.leg_lengths = [{code, size_mm, raw_text, meaning}]` |

데모 작업 3건(`block_a1`)의 셀 형태는 과제 안내의 셀 예시 1·2·3(좌 Slit·우 Slot / 좌 뒤 Collar·우 Slit / 좌 Slit·우 앞 Collar + Scallop)이고, 각장 값은 지어낸 값이다.
데모 사전에 `F`·`V`·`S`가 들어 있다. 로봇 연계 JSON에도 `cell`·`leg_lengths`가 들어간다.

해석 파이프라인에서는 2단계가 둘 다 만든다 (`ContextResult.leg_lengths` · `cell` → `to_job_fields()` → Job).

- **각장**: 사전의 각장 코드 + 숫자. 각장으로 볼 수 없는 크기는 믿지 않는다 — `F55`는 소수점이 빠진 5.5mm로 고쳐 작업자 확인, 고쳐도 2~25mm 밖이면 해석하지 않음.
- **셀 형태**: 셀 형태 기호(1단계 기호 인식 또는 VLM이 읽은 기호)를 사진 가운데 기준 왼쪽·오른쪽 끝으로 나눈다. 위치를 모르면 작업자 확인.
- **용접 조건**: 판 두께 표기가 없으면 첫 번째 각장으로 기준 행을 고른다 (`F` → 3F, `V` → 2F). 기준표는 각장별 값이라 사이 크기(5.5mm)는 가장 가까운 각장 행 + 작업자 확인. 근거는 [`data/seed/SOURCES.md`](data/seed/SOURCES.md).
- **부재·조립 경로**: PAC 셀 사진에는 부재 번호가 없어서, 사진에서 못 찾으면 작업을 만들 때 적은 조립 경로를 쓴다.
- 작업자 확인(`review` manual)에서 `cell`·`leg_lengths`를 고치면 다른 값처럼 작업자 수정(`corrections`)으로 남고 2단계부터 다시 해석한다.

## 신뢰도

| 구분 | 측정 대상 | 근거 |
| --- | --- | --- |
| 시각 인식 | 글자/기호의 시각적 모호성 | OCR/YOLO 출력 확률, 전처리 보정 강도, OCR↔VLM 교차 검증 일치도 (0~100%) |
| DB 정합성 | 맥락 일치도 | 문자/기호 사전 규칙, 조립 트리 내 부재 존재 여부, 표준 용접 기준과의 충돌 여부 |
| VLM 추론 | VLM 해석 정확도 | 출력 토큰 확률, 다중 추론 일관성 |

3단계(`calculate_reliability`)의 계산 — 전체 신뢰도는 셋 중 최솟값이고, 기준(`CONFIDENCE_THRESHOLD`, 기본 80) 이상이면서 조립 경로·용접 조건이 있어야 `awaiting_approval`이다.

- 시각 인식 = 작업자가 확인하지 않은 표기 중 가장 낮은 인식 확률과 OCR↔VLM 일치도 중 낮은 것 (보정 강도 50% 초과분 감점, 읽은 표기가 없으면 0)
- DB 정합성 = 100 − 사전·표기 규칙에 안 맞는 비율 × 25 − 부재가 트리에 없으면 40 − 표준 기준 충돌 1건당 20
- VLM 추론 = 토큰 확률·일관성 평균 (Claude처럼 토큰 확률이 없으면 일관성 × 90, 1회 추론이면 60). VLM을 끄면 100(판단에서 뺌), 호출이 실패하면 0
- 작업자 확인 항목 = 필수 값 없음 → 2단계 경고·오류 → 확률 낮은 표기(후보 포함) → VLM 추론 불일치·실패 순서, 대상마다 하나

## 적용 모델

| 단계 | 모델 |
| --- | --- |
| 전처리 | Retinexformer(조도), OpenCV(시점), SIHR(반사) |
| 인식 | PaddleOCR · TrOCR(문자), YOLO(기호·그림) |
| VLM | Qwen3-VL · InternVL(로컬), Gemini · GPT · Claude(상용) |

## API (워크스페이스 기반)

백엔드 기준 경로다. 프론트엔드 개발 서버에서는 앞에 `/api` 를 붙인다 (예: `GET /api/workspaces`).
요청·응답은 JSON(필드명 snake_case, id 는 문자열, 시각은 UTC ISO 8601)이며 스키마는 [`backend/app/schemas.py`](backend/app/schemas.py)와 `/docs` 를 참고한다.

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/health` | 상태 확인 → `{"status": "ok"}` |
| GET | `/me` | 현재 사용자 `{id, name, email}` — `X-User-Id` 헤더의 사용자 (없으면 데모 사용자, 모르는 id 면 401) |
| GET | `/users` | 데모 사용자 전체 목록 (시드 순) — "계정 추가하기"에서 고를 계정. 로그인이 없어서 있는 임시 API |
| GET | `/workspaces` | 현재 사용자가 **멤버인** 워크스페이스 목록 — 시드(폴더 이름순) 다음에 새로 만든 워크스페이스가 생성 순 |
| POST | `/workspaces` | 워크스페이스 생성 (201). `kind`: `personal`(기본) \| `team`, 현재 사용자(`X-User-Id`)가 소유자(`owner`). `dictionary_source`: `empty`(기본) \| `copy` + `copy_from_workspace_id` → 해당 사전 복사 |
| GET | `/workspaces/{workspace_id}` | 워크스페이스 조회 — `kind`, `member_count`(소유자 포함) 포함 |
| PATCH | `/workspaces/{workspace_id}` | 부분 수정 (`name`, `description`, `kind`). `team` → `personal` 은 멤버가 1명일 때만 (아니면 409) |
| GET | `/workspaces/{workspace_id}/members` | 멤버 목록 `{user_id, name, email, role, joined_at}` — 소유자 먼저, 그다음 가입 순 |
| POST | `/workspaces/{workspace_id}/members` | 멤버 초대 `{"name", "email"}` (201, `role: member`). 같은 이메일(대소문자 무시)의 사용자가 있으면 재사용. 개인 워크스페이스는 팀으로 전환. 이미 멤버면 409, 이메일에 `@` 가 없으면 422 |
| GET · POST | `/workspaces/{workspace_id}/symbols` | 문자/기호 사전 목록 · 항목 추가 (201) |
| PATCH · DELETE | `/workspaces/{workspace_id}/symbols/{symbol_id}` | 항목 부분 수정 · 삭제 (204) |
| GET · POST | `/workspaces/{workspace_id}/projects` | 프로젝트(블록) 목록(생성 순) · 생성 (201, 빈 조립 트리) |
| GET | `/workspaces/{workspace_id}/projects/{project_id}` | 프로젝트 조회 |
| GET | `/workspaces/{workspace_id}/projects/{project_id}/assembly-tree` | 프로젝트의 조립 트리 노드 목록 |
| GET | `/workspaces/{workspace_id}/jobs?q=&status=&project_id=` | 작업 검색 — `q`: 이름·조립 경로·표기 원문/해석(대소문자 무시), `status`·`project_id` 필터(빈 값이면 전체, 없는 프로젝트 id 면 빈 목록), 최신순 |
| POST | `/workspaces/{workspace_id}/jobs` | 작업 생성 (201, 상태 `draft`). `project_id` 필수 — 같은 워크스페이스의 프로젝트만, `related_job_ids` 는 같은 워크스페이스의 작업만 (아니면 422) |
| GET | `/workspaces/{workspace_id}/jobs/{job_id}` | 작업 조회 |
| POST · GET | `/workspaces/{workspace_id}/jobs/{job_id}/images` | 사진 올리기 (multipart `file`, 201 `{image_id, filename, content_type, width, height, created_at, preprocessed}`, 20MB 넘으면 413, 이미지가 아니면 422) · 올린 순서 목록 |
| GET | `/workspaces/{workspace_id}/jobs/{job_id}/images/{image_id}/file` | 올린 사진 파일 그대로 |
| GET | `/workspaces/{workspace_id}/jobs/{job_id}/images/{image_id}/preprocessed` | 1단계가 보정한 사진(PNG, OCR 이 본 사진 — 작은 사진 키우기·노이즈 제거). 보정하지 않았거나 해석 전이면 404 (`preprocessed: false`) |
| POST | `/workspaces/{workspace_id}/jobs/{job_id}/analyze` | 사진 한 장을 1·2·3단계로 해석(`backend/app/pipeline.py`) → Analysis 저장, Job 반영. 본문 `{"image_id"}` 생략 시 가장 최근 사진. **202 로 바로 끝나고 백그라운드에서 해석** — 그동안 상태 `analyzing` 이고 `analysis_stage`(`vision` → `context` → `confidence`)·`analysis_stage_at` 으로 지금 단계를 알림, 실패하면 해석 전 상태 + `analysis_error`. 사진이 없거나 이미 해석 중이면 409 |
| POST | `/workspaces/{workspace_id}/jobs/{job_id}/review` | 작업자 확인 → 가장 최근 Analysis 에서 2단계부터 다시 해석(revision + 1, `analyze` 처럼 202 + 백그라운드). `reinterpret` + `context` \| `manual` + `values`(키: `t*`·`s*`·`v*`·`part`·`interpretation`·`welding_condition`·`cell`·`leg_lengths`). 해석 전·해석 중이면 409, 잘못된 값·없는 표기면 바로 422 |
| GET | `/workspaces/{workspace_id}/jobs/{job_id}/analyses` | 해석 결과([`analysis.schema.json`](shared/schemas/analysis.schema.json)) 전체, 만든 순서 — 사진 위 bbox·후보 표시용 |
| POST | `/workspaces/{workspace_id}/jobs/{job_id}/approve` | 승인 `{"approved_by": "...", "acknowledge_review": false}` → `approved`. `awaiting_approval` 은 바로, `needs_review` 는 작업자가 확인 항목을 봤다는 `acknowledge_review: true` 가 있어야 승인. 그 밖의 상태, 확인 표시 없음, 조립 경로·표기·용접 조건이 비어 있으면 409 |
| GET | `/workspaces/{workspace_id}/jobs/{job_id}/export` | 로봇 연계 JSON ([`shared/schemas/robot_output.schema.json`](shared/schemas/robot_output.schema.json), `project_id` 포함). 승인 전이면 409 |
| GET | `/welding-standards` | 표준 용접 기준 (공통, 읽기 전용) |
| GET | `/pipeline/status` | 해석 파이프라인 연결 상태 — 1단계 OCR 모델 설치 여부·모델 이름, 기호 검출기 연결, 2단계 VLM provider·모델·추론 횟수·SDK 설치·API 키 설정 여부(키 값은 돌려주지 않음)·최근 호출 실패 이유(`vlm_last_error`), 3단계 통과 기준 |

- 작업 상태: `draft` → `analyzing` → `needs_review`(신뢰도 기준 미달) / `awaiting_approval` → `approved`
- **데모 다중 계정** (Notion 식 계정 전환): 요청 헤더 `X-User-Id: <user_id>` 가 로그인 세션을 대신해 현재 사용자를 고른다.
  헤더가 없거나 비어 있으면 시드의 현재 사용자(`user_kkm`), `GET /users` 에 없는 id 면 401 이다.
  시드 계정: `user_kkm`(`demo`, `personal`, `yeongam`), `user_ldh`(`demo`, `ldh`, `yeongam`), `user_lmh`(`demo`).
- 워크스페이스 종류: `personal`(개인) → 멤버 초대 시 `team`(팀). 직접 `PATCH` 로 바꿀 수도 있다 (팀 → 개인은 멤버 1명일 때만).
- 작업 경로는 워크스페이스 하위(`/workspaces/{workspace_id}/jobs`) 그대로이고, 작업의 `project_id` 로 프로젝트(블록)에 속한다.
  예전 `GET /workspaces/{workspace_id}/assembly-tree` 는 없어지고 프로젝트 하위로 옮겼다.
- 없는 워크스페이스의 하위 경로는 모두 404, 다른 워크스페이스의 프로젝트·작업 id 로 요청해도 404 이다. 오류 본문은 `{"detail": "..."}` (422 는 FastAPI 기본 형식).
- 다시 해석(`analyze`·`review`)하면 이전 승인은 무효가 된다 (`approved_at`·`approved_by` 비움). 단계 패키지에 실제 모델이 없으면 결과가 비어 `needs_review` 가 된다.
- VLM 호출이 실패하면 해석은 VLM 없이 이어 가고, 이유가 작업의 확인 항목(`vlm_failed`)과 `/pipeline/status` 의 `vlm_last_error` 에 남는다.
- **저장소**([`backend/app/store.py`](backend/app/store.py))는 `.env` 의 `DATABASE_URL` DB 에 남아 서버를 다시 켜도 작업·사진·해석 결과가 그대로다.
  기본은 **PostgreSQL**(`postgresql://vision:vision@localhost:5433/vision_welding`, 저장소 루트 `docker compose up -d db`)이고,
  PostgreSQL 없이 개발할 때는 SQLite 파일(`sqlite:///./vision_welding.db`, `backend/` 기준)도 된다 ([`backend/app/db/connect.py`](backend/app/db/connect.py)가 주소로 고름).
  처음 켤 때(DB 가 비었을 때) 시드 상태(팀 워크스페이스 `demo`, 팀 워크스페이스 `yeongam`, 개인 워크스페이스 `personal`·`ldh`)로 채운다.
  시드로 되돌리려면 PostgreSQL 은 `docker compose down -v`, SQLite 는 `backend/vision_welding.db*` 를 지우고 다시 켠다. `DATABASE_URL` 을 비우면 메모리만 쓴다 (테스트).
  쓰던 DB 를 옮기려면 `backend/` 에서 `python -m app.db.migrate <보내는 주소> <받는 주소>` (예: SQLite 파일 → PostgreSQL).
- 인증은 아직 없다 (TODO) — `X-User-Id` 헤더는 데모용일 뿐 누구나 아무 계정으로 요청할 수 있다.
  워크스페이스 목록만 멤버로 거르고, 그 밖의 경로는 권한 검사를 하지 않는다 (id 를 알면 누구나 접근, TODO 권한).

## 디렉터리 구조

표기 정보 해석의 1·2·3단계는 각자 독립 패키지로 개발하고, `backend`가 셋을 순서대로 호출해 통합한다.
단계 사이 데이터 형식은 모두 [`shared/schemas`](shared/schemas)에 있다 ([`shared/README.md`](shared/README.md)).

```
shared/                   # 공통 계약 — 모든 폴더가 여기에만 의존
  schemas/                # JSON 스키마 전체 (1·2·3단계 입출력 · Analysis · 로봇 출력)
  examples/               # 단계별 예시 = 각 단계 테스트의 입력
  src/vw_shared/          # 스키마 검증 · 단계 사이 규칙 · to_job_fields (python -m vw_shared.validate)
vision/                   # [1단계] 시각 인식 — recognize(image, image_id) → VisionResult
  src/vision/             #   preprocess(전처리) · ocr(문자) · symbols(기호) · recognition(진입점, ID 붙이기)
  tools/ ROADMAP.md       #   데이터 점검 도구 · 개발 계획
db_context_interpreter/   # [2단계] DB 기반 맥락 해석 — interpret(vision_result, context_input) → ContextResult
  src/db_context_interpreter/  # welding(용접 기준) · dictionary(사전) · assembly(조립 경로) · legs(각장·셀 형태) · vlm/
calculate_reliability/    # [3단계] 신뢰도 산출 — score(vision, context, corrections, threshold) → ConfidenceReport
  src/calculate_reliability/   # visual · db_consistency · vlm_reasoning · review(작업자 확인 항목)
backend/
  app/
    api/            # REST API (FastAPI) — users(/me, /users) · workspaces(멤버·사전) · projects(조립 트리) · jobs · standards
    schemas.py      # API 스키마 (Pydantic) — 프론트엔드와 공유하는 계약
    store.py        # 저장소 (메모리 + PostgreSQL · SQLite, db/connect.py)
    pipeline.py     # 1·2·3단계 통합 — DB 조회 → 단계 호출 → Analysis → Job 반영
    db/             # 조립 트리 / 문자·기호 / 용접 기준 DB, 저장 (postgres.py · sqlite.py · migrate.py)
    export/         # 로봇 연계 JSON
  tests/
  tools/eval_pipeline.py  # 실제 모델로 1→2→3단계를 돌려 정답과 비교
data/seed/
  welding_standards.csv   # 표준 용접 기준 (공통)
  users.json              # 데모 사용자 + current_user_id (X-User-Id 헤더가 없을 때의 사용자)
  workspaces/<workspace_id>/
    workspace.json, members.json, symbol_dictionary.json  # 워크스페이스(kind)·멤버·문자/기호 사전(없으면 빈 사전)
    projects/<project_id>/                                # 프로젝트(블록) — 폴더 이름이 id
      project.json, assembly_tree.csv, jobs.json          # 트리·작업 파일은 없으면 빈 것으로 봄
  # demo: 팀(멤버 3명) "울산 1도크" — block_a1(조립 트리·데모 작업 3건), block_a2(빈 블록)
  # yeongam: 팀(user_kkm·user_ldh) "영암 2도크" — block_s1(빈 블록). 사전은 demo 와 같고 FW 만 플래시버트 용접
  #   도크 이름은 시연용 가정이고, 사전·조립 트리·작업은 지어낸 목데이터
  # ldh: 개인(user_ldh) — block_b1("B1 블록", 빈 블록)
  # personal: 개인(user_kkm) — practice("연습용 블록", 빈 블록)
data/annotations/   # [1단계] 현장 사진 정답 라벨
frontend/           # UI (React + Vite + TypeScript)
docs/               # 기획 문서·이미지
```

## 시작하기

### 백엔드

**Python 3.12 이상**이 필요하다. macOS 기본 `python3`(Xcode 명령줄 도구)는 3.9라서 `python3 -m venv` 로 만들면 설치가 실패한다.
[uv](https://docs.astral.sh/uv/)로 3.12 가상환경을 만드는 걸 추천한다 (uv 가 Python 3.12 도 받아 온다).

```bash
docker compose up -d db          # 저장소 루트에서 — PostgreSQL (localhost:5433)
cd backend
uv venv -p 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp ../.env.example ../.env
uvicorn app.main:app --reload
```

Docker 없이 하려면 `.env` 의 `DATABASE_URL` 을 `sqlite:///./vision_welding.db` 로 바꾸면 SQLite 파일에 저장한다.

uv 없이 하려면 `brew install python@3.12` 후 `python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.

> **저장소를 iCloud Drive 폴더(데스크탑·문서 동기화 포함)에 두면 가상환경이 깨질 수 있다.** iCloud 가 패키지 경로 파일(`.pth`)에
> 숨김 속성을 붙이면 Python 이 그 파일을 건너뛰어 `shared`·단계 패키지를 못 찾는다 (`ModuleNotFoundError: vw_shared` 등).
> 가상환경을 iCloud 밖에 만들고(예: `uv venv -p 3.12 ~/.venvs/vision-welding-ai`, 활성화 후 `uv pip install -r requirements.txt`) 그걸 쓰거나,
> 이미 깨졌으면 `chflags -R nohidden .venv` 로 숨김 속성을 지운다.

http://localhost:8000/docs 에서 Swagger UI로 API를 바로 호출해 볼 수 있다.
처음 켤 때 데모 사용자 3명, 팀 워크스페이스 `demo`("울산 1도크", A1·A2 블록, 데모 작업 3건)·`yeongam`("영암 2도크", S1 블록 — 같은 FW 가 플래시버트 용접인 사전)와
개인 워크스페이스 `personal`·`ldh`가 시드되고 `DATABASE_URL` DB(기본 PostgreSQL)에 저장된다.
켤 때 OCR 모델을 백그라운드로 미리 불러 둔다 (`PRELOAD_MODELS=0` 이면 끔 — 첫 해석이 모델 로드로 1분 가까이 걸림).

`requirements.txt`가 `shared`와 1·2·3단계 패키지도 editable(`-e ../…`)로 함께 설치한다 (`backend` 폴더에서 실행).
실제 인식 모델은 `pip install -e "../vision[models]"`, 상용 VLM SDK는 `pip install -e "../db_context_interpreter[vlm]"`로 따로 설치한다.

테스트: `cd backend && python -m pytest -q` — 저장소 DB 테스트를 PostgreSQL 에서도 돌리려면
`TEST_DATABASE_URL=postgresql://vision:vision@localhost:5433/vision_welding python -m pytest -q` (테스트마다 스키마를 따로 만들고 지움, CI 는 항상 돌림)

**실제 모델로 점검** — CI 는 모델 없이 계약만 테스트해서 실제 OCR·VLM 동작이 깨져도 잡지 못한다. 모델을 바꾸거나 단계 코드를 고쳤으면
정답이 있는 사진(`data/annotations`, 사진은 `data/raw/` — 운영측 PAC 사진은 드라이브에서 받기)으로 전체를 돌려 비교한다.
`.env` 의 VLM 설정을 그대로 써서, VLM 을 켜면 사진마다 `VLM_RUNS` 번 API 를 부른다.

```bash
backend/.venv/bin/python backend/tools/eval_pipeline.py        # 저장소 루트에서, 결과는 data/eval/pipeline.json
```

### 해석 파이프라인 (1·2·3단계)

단계마다 `shared/examples`의 앞 단계 예시를 입력으로 테스트하므로, 앞 단계가 완성되지 않아도 따로 개발할 수 있다.
위 백엔드 가상환경에서 저장소 루트를 기준으로 각각 실행한다.

```bash
cd vision && python -m pytest -q                   # [1단계]
cd db_context_interpreter && python -m pytest -q   # [2단계]
cd calculate_reliability && python -m pytest -q    # [3단계]
python -m vw_shared.validate                       # 스키마·예시 점검
```

### 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

http://localhost:5173 에서 열린다. 백엔드(http://localhost:8000)를 먼저 띄워 두면 개발 서버가
`/api/*` 요청을 백엔드로 프록시한다 (예: `fetch('/api/health')` → `GET http://localhost:8000/health`).

### CI

`main` 브랜치 push와 모든 PR에서 GitHub Actions([`.github/workflows/ci.yml`](.github/workflows/ci.yml))가 실행된다.

- **backend** (Python 3.12): `pip install -r requirements.txt` → `python -m pytest -q`
- **pipeline** (Python 3.12, `shared` · `vision` · `db_context_interpreter` · `calculate_reliability` 각각): `pip install -e ../shared -e .` → `python -m pytest -q`
- **frontend** (Node 24): `npm ci` → `npm run lint` → `npm run build`

Actions 탭에서 수동 실행(`workflow_dispatch`)도 가능하다.
