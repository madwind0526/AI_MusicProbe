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
