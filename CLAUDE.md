# 프로젝트: Dacon 236753 — 블랙박스 영상 기반 재녹화 판별 및 교통사고 분석 AI

주최: 행정안전부/NIA, 주관: 국립과학수사연구원, 운영: 데이콘
대회 링크: https://dacon.io/competitions/official/236753

## 대회 방식
- 1차 평가(Private 리더보드 상위 15팀) → 2차 평가(모델개발보고서+학습데이터구성보고서 제출, HWP) → 최종 7팀 수상
- 1차 평가 Stage별 가중치: Stage1 0.2 / Stage2 0.4 / Stage3 0.4
- 코드 제출 대회: `submit.zip` 업로드, 평가서버에서 자동 실행 (인터넷 차단)

## 제출 파일 구조 (필수, 디렉토리/파일명 정확히 일치해야 함)
```
submit.zip
├── model/
│   ├── stage1/
│   ├── stage2/
│   └── stage3/
├── inference.py   # 필수, predict_stage1/2/3 세 함수 모두 구현
└── requirements.txt
```
평가서버가 자동 추가: `data/`(읽기전용 평가데이터), `output/submission.csv`(결과 저장 경로)

## 함수 시그니처 및 출력 컬럼
```python
def predict_stage1(data_dir, model_dir): ...  # -> DataFrame[ID, answer]
def predict_stage2(data_dir, model_dir): ...  # -> DataFrame[ID, collision_frame, entry_frame, evasion_space, entry_side]
def predict_stage3(data_dir, model_dir): ...  # -> DataFrame[ID, sample_index, accel_label, steer_label]
```

## 리소스/시간 제약 (평가서버: NVIDIA L40S, VRAM 44.7GiB, 7 vCPU, RAM 60GB)
- 전체 추론(3 Stage 합산) 60분 이내, 패키지 설치 10분 이내
- 제출 zip 10GB 이내, 압축해제 후 32GB 이내
- 평가서버 인터넷 연결 비활성화 → 사전학습 가중치는 **로컬에서 미리 받아 model/에 통째로 포함**해야 함 (오프라인 로드는 허용, 온라인 다운로드 코드만 금지)
- 모델 로드 시 `weights=None`(또는 `pretrained=False`)으로 구조만 만들고 `load_state_dict`로 체크포인트 로드
- 1일 제출 3회 제한

## 대회 규칙 (위반 시 실격/무효)
- 비공개 평가 데이터로 추가 학습/튜닝/Pseudo-Labeling 금지
- 평가 데이터는 파일(영상) 단위 독립 예측 원칙 — 한 파일을 세그먼트로 나눠 추론 후 종합은 허용, 다른 파일의 정보/예측값 이용은 금지
- 사용하는 사전학습모델/API/외부데이터는 법적 제한 없어야 하며(최소 비영리 사용 허용), 2차 평가 시 출처 명시 의무

## Stage별 입출력 스펙

### Stage 1: 재녹화 여부 판별
- 입력: `data/stage1/videos/*.mp4` (영상 파일 그 자체)
- 출력: `ID, answer` (`ORIGINAL` 또는 `RERECORDED`)
- 평가: Macro-F1

### Stage 2: 사고 주요시점·상황 분석
- 입력: `data/stage2/images/<영상ID>/frame_XXXXXX.jpg` (영상별 폴더, 프레임 번호=원본 영상 프레임 번호)
- 출력: `ID, collision_frame, entry_frame, evasion_space, entry_side`
  - collision_frame: 충돌 프레임 번호(원본 프레임 번호 그대로)
  - entry_frame: 피해차량 진입 프레임 번호
  - evasion_space: 회피 공간 여부
  - entry_side: 진입 방향(LEFT/RIGHT)
- 평가: 프레임→초 변환 후 정답시각과 비교. 예측 누락/결측/음수/범위초과/허용범주 외 값은 오답 처리

### Stage 3: 차량 거동 특성 분석 (현재 담당 파트)
- 입력: `data/stage3/videos/*.mp4` — **10Hz 실차 주행 영상** (사고 장면 아님, 일반 주행)
- CAN 계측값(속도/조향각)은 정답 생성에만 쓰이고 **모델 입력으로는 절대 제공되지 않음** → 영상만 보고 예측해야 함
- 출력: `ID, sample_index, accel_label, steer_label` — 영상당 0.1초 단위로 여러 행(디코딩 프레임 수 = sample_index 개수)
  - sample_index: 0부터 시작하는 0.1초 단위 순번
  - accel_label: `ACCELERATING`/`DECELERATING`/`CONSTANT`/`STOPPED`
  - steer_label: `LEFT`/`STRAIGHT`/`RIGHT`
- 평가: accel/steer 각각 Macro-F1. **STOPPED 프레임은 steer 평가에서 제외**되지만, 제출 형식상 모든 프레임(STOPPED 포함)에 steer_label은 반드시 채워야 함
- 대회에서 학습 데이터 미제공 — 참가자가 직접 합법적 데이터로 구성해야 함

