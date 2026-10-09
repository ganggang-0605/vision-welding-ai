# 시각 인식 로드맵 (`visual_recognition`)

표기 정보 해석 프로세스의 **[1단계] 시각 인식**(a 전처리 → b OCR 문자 인식 / c 기호 인식) 개발 계획입니다.
2단계(DB 기반 맥락 해석)와 3단계(신뢰도 산출)가 이 단계의 출력을 그대로 받아 쓰므로, **출력 형식을 먼저 지키고 정확도는 그 위에서 올린다**는 원칙으로 진행합니다.

---

## 1. 범위와 출력 형식

| 구성 | 파일 | 출력 |
| --- | --- | --- |
| a. 전처리 | `backend/app/pipeline/preprocess/denoise.py` | `(보정된 이미지, 보정 강도 0~1)` |
| b. 문자 인식 | `backend/app/pipeline/recognition/ocr.py` | `[{"text", "prob", "bbox"}]` |
| c. 기호 인식 | `backend/app/pipeline/recognition/symbols.py` | `[{"label", "prob", "bbox"}]` |

- `bbox`는 `[x1, y1, x2, y2]`, **원본 이미지 좌표 기준**으로 통일합니다. 전처리에서 원근을 펴더라도 결과를 원본 좌표로 되돌려 줘야 작업자 확인 화면에서 위치를 표시할 수 있습니다.
- `prob`는 0~1. 3단계가 0~100%로 바꿔 시각 인식 신뢰도에 씁니다.
- 아래 필드는 **추가 제안**입니다(기존 필드는 그대로, 팀 합의 후 반영).
  - `candidates`: 확률이 낮은 글자의 유사 문자 후보 (예: `[{"text": "B", "prob": 0.31}]`) → README 4번 작업자 확인에서 사용
  - `source`: 어느 모델이 낸 결과인지 (`paddleocr` / `parseq` / `trocr` / `yolox`)

## 2. 사용할 오픈소스

README의 적용 모델과 사용 가능 오픈소스 목록을 대조해 정했습니다. 모두 상용 이용이 가능한 허용형 라이선스(MIT · Apache-2.0 · BSD)입니다.

### 채택 (주 경로)

| 구성 | 오픈소스 | 라이선스 | 역할 |
| --- | --- | --- | --- |
| a. 전처리 | **OpenCV** | Apache-2.0 | 대비 보정(CLAHE), 노이즈 제거, 표기 영역 원근 보정. 모든 전처리의 기반 |
| a. 전처리 | **Retinexformer** | MIT | 어둡거나 그늘진 현장 사진의 조도 보정 |
| a. 전처리 | **UVDoc** | MIT | 곡면·휜 강판처럼 OpenCV 원근 보정으로 안 펴지는 표기의 기하 보정 |
| a. 전처리 | **SIHR** | BSD-2-Clause | 금속 표면의 반사광 제거 |
| b. 문자 | **PaddleOCR** | Apache-2.0 | 글자 영역 검출 + 1차 인식. 주력 OCR |
| b. 문자 | **PARSeq** | Apache-2.0 | 각인·스텐실 같은 현장 글씨체에 맞춰 추가 학습하는 인식기 |
| b. 문자 | **TrOCR** (HF transformers) | MIT | 마커 손글씨 표기 재인식 |
| c. 기호 | **YOLOX** | Apache-2.0 | 용접 기호·그림 검출 |
| 데이터 | **synthtiger** | MIT | 부재 번호 등 글자 이미지 합성 → PARSeq 학습 데이터 |
| 데이터 | **straug** | Apache-2.0 | 글자 이미지 증강 (PARSeq 학습용) |
| 데이터 | **albumentations** | MIT | 얼룩·스크래치·반사 증강 (YOLOX 학습용) |
| 데이터 | **GroundingDINO** | Apache-2.0 | 기호 라벨 초안 자동 생성 |

목록에서 굵게 표시된 항목(Retinexformer, UVDoc, PaddleOCR, PARSeq, TrOCR, synthtiger, straug, YOLOX)은 한 흐름으로 이어집니다.
`조도 보정 → 기하 보정 → 글자 검출(PaddleOCR) → 인식(PARSeq, 합성+증강 데이터로 추가 학습) / 손글씨(TrOCR) → 기호(YOLOX)`

### 예비 (주 경로가 막힐 때)

| 오픈소스 | 쓰는 경우 |
| --- | --- |
| doctr | PaddlePaddle 설치·실행이 막힐 때의 OCR 대안 (PyTorch 기반이라 Mac에서 다루기 쉬움) |
| OpenOCR | PaddleOCR 인식 정확도가 부족할 때 비교 후보 |
| Specular-Removal | SIHR로 반사가 충분히 안 지워질 때 |
| PaddleDetection (RT-DETR) | YOLOX 검출 정확도가 부족할 때 비교 후보 |

