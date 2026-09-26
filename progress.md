# Progress — ai-music-probe

SongYUE2와 독립적으로 실행되는 로컬 오디오 분석·탐지 앱. 핵심 기능은
음원 파일을 입력으로 받아 분석 결과와 total 점수를 반환하는 재사용 가능한 API이며,
WebUI는 이 API를 호출하는 독립 클라이언트다. SongYUE2 연동은 필수가 아니라
호출 가능한 소비자 중 하나다.
최종 갱신: 2026-09-27

---

## 1. 현재 한 줄 요약

앱은 동작한다. **그러나 "0=human, 100=AI" authorship 점수는 현재 데이터로 만들 수 없다.**
937곡 7코퍼스 실험에서 DSP feature는 생성기가 바뀌면 13.0%(우연 50%, 다수클래스 65.7%)로 붕괴한다.
100%를 내는 유일한 방법은 sample rate를 읽는 것인데, 그것은 authorship가 아니라 파일 내보낸 포맷이다.

---

## 2. 만들어진 것

| 경로 | 역할 | 상태 |
|------|------|------|
| `probe/audioio.py` | ffprobe metadata, native-rate ffmpeg decode | 동작 |
| `probe/dsp.py` | STFT, log spectrum, rolloff, tilt, band energy, transient, stereo, level | 동작 |
| `probe/loudness.py` | BS.1770-4 K-weighting, integrated LUFS, LRA, sample peak, crest | 동작, 교정 완료 |
| `probe/stages.py` | 기존 stage 묶음 비교 호환 계층 | 동작, 주 API로 유지하지 않음 |
| `probe/report.py` | 단계별 delta, peak 비교, chain floor, 포맷 flag | 동작 |
| `probe/app.py` | FastAPI + static | 동작, API smoke test 완료 |
| `probe/cli.py` | `health` / `score` / `serve` | 동작 |
| `probe/detectors/base.py` | SONICS / ArtifactNet / lofcz / attribution 슬롯 | SONICS·lofcz·ArtifactNet 연결, attribution 미구현 |
| `web/index.html`, `web/styles.css`, `web/app.js` | UI | 동작, 브라우저 주요 흐름 확인 |
| `tests/` | API·분석·이력·옵션 회귀 테스트 | **67 passed** |

### API

현재 API는 SongYUE2의 stage 경로·stage 맵을 받는 분석 API다. 제품 목표는
특정 애플리케이션의 폴더 구조에 의존하지 않고 단일 파일, 여러 파일 또는 폴더를
입력받아 **각 파일별** 분석 결과와 total 점수를 반환하는 재사용 가능한 API로
확장하는 것이다. 여러 파일을 보냈을 때도 전체를 하나의 점수로 합치지 않고,
입력 파일마다 파라미터별 결과·근거·0~100 점수를 독립적으로 반환한다. 점수는
다섯 가지 고정 분류를 표시하는 라벨이 아니라 연속적인 처리 흔적 척도이며,
인간 원본 < 인간+AI 마스터링 < AI 생성+인간 마스터링 < AI 생성+AI 마스터링
< AI 생성 원본 순서가 대략 유지될 것이라는 가설을 검증한다. 점수와 처리 단계의
관계가 선형인지 여부와 구간은 calibration 전까지 고정하지 않는다. WebUI와
외부 호출자는 같은 API 계약을 사용하고, stage 비교는 고급 호환 기능으로 남긴다.

```
GET  /health
POST /api/score
POST /api/analyze
GET  /api/detectors
GET  /api/reports
GET  /api/reports/{name}
```

---

## 3. 데이터 세트

### AI (321곡)

| 코퍼스 | 경로 | 수 | 포맷 |
|--------|------|-----|------|
| Suno 원본 | `F:\Music\Music-원본` | 179 | 48kHz WAV |
| Suno LANDR 마스터 | `F:\Music\Music-LANDR-Mastered` | 126 | 48kHz WAV |
| YuE2 | `C:\Claude\SongYUE2\Library\music` | 16 | 48kHz |

### Human (616곡)

