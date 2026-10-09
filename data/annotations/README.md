# 시각 인식 정답 데이터

현장 사진마다 "실제로 쓰여 있는 글자와 기호"를 적어 둔 정답 파일입니다. 1단계 모든 모델의 정확도를 이 정답으로 잽니다.

## 파일 위치

| 무엇 | 위치 | 저장소 |
| --- | --- | --- |
| 사진 원본 | `data/raw/<사진 이름>` | 올리지 않음 (`.gitignore`), 팀 공유는 드라이브로 |
| 정답 | `data/annotations/<data/raw 기준 경로에서 확장자를 빼고 / 를 _ 로 바꾼 것>.json` | 올림 |

예: `data/raw/IMG_0001.jpg` → `data/annotations/IMG_0001.json`, `data/raw/pac/block/1.png` → `data/annotations/pac_block_1.json`

## 정답 형식

```json
{
  "image": "IMG_0001.jpg",
  "conditions": ["dark", "glare"],
  "texts": [
    { "text": "A1-L1-M2-S1-P-1", "style": "stamped", "bbox": null },
    { "text": "FW", "style": "handwritten", "bbox": [120, 340, 210, 395] }
  ],
  "symbols": [
    { "label": "▲", "bbox": null }
  ]
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `image` | O | `data/raw/` 기준 사진 경로 (예: `IMG_0001.jpg`, `pac/block/1.png`) |
| `split` | | `train` 또는 `eval`. **비워 두면 점검 스크립트가 자동으로 정해서 적어 줌** (약 20%가 `eval`). 한번 정해지면 바꾸지 않기 |
| `conditions` | | 촬영 조건. `dark`(어두움) · `glare`(반사) · `curved`(곡면) · `skewed`(비스듬함) · `stain`(얼룩·오염) · `scratch`(스크래치) · `blur`(흔들림). 전처리 효과 비교에 씀 |
| `texts` | O | 사진에 있는 표기 글자 목록. 없으면 `[]` |
| `texts[].text` | O | 보이는 그대로 적기. 대소문자·하이픈·슬래시 그대로 |
| `texts[].style` | O | `stamped`(각인) · `stencil`(스텐실) · `handwritten`(마커 손글씨) · `printed`(인쇄·라벨) |
| `texts[].bbox` | | `[x1, y1, x2, y2]` 원본 사진 픽셀 좌표. **처음에는 `null`로 둬도 됨** — Phase 1에서 PaddleOCR이 위치 초안을 만들면 그때 채움 |
| `symbols` | O | 기호 목록. 없으면 `[]` |
| `symbols[].label` | O | 워크스페이스 문자/기호 사전(`data/seed/workspaces/<id>/symbol_dictionary.json`)의 `code`와 같은 값. 사전에 없거나 종류를 아직 못 정한 기호는 `unknown` |
| `symbols[].bbox` | | `texts[].bbox`와 같음 |

## 적는 규칙

- 사람이 봐도 확실히 읽을 수 없는 글자는 `?`로 적기 (예: `P-?`). 평가에서 그 글자는 빼고 계산합니다.
- 한 줄로 이어진 표기는 하나로 적고, 떨어져 있는 표기는 따로 적기.
- 사진을 돌리거나 자르지 말고 원본 그대로 두기 (bbox 좌표가 원본 기준).
- 휴대폰 사진에 EXIF 회전 값이 있으면 **회전을 적용한 방향(사진 뷰어에 보이는 방향)** 기준으로 좌표를 적기. 파이프라인(OpenCV)과 화면(브라우저)이 그렇게 읽습니다.
- 화살표는 방향과 관계없이 `→`, 먹매김 십자·T자는 `+`로 적고, 상자는 화살촉과 이어진 선까지 감싸기.
- 셀 끝 절단부(론지 관통부의 slit·slot·collar·scallop)는 종류가 정해질 때까지 `unknown`으로 위치만 적기. PAC 사진 7장(`pac_*.json`)의 `unknown`은 모두 셀 끝 절단부입니다.

## 점검

```bash
backend/.venv/bin/python vision/tools/check_dataset.py
```

형식 오류, 사진 누락, 사전에 없는 기호를 알려 주고 (기본은 `demo` 워크스페이스 사전, `--workspace`로 바꿈), `split`이 비어 있으면 채워 넣은 뒤 통계를 보여 줍니다.