### 제외

| 오픈소스 | 제외 이유 |
| --- | --- |
| DiffBIR, Real-ESRGAN | 복원 과정에서 원래 없던 획을 만들어 낼 수 있음. OCR이 틀려도 확률이 높게 나와 신뢰도 산출을 망가뜨림 |
| mmocr, ocrs, mmdetection | 채택한 모델과 역할이 겹치고 설정 부담이 큼 |
| InternVL, Qwen3-VL | 2단계(맥락 해석) 영역. 교차 검증용 VLM은 Claude API(`context/vlm_claude.py`)로 이미 연결됨 |
| ultralytics (YOLO) | 사용 가능 목록에 없고 AGPL-3.0. README의 "YOLO"는 YOLOX로 대체 |

## 3. 개발 환경

- **Python 3.12 가상환경 필수.** PaddlePaddle은 Python 3.14용 설치 파일이 없음(3.12용 3.3.1은 있음, 2026-10-09 확인). 1단계 패키지는 CI가 느려지지 않도록 `backend/requirements-vision.txt`로 분리.
- Mac(Apple Silicon)에서는 PaddlePaddle이 CPU로 동작하고, PyTorch 계열(PARSeq, TrOCR, YOLOX, Retinexformer)은 MPS 가속 사용 가능.
- YOLOX·PARSeq 학습은 Mac에서 느리므로 Colab 등 GPU 환경에서 학습하고, 가중치만 `weights/`에 받아 씀 (`.gitignore` 처리됨).
- 현장 사진은 `data/raw/`에 둠 (`.gitignore` 처리됨, 팀 공유는 드라이브로). 정답 라벨은 `data/annotations/`에 커밋.

## 4. 단계별 계획

### Phase 0 · 환경과 평가 데이터 (가장 먼저)
- [x] Python 3.12로 `backend/.venv` 재생성, 1단계 패키지 설치 (`backend/requirements-vision.txt`)
- [x] 정답 형식(`data/annotations/README.md`)과 점검 스크립트(`vision/tools/check_dataset.py`) 준비
- [ ] 실제 표기 사진 수집: 각인, 스텐실, 마커 손글씨, 기호가 섞인 사진 **최소 50~100장**
- [ ] 사진별 정답 작성 (`data/annotations/`): 글자 내용 + 위치, 기호 라벨 + 위치
- [ ] 정답 중 20%는 평가 전용으로 떼어 두고 학습에 쓰지 않기 (점검 스크립트가 `split`을 자동 배정)
- **완료 기준:** 패키지 설치 완료, 정답이 달린 사진 30장 이상

> 프로젝트의 가장 큰 위험 요소는 데이터입니다. 현재 저장소에 샘플 사진이 없으므로 Phase 0은 줄이지 않습니다.

### Phase 1 · 문자 인식 기본 버전 + 평가 스크립트
- [ ] `ocr.py`에 PaddleOCR 연결, 출력 형식대로 반환
- [ ] 평가 스크립트: 글자 단위 오류율(CER), 표기 단위 정확도, 사진당 처리 시간
- [ ] 2단계·3단계 담당에게 실제 OCR 결과 샘플 전달
- **완료 기준:** 원본 사진 → 글자·확률·위치 출력, 평가 숫자 확인 가능

> 이 결과물이 나오면 2단계 팀원이 실제 데이터로 작업할 수 있으므로 **가장 먼저 넘겨야 할 산출물**입니다.

### Phase 2 · 전처리
- [ ] OpenCV 기본 보정: CLAHE, 노이즈 제거, 표기 영역 원근 보정
- [ ] Retinexformer 조도 보정 (밝기가 기준 이하인 사진에만 적용)
- [ ] UVDoc 기하 보정 (곡면 표기에만 적용)
- [ ] SIHR 반사 제거 (반사 영역이 감지된 사진에만 적용)
- [ ] 보정 강도(0~1) 계산: 어떤 보정을 얼마나 적용했는지 합산 → 3단계에서 신뢰도를 깎는 근거
- [ ] 전처리 후 좌표를 원본 좌표로 되돌리는 변환 유지
- **완료 기준:** 전처리를 켰을 때와 껐을 때 정확도 비교표. 나빠지는 보정은 끔

### Phase 3 · 기호 인식
- [ ] 라벨 체계 확정: 워크스페이스 문자/기호 사전(`data/seed/workspaces/demo/symbol_dictionary.json`)의 `kind: symbol` 항목부터 시작
- [ ] GroundingDINO로 라벨 초안 생성 → 사람이 수정
- [ ] albumentations로 얼룩·스크래치·반사 증강
- [ ] YOLOX 학습 후 `symbols.py`에 연결
- [ ] 문자와 기호가 겹치는 경우 처리 규칙 (예: ▲가 OCR 글자로도 잡힐 때 어느 쪽을 남길지)
- **완료 기준:** 평가 사진에서 기호 검출 정확도(mAP@0.5) 확인 가능

