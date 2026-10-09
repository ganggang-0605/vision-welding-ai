# Phase 1 기준 성능 (steel-ocr)

사전 학습된 PaddleOCR을 **추가 학습 없이** 그대로 썼을 때의 점수입니다. 이후 전처리(Phase 2)·추가 학습(Phase 4)이 이 점수보다 나아지는지 비교하는 기준입니다.

- 측정일: 2026-10-09
- 데이터: [steel-ocr-dataset](../DATASETS.md)의 평가용 사진 110장(val 96 + test 14), 표기 168개 / 잘라낸 글자 이미지 160개. 학습용(train)은 쓰지 않음
- 환경: MacBook (Apple Silicon) CPU, Python 3.12, PaddleOCR 3.7.0
- 설정: `vision/src/vision/ocr.py`의 `DEFAULT_CONFIG`
  - 검출 `PP-OCRv6_small_det` (긴 변 1280px로 줄여 검출), 인식 `PP-OCRv6_medium_rec`, 뒤집힌 글자 줄 보정 켬

## 결과

| 평가 | 글자 오류율 (CER) ↓ | 표기 완전 일치 ↑ | 표기 찾음 | 위치 IoU ≥ 0.5 | 사진당 시간 |
| --- | --- | --- | --- | --- | --- |
| **사진 전체 (검출 + 인식)** | **0.374** | **10.7%** | 83.3% | 80.4% | 0.82초 |
| 사진 전체 + 허용 글자 후처리 | 0.315 | 26.2% | 83.3% | 80.4% | 0.82초 |
| 잘라낸 글자만 (인식만) | 0.168 | 10.0% | — | — | 0.04초 |
| 잘라낸 글자 + 허용 글자 후처리 | 0.102 | 45.6% | — | — | 0.04초 |

- **허용 글자 후처리**: 표기에 쓰일 수 있는 글자(steel-ocr은 `- 0~9 A B G M N S X Y b s` 21자)만 남기고, 없는 글자는 비슷한 글자로 바꿈 (`I`→`1`, `O`→`0` 등). 평가 옵션(`--charset`)으로만 측정했고 기본 설정에는 넣지 않음 — 조선소 표기의 글자 범위가 정해지면 적용
- 사진 전체에서 정답 위치가 없는 글자도 찾아내는데(169개), 라벨이 안 붙은 표기(예: `AYa1`)도 많아서 오검출로 보지 않음

## 설정 비교 (사진 40장)

| 검출 | 인식 | 긴 변 | 뒤집힘 보정 | CER | 완전 일치 | 사진당 시간 |
| --- | --- | --- | --- | --- | --- | --- |
| PP-OCRv6_medium (PaddleOCR 기본) | PP-OCRv6_medium | 원본 4032 | 끔 | 1장 시험: 전혀 못 읽음 | — | 21초 |
| PP-OCRv5_mobile | PP-OCRv5_server | 960 | 끔 | 0.480 | 10.6% | 0.52초 |
| PP-OCRv5_mobile | PP-OCRv5_server | 1280 | 끔 | 0.486 | 14.9% | 0.80초 |
| PP-OCRv5_mobile | PP-OCRv5_server | 1920 | 끔 | 0.633 | 12.8% | 1.26초 |
| PP-OCRv5_server | PP-OCRv5_server | 1280 | 끔 | 0.482 | 10.6% | 5.50초 |
| PP-OCRv6_small | PP-OCRv5_server | 1280 | 끔 | 0.458 | 17.0% | 0.83초 |
| PP-OCRv6_small | PP-OCRv5_server | 1280 | **켬** | 0.367 | 17.0% | 0.86초 |
| **PP-OCRv6_small** | **PP-OCRv6_medium** | **1280** | **켬** | **0.294** | 12.8% | 0.81초 |

인식 모델만 비교 (잘라낸 글자 160개): `en_PP-OCRv5_mobile` 0.300 · `PP-OCRv5_mobile` 0.214 · `PP-OCRv5_server` 0.185 · `PP-OCRv6_small` 0.196 · **`PP-OCRv6_medium` 0.168**

## 알게 된 것

1. **원본 크기 그대로 검출하면 안 됨.** 4000px 사진을 그대로 넣으면 21초가 걸리고 큰 손글씨를 잘게 쪼개 엉뚱하게 읽음. 긴 변 1280px가 속도·정확도 균형이 가장 좋음
2. **뒤집힌 표기가 많음.** 쌓아 둔 부재라 표기가 180° 돌아간 사진이 많고 (`B1Sb30N-41` → `H-NOE9518`), 보정을 켜면 CER 0.46 → 0.37
3. **헷갈리는 글자가 대부분의 오류.** 잘라낸 글자 기준 `1→I` 88번, `b→6` 42번, `b→B` 8번, `1→/` 7번, `S→5` 6번. README의 "유사 문자 후보"가 실제로 필요함
4. **확률을 믿을 수 없음.** 확률 0.9 이상으로 나온 표기 86개 중 완전히 맞은 것은 16%뿐 (예: `B1Sb30N-16`을 `B15630N-16`으로 읽고 확률 0.997). 3단계가 이 확률을 그대로 시각 인식 신뢰도로 쓰면 안 됨
5. **표기를 못 찾는 경우 17%.** 주로 세로로 찍힌 사진, 초점이 크게 흐린 사진

## 다음에 할 것 (로드맵 반영)

- Phase 2: 세로·흐린 사진 대응 (원근 보정, 대비 보정)
- Phase 4: steel-ocr 학습용(train) 잘라낸 글자 349개로 인식기 추가 학습 → `b/6`, `S/5` 해결 기대
- Phase 4: 워크스페이스별 허용 글자 후처리, 유사 문자 후보(`candidates`), 확률 보정
- 조선소 표기 사진(`data/annotations/`)이 모이면 같은 스크립트로 다시 측정: `eval_ocr.py --dataset annotations`
- PAC 과제의 수기 각장(`F5.5` 등)은 steel-ocr에 없는 글자(`F`, `V`, `.`)라 별도 사진으로 평가 필요

## 다시 측정하기

```bash
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
backend/.venv/bin/python vision/tools/eval_ocr.py --out vision/reports/runs/steel-ocr_det.json
backend/.venv/bin/python vision/tools/eval_ocr.py --charset steel-ocr
backend/.venv/bin/python vision/tools/eval_ocr.py --mode rec
```

실제 `VisionResult` 출력 예시(2단계 전달용): [`sample_vision_result.json`](sample_vision_result.json) — test 사진 `eval_IMG_0787.jpg`, 정답 `B1Sb30N-16`

## 원격 실행 (Claude Managed Agents)

맥북 대신 Anthropic 서버의 컨테이너에서 같은 평가를 돌릴 수 있습니다. 비용은 `.env`의 `ANTHROPIC_API_KEY` 계정 크레딧에서 나갑니다.

```bash
backend/.venv/bin/python vision/tools/remote_eval.py              # 10장 시험, 예산 상한 $5
backend/.venv/bin/python vision/tools/remote_eval.py --eval "--prep none"   # 110장 전체 (--limit 없으면 전체)
```

- 2026-10-09 시험 (10장): 전체 4분(설치·데이터 받기 포함, 평가 26초), 비용 $0.16. 컨테이너는 CPU 4개·메모리 15GB, GPU 없음
- 같은 10장의 예측이 맥북 결과와 **완전히 같음**
- Linux에서는 PaddlePaddle 3.3.1의 CPU 가속(oneDNN)이 PP-OCRv6 검출 모델에서 오류를 내서, `OcrConfig.enable_mkldnn=False`가 기본
