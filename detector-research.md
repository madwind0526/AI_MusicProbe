# AI 음악 탐지기 조사와 점수 설계안

최종 갱신: 2026-09-26

## 결론

`totalScore`는 DSP 파라미터의 단순 가중합으로 만들지 않는다. 공개 모델 여러 개가
내는 구간별 생성 흔적을 결합해 raw score를 만들고, 동일 음원의 처리 전후 쌍을
사용해 0~100으로 비선형 calibration한다.

점수는 다섯 개의 고정 클래스를 표시하지 않는다. 아래 순서는 검증할 가설이다.

```text
인간 원본
< 인간 제작 + AI 마스터링
< AI 생성 + 인간 마스터링
< AI 생성 + AI 마스터링
< AI 생성 원본
```

실험에서 이 순서가 유지되지 않으면 데이터를 숨기거나 점수를 강제로 맞추지 않고,
순서가 깨지는 조건을 결과의 한계로 기록한다.

## 상용·공개 서비스에서 확인된 공통 구조

| 서비스 | 입력과 결과 | 참고할 점 |
|---|---|---|
| Vobile/Pex AI Song Detector | 파일 또는 URL 1개를 입력하고 `is_ai`, 0~1 `ai_score`, 추정 생성기를 반환 | `ai_score`는 보정된 확률이 아니며 정렬·QA용이라고 명시한다. 파일 하나당 결과 하나다. |
| IRCAM Amplify AIMD | WebUI에서 MP3/WAV 최대 5개를 올리고 파일별 결과를 받는다 | 복수 입력 UX와 비동기 처리 구조를 참고할 수 있다. |
| ArtifactNet | 무료 단일 파일 WebUI와 REST batch API를 제공하며 파일별·구간별 확률, 해시, 모델 버전을 반환 | 전체 점수 외에 segment evidence를 함께 제공한다. 공개 ONNX는 비상업 전용이다. |
| Songprint | 단일·복수 업로드, 0~100 점수, Human/AI/Uncertain, 생성기 추정을 제공 | spectrogram·phase·temporal 신호의 ensemble과 gating을 표방한다. 공개 검증 수치는 제한적이다. |
| Anubis Verify | 단일 점수와 spectral/temporal/phase 근거, 구간별 timeline을 제공 | authorship의 법적 판정이 아니라 기술적 증거라고 명시한다. |
| Deezer | 생성기 decoder/codec 흔적을 학습하며 서비스에서는 강한 AI marker를 탐지 | 공개 연구 모델은 실제 운영 모델과 다르다. 미지 생성기와 후처리에 대한 일반화가 핵심 문제다. |

## 공개 구현 후보

### 1. lofcz vocoder fakeprint

- MIT 라이선스
- 1~8 kHz 부근 neural vocoder/deconvolution 흔적을 사용
- ONNX 기반으로 작고 CPU 실행이 가능
- Suno/Udio 계열에 유용하지만 새로운 생성 구조에는 재학습이 필요
- mastering, codec, EQ에 강하도록 augmentation된 CNN 경로가 별도로 있다

### 2. SONICS SpecTTTra

- 코드와 모델 MIT, 데이터셋 CC BY-NC 4.0
- 5초 또는 120초 spectrogram의 장기 spectral/temporal 관계를 학습
- 공개 5초 모델 F1은 약 0.76~0.78, 120초 모델은 약 0.88~0.97
- 스타일과 코퍼스 영향을 받을 수 있으므로 단독 판정기로 쓰지 않는다

### 3. ArtifactNet

- codec residual을 분리해 구간별 AI 흔적을 판정
- ArtifactBench의 분포 이동 평가에서 공개 비교 모델보다 높은 성능을 보고
- ONNX inference build는 CC BY-NC 4.0이며 특허 고지가 있어 상용 제품에는 별도
  라이선스가 필요
- 연구·프로토타입의 비교 기준으로는 가치가 높다

### 4. 공개 ensemble 사례

`Prototypr/ai-music-classifier`는 SONICS 두 모델, lofcz fakeprint, metadata를 결합한다.
SONICS가 단독으로 높게 나와도 fakeprint나 metadata가 뒷받침하지 않으면 강한 판정을
내리지 않는 corroboration/gating 방식을 쓴다. 이 구조는 현재 프로젝트가 참고하기
좋지만, 해당 프로젝트의 임계값을 그대로 복사하지 않고 우리 코퍼스로 다시 보정한다.

## 권장 분석 파이프라인

```text
단일 파일 / 여러 파일 / 폴더
        ↓
지원 음원 목록 확장 + 파일별 작업 생성
        ↓
공통 decode 및 정규화
        ↓
5~10초 구간으로 분할
        ↓
lofcz + SONICS + ArtifactNet(연구용) + metadata + 기존 DSP
        ↓
구간별 detector 결과와 품질 검사
        ↓
파일별 raw ensemble score
        ↓
비선형 monotonic calibration
        ↓
파일별 parameters + totalScore(0~100) + confidence + limitations
```

