# shared — 프로젝트 JSON 스키마

이 저장소의 JSON 스키마는 모두 [`schemas/`](schemas/)에 둡니다 (파이프라인 1·2·3단계, 로봇 연계 JSON).

표기 정보 해석의 **1단계(시각 인식) → 2단계(DB 기반 맥락 해석) → 3단계(신뢰도 산출)**가 서로 주고받는 데이터 형식입니다.
세 단계는 폴더를 나눠 독립 패키지로 개발하고, `backend`가 셋을 순서대로 호출해 통합합니다.

| 폴더 | 패키지 | 진입 함수 |
| --- | --- | --- |
| [`vision/`](../vision) | `vision` | `recognize(image, image_id)` → VisionResult |
| [`db_context_interpreter/`](../db_context_interpreter) | `db_context_interpreter` | `interpret(vision_result, context_input)` → ContextResult |
| [`calculate_reliability/`](../calculate_reliability) | `calculate_reliability` | `score(vision, context, corrections, threshold)` → ConfidenceReport |
| [`backend/app/pipeline.py`](../backend/app/pipeline.py) | 통합 | `analyze_image()` · `review_analysis()` → Analysis, `job_with_analysis()` → Job |
| `shared/src/vw_shared/` | `vw_shared` | `schema_errors()` · `semantic_errors()` · `to_job_fields()` · `load_example()` |

의존 방향은 한쪽으로만 흐릅니다: `shared` ← 세 단계 ← `backend` ← `frontend`(API로만).
단계끼리는 서로 import하지 않고, DB도 직접 읽지 않습니다 (2단계에 필요한 DB 값은 `backend`가 `ContextInput`으로 넘김).
각 단계는 `shared/examples`의 앞 단계 예시를 입력으로 테스트하므로 앞 단계가 완성되지 않아도 개발할 수 있습니다.

> **GUI ↔ 백엔드 계약(워크스페이스·프로젝트·작업·작업자 확인·승인)은 [`backend/app/schemas.py`](../backend/app/schemas.py)가 기준입니다.**
> 여기서는 그 계약에 없는 파이프라인 내부 형식만 정의하고, 결과를 그 계약의 `Job` 필드로 옮기는 방법을 정합니다.

