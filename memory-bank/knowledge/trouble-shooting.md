# Trouble Shooting

> 발생했던 버그와 해결 방법. 같은 문제를 두 번 겪지 않기 위한 기록.

## 오디오 지표는 컨테이너를 측정한다 (가장 중요한 교훈)

### 증상

같은 오디오를 `.mp3`와 `.wav`로 저장한 두 파일이 "아키텍처 지문" 분석에서 전혀 다른 답을 냈다.

```
identical audio? r=0.99999  frames 7038656 vs 7038656
metric         mp3           wav       moved?
combHz         237.16        197.96    CHANGED
combHarm       24            20        CHANGED
tilt           -2.87         -2.87
rolloff99      6937.5        6937.5
```

`SongYUE2\Library\music`에 같은 곡이 두 포맷으로 들어 있는 것을 우연히 발견했다.

### 원인

- MP3 인코더는 19~20kHz에서 대역을 자른다. 무손실 원본은 full band다.
- 따라서 `rolloff99`, `digitalNullHz`, 고주파 밴드 에너지(`air`)는 저작자(사람/AI)가 아니라 **인코더의 결정**이다.
- 코퍼스 전체가 MP3인 그룹과 FLAC/WAV인 그룹을 비교하면 이 차이를 AI 신호로 오독하게 된다. 실제 측정: 인간 대조군 `rolloff99` 4.4kHz / `air` −15.3dB, AI 코퍼스 6~9kHz / −5~−10dB. 이 차이는 저작자가 아니라 포맷이었다.

### 해결 / 규칙

1. 코퍼스를 비교하기 전에 **포맷·샘플레이트·손실 여부를 먼저 대조**한다.
2. 포맷이 다르면 대역 제한 영역(보통 15kHz 이상)을 제외하고 비교하거나, 포맷을 맞춘 복제본을 만든다.
3. 어떤 지표를 쓰든 **"오디오는 그대로 두고 컨테이너만 바꾼" 통제 실험**을 먼저 돌린다. 이 실험을 통과 못 한 지표는 삭제한다.
4. 샘플레이트는 44.1k(인간 MP3) vs 48k(전부 AI)로 100% 분리되지만, 이것은 파일 출처 사실일 뿐 AI 탐지가 아니다. 그렇게 팔면 안 된다.

`scratch/stability_check.py`가 이 통제 실험이다.

## spectral_comb 격자 지표는 버렸다 (검증 실패)

### 증상

현(convolution) 업샘플러는 최종 스트라이드 주파수의 배수마다 peak를 남긴다는 이론으로 "조화 격자 간격"을 검출하려 했다. 실제 데이터에서 매우 잘 separation돼 보였다.

```
[김현식 인간]  17/17 strong, combDepth med 27.59 dB
[YuE2]         15/16 strong, combDepth med 21.83 dB
```

### 원인

- **인간 곡에서 더 강하게 나타났다.** AI가 아니라면 이건 디스크리미네이터가 아니다.
- 격자 간격이 코퍼스 내에서 일관되지 않았다. YuE2만 보아도 197.96 / 215.79 / 234.83 / 237.16 / 263.22 / 295.72 / 357.51 Hz — 아키텍처 지문이라면 전부 같아야 한다.
- 197.96 ≈ G3, 237 ≈ C#4. **음악적 음높이 간격**을 검출한 것이었다. 300Hz의 스펙트럼 포락선 주기 검출은 음악의 배음 구조를 그대로 잡는다.
- 통제 실험(동일 PCM, mp3 vs wav)에서 간격이 20% 흔들렸다.

### 해결

- `COMB_ENABLED = False`로 기본 OFF. 코드는 남기되(`spectral_comb`) 점수에 반영하지 않는다.
- 실패를 막는 규칙: **디스크리미네이터를 만들 때는 음성 대조군에서 AI보다分数가 높아야 한다.** 인간에서 더 높으면 그 지표는 measuring the wrong thing이다.
- 합성 신호(정답을 아는 300Hz comb)로 검출 능력 자체는 검증했다 — 1.46Hz 오차로 복원. 문제는 **특이도(specificity)**였고, 이것은 인플레이스 대조군 없이는 절대 알 수 없다.

## `_box_filter`가 짝수 폭에서 길이가 어긋남

### 증상

```
ValueError: operands could not be broadcast together with shapes (2044,) (2045,)
```

### 원인

`np.pad(values, pad)` + `mode="valid"` 조합은 폭이 **홀수**일 때만 길이가 보존된다. `COMB_ENVELOPE_HZ / bin_hz` 같은 계산값은 짝수가 되므로 그대로 터졌다.

### 해결

패딩을 비대칭으로 잡아 모든 폭에서 길이를 유지:
```python
left = width // 2
right = width - 1 - left
padded = np.pad(values, (left, right), mode="edge")
```

## RBJ high-shelf의 부호 규약 혼동

### 증상

