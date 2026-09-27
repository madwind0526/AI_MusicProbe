# Revision Log — ai-music-probe

가설이数据和 어떻게 무너졌는지, 그리고 그때 무엇을 고쳤는지.
최종 갱신: 2026-09-27

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

## R6. 초기 상태에서 아직 안 한 것에 대한 기록

| 항목 | 상태 |
|------|------|
| ML detector 가중치 (SONICS / ArtifactNet / lofcz) | 당시 미구득, 현재 SONICS·ArtifactNet·lofcz 연결 완료 |
| 브라우저 UI 스모크 테스트 | 당시 미실시, 현재 주요 흐름 확인 완료 |
| `web/app.js::deltaBar()` CSS `top` 덮어쓰기 | 미수정 |
| git 저장소 | 당시 아님, 현재 Git 저장소 사용 중 |
| 한국 가요 vs 영어 포크 장르 confound | 미보정 |
| `vocals-original` 부재로 SVC 전 보컬 측정 | 불가 |

---

## R7. ArtifactNet 기본 집계 변경 및 E0001 4종 비교 (2026-09-27)

ArtifactNet의 구간 수와 집계 방법을 E0001 네 곡으로 비교했다. SONICS와 lofcz는 기존 설정을 유지하고 ArtifactNet만 바꿨다.

| 음원 | 5구간 + 최댓값 | 11구간 + Top-3 평균 |
|------|----------------:|--------------------:|
| 인간 원곡 | 0.1 | **0.0** |
| E0001 AI 원곡 | **93.2** | 91.3 |
| E0001 AI 원곡 + LANDR 후처리 | 86.3 | **74.5** |
| E0001 AI 원곡 + SongYUE2 다듬기 + Mastering-1 | 84.7 | 86.4 |

최댓값은 구간 하나의 고점에 크게 의존했다. 11구간 + Top-3 평균은 인간 원곡과 AI 원곡을 분리하면서 단일 이상치 영향을 줄여 기본값으로 채택했다. 다만 LANDR과 SongYUE2 후처리의 순서가 예상과 달랐으므로 이 설정을 authorship 보정값으로 확정하지 않고 E0002·E0003 및 다양한 인간 원곡에서 재검증한다.

추가로 `DetectorValueRequest`에 ArtifactNet `levelNormalize` 필드를 보강해 UI에서 변경한 값이 API에서 버려지지 않도록 했고, 전체 회귀 테스트 67개가 통과했다.

---

## R8. 90곡 앵커 평가와 운영 안전장치 (2026-09-27)

인간 원본 30곡과 동일 곡의 Mastering-1 30곡을 만들고, E/J/K로 시작하는 AI 원본을 각각 10곡씩 골라 총 90곡을 현재 3개 탐지기로 평가했다. 후처리 AI 음원은 이번 범위에서 제외했다.

- 인간 원본 중앙값 0.1, 최댓값 1.5
- 인간 Mastering-1 중앙값 0.1, 최댓값 2.3
- AI 원본 전체 최솟값 8.9
- raw threshold balanced accuracy 0.7167, Brier 0.1278
- pair-group 보정 5-fold balanced accuracy 0.9917, Brier 0.0111
- artist/year 및 E/J/K 그룹 보정 5-fold balanced accuracy 0.9750, Brier 0.0333

교차 검증 수치는 좋아졌지만 현재 표본의 완전 분리 때문에 isotonic 출력이 0과 100 두 값으로 붕괴했다. 이는 연속 Total 점수의 순위를 제거하므로 보정 모델을 런타임에 채택하지 않았다.

상세 보기에는 탐지기별 점수와 미사용·미설치·분석 실패 상태, 점수 색 점, 구간별 타임라인을 추가했다. 설정은 5개 점수 구간을 같은 크기로 표시한다. 배치 분석은 현재 파일 순번을 보여주며, 분석 화면과 독립 이력 화면 모두 제목과 정렬 도구가 스크롤 중 고정된다.

서버에는 파일별·요청 전체 업로드 제한, 활성·대기 분석 수 제한, JSON/CSV 리포트 내보내기를 추가했다. 전체 회귀 테스트 72개와 브라우저 주요 흐름을 확인했다.

설정 화면의 점수 구간 제목은 각 구간의 시작 숫자 왼쪽과 정렬했다. 분석 중 진행률은 음원 분석 패널과 왼쪽 메뉴의 최근 작업 이력·음원 비교 사이 Box에 동시에 표시하며, `작업 진행 중…`, `5/10`, 완료·오류 상태를 갱신한다.

---

## R9. ensemble 기본값 `robustMean` 확정과 90곡 anchor 재계산 (2026-09-27)