형식은 모두 [JSON Schema 2020-12](https://json-schema.org/)입니다.

## 데이터 흐름

```
POST /workspaces/{workspace_id}/jobs/{job_id}/analyze
                                   워크스페이스 사전 · 프로젝트 조립 트리 · 공통 용접 기준
                                                     │
                                         ContextInput (backend가 모음)
                                                     │
이미지 ──▶ [1단계] VisionResult ──▶ [2단계] ContextResult ──▶ [3단계] ConfidenceReport
              │                            │                            │
              └────────────── Analysis (revision 1, 2, …) ──────────────┘
                                           │ to_job_fields()
                                           ▼
          Job.status · assembly_path · marking · welding_condition · confidence · evidence · needs_review
                         (backend/app/schemas.py) ──▶ GUI · 로봇 JSON
```

## 스키마 목록

| 파일 | 내용 | 만드는 쪽 | 쓰는 쪽 |
| --- | --- | --- | --- |
| [`common.schema.json`](schemas/common.schema.json) | 좌표, 확률, ID 등 공통 타입 | — | 전체 |
| [`vision_result.schema.json`](schemas/vision_result.schema.json) | **[1단계]** 전처리 정보, 문자·기호 인식 결과 | 1단계 | 2단계, 3단계, GUI |
| [`context_input.schema.json`](schemas/context_input.schema.json) | **[2단계 입력]** 사전, 조립 트리, 용접 기준, 작업자 맥락·수정, 이전 VLM 읽기, 연결된 과거 작업 | 백엔드 (`app/pipeline.py`) | 2단계 |
| [`context_result.schema.json`](schemas/context_result.schema.json) | **[2단계]** 사전 대조, 부재·조립 경로, 용접 조건, DB 불일치, VLM 해석 | 2단계 | 3단계, 백엔드 |
| [`confidence_report.schema.json`](schemas/confidence_report.schema.json) | **[3단계]** 세 가지 신뢰도, 근거, 작업자 확인 항목 | 3단계 (이후) | 백엔드, GUI |
| [`analysis.schema.json`](schemas/analysis.schema.json) | 사진 한 장의 해석 결과 (1·2·3단계 묶음 + 작업자 수정) | 백엔드 (`app/pipeline.py`) | 백엔드 |
| [`robot_output.schema.json`](schemas/robot_output.schema.json) | 승인된 작업의 로봇 연계 JSON (`GET .../export`) | 백엔드 (`backend/app/export/robot_json.py`) | 로봇 제어·용접 프로그램 |

## 역할과 연결

| 테이블 | 역할 | 연결 |
| --- | --- | --- |
| **VisionResult** (1단계) | 글자·기호를 찾아 읽고 `t1`, `s1` 같은 ID를 붙임 | 2단계, 3단계, GUI가 이 ID로 글자·기호를 가리킴 |
| **ContextResult** (2단계) | 1단계 결과를 사전·조립 트리·용접 기준과 대조해 의미를 해석. 1단계가 놓친 표기를 VLM이 읽으면 `v1`, `v2`, …를 붙임 | `ref_ids`로 1단계 결과(`t*`, `s*`)나 VLM만 읽은 표기(`v*`)를 가리킴 |
| **ConfidenceReport** (3단계) | 신뢰도 세 가지를 계산하고 작업자 확인 항목을 고름 | `factors`가 1·2단계 값을 가져옴 |
| **Analysis** | 위 세 결과를 묶은 사진 한 장의 해석 결과 | `workspace_id`·`project_id`·`job_id`로 팀원 `Job`에 연결. 작업자 확인 때마다 `revision`이 늘어난 새 Analysis |

**연결의 중심은 1단계가 붙이는 ID(`t1`, `s1`)입니다.** 1단계가 ID를 바꾸거나 빠뜨리면 뒤 단계가 모두 깨집니다.
작업자 확인(재해석·직접 해석)은 2단계부터 다시 돌리므로, 1단계 결과와 ID는 작업이 끝날 때까지 그대로 유지됩니다.
2단계가 붙이는 `v*`도 같은 표기면 다시 돌려도 이전 revision의 ID를 그대로 씁니다 (작업자 수정 `corrections`가 이 ID를 가리킴).

**작업 하나에 사진이 여러 장이면** 사진마다 Analysis를 만들고, `Job`에는 가장 최근(`created_at`) Analysis를 반영합니다 (`vw_shared.latest_analysis()`).

## 팀원 API 계약과의 연결

### 파이프라인이 읽는 것

| 팀원 계약 (`backend/app/schemas.py`) | 파이프라인에서 쓰는 곳 |
| --- | --- |
| `SymbolEntry.code` (워크스페이스 사전) | 1단계 `SymbolDetection.label`, 2단계 `DictionaryMatch.code` |
| `SymbolEntry.welding_joint_type` | 2단계 `WeldingCondition.joint_type` 판별 |
| `AssemblyNode` (프로젝트 조립 트리) | 2단계 `Part` (`node_id`, `assembly_path`, `level`, `found_in_tree`) |
| `WeldingStandard` (공통 표준 용접 기준) | 2단계 `WeldingCondition` (`standard_matched`) |
| `ReviewRequest` `action: reinterpret` + `context` | 2단계부터 다시 해석, `ContextResult.user_context` |
| `ReviewRequest` `action: manual` + `values` | `Analysis.corrections` (`values`의 키 = `target`, 값 = `value`). `t*`·`s*`·`v*`의 의미까지 정하면 값을 `{"value", "meaning"}`으로 보냄 |

### 파이프라인 결과 → `Job` 필드 (`to_job_fields()`)

| `Job` 필드 | 채우는 값 |
| --- | --- |
| `status` | 3단계 `passed`가 true면 `awaiting_approval`, 아니면 `needs_review` (3단계 전에는 항상 `needs_review`). `passed`는 `assembly_path`·`welding_condition`이 모두 있어야 true (로봇 JSON 필수 값) |
| `assembly_path` | 2단계 `part.assembly_path` (작업자가 `part`를 고쳤으면 그 값) |
| `marking.raw_text` | 1단계 글자·기호와 VLM만 읽은 `v*`를 읽는 순서(줄 단위, 왼→오른)로 이어 붙인 것 (작업자 수정 반영) |
| `marking.symbols` | 1단계 기호 `label` + VLM만 읽은 기호 목록 |
| `marking.interpretation` | 작업자가 `interpretation`을 고쳤으면 그 값, 아니면 2단계 `vlm.interpretation` (VLM이 꺼져 있으면 사전 대조 의미를 이어 붙임) |
| `welding_condition` | 2단계 `welding_condition`의 6개 필드 (`thickness_mm`·`standard_matched`·`source`·`ref_ids`는 빠짐) |
| `confidence` | 3단계 `visual`·`db_consistency`·`vlm_reasoning`·`overall` |
| `evidence` | 3단계 `evidence[].message` |
| `needs_review` | 3단계 `needs_review[].message` |

`to_job_fields()`는 [`vw_shared/job_fields.py`](src/vw_shared/job_fields.py)에 있고, 백엔드 `app/pipeline.py`의 `job_with_analysis()`가 씁니다. 결과가 팀원 `Job` 모델을 통과하는지는 `backend/tests/test_pipeline.py`가 점검합니다.

> 이름 주의: 팀원 계약의 `Job.marking`(표기 원문·해석 요약)과 구분하려고, 2단계의 사전 대조 결과는 `DictionaryMatch`(`dictionary_matches`)라고 부릅니다.

## 사진 한 장이 지나가는 순서 (예시 파일)

[`examples/`](examples/)에 팀원 데모 시드(`demo` 워크스페이스, `block_a1` 블록)를 기준으로 한 흐름이 들어 있습니다.
사진 속 표기는 부재 `P-1`, 손글씨 `FW`, 판 두께 `t=10`, 현장 용접 기호 `▲`입니다.

| 순서 | 무슨 일 | 예시 파일 |
| --- | --- | --- |
| 1 | 1단계: `t1` "P-1", `t2` "FW"(62%, 후보 FW·EW), `t3` "t=10", `s1` "▲" | `vision_result.example.json` |
| 2 | 2단계: 부재 P-1(A1/L1/M2/S1/P-1), FW → 필렛 용접, 판 두께 10mm → 2F 수평 필렛 420-440A | `context_result.example.json` |
| 3 | 3단계: overall 62%로 기준 80% 미달, `t2` 확인 필요 | `confidence_report.example.json` |
| 4 | 세 결과를 묶음 (revision 1) → `Job.status = needs_review` | `analysis.example.json` |
| 5 | 작업자가 `t2`를 FW로 확인 → revision 2, overall 88%로 통과 → `Job.status = awaiting_approval` | `analysis_revision2.example.json` |

## 공통 규칙

| 항목 | 규칙 |
| --- | --- |
| 좌표 | `bbox`는 `[x1, y1, x2, y2]`, **원본 이미지 픽셀 좌표**. 전처리로 이미지를 폈더라도 원본 좌표로 되돌려서 출력 |
| 확률 | 1·2단계는 **0~1** (`prob`, `score`, `consistency`) |
| 신뢰도 | 3단계와 `Job.confidence`, 로봇 JSON만 **0~100(%)** |
| 인식 결과 ID | 1단계가 글자는 `t1, t2, …`, 기호는 `s1, s2, …`로 붙임. 1단계가 놓치고 VLM만 읽은 표기는 2단계가 `v1, v2, …`로 붙임 |
| 작업자 확인 대상 | 인식 결과 ID(`t*`, `s*`, `v*`), `part`, `welding_condition`, `interpretation` |
| 확인 이유 | 3단계 `needs_review.reason`은 2단계 `Conflict.type`과 같은 이름 + `low_visual_confidence`, `vlm_inconsistent`, `missing_required` |
| 기호 label | 워크스페이스 사전의 `code`. 사전에 없는 기호는 `"unknown"` |
| 모르는 값 | 필드를 빼지 말고 `null` (스키마에 null 허용으로 표시된 필드만) |
| 시간 | ISO 8601, 시간대 포함. 백엔드 API와 같이 UTC(`Z`)로 씀 |
| 필드 추가 | 스키마에 없는 필드는 오류. 필요하면 스키마를 먼저 고침 |

## 점검

```bash
python -m vw_shared.validate     # backend 가상환경 (requirements.txt가 shared를 설치)
cd shared && python -m pytest -q # CI와 같음
```

- 예시가 스키마에 맞는지
- 단계 사이 규칙: 참조한 ID가 인식 결과(1단계, `v*`)에 있는지, `char_probs` 개수가 글자 수와 같은지, `overall`이 세 신뢰도의 최솟값인지, 필수 값이 없으면 `passed`가 false이고 `needs_review`에 들어 있는지 등 (`semantic_errors()`)
- 예시가 팀원 시드 DB와 맞는지: 기호가 `demo` 사전에 있는지, 부재가 `block_a1` 조립 트리에 있는지, 용접 조건이 표준 용접 기준표에 있는지
- 2단계 입력 예시가 시드 DB를 그대로 옮긴 것인지
- 통과(`awaiting_approval`)한 결과가 로봇 JSON 스키마도 통과하는지
- 팀원 Pydantic 모델(`Job`, `RobotOutput`, `SymbolEntry` 등)과 맞는지는 `backend/tests/test_pipeline.py`가 점검
- 예시끼리 이어지는지: 1·2·3단계 예시 = `analysis` 묶음, revision 1 → 2

## 스키마를 바꿀 때

1. 스키마와 예시를 같이 고치고 `python -m vw_shared.validate`와 각 단계 테스트가 통과하는지 확인
2. PR로 올리고, **그 스키마를 만드는 쪽과 쓰는 쪽 담당 모두** 확인 후 머지
3. 기존 필드의 이름·의미를 바꾸면 `analysis.schema.json`의 `schema_version`을 올림
4. 팀원 계약(`backend/app/schemas.py`)의 `Job`·`SymbolEntry`·`AssemblyNode`·`WeldingStandard`가 바뀌면 `context_input.schema.json`, `to_job_fields()`, 이 문서의 연결 표를 같이 고침 (`backend/tests/test_pipeline.py`가 어긋나면 실패)

## 아직 정할 것

- **셀 형태·각장 (PAC 과제)**: 팀원 계약 `Job`에 `cell`(좌·우 각각 `slit`·`slot`·`collar_front`·`collar_back`·`scallop` 목록)과
  `leg_lengths`(수기 각장 `F`·`V`·`S` + mm, 예: `F5.5` → 3F 용접장 각장 5.5mm)가 생겼고 로봇 JSON에도 들어감.
  파이프라인 어느 단계가 셀 형태를 판별하고 각장을 읽을지, `to_job_fields()`에서 어떻게 채울지 정해야 함 (지금은 비어 있는 값)

- 사진 여러 장일 때 "가장 최근 Analysis"로 충분한지, 사진들의 결과를 합칠지
- `analyze`·`review` API(지금 501) 연결: 이미지 저장, Analysis 저장, 사진 → `image_id`가 정해지면 `app/pipeline.py`를 호출
- `ReviewRequest(manual).values`의 키: 지금 백엔드 테스트(`test_jobs.py`)는 `{"raw_text": …}`를 쓰는데, 파이프라인은 `t*`·`s*`·`v*`·`part`·`welding_condition`·`interpretation`만 받음 (그 밖의 키는 `AnalysisError`)
- `Analysis`를 저장·조회하는 API를 둘지 (GUI가 사진 위 `bbox`·후보를 그리려면 필요) — 예: `GET /workspaces/{workspace_id}/jobs/{job_id}/analyses`
- 이미지 업로드(`POST .../images`) 응답의 `image_id` 형식