> **워크스페이스 이식성:** README는 조선소마다 자체 기호를 등록해 쓰는 것을 목표로 합니다. YOLOX는 학습한 기호만 알기 때문에, 해커톤에서는 예시 기호 세트로 학습하고, 이후에는 "기호 영역만 찾는 검출기 + 등록된 기호 이미지와 비교하는 분류" 구조로 확장하는 방향을 제안합니다.

### Phase 4 · 현장 글씨체 대응과 후보 제시
- [ ] synthtiger로 부재 번호 형식(예: `P-1`, `A1/L1/M2`)의 글자 이미지 합성, straug로 증강
- [ ] PARSeq 추가 학습 → PaddleOCR 인식기와 정확도 비교, 더 나은 쪽 채택
- [ ] 손글씨로 보이거나 확률이 낮은 글자 영역만 잘라 TrOCR로 재인식
- [ ] 확률이 낮은 글자에 유사 문자 후보(`candidates`) 붙이기 (0/O, 8/B, 1/I/l, 5/S 등)
- [ ] 확률 보정 점검: 확률 0.9로 나온 결과가 실제로 90% 정도 맞는지 확인하고 필요하면 조정
- **완료 기준:** 평가 세트에서 Phase 1 대비 정확도 향상 확인, 낮은 확률 결과에 후보 목록 포함

### Phase 5 · 통합과 시연 준비
- [ ] `run_pipeline`으로 1~3단계 끝까지 연결
- [ ] OCR ↔ VLM 교차 검증: Claude API로 같은 사진을 읽게 해 OCR 결과와 일치하는지 비교 → 시각 인식 신뢰도 근거 (3단계 담당과 협업)
- [ ] 시연용 사진 세트 구성: 잘 되는 사진 + 어려운 사진(작업자 확인으로 넘어가는 사례)
- [ ] 사진당 처리 시간 측정, 필요하면 무거운 보정은 조건부로만 실행
- **완료 기준:** 사진 한 장 입력 → 1단계 결과가 2·3단계까지 이어져 출력

## 5. 평가 지표

| 대상 | 지표 |
| --- | --- |
| 문자 인식 | 글자 단위 오류율(CER), 표기 단위 정확도(완전 일치 비율) |
| 기호 인식 | mAP@0.5, 기호별 재현율 |
| 신뢰도 | 확률과 실제 정답률의 차이(보정 오차) |
| 전처리 | 켰을 때와 껐을 때의 정확도 차이 |
| 속도 | 사진당 처리 시간 |

## 6. 위험 요소와 대응

| 위험 | 대응 |
| --- | --- |
| 실제 현장 사진 부족 | Phase 0 최우선. 부족하면 synthtiger 합성 + 직접 촬영(강판·마커 모형)으로 보충 |
| PaddlePaddle 설치·실행 문제 | Python 3.12 사용, 막히면 doctr로 대체 |
| Mac에서 학습이 느림 | Colab 등 GPU 환경에서 학습, 추론만 로컬 |
| 전처리가 오히려 정확도를 떨어뜨림 | 보정은 조건부 적용, Phase 2 비교표로 판단 |
| 사전학습 가중치·데이터셋 라이선스 | 코드 라이선스와 별개이므로 사용하는 가중치마다 출처와 라이선스 기록 |

## 7. 팀과 합의할 사항

- [ ] 출력에 `candidates`, `source` 필드 추가 여부
- [ ] `bbox`를 원본 이미지 좌표 기준으로 통일
- [ ] README 적용 모델 표의 "YOLO"를 "YOLOX"로 수정
- [ ] 기호 라벨 체계와 워크스페이스 기호 사전의 연결 방식
- [ ] 현장 사진 공유 위치 (`data/raw/`는 저장소에 올라가지 않음)

## 8. 일정이 빠듯할 때 줄이는 순서

1. UVDoc, SIHR → 해당 사진이 있을 때만 추가
2. PARSeq 추가 학습(synthtiger, straug 포함) → PaddleOCR 인식기 그대로 사용
3. Retinexformer → OpenCV 보정만 사용
4. YOLOX 학습 → 기호 인식을 Claude API에 임시로 맡김 (시연은 가능, 정확도는 낮음)
5. TrOCR → PaddleOCR 하나만 사용

**Phase 0(실제 사진과 정답)과 Phase 1(PaddleOCR 기본 버전 + 평가 스크립트)은 줄이지 않습니다.** 이 둘이 없으면 다른 단계의 개선 여부를 판단할 수 없습니다.