| 코퍼스 | 경로 | 수 | 포맷 | 그룹 |
|--------|------|-----|------|------|
| 김현식 | `G:\input\music\김현식` | 17 | 44.1k MP3 | 아티스트 1명, 1980s |
| 멜론 연도별 | `Y:\Music\가요\챠트-멜론 년별` | 46 | 44.1k MP3 | 23개 연도 |
| 가수별 best | `Y:\Music\가요\가수별 best` | 530 | 44.1k MP3 | **274명** |
| 무손실 | `Y:\Music\무손실 음원` | 23 | 44.1k FLAC | 13개 컴필레이션 |

Y: 세트가 추가되면서 해결된 것: ① MP3 대역 리미팅 교란 제거 ② 단일 아티스트 편향 제거.
남은 교란: **AI는 100% 48kHz, 인간 무손실은 44.1kHz 23/26곡.** 포맷 교관은 그대로다.

`>48kHz` 파일 3곡(192k/96kHz)은 48kHz AI 세트와 스펙트럼 비교가 불가능해 제외했다.

---

## 4. 핵심 실험 결과

`scratch/score_build.py --per-subdir 2` → 937곡, 616 human / 321 AI, 311개 그룹

| feature 집합 | 랜덤 split | 코퍼스 hold-out | 가수/연도 hold-out |
|--------------|-----------|----------------|-------------------|
| 포맷만 (sampleRate, codec, lossy, duration) | 100.0% | **98.0%** | 99.5% |
| DSP만 (admissible) | 75.5% | **13.0%** | 76.3% |
| 전부 | 99.6% | 98.0% | 99.5% |

기준선: 다수 클래스 = 616/937 = **65.7%**

### 읽는 법

- **98%는 위조다.** 인간 44.1kHz / AI 48kHz이므로 sample rate 하나로 분리된다. 48kHz human master를 "100 AI", 44.1kHz AI render를 "0 human"으로 부르는 classifier다.
- **13%는 우연보다 나쁘다.** 보편 추정이 뒤집힌다. 코퍼스가 바뀌면 학습된 방향이 반대로 도는 것 → 모델이 authorship가 아니라 "어느 코퍼스인지"를 배운다.
- **76.3% (가수/연도 hold-out)** 가 실제로 유일하게 의미 있는 수치지만, 배포 가능한 수준이 아니다.

---

## 5. 탐지기 옵션과 최신 ArtifactNet 실험

ArtifactNet 기본값은 `11구간 / even / top-3 / levelNormalize=false`로 설정했다. E0001 네 곡에서 `5구간+최댓값`과 비교한 결과는 다음과 같다.

| 음원 | 5구간 + 최댓값 | 11구간 + Top-3 |
|------|----------------:|----------------:|
| 인간 원곡 | 0.1 | **0.0** |
| E0001 AI 원곡 | 93.2 | 91.3 |
| E0001 LANDR 후처리 | 86.3 | 74.5 |
| E0001 SongYUE2 다듬기 + Mastering-1 | 84.7 | 86.4 |

11구간 + Top-3는 최댓값보다 단일 고점에 덜 의존하므로 현재 우선 후보로 채택했다. 후처리 두 결과의 상대 순서는 예상과 달라 paired corpus를 늘려 검증해야 한다. 기본값을 바꿔도 `detector-options.json`의 설정은 다음 분석부터 적용되며 기존 결과는 변경되지 않는다.

## 6. crest 가설의 사망

17곡 김현식 세트에서 crest factor가 human [17..22] dB vs AI [11..16] dB로 완전히 갈라져
"유일하게 유망한 후보"로 보였었다. 코퍼스를 40배로 넓히자 median이 겹쳤다.

| 코퍼스 | crest median (dB) |
|--------|-------------------|
| 김현식 (1인, 1980s) | **18.31** |
| 멜론 연도별 | 12.16 |
| 가수별 best | 13.40 |
| 무손실 | 13.62 |
| Suno 원본 | 13.66 |
| Suno 마스터 | 13.69 |
| YuE2 | 16.08 |

