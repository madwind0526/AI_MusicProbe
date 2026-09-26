# Patterns

> 이 프로젝트에서 확인된 재사용 가능한 코드 패턴.

## 검증 게이트를 코드에 둔다

지표 하나가 아니라 지표 **클래스**를 검증하는 함수를 먼저 만들고, 새 지표는 반드시 그 gates를 통과해야 한다.

- `scratch/comb_validate.py` — 정답이 알려진 합성 신호(격자 300Hz → 1.46Hz 오차 복원) + 음성 대조군(무작위 소음 → strong 아님)
- `scratch/stability_check.py` — "오디오는 그대로, 컨테이너만 변경" 통제
- `tests/test_loudness.py` — **게시된 외부 규격**으로 절대 교정 (BS.1770-4: 997Hz / −23dBFS stereo → −23.0 LUFS)

게시 규격으로 교정 가능한 것(LUFS, crest, FFT 주파수)은 반드시 그렇게 한다. 자기 자신과의 일관성만으로는 필터 오류가 통과한다. 실제로 이 프로젝트에서 RBJ 부호 오류가 자기일관성으로는 통과했고, −23 LUFS 교정에서만 잡혔다.

## 디스크리미네이터는人类 대조군에서 검증한다

| 검증 | 방법 |
|------|------|
| 검출 능력 (sensitivity) | 정답이 알려진 합성 입력 |
| **특이도 (specificity)** | **음성 대조군. 반드시 인플레이스 파일이어야 함** |
| 컨테이너 불변성 | 동일 PCM, 다른 포맷 |
| 처리 체인 불변성 | 동일 세대, 마스터 전/후 |

`spectral_comb`는 1~3번을 통과하고 **4번(특이도)에서 실패**했다 — 인간 17/17에서 AI보다 더 강하게 나타났다. 순서상 마지막에 놓은 게이트가 유일하게 결정적이었다.

## 마스터링 전후가 유일한 지상 참값

같은 세대의 원본/마스터 쌍은 "후처리가 무엇을 바꾸는가"에 대한 유일한 지상 참값이다. 50쌍에서 96~100% 일관된 변화:

| 지표 | 변화 | 같은 방향 |
|------|------|-----------|
| LUFS | +3.51 dB | 100% |
| LRA | −3.21 LU | 100% |
| True peak | +3.14 dBFS (→0.00) | 100% |
| Side/Mid | +2.12 dB | 100% |
| Air 8-16k | +3.47 dB | 98% |
| rolloff99 | +3.00 kHz | 100% |
| Crest factor | ±0.02 dB | 변화 없음 |

**중요:** 이 변화량(+3.5 LUFS, −3.2 LU)이 코퍼스 간 격차보다 **크다.** 즉 저작자보다 마스터링 프로필이 더 큰 혼란 변수다. "인간 같은 지표"의 목표는 저작자가 아니라 **마스터링 프로필 일치**여야 한다.

Crest factor가 마스터링에 반응하지 않았다는 점은 그 지표가 마스터링 아티팩트가 아니라 원본 성질이라는 뜻이므로, 후보로는 여전히 유효하다.

## 필터를 샘플레이트별로 설계하되, 표준이 표기한 레이트는 표를 쓴다

scipy 없이 biquad 쓰기:

1. RBJ 공식을 `a0 = 1`로 정규화해 `(b0, b1, b2, a1, a2)` 반환
2. 차분방정식으로 impulse response 직접 생성 (4096 taps 충분)
3. FFT 컨볼루션으로 적용 (긴 파일에서 O(N·M)는 불가)

48kHz는 BS.1770 표기 계수를 **그대로** 쓴다. f0/Q에서 재구성하면 2e-6 어긋나고, 그것이 DC gain 0.01 → 40dB notch → DC gain −9 → +20dB 증폭으로 이어질 수 있다.

## 3분 오디오는 열 때마다 데려가지 않는다

코퍼스 스윕은 파형 전체가 아니라 **포락선**으로 매칭한다. `ffmpeg -ac 1 -ar 8000 -f f32le -`로 100Hz 로그 에너지 포락선만 뽑으면 179개 파일도 수 분에 비교 가능하다. 게인·EQ 변경에 불변이라 마스터링된 쌍도 매칭된다.

원시 샘플 상관은 **검증 단계에만** 쓴다 (포락선이 맞으면 원시 샘플도 맞아야 한다).


## 4. 대조군 규모가 아니라 "다양성"이 신뢰도를 결정한다

