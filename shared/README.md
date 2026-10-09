# shared — 파이프라인 공용 스키마

표기 정보 해석의 **1단계(시각 인식) → 2단계(DB 기반 맥락 해석) → 3단계(신뢰도 산출)**가 서로 주고받는 데이터 형식입니다.
1단계와 2단계를 폴더를 나눠 따로 개발하기 전에 형식을 먼저 정해 둡니다. 3단계는 나중에 개발하지만, 1·2단계가 무엇을 미리 출력해 둬야 하는지 알 수 있도록 형식은 지금 정합니다.

```
스키마 설계 (shared/)  →  1단계 · 2단계 · GUI 폴더 분리 개발  →  3단계 개발
```

> **GUI ↔ 백엔드 계약(워크스페이스·프로젝트·작업·작업자 확인·승인)은 [`backend/app/schemas.py`](../backend/app/schemas.py)가 기준입니다.**
> 여기서는 그 계약에 없는 파이프라인 내부 형식만 정의하고, 결과를 그 계약의 `Job` 필드로 옮기는 방법을 정합니다.

형식은 [JSON Schema 2020-12](https://json-schema.org/)로, `schemas/robot_output.schema.json`과 같습니다.

## 데이터 흐름

```
POST /workspaces/{workspace_id}/jobs/{job_id}/analyze
                                   워크스페이스 사전 · 프로젝트 조립 트리 · 공통 용접 기준
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
| [`context_result.schema.json`](schemas/context_result.schema.json) | **[2단계]** 사전 대조, 부재·조립 경로, 용접 조건, DB 불일치, VLM 해석 | 2단계 | 3단계, 백엔드 |
| [`confidence_report.schema.json`](schemas/confidence_report.schema.json) | **[3단계]** 세 가지 신뢰도, 근거, 작업자 확인 항목 | 3단계 (이후) | 백엔드, GUI |
| [`analysis.schema.json`](schemas/analysis.schema.json) | 사진 한 장의 해석 결과 (1·2·3단계 묶음 + 작업자 수정) | 파이프라인 (`run_pipeline`) | 백엔드 |

## 역할과 연결

| 테이블 | 역할 | 연결 |
| --- | --- | --- |
| **VisionResult** (1단계) | 글자·기호를 찾아 읽고 `t1`, `s1` 같은 ID를 붙임 | 2단계, 3단계, GUI가 이 ID로 글자·기호를 가리킴 |
| **ContextResult** (2단계) | 1단계 결과를 사전·조립 트리·용접 기준과 대조해 의미를 해석 | `ref_ids`로 1단계 결과를 가리킴 |
| **ConfidenceReport** (3단계) | 신뢰도 세 가지를 계산하고 작업자 확인 항목을 고름 | `factors`가 1·2단계 값을 가져옴 |
| **Analysis** | 위 세 결과를 묶은 사진 한 장의 해석 결과 | `workspace_id`·`project_id`·`job_id`로 팀원 `Job`에 연결. 작업자 확인 때마다 `revision`이 늘어난 새 Analysis |

**연결의 중심은 1단계가 붙이는 ID(`t1`, `s1`)입니다.** 1단계가 ID를 바꾸거나 빠뜨리면 뒤 단계가 모두 깨집니다.
작업자 확인(재해석·직접 해석)은 2단계부터 다시 돌리므로, 1단계 결과와 ID는 작업이 끝날 때까지 그대로 유지됩니다.

## 팀원 API 계약과의 연결

### 파이프라인이 읽는 것

| 팀원 계약 (`backend/app/schemas.py`) | 파이프라인에서 쓰는 곳 |
| --- | --- |
| `SymbolEntry.code` (워크스페이스 사전) | 1단계 `SymbolDetection.label`, 2단계 `DictionaryMatch.code` |
| `SymbolEntry.welding_joint_type` | 2단계 `WeldingCondition.joint_type` 판별 |
| `AssemblyNode` (프로젝트 조립 트리) | 2단계 `Part` (`node_id`, `assembly_path`, `level`, `found_in_tree`) |
| `WeldingStandard` (공통 표준 용접 기준) | 2단계 `WeldingCondition` (`standard_matched`) |
| `ReviewRequest` `action: reinterpret` + `context` | 2단계부터 다시 해석, `ContextResult.user_context` |
| `ReviewRequest` `action: manual` + `values` | `Analysis.corrections` (`values`의 키 = `target`, 값 = `value`) |

### 파이프라인 결과 → `Job` 필드 (`to_job_fields()`)

| `Job` 필드 | 채우는 값 |
| --- | --- |
| `status` | 3단계 `passed`가 true면 `awaiting_approval`, 아니면 `needs_review` (3단계 전에는 항상 `needs_review`) |
| `assembly_path` | 2단계 `part.assembly_path` (작업자가 `part`를 고쳤으면 그 값) |
| `marking.raw_text` | 1단계 글자·기호를 읽는 순서(줄 단위, 왼→오른)로 이어 붙인 것 |
| `marking.symbols` | 1단계 기호 `label` 목록 |
| `marking.interpretation` | 2단계 `vlm.interpretation` (VLM이 꺼져 있으면 사전 대조 의미를 이어 붙임) |
| `welding_condition` | 2단계 `welding_condition`의 6개 필드 (`thickness_mm`·`standard_matched`·`source`는 빠짐) |
| `confidence` | 3단계 `visual`·`db_consistency`·`vlm_reasoning`·`overall` |
| `evidence` | 3단계 `evidence[].message` |
| `needs_review` | 3단계 `needs_review[].message` |

`to_job_fields()`는 [`validate.py`](validate.py)에 기준 구현이 있고, 결과가 팀원 `Job` 모델을 통과하는지 점검합니다. 백엔드 `analyze`·`review` 구현 때 그대로 가져다 쓸 수 있습니다.

> 이름 주의: 팀원 계약의 `Job.marking`(표기 원문·해석 요약)과 구분하려고, 2단계의 사전 대조 결과는 `DictionaryMatch`(`dictionary_matches`)라고 부릅니다.

## 사진 한 장이 지나가는 순서 (예시 파일)

[`examples/`](examples/)에 팀원 데모 시드(`demo` 워크스페이스, `hull_3201` 호선)를 기준으로 한 흐름이 들어 있습니다.
사진 속 표기는 부재 `P-1`, 손글씨 `FW`, 판 두께 `t=10`, 현장 용접 기호 `▲`입니다.

| 순서 | 무슨 일 | 예시 파일 |
| --- | --- | --- |
| 1 | 1단계: `t1` "P-1", `t2` "FW"(62%, 후보 FW·EW), `t3` "t=10", `s1` "▲" | `vision_result.example.json` |
| 2 | 2단계: 부재 P-1(A1/L1/M2/S1/P-1), FW → 필렛 용접, 판 두께 10mm → 220-260A | `context_result.example.json` |
| 3 | 3단계: overall 62%로 기준 80% 미달, `t2` 확인 필요 | `confidence_report.example.json` |
| 4 | 세 결과를 묶음 (revision 1) → `Job.status = needs_review` | `analysis.example.json` |
| 5 | 작업자가 `t2`를 FW로 확인 → revision 2, overall 88%로 통과 → `Job.status = awaiting_approval` | `analysis_revision2.example.json` |

## 공통 규칙

| 항목 | 규칙 |
| --- | --- |
| 좌표 | `bbox`는 `[x1, y1, x2, y2]`, **원본 이미지 픽셀 좌표**. 전처리로 이미지를 폈더라도 원본 좌표로 되돌려서 출력 |
| 확률 | 1·2단계는 **0~1** (`prob`, `score`, `consistency`) |
| 신뢰도 | 3단계와 `Job.confidence`, 로봇 JSON만 **0~100(%)** |
| 인식 결과 ID | 1단계가 글자는 `t1, t2, …`, 기호는 `s1, s2, …`로 붙임 |
| 기호 label | 워크스페이스 사전의 `code`. 사전에 없는 기호는 `"unknown"` |
| 모르는 값 | 필드를 빼지 말고 `null` (스키마에 null 허용으로 표시된 필드만) |
| 시간 | ISO 8601, 시간대 포함 |
| 필드 추가 | 스키마에 없는 필드는 오류. 필요하면 스키마를 먼저 고침 |

## 점검

```bash
backend/.venv/bin/pip install jsonschema
backend/.venv/bin/python shared/validate.py
```

- 예시가 스키마에 맞는지
- 단계 사이 규칙: 참조한 ID가 1단계 결과에 있는지, `char_probs` 개수가 글자 수와 같은지, `overall`이 세 신뢰도의 최솟값인지 등 (`semantic_errors()`)
- 예시가 팀원 시드 DB와 맞는지: 기호가 `demo` 사전에 있는지, 부재가 `hull_3201` 조립 트리에 있는지, 용접 조건이 표준 용접 기준표에 있는지
- `to_job_fields()` 결과가 팀원 `Job` 모델(Pydantic)을 통과하는지
- 예시끼리 이어지는지: 1·2·3단계 예시 = `analysis` 묶음, revision 1 → 2

## 스키마를 바꿀 때

1. 스키마와 예시를 같이 고치고 `validate.py`가 통과하는지 확인
2. PR로 올리고, **그 스키마를 만드는 쪽과 쓰는 쪽 담당 모두** 확인 후 머지
3. 기존 필드의 이름·의미를 바꾸면 `analysis.schema.json`의 `schema_version`을 올림
4. 팀원 계약(`backend/app/schemas.py`)의 `Job`·`SymbolEntry`·`AssemblyNode`·`WeldingStandard`가 바뀌면 `to_job_fields()`와 이 문서의 연결 표를 같이 고침

## 아직 정할 것

- `Analysis`를 저장·조회하는 API를 둘지 (GUI가 사진 위 `bbox`·후보를 그리려면 필요) — 예: `GET /workspaces/{workspace_id}/jobs/{job_id}/analyses`
- 이미지 업로드(`POST .../images`) 응답의 `image_id` 형식
- `to_job_fields()`를 백엔드(`backend/app/`)로 옮길지
- `validate.py`를 CI에 넣을지 (`jsonschema`를 `backend/requirements.txt`에 추가해야 함)