김현식이 "human"이 아니라 **특정 시대의 아날로그 녹음**이었다.
2010~2020년대 인간 음원 median은 12~14dB로 AI와 사실상 같다.

> 교훈: 단일 아티스트·단일 시대 대조군에서 분리되는 어떤 지표든, 대조군을 넓히면 사라진다.

---

## 6. 검증에서 걸러진 지표 (쓰지 말 것)

### mastering에 휘발됨 — authorship 점수 금지

50쌍 Suno 원본/LANDR 마스터로 실측. 방향 일관성 100%:

| 지표 | 마스터 전→후 | 일관성 |
|------|-------------|--------|
| LUFS | +3.51 dB | 50/50 |
| LRA | −3.21 LU | 50/50 |
| true peak | +3.14 dBFS (중앙값 0.00) | 50/50 |
| side/mid | +2.12 dB | 50/50 |
| rolloff99 | +3.00 kHz | 50/50 |
| air (8–16k) | +3.47 dB | 49/50 |
| crest | ±0.02 dB | 변화 없음 |

마스터링은 사용자의 선택이지 authorship의 속성이 아니다. 위 지표로 점수를 만들면
"마스터링 도구를 돌렸나"를 측정하게 된다.

### container에 휘발됨 — provenance 기록용

동일 PCM을 MP3/WAV로 저장하면 null 주파수 19253.9 → 24000 Hz, comb 간격 237.16 → 197.96 Hz.
스펙트럼 지표는 파일 저장 포맷에 의존한다.

### specificity 실패 — 폐기

`spectral_comb`가 인간 17/17에서 AI 15/16보다 더 강하게 검출됨. **사용 금지.**
`COMB_ENABLED = False`. `harmonic_grid` / `HARMONIC_*` 경로도 폐기.

---

## 7. SongYUE2 실측

`C:\Claude\SongYUE2\runs\775331c1-72e4-498f-b72f-ff3be97672fc\stems`

| stage | sample rate | codec | 길이 | spectral tilt |
|-------|-------------|-------|------|---------------|
| source | 44,100 | pcm_s16le | 48.5s | −3.69 |
| instrumental | 44,100 | pcm_s16le | 48.5s | −4.23 |
| vocal_post_svc | 44,100 | pcm_s16le | 48.5s | **+0.67** |

SVC 후 digital null 21318 Hz. `vocals-original`이 없어 SVC 전 보컬 단계는 측정 불가.

---

## 8. 재현 방법

```powershell
cd C:\Claude\ai-music-probe
.\.venv\Scripts\python.exe -m pytest -q                    # 13 passed
.\.venv\Scripts\python.exe -m probe.cli health
.\.venv\Scripts\python.exe scratch\score_build.py --per-subdir 2
```

`scratch/score_features.json`(520KB)이 feature 캐시다. 삭제하지 않으면 재실행이 즉시 끝난다.
`--refresh`는 937곡 재디코딩에 약 10분 걸린다.

| 스크립트 | 용도 |
|----------|------|
| `scratch/score_build.py` | 7코퍼스 점수 실험 + CV (핵심) |
| `scratch/mastering_delta.py` | Suno 원본/마스터 50쌍 페어링 + delta |
| `scratch/corpus_sweep.py` | 코퍼스별 지표 분포 |
| `scratch/comb_validate.py` | comb 감도/특이도 검증 |
| `scratch/stability_check.py` | 동일 PCM container 안정성 |
| `scratch/grid_check.py` | DSP 개발 검사 |

---

## 9. 정직한 한계

1. authorship 0-100 점수는 **현재 불가**. DSP로는 생성기 변경 시 13.0%.
2. ML detector(SONICS / ArtifactNet / lofcz) 가중치 없음 — `onnxruntime`도 미설치.
3. 인간 코퍼스가 한국 가요 중심이라 AI 세트(영어 포크/재즈)와 장르가 다르다. 이것도 미보정 confound.
4. API 브라우저 스모크 테스트 미실시.
5. `probe/app.py`와 `web/app.js`의 `deltaBar()` CSS `top` 덮어쓰기 버그 미수정.
6. git 저장소가 아니다 (`fatal: not a git repository`).