K-weighting 필터의 DC gain이 0.0136이 되고, 997Hz 응답이 −36.5dB. 60Hz는 −40dB.

### 원인

RBJ high-shelf는 **분자와 분모에서 부호가 서로 다르다**.

- 분자 b0, b2: `(A+1) + (A-1)*cos ± 2√A·α`
- 분모 a0, a2: `(A+1) - (A-1)*cos ∓ 2√A·α`

low-shelf의 `+ (A-1)cos` 형태를 그대로 쓰면 DC gain이 0.0136으로 무너진다. 반대로 분자에 minus 형태를 쓰면 DC gain이 **−9**가 되어 전체가 반전·증폭된다(+19.6dB).

### 해결

게시된 계수를 그대로 쓰고, DC gain 불변식을 테스트로 고정:
```python
numerator_common = (a + 1.0) + (a - 1.0) * cos_w0
denominator_common = (a + 1.0) - (a - 1.0) * cos_w0
```
48kHz에서는 표준 표기값(`SHELF_REFERENCE`, `HIGHPASS_REFERENCE`)을 **그대로 사용**한다. f0/Q에서 재구성하면 2e-6 어긋나 규격 일치가 아니다.

## LUFS 게이팅의 배열→스칼라 오류

### 증상

```
TypeError: only 0-dimensional arrays can be converted to Python scalars
```

### 원인

`_block_loudness()`가 항상 배열을 반환하는데 `float()`으로 감쌌다. relative gate 임계값 계산이었다.

### 해결

`powers[keep].mean(axis=0, keepdims=True)`는 shape `(1,)`이므로 결과에서 `[0]`을 꺼낸다.

## 파일명 ID 규칙을 신뢰하지 말 것

### 증상

`Music-원본\E0001-1 ...wav`(181.72s)와 `Music-Mastered\K0001-1 ...-remastered.wav`(161.68s)를 ID로 페어링했더니 상관계수가 전부 0.00. "다른 rendition라면 0.3~0.6이 나와야 하는데 0.00은 구조적 오류"였다.

### 원인

숫자 ID(`E0001` ↔ `K0001`)가 우연히 겹칠 뿐 **공통 키가 아니다.** 두 폴더는 서로 다른 세대의 생성물을 담고 있었다. `Music-LANDR-Mastered`가 원본과 **파일명이 정확히 동일**(`-Remastered`만 추가)해서 진짜 페어 세트였다.

### 해결

- 페어는 파일명이 아니라 **오디오로 검증**한다. 로그는 100Hz 로그 에너지 포락선 상관(게인·EQ 불변, 어긋남 허용)으로 후보를 잡고, 상관 0.80 미만은 기각.
- `Music-LANDR-Mastered`에서 51쌍 페어 → 50쌍 검증 통과(1쌍 기각, r=0.763).
- 포락선 상관이 맞으면 raw 샘플 상관도 높아야 한다. 두 결과가 다르면 페어가 아니다.

## Windows 콘솔 인코딩

### 증상

`python.exe : ...Illegal byte sequence`, `Command을 찾을 수 없습니다`, 한국어文件名이 깨짐.

### 원인

PowerShell 5.1 콘솔이 CP949/CP949 혼합. 인자로 경로를 넘길 때 깨진다.

### 해결

