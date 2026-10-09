# 외부 데이터셋

1단계 개발·평가에 쓰는 외부 데이터입니다. 원본은 `data/raw/external/`에 두고 저장소에는 올리지 않습니다 (`.gitignore`).

| 이름 | 출처 | 라이선스 | 위치 | 내용 | 용도 |
| --- | --- | --- | --- | --- | --- |
| steel-ocr-dataset | [Hoshino121/steel-ocr-dataset](https://huggingface.co/datasets/Hoshino121/steel-ocr-dataset) (원본: iput-tk230215/steel-ocr-dataset) | MIT | `data/raw/external/steel-ocr/` | 철골 H빔의 녹슨 면에 페인트 마커로 쓴 부재 코드 (예: `B1Sb40N-36`). 검출 사진 333장(학습 319·테스트 14), 잘라낸 글자 이미지 509장. 일본 현장 사진, 4032×2268 | 마커 손글씨 OCR 성능 확인, PaddleOCR 평가 스크립트 개발 |
| MPSC | [TongkunGuan/RFN](https://github.com/TongkunGuan/RFN/blob/main/IndustrialTextDataset.md) (Guan et al., TCSVT 2022) | CC BY-NC 4.0 (학술 연구만, 상업 이용 불가) | `data/raw/external/mpsc/MPSC/` | 금속 주물·가공 부품에 양각·음각·각인된 글자. 사진 3,194장(학습 2,555·테스트 639), 글자 박스 15,575개(그중 `###` 568개). 해상도 416×312~2560×1920 섞여 있음 | 녹·오염·저대비 금속 표면에서 글자 영역 검출 성능 확인 |

## 받기

```bash
mkdir -p data/raw/external/steel-ocr
backend/.venv/bin/python -I -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Hoshino121/steel-ocr-dataset', repo_type='dataset', local_dir='data/raw/external/steel-ocr')"
```

약 1.4GB, 852개 파일. 라벨은 PaddleOCR 형식입니다.

| 파일 | 형식 |
| --- | --- |
| `train_data/det/train.txt`, `val.txt`, `test_data/det/test.txt` | `이미지 경로 \t [{"transcription", "points"(꼭짓점 4개), "difficult"}]` |
| `train_data/rec/rec_gt_train.txt`, `rec_gt_val.txt` | `잘라낸 이미지 경로 \t 글자` |
| `train_data/rec/dict.txt` | 글자 목록 21자: `- 0~9 A B G M N S X Y b s` |

### MPSC

```bash
pip install gdown
mkdir -p data/raw/external/mpsc
gdown 1wPHXf4sKjEr7JFfobKV9IqC0EKM79J6G -O data/raw/external/mpsc/MPSC.zip
unzip -q data/raw/external/mpsc/MPSC.zip -d data/raw/external/mpsc && rm data/raw/external/mpsc/MPSC.zip
```

zip 1.16GB, 풀면 1.1GB, 6,388개 파일. 라벨은 ICDAR2015 형식입니다.

| 파일 | 형식 |
| --- | --- |
| `image/{train,test}/MPSC_img_N.jpg` | 사진 |
| `annotation/{train,test}/gt_img_N.txt` | 한 줄에 글자 박스 하나: `x1,y1,x2,y2,x3,y3,x4,y4,글자` (UTF-8). `###`은 판독 불가(평가 제외) |

- 사진과 라벨은 파일 이름 앞부분이 다릅니다 (`MPSC_img_N` ↔ `gt_img_N`).
- 글자는 영문 대·소문자, 숫자, 기호(`-./:()×` 등) 87종입니다. 사진 1장에 박스가 평균 4.9개, 글자 길이는 평균 4.5자입니다.

## 주의

- MPSC 글자는 바탕과 색이 같은 **양각·각인**이라 대비가 낮습니다. 대비가 높은 우리 페인트 마커 표기보다 검출이 어려운 조건이니, **검출이 버티는지 시험하는 용도**로 씁니다. 손글씨 인식과 기호에는 도움이 되지 않습니다.

- 우리 표기(`P-1`, `FW`, `t=10`, `▲`)와 글자 구성이 다릅니다. 손글씨 OCR을 미리 확인하는 용도로만 쓰고, **최종 평가는 조선소 표기 사진(`data/annotations/`)으로** 합니다.
- 일부 사진은 초점이 크게 흐리거나 글자 일부만 찍혀 있습니다 (`blur` 조건 사례로 활용 가능).
