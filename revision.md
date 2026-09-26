# Revision Log — ai-music-probe

가설이数据和 어떻게 무너졌는지, 그리고 그때 무엇을 고쳤는지.
최종 갱신: 2026-09-26

---

## R1. 조화 격자(harmonic grid) 지표

**가설:** AI 생성 음원은 vocoder/VAE 아티팩트로 특정 배음 격자를 갖는다. 배율 간격을 추출하면 탐지 가능하다.

**구현:** 고정 허용오차(tolerance)로 배음 peak를 찾는 방식. `HARMONIC_*` 상수를 `probe/config.py`에 추가.

**실패:** tolerance가 고정이라 인접 peak가 같은 배율로 흡수되어 peak 목록이 24개로 포화되고 간격이 5.38 Hz로 퇴화. 그리고 근본적으로:

- 인간 파일에서 AI보다 **더 강하게** 검출됨
- 동일 PCM을 MP3/WAV로 저장하면 간격이 237.16 → 197.96 Hz로 변함
- human 17/17 strong, AI 15/16 strong

**결론:** 폐기. `harmonic_grid`, `HARMONIC_*` 상수 전부 제거.

---

## R2. comb residual 지표

**가설:** 아날로그 tape saturation 특유의 고조파 comb가 AI 출력에서 결손한다. peak 사이 잔차로 검출한다.

**구현:** `probe/dsp.py::spectral_comb()`, `COMB_*` 상수.

**검증 (`scratch/comb_validate.py`):**

| control | 결과 |
|---------|------|
| 합성 300 Hz comb | 통과 (1.46 Hz 오차) |
| white noise | strong으로 오검출 안 됨 |
| soxr 44.1k→32k 리샘플 | comb 안 생김 |

**실패:** 실제 파일에 적용하니 인간 17/17이 AI 15/16보다 강했다. 특정 주파수 정수배가 강하다는 건 AI 부재가 아니라 **resonator/room 모드**의 존재다.

**결론:** `COMB_ENABLED = False`로 비활성화. `spectral_comb()`는 탐색용으로 코드만 남김. `artifactFingerprint`는 UI 표시용으로 강등.

---

## R3. crest factor가 답이 되리라

**관찰:** 최초 17곡(김현식) 코퍼스에서 crest factor가 완전히 갈라졌다.

- 김현식 (human): median **18.3 dB**, range [17..22]
- Suno 원본: median **13.7 dB**, range [11..16]
- Suno 마스터: median **13.7 dB** — mastering에도 불변
- YuE2: median 16.1 dB

겹치는 구간이 없고, 50쌍 mastering 대조군에서 변화가 ±0.02 dB뿐이었다.
**유일하게 유망한 후보**로 지목되었다.

**패배:** Y: 코퍼스(274명 + 멜론 2002~2022 + 무손실 5813곡)로 확장하자:

| 코퍼스 | crest median (dB) |
|--------|-------------------|
| 김현식 (1인, 1980s) | **18.31** |
| 멜론 연도별 | 12.16 |
| 가수별 best | 13.40 |
| 무손실 | 13.62 |
| Suno 원본 | 13.66 |
| Suno 마스터 | 13.69 |
| YuE2 | 16.08 |

2010~2020년대 인간 음원이 12~14 dB. AI와 겹친다.

**원인:** 김현식 녹음(1980s 아날로그 테이프)이 "human"이 아니라 **특정 시대의 특정 장치**였음.

**교훈 (PATTERNS.md §4로 기록):** 대조군의 *규모*가 아니라 *다양성*이 신뢰도를 결정한다. 단일 아티스트/단일 시대 대조군에서 분리되는 지표는 대조군을 넓히면 반드시 사라진다.

---

## R4. 내 스크립트의 두 가지 버그 (자기 검증)

937곡 첫 실행에서 `admissible feature만 83.9%`가 나왔다. 그 숫자가 거짓이었다.

### 버그 1 — `onsetCount`는 duration proxy였다

`ADMISSIBLE`에 `onsetCount`를 넣었는데, 실제 값:

| 코퍼스 | onsetCount | duration | onsets/sec |
|--------|-----------|----------|-----------|
| 김현식 | 2296 | 245 s | 9.4 |
| Suno 원본 | 1580 | 157 s | 10.1 |
| YuE2 | 1313 | 134 s | 9.8 |

raw count는 duration을 선형 따라간다. **onsets/sec는 전 코퍼스 8.4~10.3으로 거의 일정.**
모델이 "인간 파일이 더 길다"를 학습한 것이었다. duration을 admissible에서 빼놓고 그 직접 부산물을 넣은 것.

**수정:** `onsetCount` → `onsetRatePerSec` = `onsetCount / durationS`. 결과 83.9% → 75.5%.

### 버그 2 — 그룹 CV가 자명한 100%를 냈다

`group_accuracy`에서 train을 **같은 코퍼스로만** 제한했다. 코퍼스 안에서는 라벨이 전부 같아서(인간 코퍼스면 전부 0) 상수 하나만 배우면 100%가 된다. 의미 없는 지표였다.

**수정:** train을 전체 코퍼스로 확장하고, held-out 그룹만 제외.

---

## R5. 최종: DSP로는 점수가 성립하지 않는다

두 feature 집합을 같은 937행에 대해 비교했다.

| feature 집합 | 랜덤 split | 코퍼스 hold-out | 가수/연도 hold-out |
|--------------|-----------|----------------|-------------------|
| 포맷만 | 100.0% | 98.0% | 99.5% |
| DSP만 (수정 후) | 75.5% | **13.0%** | 76.3% |
| 전부 | 99.6% | 98.0% | 99.5% |

다수 클래스 기준선 = 616/937 = 65.7%.

- **포맷 98%** — 인간 44.1kHz / AI 48kHz. authorship가 아니라 파일 내보낸 포맷을 읽는다. 48kHz human master를 100 AI로 부른다.
- **DSP 13.0%** — 기준선보다 나쁘다. 보편 추정 방향이 통째로 뒤집힌다. 코퍼스가 바뀌면 학습된 방향이 반대로 돈다.

**결론: 0-100 authorship 점수는 ML detector 없이는 ship 불가.**

---

## R6. 아직 안 한 것에 대한 정직한 기록

| 항목 | 상태 |
|------|------|
| ML detector 가중치 (SONICS / ArtifactNet / lofcz) | 미구득, `onnxruntime` 미설치 |
| 브라우저 UI 스모크 테스트 | 미실시 |
| `web/app.js::deltaBar()` CSS `top` 덮어쓰기 | 미수정 |
| git 저장소 | 아님 |
| 한국 가요 vs 영어 포크 장르 confound | 미보정 |
| `vocals-original` 부재로 SVC 전 보컬 측정 | 불가 |