- Python 안에서 `sys.stdout.reconfigure(encoding="utf-8")` (CLI 엔트리포인트에서 처리).
- 파일 경로는 PowerShell 대신 Python에서 다룬다. ffmpeg 호출도 `subprocess`로 Python 안에서 하면 안전.
- 콘솔에서 파일명 다룰 때만 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`.


## 0-100 human/AI 점수: 937곡 7코퍼스 실험에서 일반화되지 않음 (2026-09)

### 증상

`scratch/score_build.py`가 937곡(인간 616 / AI 321), 311개 그룹에서 아래를 냈다.

- format feature만 (sampleRate/lossy/duration/codec): random split **100.0%**, 코퍼스 hold-out **98.0%**
- admissible feature만 (crest/flux/noise/DC/stereo): random split **75.5%**, 코퍼스 hold-out **13.0%**

### 원인

두 가지가 겹쳤다.

1. **format feature는 provenance를 학습한다.** 인간은 44.1kHz, AI는 전부 48kHz다. Y: 무손실 세트도 44.1kHz 23/26곡이다. 즉 98%는 "내보낸 포맷"을 읽은 결과지 authorship가 아니다.
2. **admissible feature의 13.0%는 다수 클래스 baseline(65.8%)보다 나쁘다.** 보편 추정이 뒤집힌다. 코퍼스 hold-out에서 모델은 authorship가 아니라 "어느 코퍼스인지"를 학습하고, 코퍼스가 바뀌면 방향이 반대로 돌아간다.

### crest 가설의 사망 (가장 중요한 교훈)

17곡 김현식 대조군에서는 crest가 human [17..22] dB vs AI [11..16] dB로 갈라져 유일한 후보로 보였다. 274명 가수 + 멜론 2002~2022 + 무손실 세트로 바꾸자 **median이 겹쳤다**.

| 코퍼스 | crest median (dB) |
|---|---|
| 김현식 (1인, 1980s) | 18.31 |
| 멜론 연도별 | 12.16 |
| 가수별 best | 13.40 |
| 무손실 | 13.62 |
| Suno 원본 | 13.66 |
| Suno 마스터 | 13.69 |
| YuE2 | 16.08 |

김현식이 "human"이 아니라 **특정 시대의 아날로그 녹음**이었던 것이다. 단일 아티스트/단일 시대 대조군으로 만든 어떤 지표든 이 함정에 빠진다.

### 내 스크립트에서 고친 두 버그 (자기 검증)

1. `onsetCount`를 admissible에 넣었는데 사실 duration proxy였다. raw count 2296(human, 245s) vs 1313(YuE2, 134s), 그러나 onsets/sec는 전 코퍼스 8.4~10.3으로 동일. rate만 사용해야 한다. 첫 실행의 83.9%는 "인간 파일이 더 길다"를 학습한 것이었다.
2. 그룹 CV에서 train을 같은 코퍼스로 제한하니 자명한 100%가 나왔다. 코퍼스 안에서는 라벨이 전부 같아서 상수만 배우면 된다. train은 전체 코퍼스로 확장.

### 결론

- 0-100 숫자를 **출력하는 것**은 언제나 가능하다. 그게 authorship 확률인 것은 아니다.
- DSP feature만으로는 생성기가 바뀌면 13.0%로 붕괴한다. 0-100 authorship 점수는 ML detector 가중치 없이는 ship 불가.
- cache에 `onsetCount` + `durationS`만 있으면 재디코딩 없이 rate를 파생할 수 있다. `--refresh`는 937곡에 10분 걸린다.
## Detector and mastering controls

- A single lofcz full-track output saturated at 1.0 for both one AI original and its LANDR master. Segment aggregation and a second detector are required.
- On one matched AI pair, the provisional two-detector score was 94.0 before LANDR and 85.4 after LANDR.
- Three human originals and their SongYUE2 Mastering-1 derivatives all scored 0.1. SONICS moved in both directions while lofcz stayed 0.0.
- Therefore mastering intensity must not be mapped directly onto AI-generation score. Treat the expected ordering as a hypothesis for corpus validation.

## E0001 postprocess comparison

- E0001 scored 94.0 as the raw AI render, 96.4 after SongYUE2 default AI song polish, 89.6 after polish plus Mastering-1, and 85.4 after LANDR mastering.
- On this file, denoise/lifter/naturalize made SONICS more confident instead of hiding generation traces. Mastering reduced the score, while lofcz stayed saturated at 1.0 throughout.
- SongYUE2 `/api/audio-tools/polish` calls `normalizeInputAudio`, which converts input to mono 44.1 kHz. Do not use that route for stereo song comparisons. Run the same `backend/postfx/worker.mjs` path with stereo float input, or use the saved-project polish route.

## E0002 후처리 탐지 점수 변화가 거의 없었던 사례 (Wave 5)

- E0002 AI 원본 99.6, LANDR 후처리 99.4, SongYUE2 AI 곡 다듬기 + Mastering-1 99.5.
- E0001에서는 원본 94.0에서 각각 85.4와 89.6으로 내려갔지만 E0002에서는 변화가 0.1~0.2점에 그쳤다.
- 마스터링이 AI 탐지 흔적을 항상 인간 방향으로 약화한다는 가정은 곡별 변동 때문에 성립하지 않는다.
### FastAPI fixed route ordering

When a fixed endpoint such as `/api/audio/peaks` is declared after `/api/audio/{kind}`, requests can be captured by the dynamic route and return the wrong validation error. Declare fixed paths before parameterized paths.

## ArtifactNet v9.4 기준군 역방향 결과 (Wave 8)

- 공개 ONNX를 44.1 kHz 모노, 균등 4초 구간 7개, 유효 구간 중앙값으로 실행했다.
- 인간 원곡 2개는 0.5570·0.8561, YuE2 계열 AI 원본/후처리 6개는 0.0026~0.0505였다.
- 모델 설명의 `P(AI)`와 현재 기준군 결과가 반대이므로 점수를 임의 반전하지 않는다.
- 모델은 설치하되 기본 비활성화하고, 기준군 상세 화면에서 `평가만`으로 표시하며 Total에서 제외한다.
- 일부 인간 MP3 구간에서 ONNX가 유효하지 않은 값을 반환했다. 7개 중 4개 이상의 유효 구간을 요구하고 유효 구간 중앙값 및 coverage를 기록한다.

## ArtifactNet의 E0003 역방향 점수와 앙상블 영향 (2026-09-26)

- 3개 활성 탐지기로 E0003 계열을 평가했을 때 ArtifactNet `P(AI)`는 AI 생성 원본 0.0022, LANDR 후처리 0.1088, SongYUE2 다듬기+Mastering-1 0.0117이었다.
- 같은 파일에서 lofcz는 모두 1.00, SONICS는 0.51~0.61이었으므로 ArtifactNet 값이 기하평균 Total을 11.1~40.0 범위로 크게 낮췄다.
- 모델 설치·활성 여부와 결과별 적용 탐지기 수를 함께 기록해야 서로 다른 시점의 Total을 올바르게 비교할 수 있다.
- ArtifactNet을 판정 앙상블에 계속 포함할지는 더 다양한 인간/AI paired corpus에서 방향성과 calibration을 확인한 뒤 결정한다.
- ArtifactNet을 제외하고 SONICS+lofcz만 사용하면 인간 원곡 0.1, E0003 원본 78.4, LANDR 후처리 76.7, SongYUE2 다듬기+Mastering-1 71.5가 나왔다. 이 비교에서는 ArtifactNet 포함 결과 11.1~40.0보다 AI 세 곡의 점수 분리가 명확했다.

## CSS Grid 카드가 다음 행과 겹치는 문제 (2026-09-26)

- `auto-fill` Grid 안에서 stretch되는 카드에 `aspect-ratio: 1`과 `min-height`를 함께 지정하자 Grid가 계산한 행 높이보다 실제 카드가 커져 다음 행을 침범했다.
- 카드 크기를 320×320px로 고정하고 `grid-auto-rows: 320px`을 명시해 실제 카드와 Grid 행 높이를 일치시켰다.
- `gap: 14px`을 한 번만 지정해 가로와 세로 간격을 동일하게 유지했다.

## Detector parameter audit (2026-09-27)

- SONICS currently uses 16 kHz, 5-second windows, 2.5-second hop, at most 24 windows, and a top-3 segment mean. Window sampling and aggregation can change the score; model input rate and duration must remain matched to the selected checkpoint.
- lofcz currently scores the full track truncated at 300 seconds. Its 30-second/15-second-hop segment pass is diagnostic only and does not affect Total. The 16 kHz, 8192 FFT, 1-8 kHz band, hull size 10, and dB bounds are model-coupled preprocessing.
- ArtifactNet v9.4 currently follows the public 44.1 kHz, 4-second, fixed-7-chunk median protocol with at least 4 valid chunks. Alternative mean/max/top-3 aggregation did not correct directionality across the existing E0001/E0002 reference set.
- A per-detector threshold changes only a binary verdict unless the score-combination function explicitly uses it. The current Total uses the equal-weight geometric mean of raw detector scores, so one near-zero detector can collapse the result.

## Pydantic model_dump() turns omitted optional fields into explicit None (2026-09-27)

- Symptom: a partial `PUT` body (`{"detectors":{"sonics":{"topK":1}}}`) silently turned `includedInTotal` to `false` for every detector it touched, disabling Total reflection.
- Cause: `DetectorValueRequest.includedInTotal` was `bool | None = None`, but the handler called `request.model_dump()`. Pydantic emits **every declared field**, so the omitted key arrived as an explicit `None`. `normalize()` tested key presence with `if "includedInTotal" in raw` and then did `bool(raw.get(...))`, and `bool(None)` is `False`.
- Unit tests missed it because they passed a hand-written dict where the key was genuinely absent. Only a payload shaped like `model_dump()` reproduced the bug.
- Fix: treat `None` as "not provided" in the normalizer (`if raw.get("includedInTotal") is not None:`), and let the route fill an omitted `ensemble` block from the currently saved values so a detector-only update cannot reset the combination method.
- Rule: for any partial-update API, normalize with `.get(key) is not None`, never with `key in dict` plus a truthiness cast. And test the exact `model_dump()` shape, not a hand-written dict.
## 가중 결합 설정의 0 가중치와 부분 저장

- 가중 기하평균에서 모든 Total 대상 가중치가 0이면 산술평균으로 자동 대체하지 않는다. 설정 오류로 처리하고 하나 이상의 양수 가중치를 요구한다.
- 가중치 0인 탐지기는 Total뿐 아니라 탐지기 합의도와 신뢰 지표에서도 제외해야 UI 설명과 계산 의미가 일치한다.
- 일부 탐지기 옵션만 저장하는 API는 기본 설정에 요청값을 덮어쓰면 다른 사용자 설정이 초기화된다. 현재 저장값에 요청 patch를 병합한 뒤 정규화한다.

## 반복 분석 결과와 저장 파일 이름 충돌

- 반복 분석을 중복 제거하면 새 실행이 사라져 이전 결과를 덮어쓴 것처럼 보인다. 실행마다 고유 ID를 저장하고 표시 이름은 저장 시 `(1)`, `(2)` 순서로 확정한다.
- 리포트 파일은 존재 확인 후 일반 쓰기를 하면 동시 저장 사이에 경합이 생길 수 있다. 배타 생성 모드로 파일을 열고 충돌할 때 다음 순번을 선택한다.
- 표시 이름만 바꾸고 원본 `file` 경로는 유지해야 상세 정보와 오디오 재생이 계속 원본을 가리킨다.

## Report/history copy deduplication

- 한 번의 배치 분석은 `reports/*.json` 리포트 1개와 `reports/history/*.json` 이력 사본 1개를 만들 수 있다.
- 이력 로더가 두 위치를 함께 읽을 때 같은 실행 시각·파일·점수·상태를 가진 리포트 원본 항목만 제외하고 이력 사본을 사용한다.
- 서로 다른 실제 반복 실행은 `historyItemId`가 각각 다르므로 점수와 파일이 같아도 합치지 않는다.

## ArtifactNet option split and API schema parity (2026-09-27)

- E0001-1 raw AI audio produced a two-detector Total of 94.0 from SONICS 0.8839 and lofcz 1.0.
- Across every exposed ArtifactNet combination, the closest three-detector result was 93.2 with 5 evenly selected segments, max aggregation, and level normalization disabled. Minimum-valid 3 versus 4 made no difference because all five segments were valid.
- The five raw ArtifactNet segment scores were 0.0025, 0.0228, 0.1093, 0.0033, and 0.9146. Max aggregation therefore matches the target by selecting one outlier and is not a calibrated correction. Validate it against AI and human reference tracks before changing the default.
- A UI option can appear in the detector schema but still be silently discarded when its field is absent from `DetectorValueRequest`. Keep the API request model in parity with every editable schema key and add a round-trip test for newly exposed options.
- On the four-track E0001 reference set, 11 evenly selected segments with top-3 aggregation produced Total scores of 0.0 for the human track, 91.3 for the AI original, 74.5 for LANDR mastering, and 86.4 for SongYUE2 polish plus Mastering-1. This is less outlier-dependent than max aggregation, but the two post-processing variants did not preserve the expected relative order.
- The selected default is now 11/even/top3 with level normalization disabled and ArtifactNet included in Total. The persisted detector options and the schema defaults must be updated together; changing only the schema leaves an existing `detector-options.json` unchanged.

## Audio comparison delta panel (2026-09-27)

- The independent comparison module rendered waveforms and spectrograms but had no post-visual numeric delta section. Add a dedicated `/api/audio/compare` endpoint and request it only after both paths are selected.
- Compare scale-relative band levels for low, low-mid, mid, high-mid, high, and ultra-high bands, and report absolute RMS, peak, and true-peak deltas separately. This keeps overall gain changes distinct from spectral-shape changes.

## 완전 분리 표본에서 isotonic 보정이 두 단계로 붕괴 (2026-09-27)

- 인간 60개 점수가 모두 2.3 이하이고 AI 30개 점수가 모두 8.9 이상인 90곡 표본에서는 그룹 교차 검증 성능이 높아도 class-balanced isotonic 보정이 출력값을 0과 100 두 단계로 압축했다.
- 분류 지표 개선만 보고 보정기를 적용하면 연속 Total의 곡별 순위와 미세 차이가 사라진다.
- 런타임 후보는 교차 검증 지표와 함께 보정 출력의 고유 단계 수를 검사해야 한다. 현재는 최소 5단계를 요구하고, 부족하면 raw Total을 유지한다.

## robustMean(이상치 제외 평균)은 탐지기 3개가 서로 다 떨어져 있으면 아무도 못 거른다 (2026-09-27)

- `_robust_mean`([probe/file_analysis.py:73](../../probe/file_analysis.py))은 median 기준 MAD로 이상치를 거른다. n=3일 때 median은 항상 가운데 값 자체이므로, MAD는 사실상 `min(중앙값-최솟값, 최댓값-중앙값)`으로 정해진다.
- 실제 사례(K0062): SONICS 20.8 / lofcz 0.0 / ArtifactNet 99.8. median=20.8이라 **0.0이 99.8보다 median에 더 가깝다**(거리 20.8 vs 79.0). z-점수도 0.0쪽(≈-0.67)보다 99.8쪽(≈2.57)이 더 크게 나와, 사람이 보기엔 0.0이 의심스러워도 통계적으로는 오히려 99.8이 이상치 후보다. 둘 다 3.5 컷오프를 못 넘어 결국 아무것도 제외되지 않고 3개 평균(40.2)으로 떨어졌다.
- 즉 "둘이 가깝고 하나만 멀리 떨어진" 패턴(예: 0.854/0.996/0.0 — 테스트로 고정된 케이스)에서만 이 방식이 의도대로 하나를 제외한다. 세 값이 서로 고르게 흩어져 있으면 중립적 통계 규칙으로는 "탐지기 점수가 낮은 쪽을 우선 배제"하는 결론이 나오지 않는다 — 그건 통계가 아니라 정책(어떤 탐지기를 더 신뢰할지) 문제다.
- 결론: 이 현상을 발견해도 `_robust_mean`은 버그가 아니다. 특정 탐지기를 더 신뢰하고 싶으면 `weightedGeometric` + 가중치로 명시적으로 정책화할 것. 이상치 제외 임계값(`ROBUST_Z_THRESHOLD`)을 낮추는 시도는 방향을 예측하기 어렵다(median에서 먼 쪽이 항상 걸리므로, 낮은 값이 아니라 높은 값이 먼저 걸릴 수 있다).

## 앙상블 결합 방식이 바뀌면 anchor 코퍼스 재계산 결과가 크게 움직인다 (2026-09-27)

- `detector-options.json`의 ensemble method가 `robustMean`(기본값)으로 확정된 뒤 90곡 anchor를 재계산하니 분포가 크게 달라졌다: 인간 원곡 최댓값 1.5→26.6, AI 최솟값 8.9→43.2로 인간·AI 간격이 6.6점에서 16.6점으로 넓어졌다(방향은 개선). 50점 임계값 balanced accuracy는 71.7%→88.3%.
- 재계산은 `scratch/evaluate_anchor_corpus.py`의 로직을 그대로 재사용하되, `analyze_batch`(HTTP POST `/api/analyze/progress`, `save: true`)를 쓰지 않고 `probe.file_analysis.analyze_files`를 직접 호출해서 수행했다. 이유: HTTP 경로는 결과를 `save_history()`로 실제 분석 이력에 적재하고, `historyLimit`을 넘기면 오래된 항목을 디스크에서 지운다. 사용자의 실 이력을 건드리지 않고 `scratch/evaluations/anchor-corpus-evaluation.json`만 갱신하려면 저장 없는 직접 호출 경로를 써야 한다.
- 총점 계산 로직이나 detector-options 기본값이 바뀌면 README의 anchor 표·`scratch/evaluations/*.json`이 곧바로 stale해진다. 다음에 또 바뀌면 같은 방식(직접 `analyze_files` 호출 + `evaluate_anchor_corpus`의 통계 함수 재사용)으로 재생성할 것.
- 인간 hard negative와 낮은 점수의 AI 외부 표본이 추가된 뒤 다시 적합해야 한다.

## 저장 데이터 재계산과 오디오 지표의 방어적 처리 (2026-09-27)

- 과거 Total 재계산은 의도적으로 실 JSON을 갱신하는 관리 작업이다. 직접 `write_text` 대신 같은 폴더의 임시 파일을 flush/fsync한 뒤 `replace`하고, 실행 전 `--dry-run`으로 변경 건수를 확인한다.
- 각 결과의 `detectorSettings.ensemble.weights`를 보존하지 않으면 가중 기하평균 재계산이 당시 설정과 달라진다. 결합 방식만 교체하고 저장 가중치는 결과별로 유지한다.
- True Peak는 선형 보간으로 인터샘플 피크를 만들 수 없다. polyphase 4배 oversampling을 사용하고 표본 peak보다 낮아지지 않도록 원래 peak와 최댓값을 취한다.
- BS.1770 다채널 합산은 모든 채널에 1.41을 적용하면 안 된다. L/R/C는 1.0, LFE는 0, surround만 1.41을 사용한다.
- 비동기 UI 요청은 선택이 바뀐 뒤 예전 응답이 도착할 수 있다. 요청 순번과 현재 경로를 함께 검사한 뒤 DOM을 갱신한다.

## Scratch 파일은 저장 결과의 참조를 기준으로 정리 (2026-09-27)

- 브라우저 업로드 원본을 분석 직후 무조건 삭제하면 이력 상세 보기의 오디오 재생이 깨진다. `reports/*.json`과 `reports/history/*.json`의 `results[].file`을 참조 집합으로 사용한다.
- 앱 시작, 분석 이력 저장·트림, 이력/리포트 삭제 뒤에 참조되지 않는 `scratch/uploads` 파일을 삭제한다. 새 업로드를 받기 전 정리는 진행 중 요청과 충돌하지 않도록 1시간 유예한다.
- 비주얼 캐시는 참조 음원의 현재 `path+mtime+kind` 해시를 다시 계산해 해당 PNG만 보존한다. 음원 수정, 이력 삭제로 더 이상 도달할 수 없는 캐시는 자동 제거된다.

## 정밀 단위 테스트가 있어도 프로덕션 호출 경로를 별도로 검증 (2026-09-27)

- `integrated_loudness()`는 BS.1770 절대 기준 테스트를 통과했지만 `dsp.analyze()`에서 호출되지 않아 실제 API에는 LUFS가 없었다.
- 계산 모듈 테스트와 별도로 최종 조립 함수가 응답 계약 키를 포함하는지 검사한다. 이 프로젝트는 `dsp.analyze(audio)["levels"]`에 `integratedLufs`, `truePeakDbtp`, `crestDb`가 실제 값으로 들어오는 테스트를 둔다.
- 내부 계산 이름(`lufsIntegrated`)과 UI 계약 이름(`integratedLufs`)이 다르면 프로덕션 경계에서 명시적으로 변환하고, UI는 과거 저장 리포트를 위한 fallback을 유지한다.
## Long FIR filtering should use overlap-add for full tracks

Padding an entire multi-minute signal to the next power of two for every FIR pass caused the
BS.1770 level profile to dominate analysis time and memory. `scipy.signal.oaconvolve` preserves
the causal `full[:signal.size]` result within floating-point tolerance while processing bounded
blocks. A 3-minute 48 kHz mono convolution measured 0.778 s before and 0.200 s after. Always keep
a direct-convolution equivalence test when changing the block strategy.

## Detector diagnostics must describe the windows used for the score

lofcz previously computed the song score from evenly spaced long windows but reported segment
statistics from separate 30-second windows limited to the first 300 seconds. This made the detail
panel explain different evidence than the Total input and repeated expensive inference. Reuse the
actual scoring windows for `segments`, `segmentMean`, `segmentMin`, and `segmentMax`.

## Standard-deviation normalization needs a degenerate-input guard

Dividing an almost constant waveform by `max(std, 1e-6)` can turn a small DC signal into an
out-of-distribution model input with amplitude near 1000. Treat non-finite or effectively zero
standard-deviation windows as silence before inference and cover a constant nonzero signal in tests.

## 시각화 캐시는 완성 파일만 원자적으로 공개해야 한다 (2026-09-27)

- 상세창은 재생 전·후 색상을 나누기 위해 같은 spectrogram을 두 이미지로 사용한다. 두 HTTP 요청이 동시에 cache miss를 만나 FFmpeg가 같은 최종 PNG에 직접 쓰면, 한 응답이 다른 렌더의 부분 파일을 읽어 간헐적으로 이미지가 깨진다.
- 경로별 잠금 안에서 고유 임시 PNG를 만들고 PNG signature를 검증한 뒤 `replace()`로 최종 경로에 공개한다. 기존 캐시도 signature가 잘못되면 삭제하고 다시 만든다.
- 프론트엔드는 spectrogram을 한 번만 fetch해 하나의 object URL을 두 이미지에 공유하고, 상세창 전환 시 이전 URL을 폐기한다. 실제 브라우저에서 두 이미지가 같은 `blob:` URL, 1200×300 완전 로드 상태인지 확인한다.

## lofcz 위치·집계 옵션은 음원이 최대 분석 길이보다 짧으면 결과가 같다 (2026-09-27)

- `maxDurationS=300`에서 124.64초 또는 267.28초 음원은 곡 전체가 단일 scoring window가 된다. 이 경우 `analysisPosition=start/even`과 `aggregation=mean/median`을 바꿔도 같은 한 점을 집계하므로 원점수와 Total이 바뀌지 않는다.
- E0002 4종 재분석에서 `start+mean`을 `even+median`으로 변경했지만 네 파일 모두 Total과 세 탐지기 점수가 정확히 같았다. 옵션 영향을 비교하려면 300초보다 긴 곡을 쓰거나 `maxDurationS`를 60/180초로 낮춰 scoring window가 둘 이상 생기게 해야 한다.

## Windows에서 재시작한 서버가 살아남은 서버의 포트를 빼앗는다 (2026-09-27)

- **증상**: 서버 실행 중 `start.bat`을 다시 실행하면 브라우저 SSE(`/api/analysis/stream`)가 끊겼다가 새 서버에 붙고, 화면은 "분석 완료 3/4"에서 멈춘다. **서버 로그에 오류가 없고 크래시 기록도 없다.** 정작 서버는 정상 실행 중이다.
- **원인 1 — SO_REUSEADDR**: Windows 소켓은 TIME_WAIT가 남아 있어도 **이미 다른 프로세스가 LISTEN 중인 포트에 bind와 listen이 성공**한다. kill 직후 재시작하면 새 인스턴스가 살아남은 인스턴스의 포트를 가져간다. Linux와 동작이 다르므로 Linux에서 검증한 stop/start 스크립트를 그대로 쓰면 안 된다.
- **원인 2 — PID를 잘못 잡음**: `netstat -ano`로 포트의 PID를 구해 종료하면 자식 `python.exe`가 아니라 그보다 위쪽 launcher가 죽는다. 부모가 살아남아 kill과 재시작 사이에 포트가 정리되지 않는다.
- **해결**: `Win32_Process`로 조회해 `python.exe`이면서 명령행에 앱 모듈 문자열(`probe.app`)이 있는 **모든** 프로세스를 종료한 뒤, 포트가 해제될 때까지 최대 10초 대기한다. 시작 스크립트는 종료 스크립트를 먼저 호출한다. 명령행 패턴으로 좁히면 같은 포트를 쓰는 무관 서버는 건드리지 않는다.
- **검증**: 실행 중 재시작했을 때 신규 launcher/server만 남고 기존 인스턴스가 0개인지, `/health` OK와 탐지자 active, 상태 idle인지 확인한다. 실제 유령 서버 3개(잔여 메모리 2,317 MB)가 남아 있던 것을 발견했다.

## 검증 없이 코드에서 결함을 지목하지 않는다 (2026-09-27)

- **패턴 grep은 존재 부부의 증거이지 부재의 증거가 아니다.** 해결 여부를 grep으로 판정해 세 번 연속으로 오판했다.
  - `sonics.py`의 `1e-6`은 상수 **선언**이라 남아 있고, 실제 수정은 그 아래 분기의 `np.zeros_like` 치환이었다.
  - `history.py`의 `payload.get(` 라인은 남아 있지만, 가드는 **별도 라인**의 `isinstance(payload, dict)`이고 5곳에 있었다.
  - `audioio.py`의 `-ar`/`-ac`는 44100/1 하드코드가 아니라 ffprobe로 읽은 `meta.sample_rate`/`meta.channels`(파일 네이티브 값)였다. 발견 내용이 처음부터 오독이었다.
- **"고쳤다"고 기록한 항목도 코드로 확인한다.** `nan_to_num` 무음 치환(M-23)을 M-2와 묶어 "자체 수정"으로 집계했지만 실제 반영은 M-2의 `ddof=1`뿐이었다. 문서 수정은 실제 결함을 고치지 않는다.
- **판정 방법**: 해당 함수의 **전체 본문**을 읽고, 가능하면 venv에서 최소 재현을 돌린 뒤에 해결/잔존을 확정한다. 집계 숫자를 먼저 쓰고 근거를 나중에 채우지 않는다.

## 두 소스를 값으로 중복 제거하면, 한쪽이 트림될 때 좀비가 부활한다 (2026-09-27)

### 증상

사이드바 "분석 이력" 배지가 217 → 156처럼 사용자가 실제로 본 적 없는 큰 숫자로 계속 올라간다. `historyLimit` 설정(300)보다 작은데도 "지금까지 분석한 총 횟수"처럼 보인다는 제보.

### 원인

`probe/history.py::load_history()`가 두 디렉터리를 합쳐 읽었다:
- `REPORTS_DIR`(루트) — `save=true`로 "저장"한 리포트. **영구, 절대 트림 안 됨.**
- `HISTORY_DIR`(`reports/history/`) — 모든 분석 후 항상 자동 저장되는 사본. `trim_history()`가 `historyLimit`만큼만 남기고 오래된 것부터 지운다.

같은 분석은 두 곳에 동시에 생기므로, 로더는 `(generatedAt, file, totalScore, status)` 값 일치로 "이미 HISTORY_DIR 사본이 있는 REPORTS_DIR 항목"을 건너뛰어 카드가 두 번 보이지 않게 했다. 문제는 **그 HISTORY_DIR 사본이 나중에 `trim_history()`로 지워지면**, 다음 로드부터는 매칭할 사본이 없어 REPORTS_DIR의 원본이 "새로 나타난 항목"처럼 다시 집계된다는 것이다. `REPORTS_DIR`는 절대 안 지워지므로 이 좀비 항목은 영구히 쌓인다.

실측(2026-09-27): `historyLimit=300`, 배지 156, 그러나 실제 유효 `historyItemId`(HISTORY_DIR에서만 부여됨)는 100개뿐이었다. 나머지 56개가 정확히 이 좀비였다(`REPORTS_DIR` root-only 50개 + 소량의 다른 mismatch). UI에서 "삭제"해도 HISTORY_DIR 사본만 지워지고 REPORTS_DIR 원본은 그대로 남아, 다음 로드에 다시 부활했다.

### 해결 / 규칙

- **값 기반 중복 제거로 두 소스를 합치지 않는다.** 한쪽만 트림되는 구조라면 시간이 지나면 반드시 이 버그가 재발한다.
- `load_history()`/`change_signature()`를 `HISTORY_DIR` 단일 소스로 변경했다. `REPORTS_DIR`(저장된 리포트)는 `/api/reports`가 이미 완전히 독립적으로 목록·조회·삭제를 제공하므로 잃는 기능이 없다.
- **표시 개수와 트림 정책은 항상 같은 소스 집합을 봐야 한다.** "몇 개 있나"를 보여주는 카운터와 "몇 개까지 남길까"를 결정하는 트림 로직이 다른 파일 집합을 스캔하면, 한쪽만 바뀌어도 사용자에게는 모순으로 보인다.
- `historyLimit`을 낮추면 `PUT /api/settings`가 즉시 `trim_history()`를 호출해 오래된 것부터 지운다(이미 구현돼 있었음 — 배지 버그가 이 동작을 가리고 있었을 뿐).