단일 아티스트/단일 시대 대조군으로 얻은 지표는 나중에 100배 규모로 재현해도 뒤집힌다.
김현식 1인 1980s MP3에서 crest가 유일한 후보처럼 보였지만, 274명 + 2002~2022 차트 + 무손실로
넓히자 human/AI median이 겹쳤다. 교차 검증도 규모가 아니라 **그룹 구성**에 좌우된다.

검증 순서:

1. 코퍼스 단위 hold-out (생성기가 학습에 없음)
2. 코퍼스 안에서 가수/연도 그룹 hold-out
3. 그 다음에야 랜덤 split

랜덤 split을 먼저 보면 항상 좋은 수치가 나온다. 코퍼스 hold-out을 먼저 본다.
## File-level detector ensemble

- Decode each file once per detector, split it into deterministic overlapping windows, and preserve the segment timeline and model version.
- Return one result per input file even for folder or multi-file requests.
- Keep DSP measurements as evidence and diagnostics. Aggregate learned detector outputs separately.

## WebUI 로컬 탐색기와 분석 이력 (Wave 5)

- 로컬 WebUI 파일 탐색기는 서버 API가 절대 경로의 폴더·지원 음원 목록을 반환하고, 프론트엔드가 파일 모드와 폴더 모드를 분리한다.
- 파일 모드는 체크박스 복수 선택, 폴더 모드는 한 번 클릭 선택·두 번 클릭 이동으로 구현한다.
- 파형·스펙트로그램은 FFmpeg PNG를 `경로 + mtime + 종류` 해시로 캐시해 상세 팝업이 열릴 때 지연 생성한다.
- 분석 결과는 실행별 JSON으로 보존하되, 이력 로딩 시 동일 파일·점수·상태 결과는 중복 표시하지 않는다.
### SongYUE2 compare visualization

The SongYUE2 compare layout uses an SVG waveform with normalized peak lines, a shared fractional playhead, a frequency axis, time axis, and dBFS color bar. Reusing the same 0–1000 SVG coordinate system keeps the seek highlight and white playhead aligned with the spectrogram.

Report lists should expose a structured summary view and keep the JSON endpoint behind the UI; file-level result rows are easier to scan than raw serialized objects.

Score bands can be represented with CSS classes and a `--score-color` variable so cards and detail dialogs share the same thresholds without duplicating rendering logic.

## 분석 이력 카드의 고정 정사각형 그리드

- 고정 카드에는 `grid-template-columns: repeat(auto-fill, 320px)`와 `grid-auto-rows: 320px`을 함께 지정한다.
- 카드 자체도 `width`와 `height`를 320px로 지정하면 열 수가 바뀌어도 X/Y 비율과 `gap`이 유지된다.
- 520px 이하에서만 한 열 `minmax(0, 320px)`로 바꾸고 카드에 `width: 100%; height: auto; aspect-ratio: 1/1`을 적용한다.

카드 크기는 `historyCardSize`, 크기 방식은 `variableHistoryCards`로 저장한다. 고정 모드에서는 같은 CSS 변수를 열·행·카드 폭·높이에 적용하고, 가변 모드에서는 입력값을 최소 열 너비로 사용한 뒤 `ResizeObserver`가 각 카드 높이를 실제 너비와 맞춘다.

## Per-detector analysis options served by one schema (2026-09-27)

- `probe/detector_options.py` is the single source of truth. It exposes `describe()` for the UI and `normalize()` for writes, so the WebUI never hardcodes an option list and cannot drift from the server.
- A detector entry carries `locked` (model-coupled values, e.g. 16 kHz / 5s, 8192 FFT, 1-8 kHz) separate from `options` (user-tunable). Splitting them lets the popup show what cannot change instead of hiding it, which stops users from "fixing" values that are bound to the checkpoint.
- Each option carries `effect`: `score`, `verdict`, or `total`. Rendering a badge from `effect` is cheaper and less error-prone than hand-labelling every field in the UI.
- `includedInTotal` is modelled as a first-class option with `effect: total` rather than a special-cased boolean, so the popup renders it through the same `optionRow()` path as everything else.
- Adapters read live values through `detector_options.for_detector(name)` instead of taking arguments, so adding a knob never changes a detector signature or a caller.
- `analyze_file` snapshots `current()` into the result as `detectorSettings` and `scoreInfo.components` records `method`, `inputs`, `included`, `excluded`, `weights`, `agreement`. Without the snapshot, a score cannot be explained after the fact.
- Keep detector option values in their own `detector-options.json` rather than the general `settings.json`: the general file holds UI preferences, this one holds analysis semantics, and they change for different reasons.