## 베이스라인 코드 요약 (제공된 노트북 2개 기준)
- **Stage1**: `mvit_v2_s` (torchvision video model), 영상당 16프레임 클립을 3구간에서 뽑아 평균 → 이진분류
- **Stage2**: ResNet18(ImageNet 가중치, 오프라인 파일로 로드) 프레임별 피처 1회 추출 + BiGRU(2layer, hidden192, bidirectional) → collision/entry는 시점별 점수 argmax, evasion/entry_side는 별도 분류헤드. **공개 예제엔 collision 라벨만 있어 나머지 3개 헤드는 구조 검증용 더미 수준**
- **Stage3**: `mvit_v2_s`를 **사전학습 없이(weights=None) 처음부터 학습**, 공유 백본 + accel(4cls)/steer(3cls) 선형 헤드. 학습 라벨은 `labels.csv`(ID, frame_index, accel_label, steer_label) 형태의 **희소 라벨**(영상 전체가 아니라 일부 시점만) — 라벨된 프레임을 중심으로 16프레임 클립 하나씩 학습. 추론 시 영상 전체를 디코딩한 뒤 8개씩 묶어 슬라이딩 윈도우(각 프레임 중심 16프레임 클립)로 프레임마다 예측.

## 베이스라인의 알려진 한계 (개선 대상)
1. Stage3 from-scratch MViT는 데이터가 적으면 사실상 학습이 안 됨 → 사전학습 가중치를 로컬에서 받아 `model/stage3/`에 통째로 포함하는 방안 검토
2. Stage3 추론이 프레임마다 16프레임 클립을 반복 통과시키는 구조라 느림 → Stage2처럼 "프레임 피처 1회 추출 + 경량 시퀀스모델(GRU/TCN)"로 바꾸면 속도/데이터효율 모두 유리
3. Stage2 baseline은 collision만 실제 학습됨 — entry_frame/evasion_space/entry_side는 별도 라벨·모델 필요
4. accel/steer 판정 임계값(몇 m/s² 이상이 ACCELERATING인지 등)이 대회에서 공식적으로 공개되지 않음 → 자체 정의 필요, 실제 정답 기준과 다를 리스크 있음

## Stage 3 데이터 전략 (결정됨)
- **comma2k19** 데이터셋 사용 결정. 카메라 영상 + CAN/global_pose 계측값(속도, 조향각 등)이 이미 포함되어 있어 **사람이 눈으로 보고 매기는 수동 라벨링은 불필요** — 계측값을 임계값 규칙으로 accel_label/steer_label로 변환(자동 생성)하는 방식으로 진행
- 라벨 생성 후보 소스:
  - (A) `global_pose/frame_velocities`, `frame_orientations` — 카메라 프레임에 이미 시간 정렬되어 있어 구현이 쉬움
  - (B) `processed_log/CAN/speed`, `steering_angle` — 원시 신호라 프레임 타임스탬프에 맞춰 보간 필요, steer 정의에는 더 직접적
  - ⚠️ 정확한 폴더/필드명은 실제 다운로드한 세그먼트에서 확인 필요 (노트북/AI가 기억으로 단정하지 말 것)
- **리스크**: comma2k19은 미국 고속도로 통근 주행 위주 → STOPPED/LEFT/RIGHT 이벤트가 매우 희소할 가능성 큼. 국내 도심·정지·회전 상황을 보강할 추가 데이터(예: AiHub) 검토 필요
- 라이선스: comma.ai 라이선스 조건(비영리 사용 허용 범위) 확인 및 2차 평가 보고서용 출처 기록 필요

## Stage 3 로드맵
1. **[다음 할 일]** comma2k19 세그먼트 폴더 구조 실측 확인 (`ls -R <segment>`) → 정확한 필드명 파악
2. 라벨링 규칙(임계값) 설계 및 소규모 육안 검증
3. 데이터 파이프라인 구축: 0.1초 그리드 정렬, dense label csv 생성(`ID, sample_index, accel_label, steer_label` 형태), train/val 분할(영상 단위, leakage 방지)
4. 모델 설계/학습: 프레임 피처 추출 + 시퀀스 모델 구조로 전환 권장, 사전학습 가중치 오프라인 번들링
5. 추론 코드 통합: `predict_stage3` 교체, 60분 전체 제한 내 속도 검증
6. 로컬 스모크 테스트 & `submit.zip` 구조/용량/오프라인 실행 검증
7. 2차 평가 대비: 사용 데이터 출처·라이선스 문서화, 재현 가능한 학습 코드 정리

## 2인 분업안
- **A (데이터/라벨링)**: comma2k19 구조 분석 → 규칙기반 라벨 생성 스크립트 → 클래스 불균형(정지/회전 희소) 보강 → 증강 → 출처/라이선스 정리
- **B (모델/추론)**: 베이스라인 구조 개선(프레임피처+시퀀스모델) → 사전학습 가중치 오프라인 번들 → A의 label csv로 학습 스크립트 작성 → `predict_stage3` 속도 최적화 → `submit.zip` 통합/검증
- 두 사람 모두 시작 전 **label csv 스키마(ID, sample_index, accel_label, steer_label)를 먼저 합의**하면 이후 독립적으로 진행 가능