여러 파일이나 폴더를 입력해도 전체 점수는 만들지 않는다. 실패한 파일은 그 파일에만
오류를 기록하고 나머지 파일 분석을 계속한다.

## 점수 산출 방법

### 내부 신호

- `generationEvidence`: neural generator/codec 흔적
- `postProcessEvidence`: mastering, codec, resampling 때문에 흔적이 가려지거나 변한 정도
- `agreement`: 서로 다른 detector가 같은 방향을 가리키는 정도
- `coverage`: 분석 가능한 유효 구간의 비율
- `formatRisk`: sample rate, codec 등 confound 위험. 점수 근거가 아니라 신뢰도 감점에 사용

최종 점수는 고정 가중 평균보다 calibration 모델의 출력으로 만든다. 초기에는
isotonic regression처럼 단조성만 가정하는 방법을 사용한다. 선형 관계는 가정하지
않는다.

### 필요한 anchor 데이터

같은 콘텐츠에서 처리만 바뀐 paired dataset을 만든다.

1. 인간 원본
2. 같은 인간 원본을 AI mastering한 결과
3. AI 생성 원본
4. 같은 AI 원본을 사람이 mastering한 결과
5. 같은 AI 원본을 AI mastering한 결과

장르, 곡 길이, sample rate, codec 차이로 점수가 갈리지 않도록 동일 source identity를
그룹으로 묶는다. train/calibration/test 사이에는 같은 원곡과 파생본이 동시에 들어가면
안 된다.

### 검증 순서

1. 미지 생성기 hold-out
2. source-lineage hold-out
3. codec·sample-rate·mastering 변형 테스트
4. 장르·언어·연도별 human hard-negative 테스트
5. 마지막에만 random split 수치를 참고

보고 지표는 AUROC 하나가 아니라 generator별 TPR, human domain별 FPR, coverage,
calibration error, score ordering 유지율을 함께 쓴다.

## 현재 프로젝트 이력과의 연결

- 기존 DSP만 사용한 코퍼스 hold-out은 13.0%로 붕괴했다. 따라서 DSP를 주 판정기로
  사용하지 않는다.
- sample rate와 codec은 98%를 만들었지만 authorship가 아니라 포맷을 분류했다.
  `formatRisk`로만 사용한다.
- LUFS/LRA/peak/side-mid/rolloff/air는 mastering에 따라 크게 움직였다. 생성 흔적
  점수의 직접 근거에서 제외하고 후처리·신뢰도 설명에만 사용한다.
- crest factor는 인간 대조군을 넓히자 AI와 겹쳤다. 단독 detector로 사용하지 않는다.
- `spectral_comb`과 `harmonic_grid`는 실제 인간 음원에서 false positive가 높아
  되살리지 않는다.

### ArtifactNet v9.4 기준군 점검

공개 ONNX를 공식 어댑터와 같은 44.1 kHz 모노, 균등 배치한 4초 구간 7개,
유효 구간 중앙값 방식으로 실행했다. 현재 8개 기준 음원에서는 인간 원곡 두 곡이
각각 0.5570과 0.8561이었고, YuE2 계열 AI 원본·후처리 여섯 곡은
0.0026~0.0505였다. 공개 모델 설명의 `P(AI)` 방향과 반대로 나타났으므로 점수를
임의로 뒤집지 않고 Total에서 제외했다. 모델은 비교 실험을 위해 설치 상태로 유지하되
기본 비활성화한다. 원시 결과는 `scratch/evaluations/artifactnet-eight-reference-results.json`에
보존한다.

## 구현 우선순위

1. MIT 모델인 lofcz와 SONICS 5초 모델을 adapter 형태로 연결한다.
2. 모든 모델을 동일한 파일 구간에 실행하고 원시 출력과 모델 버전을 저장한다.
3. 현재 937곡 코퍼스로 detector별 분포 이동과 human false positive를 다시 측정한다.
4. ArtifactNet 공개 ONNX를 연구 기준으로 추가해 세 모델을 같은 cohort에서 비교한다.
5. paired mastering anchor dataset을 만든 후 비선형 calibration을 학습한다.
6. 점수 안정성이 확인된 뒤에만 `totalScore`를 제품 응답에 활성화한다.

## 참고 자료

- Deezer 연구: https://github.com/deezer/deepfake-detector
- Deezer 논문: https://arxiv.org/abs/2501.10111
- SONICS: https://github.com/awsaf49/sonics
- lofcz detector: https://github.com/lofcz/ai-music-detector
- 공개 ensemble 사례: https://github.com/Prototypr/ai-music-classifier
- ArtifactNet 논문: https://arxiv.org/abs/2604.16254
- ArtifactBench: https://arxiv.org/abs/2609.23550
- Vobile/Pex API: https://docs.pex.com/ai-song-detector/api-documentation/
- IRCAM Amplify demo: https://aidetector.ircamamplify.io/
- ArtifactNet 서비스: https://intrect.io/artifactnet/
- Songprint: https://songprint.space/
- Anubis Verify: https://anubisaudio.com/