**가설(사용자 제기):** 이상치 제외 평균에서 SONICS 20.8 / lofcz 0.0 / ArtifactNet 99.8이 나온 파일(K0062)의 totalScore가 40.2로 나온 건, lofcz의 0.0을 이상치로 제외한 뒤 나머지 두 값을 3으로 나누는 나눗셈 버그다. `(99.8+20.8)/2`가 맞다.

**조사:** 실제 리포트를 확인하니 `outliersExcluded: []` — 아무것도 제외되지 않았고 3개 평균이 그대로 쓰였다. `_robust_mean`은 n=3일 때 median이 항상 가운데 값이 되므로, median에서 먼 쪽이 이상치 후보가 된다. 이 케이스는 median(20.8)에서 0.0까지 거리(20.8)가 99.8까지 거리(79.0)보다 짧아, 중립적 통계로는 오히려 **99.8 쪽이 이상치에 더 가깝다**(z≈2.57 vs z≈-0.67, 둘 다 컷오프 3.5 미만이라 결국 제외 없음). "낮은 값을 우선 배제"는 통계가 아니라 정책 판단이라 사용자에게 확인을 구했다.

**결정:** 사용자가 "임계값 완화 없이 현행 유지"를 선택. `ROBUST_Z_THRESHOLD`(3.5)와 `_robust_mean` 로직은 변경하지 않았다. 특정 탐지기를 더 신뢰하고 싶으면 `weightedGeometric` + 가중치로 명시적으로 정책화할 것.

**부수 확인:** 이 조사 중 `detector-options.json`의 ensemble 기본값이 이미 `robustMean`으로 확정돼 있었고, 실제 분석 이력 100개도 이 방식으로 재계산돼 있었다(`scripts/recompute_totals.py`로 detector 원점수는 그대로 두고 totalScore만 일괄 재계산하는 방식). 이 변경이 90곡 anchor 코퍼스에는 아직 반영되지 않아, `scratch/evaluate_anchor_corpus.py`의 통계 함수를 재사용해 `probe.file_analysis.analyze_files`를 직접 호출하는 방식으로(실 분석 이력은 안 건드림) 90곡을 재분석했다.

| 지표 | R8(이전) | R9(재계산) |
|------|---------:|----------:|
| 인간 원본 최댓값 | 1.5 | 26.6 |
| 인간 Mastering-1 최댓값 | 2.3 | 25.6 |
| AI 원본 최솟값 | 8.9 | 43.2 |
| 인간·AI 간격 | 6.6 | 16.6 |
| raw threshold balanced accuracy | 0.7167 | 0.8833 |
| pair-group 5-fold 보정 balanced accuracy | 0.9917 | 0.9917 |
| isotonic 레벨 수 | 2(붕괴) | 2(붕괴, 재현) |

간격은 넓어지고 raw 정확도도 크게 개선됐지만, isotonic 붕괴는 여전히 재현된다. 인간 원곡 쪽에도 20점대 오탐 후보(`George Michael - Outside` 26.6)가 새로 나타나 다음 검증 대상에 추가했다. 상세는 `scratch/evaluations/anchor-corpus-evaluation.json`/`.csv`, README `90곡 anchor 교차 검증` 절 참고.

---

## R10. 코드 리뷰 높은 중요도 결함 수정 (2026-09-27)

경로 이탈 이력 삭제, True Peak 마지막 샘플 누락과 선형 보간, 멀티채널 LUFS 가중치, MAD=0 이상치 누락, 0 가중치 검증 우회, ArtifactNet 중복 구간, 업로드 이름 순서 오류를 수정했다. ffmpeg/ffprobe timeout, 손상 리포트의 400 응답, 부분 설정 패치 보존, 자원 폴링 중복 방지, 상세·비교 화면의 오래된 응답 차단도 함께 반영했다.

`recompute_totals.py`는 과거 결과의 Total을 실제로 갱신하는 도구라는 사용자 의도를 유지했다. 자동 백업을 강제하지 않고, 임시 파일 교체 방식의 원자 저장과 `--dry-run`, 허용 방식 검증, 결과별 기존 가중치 보존을 추가했다. 회귀 테스트는 프로젝트 루트와 상위 폴더 실행에서 각각 87개 통과했다.

### Scratch 정리 정책

앱 lifespan 시작 단계에서 리포트와 분석 이력의 `file` 경로를 모아 참조 중인 업로드 원본을 판별한다. 참조되지 않는 `scratch/uploads` 파일과 현재 `path+mtime+kind`에 해당하지 않는 `scratch/visuals` PNG를 삭제한다. 분석 저장, 이력 제한 적용, 개별 이력·리포트 삭제 뒤에도 다시 정리해 삭제된 항목의 캐시가 남지 않게 했다. 참조 중인 업로드는 이력의 오디오 재생을 위해 보존한다.

### N-1. Loudness 프로덕션 배선

`probe/loudness.py`의 BS.1770 계산은 정밀 테스트만 존재하고 `dsp.analyze()`에서 호출되지 않았다. `level_metrics()`와 `integrated_loudness()`·`crest_factor_db()`를 `level_profile()`로 합쳐 실제 API의 `parameters.levels`에 연결했다. UI 계약에 맞춰 `integratedLufs`, `truePeakDbtp`, `crestDb`를 출력하고, 기존 비교 API가 사용하는 `truePeakDbfs` 등 기존 키도 유지했다.

---

## R11. 재시작 시 새 서버가 살아남은 서버의 포트를 빼앗음 (2026-09-27)

서버를 실행한 채 `start.bat`을 다시 실행하면 브라우저의 SSE(`/api/analysis/stream`)가 끊겼다가 새 서버에 다시 붙고, 화면은 "분석 완료 3/4"에서 멈췄다. 서버 로그에 오류가 없어서 Python 크래시로 오인했다. 실제로는 크래시가 아니었고 **Application Error ID 1000 기록 자체가 없었다.**

원인은 세 가지가 겹친 것이었다.

첫째, Windows 소켓은 `SO_REUSEADDR`로 **TIME_WAIT가 남아 있어도 이미 다른 프로세스가 LISTEN 중인 포트에 bind와 listen이 성공**한다. 즉 이전 서버가 살아 있는 포트를 새 인스턴스가 그대로 가져간다.

둘째, 기존 `stop.bat`은 `netstat -ano`로 포트 8792의 PID를 잡아 종료했는데, 실제 프로세스 트리에서 `python.exe`는 그보다 위쪽 launcher의 자식이었다. 남은 launcher가 살아 있어서 kill과 재시작 사이 1초 안에 포트가 정리되지 않았다.

셋째, 그 결과 **죽인 인스턴스가 아니라 살아남은 인스턴스**가 포트를 계속 보유했다.

`stop.bat`을 `Win32_Process` 조회로 바꿔 `python.exe`이면서 명령행에 `probe.app`이 있는 프로세스를 전부 종료하고, 8792이 해제될 때까지 최대 10초 기다리도록 했다. `start.bat`은 시작 전에 `stop.bat`을 호출한다. 명령행 패턴이 `probe.app`으로 한정되어 있어 같은 포트를 쓰는 무관한 서버는 건드리지 않는다.

검증에서 기존 방식이 놓치던 유령 서버 3개가 남아 있었고(잔여 메모리 2,317 MB), 8190 포트의 ComfyUI 서버는 그대로 생존했다. 서버 실행 중 `start.bat`을 다시 실행하자 launcher와 서버가 신규 2개만 남고 이전 인스턴스는 0개가 되었으며, `/health` OK·탐지자 4개 active·상태 idle을 확인했다.

### M-21 기각과 M-23 집계 정정

같은 회차의 코드 리뷰에서 **M-21을 기각**했다. 최초 리뷰는 `audioio.load()`가 `-ar`/`-ac`로 44100/1을 강제한다고 적었지만, 실제로는 ffprobe로 읽은 `meta.sample_rate`/`meta.channels`(파일 네이티브 값)을 넘긴다. 동일 값 지정은 옵션 생략과 바이트 단위로 같고 `git diff`에도 해당 변경이 없어, 모듈 docstring과 코드가 처음부터 일치했다.

**M-23은 미해결로 되돌렸다.** Round 3에서 M-2와 묶어 "자체 수정"으로 집계했지만 실제로는 M-2의 `ddof=1`만 반영되었고, `audioio.py`의 `nan_to_num` 무음 치환은 그대로다.

### 판정 방식

M-8과 M-17을 이미 해결된 상태로 "미해결"이라 잘못 보고한 것이 이번 회차의 직접적인 원인이었다. 두 건 모두 **패턴 grep**만 보고 판단했다 — M-8은 상수 선언 `MIN_NORMALISATION_STD = 1e-6`이 남아 있는 것을 보고, M-17은 `payload.get(` 라인이 남아 있는 것을 보고 실제 가드는 별도 라인의 `isinstance(payload, dict)`였음을 놓쳤다. 이는 같은 문서 안에서 "grep 패턴은 존재 부부의 증거이지 부재의 증거가 아니다"고 기록해 둔 원칙을 자기 자신이 위반한 것이며, 세 번째 반복이다. 이제부터 판정은 항상 함수의 전체 본문을 읽은 뒤에만 내린다.
