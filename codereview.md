# codereview.md

ai-music-probe 전체 코드 리뷰

- 최초 리뷰 대상: `656cf1c` (2026-09-27) — 커밋된 전체 소스
- 범위: `probe/` 22개 파일 (약 3,600줄 Python), `web/` 5개 파일 (약 1,700줄), `tests/` 9개, `scripts/` 1개
- **현행 기준선: `70a0829` + 미커밋 35개 파일(127 tests)**
- 최초 리뷰는 읽기 전용이었고, 이후 Round 3~7에서 아래 명시된 항목만 수정했습니다.

> **인코딩 repaired (2026-09-27)**: 이 파일의 부록이 CP949 바이트로 기록되어 UTF-8 본문과
> 혼재 인코딩 상태였습니다. 부록 7,532바이트를 CP949로 디코드해 UTF-8로 재기록했습니다
> (replacement character 0건, 내용 무손실).

## 검증 표기

| 표기 | 의미 |
|------|------|
| **[확인]** | orchestrator가 소스 + venv 실행으로 직접 재현함. 사실로 확신 |
| **[정적]** | 소스 정독으로 확정. 미실행. 신뢰도 높음 |
| **[설계]** | 버그가 아니라 설계 선택에 대한 지적 |
| **[수정]** | 이후 리뷰 회차에서 실제로 코드로 수정됨 |
| **[잔존]** | 2026-09-27 현재에도 코드에 남아 있음 |

심각도 집계: **높음 15 / 중간 24 / 낮음 64·(정적)**, 총 103건.
수치 버그 후보 중 **[확인] 6건은 전부 재현 성공**했습니다. 반대로 서브에이전트가 보고한 1건은
재현 시나리오를 교정하니 **기각**했습니다(아래 「기각된 보고」 참고).

## 현행 결론 (2026-09-27, Round 7 반영)

| 등급 | 전체 | 해결 | 잔존 | 기각 |
|---|---|---|---|---|
| 높음 | 15 | **15** | 0 | 0 |
| 중간 | 24 | **21** | **2** (M-20, M-23) | **1** (M-21) |
| 낮음/정적 | 64 | 0 | 64 | 0 |

- **Round 6**에서 M-3·M-8·M-9·M-10·M-11·M-17·M-24를 수정했습니다.
- **Round 7**은 `start.bat`/`stop.bat`의 포트 처리 결함(R-4)을 고쳤습니다. 상세는 부록 「Round 7」 참고.
- **M-21은 기각**했습니다. 최초 리뷰는 `-ar`/`-ac`가 44100/1을 강제한다고 적었으나,
  `audioio.load()`는 ffprobe로 읽은 **파일 네이티브 값**(`meta.sample_rate`/`meta.channels`)을
  넘깁니다. 동일 값 지정은 옵션 생략과 바이트 단위로 같고 `git diff`에도 해당 변경이 없습니다.
  docstring과 코드가 처음부터 일치했으므로 문서 항목이 아니라 **기각**이 맞습니다.
- **M-23은 미해결**입니다. Round 3 집계에서 "자체 수정"으로 잘못 세었으나 실제 코드는 그대로입니다.
- M-20은 기본 loopback 실행에서는 허용되는 설계이며, 외부 네트워크 바인딩을 지원할 때
  인증 또는 탐색 루트 제한이 필요합니다.
- 리뷰 중 발견한 **R-3 성능 회귀는 Round 6에서 overlap-add convolution으로 수정**했습니다.

---

## 1. 높음 (High) — 15건

### C-1 [확인] `delete_history`가 임의 파일 삭제/덮어쓰기에 열려 있음

`probe/history.py:239-246`

```python
def delete_history(item_id: str) -> bool:
    try:
        stem, raw_index = item_id.rsplit(":", 1)
        index = int(raw_index)
    except (ValueError, TypeError):
        return False
    candidates = [REPORTS_DIR / f"{stem}.json", HISTORY_DIR / f"{stem}.json"]
```

`item_id`는 `DELETE /api/history/{item_id:path}` (`app.py:300`)로 들어옵니다. `:path` 변환자는
**슬래시를 명시적으로 허용**합니다. `_report_path`(`app.py:605-611`)는 `/`, `\`, `..`를 거부하지만
이 함수에는 이름 검증이 전혀 없습니다.

직접 계산 결과:

```
id='20260927T030000Z_abcd1234:0'  -> C:\Claude\ai-music-probe\reports\2026...json   inside=True
id='../../../../scratch/loot:0'   -> C:\scratch\loot.json                            inside=False
```

`C:\scratch\loot.json`은 리포트 디렉터리 밖입니다. 대상이 존재하고 JSON 파싱되며 `results` 리스트가
있으면 **삭제**(0건)하거나 **재포맷 JSON으로 덮어쓰기**(2건 이상) 합니다. 인증·확인·로그 없음.

**완화 요소:** 서버가 loopback에만 바인딩된다면 원격 공격은 어렵습니다. 그래도 방어적 검증이
필요하며, 동일 라우트 계열인 `set_favorite`(`app.py:293`)는 `load_history()`가 만든 id만 조회하므로
안전합니다. 이 비대칭이 방치된 이유입니다.

### C-2 [확인] true peak 계산이 마지막 샘플을 버림

`probe/dsp.py:470-475`

```python
def _interpolate_4x(x: np.ndarray) -> np.ndarray:
    if x.size < 4:
        return x
    positions = np.arange(x.size - 1) * 4
    grid = np.arange((x.size - 1) * 4, dtype=np.float64)
    return np.interp(grid, positions, x[:-1].astype(np.float64))
```

`x[:-1]`이 마지막 샘플을 버리고, `np.interp`는 구간 끝점을 외삽하지 않습니다.

```
input max=0.900  output max=0.300   (len 4 -> 12)
```

**마지막 프레임이 최대인 트랙은 `truePeakDbfs`가 `peakDbfs`보다 낮게 보고됩니다** — 지표 이름과
주석이 약속하는 것과 정반대입니다.

부수 문제 [정적]: `np.interp`는 **구간 선형** 보간이라 볼록성에 의해 `max(|x[n]|,|x[n+1]|)`를
구조적으로 초과할 수 없습니다. 따라서 4배 오버샘플링으로 인터샘플 피크를 잡을 수 없고,
`truePeakDbfs ≤ peakDbfs`는 항상 성립하는 불변식이 됩니다. 실제로 4배 오버샘플링이 필요하면
다항식 보간(예: `scipy.interpolate` cubic spline)이 필요합니다.

### C-3 [확인] BS.1770 채널 가중치가 L/R에도 적용됨

`probe/loudness.py:170`

```python
gains = np.full(channels, 1.0 if channels == 1 else (1.0 if channels == 2 else SURROUND_GAIN))
```

직접 실행:

```
1ch -> [1.]
2ch -> [1. 1.]
6ch -> [1.41 1.41 1.41 1.41 1.41 1.41]
```

BS.1770-4는 **L/R = 1.0**, 서라운드만 1.41입니다. 5.1에서 L=R=1, 서라운드≈0인 신호를 넣으면
코드는 `1.41²·(1+1) = 3.98`, 규격대로면 `2.0` → **에너지 +3 dB → LUFS +6.0 dB 오차**.
`AUDIO_EXTENSIONS`에 `.aiff`/`.aif`가 있어 도달 가능합니다. 같은 함수의 60행 주석이 규격을
올바르게 서술하고 있어, 코드와 주석이 정면으로 충돌합니다.

### C-4 [확인] `robustMean`의 이상치 제거가 MAD=0에서 완전히 무력화됨

`probe/file_analysis.py:76-79`

```python
mad = float(np.median(np.abs(values - median)))
if mad == 0.0:
    return float(np.mean(values)), []
```

MAD가 0이면 이상치 판정 없이 **전부 평균**냅니다. n=3에서 MAD=0은 정렬 인접 두 값이 같을 때
발생하므로, 두 탐지기가 소수 4자리에서 같은 값으로 반올림되면 일상적으로 닿습니다.

```
[0.854, 0.996, 0.0] -> total=0.9250  outliers=['d2']   (정상 동작)
[0.854, 0.854, 0.0] -> total=0.5693  outliers=[]       (0.0 이득자가 그대로 평균에 합류)
```

UI 힌트(`detector_options.py:61-63`)가 예시로 든 `[0.854, 0.996, 0.0]`만 정확히 설명합니다.

### C-5 [확인] 모든 가중치 0 방어 가드가 `attribution` 때문에 무력화

`probe/detector_options.py:194-199` + `:326-333`

`DEFAULT_INCLUDED`에 `attribution: True`가 들어 있고, 이 이름은 **탐지기 결과에 절대 나타나지
않습니다**. 검증 로직은 `included` 목록과 가중치를 교차 검사하는데:

```
included list                 = ['sonics','lofcz','artifactnet','attribution']
weights sent                  = {'sonics':0.0,'lofcz':0.0,'artifactnet':0.0}
weights.get('attribution',1.0)= 1.0
any(weight>0) over included   = True
-> 0-가중치 가드 발동 여부    = False
```

`PUT /api/detector-options`로 실제 탐지기 3개 가중치를 모두 0으로 저장이 통과하고, 이후 모든 분석이
`totalScore: null` + `"Total 반영 탐지기가 없어 점수를 계산하지 못했습니다."`가 됩니다. 이 가드는
바로 그 실패를 막으려고 만들어졌습니다. `web/app.js:733`의 클라이언트 쌍도 동일 결함이라 토스트조차
나지 않습니다.

### C-6 [확인] ArtifactNet 구간 시작점 clamp가 중복 구간을 만든다

`probe/detectors/artifactnet.py:66-69`

```python
tail = length - SEGMENT_SAMPLES
if selection == "start":
    return [min(index * SEGMENT_SAMPLES, tail) for index in range(count)]
```

짧은 파일에서는 `index * SEGMENT_SAMPLES`가 `tail`을 넘어 **clamp**되고, 같은 시작점이 반복됩니다.

```
 4.5초 클립 (len=198450) -> starts=[0, 22050, 22050, 22050, ...]  unique= 2/11
20.0초 클립 (len=882000) -> starts=[0,176400,352800,529200,705600,705600,...]  unique= 5/11
```

출시 기본값이 `aggregation:"top3"`이므로 "상위 3개 구간 평균"이 **같은 창 3벌의 평균**이 되고,
보고서는 이를 서로 뒷받침하는 3개 구간으로 제시합니다.

`tests/test_detector_aggregation.py:70-75`(`test_artifactnet_start_selection_clamps_to_the_last_full_segment`)
가 clamp 경로를 건드리지 않아 **스위트가 이 부분을 잘못 안심시키고 있습니다.**

### C-7 [확인] `recompute_totals.py --method`가 검증 없이 조용히 기하평균으로 대체

`scripts/recompute_totals.py:76,84` + `probe/file_analysis.py:101`

`/api/analyze`, `/api/analyze/progress`, CLI는 모두 `detector_options.normalize()`를 지나지만
이 스크립트만 우회합니다. 오타가 `_combine`의 마지막 `return`으로 흘러 **기하평균으로 재계산**되고
`"detector-geometric-mean-v1"`로 기록됩니다. 검증 결과: `--method harmonic` 실행 시 total `77.1`이
기하평균 값으로 stamp되고 화면에는 `방식: harmonic`이 출력됩니다. 100개 파일이 조용히 재작성됩니다.

### C-8 [정적] `recompute_totals.py`가 백업·원자성·롤백 없이 실제 데이터를 덮어씀

`scripts/recompute_totals.py:58,70` — `path.write_text(...)` 직접 호출.
`app_settings.save_settings`와 `detector_options.save`는 `tmp` + `replace`를 쓰는데 이 스크립트만
`write_text`입니다. `--dry-run`도 백업 디렉터리도 없습니다. `KeyboardInterrupt`나 디스크 풀로
파일 하나가 잘리면 그 안의 **모든 분석 결과**가 사라집니다. 이 스크립트는 이미 100건에 대해
실행된 상태여서 원상 복구 불가입니다.

### C-9 [정적] `recompute_totals.py`가 저장된 가중치를 버림

`scripts/recompute_totals.py:84` — `ensemble = {"method": args.method, "weights": {}}`

각 결과는 자기 설정의 `detectorSettings.ensemble.weights`를 가지고 있는데 빈 dict로 대체됩니다.
사용자가 SONICS 가중치 3 / lofcz 1로 튜닝해 둔 상태에서 `--method weightedGeometric`을 실행하면
100개 total이 **균일 가중치**로 재계산되고 `detector-weighted-geometric-mean-v1`로 기록됩니다.
경고도, 가중치를 전달할 플래그도 없습니다.

### C-10 [정적] `audioio.py`의 ffprobe/ffmpeg에 `timeout`이 없음

`probe/audioio.py:65-78`, `:126-134`

두 호출 모두 `subprocess.run(..., capture_output=True)`인데 `timeout=`이 없습니다. 네트워크
드라이브, FIFO `\\.\pipe\...`, 드라이버 레벨 행에서 **영영 반환하지 않으면** FastAPI 요청이
완료되지 않고 자식 프로세스를 앱에서 죽일 수 없습니다(서버 재시작 필요). 같은 패키지의
`resources.py:30`은 `timeout=3`을 설정하므로 의도된 선택이 아니라 누락입니다.

### C-11 [정적] 잘못된 옵션 값이 저장값이 아닌 스키마 기본값으로 덮어써짐

`probe/detector_options.py:255` → `option["default"]`

`{k: _coerce_choice(value, option, option["default"])}`로 잘못된 값을 **스키마 기본값**으로
coerce합니다. 현재 저장값이 기본값이 아닌 경우, 나쁜 patch가 사용자 설정을 기본값으로 덮어씁니다.
검증 사례: `maxWindows`가 16으로 저장돼 있는데 `{"maxWindows": 99}` patch → **24**(기본값)로 변경.
UI로도 도달 가능합니다 — 판정 임계값 필드를 비우고 저장하면 `web/app.js:788`이 `Number("") = 0`을
보내고 `_clamp_number`가 `0.05`로 clamp → **모든 탐지기가 0.05 이상이면 "AI 우세"** 판정 +
성공 토스트.

### C-12 [확인] 업로드 파일명이 결과에 잘못 매핑 (errors_report.md E-1)

`probe/app.py:492`, `:580` — `zip(result["results"], original_names)` 위치 기반 매핑이
`file_analysis.py:36`의 무조건 `sorted()`와 충돌. 2개 이상 업로드하면 이름이 섞이고 이력 카드에
**잘못된 파일명**이 표시됩니다. 상세 재현은 `errors_report.md` E-1 참조.

### C-13 [정적] 리소스 폴링에 in-flight 가드가 없어 응답이 역전됨

`web/app.js:1045` — `setInterval(loadResources, 3000)`

서버는 매 폴링마다 `nvidia-smi`를 실행하며 `timeout=3`(`probe/resources.py:22-33`)이라 한 틱이
3초를 넘을 수 있습니다. 진행 중 요청 위에 새 요청이 쌓이고 늦은 응답이 새 값을 덮어써
GPU/VRAM/CPU/RAM 계기가 뒤로 뛰거나 `GPU 확인 불가`와 실측값이 번갈아 표시됩니다.

### C-14 [정적] 오래된 fetch 응답이 새 대화상자에 잘못된 파형/스펙트로그램을 칠함

`web/audio-compare.js:158,160,166` / `web/app.js:361-365`

두 곳 모두 요청 순서화(sequence)나 `AbortController`가 없습니다.

- 비교: 큰 FLAC을 음원-1에 불러오는 중 더 작은 파일을 불러오면, 느린 1번 응답이 늦게 도착해
  **옛 파일 파형**으로 칠하고 `slots[0].sampleRate`를 덮어써 **주파수 축 라벨이 틀어지며**
  스펙트로그램을 교체합니다. `<audio src>`와 이름 라벨만 새 파일입니다.
- 상세: `Esc`로 닫고 다른 파일을 열면 `svg.innerHTML`이 옛 파일 파형이 되고,
  `updateVisualProgress(0)`가 새 대화상자의 seek 그라디언트까지 덮어씁니다.

### C-15 [확인] 테스트 스위트가 프로젝트 루트 밖에서 수집 실패 + gitignore된 `scratch/`에 의존

- `.gitignore`에 `scratch/` 포함, `git ls-files scratch` → **0개 파일**
- `conftest.py` 부재 + `pytest.ini`가 `testpaths = tests`만 담고 `pythonpath`가 없음 →
  프로젝트 루트가 아닌 CWD에서 `pytest` 실행 시 **9/9 collection error**
- `tests/test_anchor_evaluation.py:1`이 `scratch.evaluate_anchor_corpus`를 import

즉 **`76 passed`는 이 컴퓨터의 `scratch/` 디렉터리 상태의 성질이지, 저장소의 성질이 아닙니다.**
새 클론이나 CI, IDE 테스트 러너에서 바로 실패합니다.

---

## 2. 중간 (Medium) — 24건 (발췌)

> **현행 상태 (2026-09-27).** 아래 본문은 최초 리뷰 시점의 발견 내용을 그대로 보존한 것입니다.
> 각 항목의 해결/잔존 판정은 부록 「해결 현황」 표를 보십시오.

| 상태 | 항목 | 건수 |
|---|---|---|
| **[수정]** Codex (Round 1) | M-1, M-13, M-14, M-16, M-22 | 5 |
| **[수정]** 자체 (Round 3) | M-2, M-4, M-5, M-6, M-7, M-12, M-15, M-18, M-19 | 9 |
| **[수정]** Round 6 | M-3, M-8, M-9, M-10, M-11, M-17, M-24 | 7 |
| **[잔존]** | M-20, M-23 | **2** |
| **[기각]** | M-21 | **1** |
| | 합계 | **24** |

### 점수 계산 정합성

| # | 위치 | 내용 |
|---|------|------|
| M-1 | `file_analysis.py:134-135` [정적] | `agreement`/`confidence`가 **이상치 제거 전** `values`로 계산되어 버려진 탐지기가 여전히 신뢰도를 깎음. `[0.854, 0.0, 0.996]` → conf 10.2. lofcz 토글을 **끄면** 같은 Total 92.5인데 conf가 72.9로 **7배 반전**. 불일치 탐지기를 추가할수록 신뢰도가 떨어지는 모순 |
| M-2 | `file_analysis.py:134` [설계] | `agreement`가 모집단 표준편차라 탐지기 수 간 비교가 불가능. `[0.85,0.60]`→0.75 vs `[0.85,0.60,0.90]`→0.7375. 두 개가 일치하면 세 개보다 높게 나옴 |
| M-3 | `artifactnet.py:133` [정적] | `required = min(min_valid, len(segments))`가 `minValidSegments`를 조용히 낮춤. 4초 파일은 구간이 1개라 `required=1` → 통과하면서 리포트는 `options.segmentCount: 11`이라 표시. 16초 미만 파일에서 4구간 최소가 강제되지 않음 |
| M-4 | `artifactnet.py:135` vs `detector_options.py:165-167` [정적] | 힌트는 "**총점 계산에서 제외**된다"고 하나 코드는 `ValueError`를 던짐. `file_analysis.py:164`가 잡아 **탐지가 에러로 사라지며** 사용자에게 반대 말로를 전함 |
| M-5 | `artifactnet.py:31-38` vs `detector_options.py:170-178` [정적] | 모듈 주석은 레벨 정규화가 적용되어 NaN 구간이 제거된다고 서술하나 **출시 기본값은 off**. 주석이 현재 코드 동작처럼 읽힘 |
| M-6 | `detector_options.py:15-17` + `base.py:155-157` [정적] | 두 개의 수동 동기화 레지스트리(`DETECTORS`/`DETECTOR_SCHEMA`)에 상호 검증이 없음. 스키마 없는 5번째 탐지기를 추가하면 `base.describe()`가 `KeyError`를 내고 `/health`가 500 |
| M-7 | `base.py:43-45` [정적] | `unavailable_reason()`이 `run is None`을 먼저 검사 → 서버 시작 후 모델을 추가하면 "런타임이 아직 연결되지 않았습니다"로 잘못 안내. 진짜 원인은 "서버 재시작"이며 surfaced되지 않음 |
| M-8 | `sonics.py:56` [정적] | `max(std, 1e-6)`이 퇴화 구간을 100만 배 증폭. 상수 `0.001` 5초 구간에서 `std=0.0` → 정규화 후 absmax **1000.0**. 표준편차 1.0 학습 모델에 amplitude-1000 입력 |
| M-9 | `lofcz.py:119` [정적] | 30초 진단 타임라인이 모듈 상수 `MAX_DURATION_S = 300`에 고정되어 사용자 `maxDurationS`를 무시. 1800초 트랙에서 점수는 6개 창으로 0→1800을 덮지만 `segments`는 300.0초에서 멈춤 → `segmentMean/Max/Min`이 `score`와 다른 구간을 설명하고 `even`과 달리 상한이 어떤 필드에도 드러나지 않음 |
| M-10 | `stages.py:74-75` [확인] | `SONGYUE_STEM_MAP`의 두 이름이 `"source"`로 매핑되어 dict 대입이 하나를 조용히 버림. `source-44k.wav`와 `source.wav`가 같이 있으면 하나가 사라지고 스테이지 diff가 잘못된 기준을 비교 |
| M-11 | `report.py:74-84` [정적] | `series`에 `null`이 들어갈 수 있는데 `first`/`last`/`change`는 **존재하는 값만으로** 계산 → 기록된 변화량이 엔드포인트와 다른 스테이지 쌍을 설명. mono 스테이지가 섞인 3단 체인이 "content-specific 변화"로 `_decompose`에 유입 |
| M-12 | `app_settings.py:45-52` + `:62-68` [확인] | 필드 하나가 잘못되면 `_merged`가 raise하고 `load_settings`가 삼킴 → **전체 사용자 설정이 조용히 기본값으로 초기화**. 로그도, 나쁜 파일 백업도 없음 |
| M-13 | `history.py:169-171` [정적] | `source.stat()`이 try/except **밖**에 있어 TOCTOU `FileNotFoundError` → `GET /api/history`가 500 |
| M-14 | `app.py:667` [정적] | `read_report`에 `JSONDecodeError` 가드 없음. 잘린 리포트가 500 (`list_reports`/`export_report`는 둘 다 처리함) |
| M-15 | `history.py:128,207,214` [정적] | ISO-8601 타임스탬프를 **문자열**로 비교 → 오프셋이 섞이면 사전순으로 잘못 정렬. `historyLimit` 적용 시 어떤 항목이 **삭제될지**가 이 오류에 달려 있음. `test_...`가 `+09:00`을 의도적으로 사용 중 |
| M-16 | `history.py:148,261,91` [정적] | 비원자적 in-place `write_text` 3곳. `_SAVE_LOCK`이 `save_history`만 덮고 `delete_history`/`trim_history`는 잠금 없음 → 삭제와 재저장이 경합하면 last-writer-wins로 삭제가 유실 |
| M-17 | `history.py:35,66,124,166,251` [정적] | 유효 JSON이 객체가 아니면 `payload.get(...)`이 `AttributeError` → 어떤 리더도 잡지 않음 |
| M-18 | `cli.py:44` [확인] | `health`가 ffmpeg·ffprobe·모든 탐지기가 MISSING인 상태에서도 **exit 0**. CI나 시작 스크립트의 준비 상태 확인으로 사용 불가 |
| M-19 | `cli.py:121` [확인] | `--save`가 `config.REPORTS_DIR`가 아니라 **CWD 상대** `Path("reports")`에 씀 → 프로젝트 루트 밖에서 실행하면 서버가 목록화하지 않는 별도 폴더에 저장됨. 파일명 포맷과 `isalnum()` 새니타이저는 `app.py:194-195`에 중복 |
| M-20 | `file_browser.py:35-41` [설계] | 루트 구속과 인증 없음 → 전체 디스크 목록 + 임의 경로 분석. loopback 바인딩이면 설계 포스트이지만, 바인딩 주소가 바뀌면 즉시 문제가 됨 |
| M-21 | `audioio.py:130-131` vs 모듈 docstring [정적] | `-ar`/`-ac`로 디코드를 강제하면서 docstring(3-5행)은 "네이티브 레이트, 리샘플링 없음"이라고 단언. 레이트가 어긋나면 ffmpeg `swr` 리샘플러가 로우패스를 걸어 **이 도구가 찾는 brickwall 증거를 인위적으로 생성** |
| M-22 | `audioio.py:83` [정적] | `json.loads(result.stdout or "{}")`에 try 없음. rc=0 + 비JSON stdout면 `JSONDecodeError`(`ValueError`이므로 `AudioToolError` 아님) → 500 + 스택트레이스 대신 깨끗한 한국어 오류여야 함 |
| M-23 | `audioio.py:143-146` [정적] | `nan_to_num`이 손상 파일을 **디지털 무음으로 조용히 변환**. `peakDbfs: -240.0`으로 정상 무음과 구별 불가. 처리 아티팩트를 탐지하는 도구에서 디코드 실패를 측정값으로 내는 것은 무결성 문제 |
| M-24 | `loudness.py:209-210` [정적] | `peak = float(np.abs(samples).max())`에 empty 가드 없음. 같은 모듈의 `integrated_loudness`(:165)와 `level_metrics`(:451)는 둘 다 `size == 0`을 막는데 여기는 유일하게 비어 있음. `load`가 빈 stdout를 거부하므로 잠재 |

---

## 3. 낮음 / 코드 냄새 — 64건 (요약)

**사각지대**
- `dsp.py:48` `BRICKWALL_DB_PER_KHZ = -20.0` 정의 후 **어디서도 미사용**. `steepest_rolloff`는
  기울기를 반환만 하고 임계 비교를 하지 않아, docstring(46-47행)이 약속하는 "brickwall 판정"이
  적용되지 않음
- `dsp.py:219` `spectral_comb(..., sample_rate)` 인자 미사용
- `dsp.py:439-441` `total` 계산 후 즉시 `del` — 잔재
- `dsp.py:381` `return peaks[:limit] if limit else peaks` → `limit=0`이 **전체 반환** (통상적
  "0이면 없음"의 반대)
- `dsp.py:82-83` `np.resize` 분기 도달 불가. 8길이 × 9폭 전수 확인
- `sonics.py:20-23` 미사용 상수 3개, `artifactnet.py:21-22` 미사용 상수 2개.
  특히 `artifactnet.SEGMENT_COUNT = 7`이 스키마 기본값 `11`과 **모순** → 잘못된 상수를 찾는 유인
- `lofcz.py:65-71` `np.interp` resize 분기 도달 불가
- `stages.py:103` `else target.stem` 도달 불가, `file_analysis.py:95-96` 도달 불가
- `report.py:37,46` `EXCLUDED_PREFIXES` 두 항목 모두 죽은 코드
- `app_settings.py:83` `configured_path()` 호출자 없음
- `index.html:35` + `web/app.js:986` `<span id="page-title" hidden>`에 쓰이지만 **unhidden 되지 않음**
  → `PAGE_META` 무효

**가변 전역 노출 / 파괴**
- `detector_options.py:381-382` `describe()`가 `_INCLUDED_OPTION`과 캐시 `values` dict를
  **참조로** 반환. 확인: `describe()['detectors'][0]['includedInTotalOption'] is _INCLUDED_OPTION`
  → `True`. 반환 dict를 변형하면 프로세스 전역 상태가 오염됨
- `report.py:277-279` `with_chain_flags`가 in-place 변형이며 **멱등 아님** → 두 번 호출하면
  모든 chain-dominant 플래그가 중복
- `report.py:186-209`, `cli.py:54-60` dsp 키에 직접 서브스크립트(`meta["lossy"]`) →
  `analyze()`의 `.get()` 관용과 불일치
- `stages.py:31-34` `@dataclass(frozen=True)` 안의 가변 dict. `frozen=True`가 `__hash__`를
  생성하므로 해시 시 `TypeError`
- `detector_options.py:212-213` `default_options()`은 테스트만 쓰는 공개 API. 프로덕션은
  `normalize(None)` — "기본값"의 두 표기가 갈라질 수 있음

**수치/직렬화 정합성**
- `loudness.py:176,183` vs `:202` — 같은 `samplePeakDbfs` 식이 **세 번** 복제. 0.3초 파일은
  `-6.020599913279624`, 3초 파일은 `-6.02`로 **같은 필드가 다른 정밀도**로 직렬화
- `loudness.py:174-176` `< 2` 블록 → 48 kHz 기준 0.40~0.50초 파일이 `lufsIntegrated: None`.
  400ms 블록 하나는 유효한 integrated loudness이고 `< 2`는 LRA 퍼센타일에만 필요
- `loudness.py:150` prefix-sum이 float64 전체 복사 3벌. 10분 48k stereo에서 **약 1.3 GiB 임시**
  (`dsp.magnitude_spectrum`은 같은 이유로 512프레임 블록 루프를 쓰는데 여기는 아님)
- `audioio.py:126-147` 디코드 PCM 전체를 `bytes`로 버퍼링(30분 48k stereo float32 = 1.29 GiB).
  `magnitude_spectrum`의 "bounded blocks"는 FFT 스크래치만 제한하고 파일은 이미 상주
- `dsp.py:109` `np.concatenate` 후 `chunks`가 함수 끝까지 참조 → 출력은 제한되지만 피크는 2배
- `dsp.py:150` vs `:209` `_in_band_median_db`는 20 kHz 상한, `digital_null_hz`는 Nyquist까지.
  44.1 kHz 파일에서 20 kHz 초과 **191개 빈이 참조에 없던 기준으로 채점**됨. 20 kHz 캡이 미문서화
- `dsp.py:118-123` / `:137-143` band-mask + power-sum + log 블록이 두 번 복제
- `dsp.py:77-79` `right = width - 1 - left`가 `-1` 가능 → `np.pad` `ValueError`. 4개 호출부가
  모두 가드하므로 **도달 불가**, 잠재만
- `audioio.py:56` `LOSSLESS_CODECS`에 `pcm_f64le`/`pcm_s16be`/`pcm_u8` 없음 → 64비트 float WAV가
  `lossy=True`. 형식 판정이 아니라 결론 자체가 틀어짐
- `audioio.py:139-142` `ascontiguousarray`가 이미 연속인 배열에 no-op. `nan_to_num` 분기 여부에 따라
  writability가 달라짐
- `audioio.py:209-210` `loudness` peak에 empty 가드 없음(C-24와 동일 계열)
- `detector_options.py:248-249`, `:258-259` `bool(value)`가 손으로 편집한 JSON의 비어있지 않은
  문자열을 모두 True로. HTTP 경로는 pydantic이 먼저 정규화하므로 안전
- `artifactnet.py:96` 입력명 `"audio"` 하드코딩. 현재 모델과 일치하나 `lofcz.py:63`처럼 동적
  조회가 아님 — 모델 교체 시 매 호출 ORT 에러
- `report.py:134` 죽은 `else`. `_note` 메타데이터를 metric과 같은 dict에 저장해 모든 소비자가
  `_` 접두사 키를 걸러야 함

**파일/프로세스 자원**
- `resources.py:13` `cpu_percent(interval=None)` 첫 호출이 0.0 → 첫 폴링에서 CPU 0%로 표시
- `resources.py:22-33` 3초마다 `nvidia-smi`를 새로 spawn, 실패 시 **네거티브 백오프 없음**.
  `app.py:274`가 sync `def`라 최대 3초 동안 threadpool 슬롯 점유
- `resources.py:34` 멀티 GPU에서 GPU 0만 보고. payload 키가 단수라 자기 일관성은 있음
- `audioio.py:72` `ffprobe`에 경로를 맨 positional 인자로 전달하고 `--` 구분자 없음 → `-v.wav` 같은
  파일명이 옵션으로 파싱됨. ffmpeg(:128)은 `-i`가 앞에 있어 안전
- `audioio.py:80-81`, `:136-137` stderr의 **마지막** 줄만 노출. ffmpeg은 진단을 먼저 출력하므로
  가장 쓸모없는 줄이 사용자에게 보임
- `audioio.py:126-134` `CREATE_NO_WINDOW` 없음. `resources.py:32`는 설정 — 패키지 내 불일치
- `loudness.py:133-134` 파일마다 4096-iteration Python 루프 2회 재계산(**2.3 ms/파일**).
  계수는 이미 모듈 상수인데 `lru_cache` 없음
- `lofcz.py:54-58`, `artifactnet.py:85-91` `lru_cache`d ORT 세션 무효화 없음 → 서버 실행 중
  가중치 교체 시 옛 그래프 계속 제공
- `detector_options.py:353-358` 캐시가 float `st_mtime`에만 의존
- `history.py:90-91` 파일명이 `%f`+`uuid4()[:8]`인데 `write_text`(O_EXCL 아님) → 2⁻³² 충돌 시
  **조용히 덮어씀**
- `app_settings.py:77-79`, `detector_options.py:334`, `history.py:43` 세 writer가 **고정된 동일
  `.tmp` 파일명** 공유 → 동시 저장 시 반쯤 쓰인 파일을 `replace()`할 수 있음
- `report.py:286-298` `save()`는 충돌 안전(O_EXCL)이지만 **비원자적** → 크래rash 시 실명 파일이 손상
- `config.py:19,23-26` import 시점 `int(os.environ[...])` → 잘못된 환경변수에서 처리되지 않은
  `ValueError` 트레이스백
- `cli.py:156-157` `--port`/`--log-level` 미검증 → uvicorn 트레이스백

**프론트엔드**
- `web/app.js:1045` → C-13
- `web/app.js:111-118` `renderBrowser()`가 체크박스 토글마다 **전체 목록을 재구축** →
  포커스된 `<input>`이 파괴되어 키보드로 두 번째 체크박스를 못 ticking. 360px 리스트는 최상단으로
  스크롤 리셋 가능성 높음. `#browser-list`가 `role="listbox"`인데 `role="option"` 자식이 없어
  방향키도 무동작
- `web/app.js:461-473` 이력 로드 실패 경로가 `scrollTop` 복원 없이 그리드를 통째로 교체 →
  2.5초간 카드 전부 사라지고 스크롤 위치 영구 손실
- `web/audio-compare.js:102` `playRow`가 메타데이터 미로딩 시 `currentTime = 0`.
  `(NaN || 0) - .02` → 0 → A/B 비교가 엉뚱한 위치에서 재생. play 버튼은 메타데이터 도착 전에
  이미 활성화됨
- `web/app.js:720`, `:743` `value="${...}"`와 `min`/`max`/`step`가 raw. 같은 템플릿의 이웃 속성은
  전부 `escapeHtml` → 서버 옵션 파일이 신뢰 경계. UI로는 도달 불가
- `web/audio-compare.js:132` `${item.label}`을 `escapeHtml` 없이 innerHTML에 삽입. 이 파일엔
  `escapeHtml`가 아예 없고 `app.js:8`과 중복 구현. 현재 라벨은 하드코딩 한국어라 **도달 불가**지만,
  라벨이 파일명에서 파생되는 순간 인젝션이 됨
- `web/app.js:352`, `audio-compare.js:74` 재생 위치 오버레이가 `timeupdate` 시점에 `clientWidth`
  **px로 고정**되고 리사이즈 시 재계산 없음 → 창 크기를 바꾸면 하이라이트가 어긋남
- `web/app.js:86`, `:1041` "다이얼로그 열림" 판정에서 `'audio-compare-dialog'` 누락
- `web/app.js:364` 비수치 `peaks[i]` → `y1="NaN"`. 조용히 렌더되지 않고 위치 표시도 안 바뀜
- `web/app.js:429`, `:673` → `:310` `openResult(state.history.find(...))`에 null 가드 없음.
  2.5초 폴이 같은 틱에서 목록을 재렌더 → `TypeError`로 silent no-op
- `web/app.js:245`/`:374`/`audio-compare.js:5` **5벌의 중복 헬퍼가 이미 분기됨**. `formatTime`은
  음수를 clamp하지 않아 `formatTime(-5)` → `"-0:-5"`. `frequencyAxisLabels`는 44100 기본,
  `frequencyLabels`는 48000 기본 → `sampleRate`가 빠진 44.1 kHz 파일이 상세에서는 22.05, 비교에서는
  24 kHz 축을 받음
- `web/app.js:391` `document.querySelectorAll('[data-audio-action]')`이 document 스코프 —
  다른 모든 오디오 쿼리는 dialog 스코프. 다음 dialog이 같은 속성을 재사용하면 두 dialog이
  하나의 `<audio>`를 제어하게 됨
- `web/app.js:258`, `:262` `Math.max(fallback, ...segments.map(...))`가 무한 배열 spread,
  `laneEnds.findIndex`가 O(n²)
- `web/app.js:613` catch가 "서버 도달 불가"와 "예상 못한 payload"를 구분하지 않음
- `web/app.js:64-69` `browse()`에 요청 순서화 없음

---

## 4. 테스트 커버리지 평가

기준선 `76 passed in 2.56s` — 단, **루트 CWD + 채워진 `scratch/`에서만** 성립 (C-15).

| 파일 | 개수 | 실제로 덮는 것 | 덮지 못하는 것 |
|------|------|----------------|----------------|
| `test_loudness.py` | 12 | **최강.** 절대 외부 기준값: BS.1770-4 −23 LUFS, −6.0206 dB 스케일, +3.0103 dB 채널 가중, LRA-10, −70 LUFS 게이트, 48 kHz 계수표, DC/나이퀴스트 항등 | 실질 없음. 단 44.1 kHz 검증이 48 kHz와 **동일한 0.01 허용오차**라 0.5 dB 셸프 오류가 통과 (C-3 계열 회귀를 못 잡음) |
| `test_detector_options.py` | 18 | normalize/merge clamp, choice coerce, None-대-누락 구분, **0-가중치 거부 + 파일 미생성까지** 검증, 손상 파일 fallback, tmp 왕복 | `save()`의 원자성 미검증. `test_defaults_match_the_locked_model_specs`는 *기본값*만 검증하는데 실제 `detector-options.json`이 `topk`/`topK:5`로 덮어씀 |
| `test_file_analysis.py` | 14 | 5개 method 전부 `_score`, 이상치 로직, NaN 거부, 가중치 0 제외, median, `expand_inputs` 단일파일 중복제거 | **`analyze_files`/`analyze_file` 0개 테스트.** 배치 동작, 파일별 실패 격리(E-3), `detectorErrors` 전부 미커버 |
| `test_detector_aggregation.py` | 15 | 3탐지기 구간 선택/집계 순수 수학. mock 없음, 직접적 | `_level_normalise` — **F-5 수정에 회귀 테스트 없음** (`grep _level_normalise tests/` → 0). C-6 clamp 경로도 미커버 |
| `test_history.py` | 7 | F-4 회귀, `historyItemId` 독립성, 이름 인덱싱, report/history 중복 제거, 즐겨찾기-exempt trim | 파일명 유일성, `delete_history` vs `trim_history` 경합(M-16), 손상 JSON 허용, `stat()` TOCTOU(M-13), 혼합 오프셋 정렬(M-15) |
| `test_reports_api.py` | 6 | 리포트 목록/삭제, **실질적 traversal 거부**, CSV 평탄화, 큐 429, 업로드 크기 제한 | `read_report` 손상 JSON(M-14), **`_progress_response` — F-6 `NameError` 수정에 회귀 테스트 없음**, 업로드 *성공* 정리(E-2), 2↔3탐지기 CSV |
| `test_report.py` | 1 | `report.save()`의 증가 이름 규칙뿐 | **`analyze`/`flatten_numbers`/`_decompose`/`_verdict`/`_peak_diff`/`_flags`/`with_chain_flags` 전부 0개.** 300줄 모듈이 이름 루프 하나만 검증 |
| `test_file_browser.py` | 2 | 확장자 필터 + 정렬 순서, 파일 경로 거부 | `::drives`, 드라이브 루트 `parent`, 숨김 파일, `PermissionError`. traversal 단언 없음 |
| `test_anchor_evaluation.py` | 2 | 단조 isotonic fit, grouped holdout 무오류 | **gitignore된 `scratch/` 의존.** `test_isotonic_fit_...`는 단조성만 검증 — 함수 이름의 절반인 **class balance를 검증하지 않음** |

### (a) 테스트가 아예 없는 모듈
`probe/app_settings.py` (0), `probe/cli.py` (0), `probe/resources.py` (0),
`scripts/recompute_totals.py` — **112줄, 0개** (`e4b4f04`에서 실제 100개 데이터 파일을 건드린
같은 커밋으로 추가됨), `report.analyze` 및 `report.py` 대부분, `file_analysis.analyze_files`,
`visuals.waveform_peaks` — **F-1 수정 미커버**, `app._progress_response` — **F-6 미커버**,
`detectors/artifactnet._level_normalise` — **F-5 미커버**

### (b) 잘못된 것을 검증하거나, 코드에 매달려 통과하는 테스트
- `test_expand_inputs_returns_supported_files_once`(`test_file_analysis.py:9`)가 **파일 1개**만
  써서 순서 무감지 → E-1(무조건 정렬의 근본 원인)을 구조적으로 잡을 수 없음. 게다가 정렬된 반환값과
  비교하므로 **버그 있는 계약을 정답으로 고정**함
- `test_upload_total_size_limit_removes_partial_files`는 `_store_uploads`의 `except` 분기만
  검증. 이름이 "파일을 제거한다"지만 읽는 사람은 "업로드가 정리된다"로 오해 → E-2에 대한
  **과도한 안심**
- `test_analysis_queue_rejects_requests_beyond_pending_limit`는 수동으로 만든 큐의 반환 dict만
  검증. 429 경로에서 `reserve()`가 세마포어를 반납하지 않아도 통과함
- `test_report_and_history_copies_of_same_run_are_shown_once`는 `len==1`만 검증 →
  중복 제거가 과잉으로 **둘 다** 버려도 통과. 어느 쪽이 남았는지 검증해야 함
- `test_change_signature_changes_without_loading_payloads`는 문자열이 다르다는 것만 검증 →
  시그니처가 `str(uuid4())`여도 통과
- `test_isotonic_fit_is_monotonic_and_class_balanced`는 `scores == sorted(scores)`만 검증 →
  **class balance 미검증**
- `test_grouped_holdout_...`는 완벽히 분리 가능한 데이터(0–9 vs 90–99)에 `raw.count==20`과
  `balancedAccuracy>=0.8`만 검증 → 단조 구현이면 무엇이든 통과

### (c) 이미 고친 버그의 회귀 테스트 유무

| 수정된 버그 | 테스트 |
|---|---|
| F-1 파형이 슬래브로 뭉개짐 | **없음** |
| F-4 동일 결과가 이력에서 소멸 | 있음 (4개, 양호) |
| F-5 ArtifactNet NaN | **없음** |
| F-6 `_progress_response` `emit` NameError | **없음** |
| pydantic `includedInTotal: null` | 있음 — **`None`-대-누락을 명시 검증, 모범 사례** |
| NaN 점수가 1.0으로 클리핑됨 | 있음 |

---

## 5. 리뷰 결과 이상이 없었는지 — 깨끗하다고 확인한 영역

객관적으로 검증했고 **문제 없음**을 확인했습니다. 이 부분은 그대로 두어도 됩니다.

**수치/신호 처리**
- `_box_filter` 비대칭 패드 — 홀수/짝수 폭 모두 정확, 출력 길이 클램프가 보장
- STFT 프레이밍 `1 + (x.size - N_FFT) // HOP` — 최대 오프셋이 프레임 안, 슬라이딩 윈도 인덱스가
  범위 내. off-by-one 없음. 빈 입력은 0 패딩된 프레임 하나로 처리
- 나이퀴스트 마스크 — `sr/4096`이 정수 `sr`에 대해 이진에서 정확하고 `2048·(sr/4096) == sr/2`가
  정확히 성립. `freqs[2048] == nyquist`이므로 최상위 빈에 off-by-one이 없음
- `steepest_rolloff`의 `np.roll` wrap — `interior[2:-2] = True`가 양 끝을 모두 마스킹하므로
  **문서상 위험하지만 버그 아님**(의도적으로 확인)
- `_comb_harmonics` 경계 — `lo`/`hi` 클램프, `lo >= hi` 가드, 비어있지 않은 슬라이스 모두 정확
- `spectral_comb` 주기 축 — `period_axis[0] = inf`가 대역 조건에서 올바르게 제외.
  peak와 floor 양쪽에 `_EPS`가 대칭이라 올영역이 위조 240 dB가 아니라 `depth=0`
- `transient_metrics` 퇴화 케이스 — 무음과 정상 톤 모두 `onsets=0`(엄격 `>`). **버그 아님**
- `level_metrics` DC offset float32 — 10분 48k에서 랜덤/50Hz/교대/계단 신호 모두 float64 대비
  최대 오차 **7e-13**. numpy pairwise 합산으로 충분
- `energy_rolloff_hz` float32 cumsum — 200회 시험에서 `|cum[-1] − 1| ≤ 2.5e-6`, 0/500회
  `cum[-1] < 0.99`. clamp은 load-bearing 아님
- **아래 4건은 검사 후 보고를 철회했습니다**: float32 `dcOffset` 정밀도, `transient_metrics`
  onset 오계산, `energy_rolloff_hz` cumsum 드리프트, `psutil` 첫 호출 0.0
- K-필터 `_impulse_response` 지연선 순서 — DF-I 정확
- `_fft_convolve` 사이징 — `1 << (size-1).bit_length()`가 선형 길이 이상임을 1/10/30분,
  96 kHz에서 검증. 원형 앨리어싱 없음
- `_block_powers` 인덱싱 — `max(starts)+block ≤ n` 보장, 알려진 펄스로 수치 검증(`1000·4/19200 = 0.2083`
  정확히 일치)
- 게이팅 로직 — 절대 −70, 상대 게이트 = 절대 게이트 통과 평균 − 10, LRA = (integrated − 20) 초과
  블록의 P95 − P10. BS.1770-4 / EBU Tech 3342 일치

**탐지기 계약**
- 옵션 검증 — 3개 탐지기가 읽는 모든 키가 `DETECTOR_SCHEMA`에 존재하고 모든 경로
  (`load`/`merge`/`for_detector`)에서 `normalize()`가 생성. **탐지기에 `KeyError`나 미검증 값이
  도달할 수 없음.** `threshold`는 0.05–0.95 하드 경계, 모든 수치 choice는 membership 검사,
  12개 `_choice(..., strict=True)` 라벨/값 순서 모두 정합
- 점수 범위 계약 — 3탐지기가 모두 0..1 유지. lofcz는 clip하지 않지만 그래프를 추적해
  `torch.sigmoid`로 끝남을 확인
- ONNX 입출력 — 실제 파일 대조: artifactnet `('audio', ['batch', 176400])` = `SEGMENT_SAMPLES` 정확,
  lofcz `('fakeprint', ['batch_size', 3585])` = `_fakeprint` 출력 3585 정확
- ORT 세션 — `lru_cache`로 모델 경로당 1회 생성, `run`은 thread-safe. 호출당 생성 없음
- 결정성 — `mean`/`median`/`geometric`/`weightedGeometric`/`robustMean` 전부 순서 무관.
  같은 파일·같은 설정이면 비트 단위로 동일
- `_score`의 0나눗 — `values.size ≥ 1` 보장, `GEOMETRIC_FLOOR`가 `log(0)` 차단,
  `_robust_mean`은 `n ≤ 2` 조기 반환. 도달 가능한 `ZeroDivisionError` 없음
- 모든 탐지기가 실패한 파일은 `totalScore: null` + 한국어 설명으로 처리 (크래시나 0이 아님)
- **2탐지자 vs 3탐지기 처리는 의도된 동작**이며 UI 힌트에 명시. 버그 아님

**보안**
- **XSS — 깨끗함.** 디스크/서버에서 온 모든 문자열이 HTML 위치에 들어가기 전에 `escapeHtml`
  (`& < > ' "` 포함, 텍스트/속성 컨텍스트 모두 커버). `insertAdjacentHTML`/`outerHTML` **사용처
   없음**. `href`/`src` URL 보간은 전부 `encodeURIComponent` 또는 `URLSearchParams`.
  `toast()`는 `textContent`. 한글/일본어 파일명이 깨지지 않음
- `app._report_path`(`app.py:605-611`) traversal 안전 — `/`, `\`, `..` 거부. Windows 드라이브-상대
  형식 `C:evil.json`도 pathlib가 `REPORTS_DIR\evil.json`으로 접어 탈출 불가.
  `test_delete_report_rejects_path_traversal`은 실질적 traversal 테스트
- `audioio` 셸 인젝션 없음 — 전부 list 인자, `shell=True` 없음. rc 검사 양쪽 모두, stderr 캡처 양쪽
  모두. `-nostdin` 존재. 0 나누기 가드가 modulo보다 **앞에**
- `resources.py` 예외 처리 완전 — 실제 NVIDIA RTX 5070에서 검증

**안정성**
- **이벤트 리스너/DOM 누수 없음.** 모든 재렌더 경로가 새로 만든 노드에 `.onclick =`만 대입,
  `addEventListener` 미사용 → 누적될 것이 없음. `setInterval` ×2, `ResizeObserver` ×1, document
  리스너는 각각 정확히 1회. **`EventSource`는 어디에도 없음.** `historyView` 단일 인스턴스
  기법이 실제로 동작함
- **SSE 파싱 — 깨끗함.** 서버는 정확히 `data: {json}\n\n` 방출, 리더는
  `decode(value, {stream:true})` + `buffer = lines.pop() || ''`로 TCP 청크 분할을 재조립.
  중간 에러는 스트림 종료 **후** 던져 성공으로 오보고하지 않음
- **오디오 — 깨끗함.** Web Audio API/`AudioContext`/`decodeAudioData` 없음. 닫을 때 pause.
  상세 dialog이 `position:fixed; inset:0` modal이라 **이전 `<audio>`의 `timeupdate`가 새 dialog에
  쓰는 stale closure는 도달 불가**
- **Canvas — 해당 없음.** `<canvas>`/`getContext`/`devicePixelRatio` 전무. 파형은 SVG `<line>` +
  `vector-effect="non-scaling-stroke"`로 해상도 독립. DPR/리사이즈/clear/NaN-path 계열 버그가 존재하지 않음
- **숫자 포맷 — 깨끗함.** 표시 문자열에 `parseFloat` 없음. `toLocaleString('ko-KR')`은 날짜
  표시에만 쓰이고 다시 숫자로 파싱되지 않음. 모든 `.toFixed`는 가드됨.
  `renderHistory`는 `.filter()` 사본을 정렬해 `state.history`를 변형하지 않음
- 이력 리더 5곳 전부 손상 JSON 허용 — 잘린 파일은 건너뛰고 치명적이지 않음 (쓰기 쪽이 문제, M-16)
- 이력 id 유일성 — `%Y%m%dT%H%M%S%fZ`(마이크로초) + `uuid4().hex[:8]`. 동일 초 충돌 우려 없음
- `report.save()` 충돌 처리 — `open("x")`는 `O_CREAT|O_EXCL` 원자적 exclusive create.
  프로세스 간 안전, 덮어쓰지 않음
- `AnalysisQueue` 예약 회계 — `reserve()`는 예약 생성 **전에** raise하므로 429 경로에서
  `submitted`/세마포어 누출 불가, `__exit__`는 `with`가 정확히 1회 호출
- `file_browser` 내부 정합성 — `::drives`, `parent == target` 루트 판정, 숨김/`$RECYCLE.BIN` 필터,
  자식별 `OSError` 허용, 디렉터리 우선 casefold 정렬 모두 정확
- `recompute_totals`에 **인덱스 이동 위험 없음** — 리스트 위치를 변형하지 않고 파일을 삭제하지 않음.
  그리고 **실데이터 100건 전수 재계산 결과 `robustMean` 기준 2차 실행 시 0/100건이 변함** → 멱등성 확인
- `cli.main()`의 `stream.reconfigure(encoding="utf-8")`가 cp949 크래시(E-8)를 실제로 해결
- 스레드 안전성 — `dsp`, `loudness`, `audioio`는 입력의 순수 함수, 모듈 상수는 불변.
  공유 가변 상태 없음
- 프로젝트 규칙 G-01(영어 주석) — AST 스캔 결과 대상 파일 전부 **한글 0건**.
  한국어는 사용자 노출 문자열에만 존재(G-02 준수)

---

## 6. 기각된 보고

정직함을 위해 남깁니다. 서브에이전트가 **높음**으로 보고했으나 제가 재현 시나리오를 교정한 결과
**기각**한 건입니다.

- **"zero-weight 가드가 `attribution` 때문에 무력화된다"** — 처음에는 사실로 검증하려 했으나
  attribution에도 가중치 0을 명시하면 가드가 정상 동작하여 반례가 나왔습니다. 그런데 서브에이전트가
  보고한 **정확한** 시나리오(실제 3개 탐지기 키만 전송, `attribution` 키 없음)로 재검증하니
  **가드는 실제로 무력화됩니다**(`weights.get('attribution', 1.0) == 1.0`).
  → **기각이 아니라 확인으로 정정**했습니다. 최초 검증 스크립트가 시나리오를 잘못 세웠을 뿐입니다.
  C-5로 등재.

---

## 7. 권장 조치 순서

**즉시 (데이터 파괴 위험)**
1. `delete_history`에 `_report_path`와 동일한 이름 검증 추가 (C-1)
2. `recompute_totals.py`에 `--dry-run` + 백업 + tmp/replace 도입 (C-8). **100건에 이미 실행됨**
3. `--method`를 `detector_options.normalize()`로 검증 (C-7), 저장 가중치 보존 (C-9)

**측정값 신뢰도 (결과 수치를 신뢰할 수 없게 만드는 것)**
4. `dsp._interpolate_4x` 마지막 샘플 누락 (C-2)
5. `loudness` 5.1 채널 가중치 (C-3)
6. `file_analysis` MAD==0 단락 (C-4) + `agreement` 사전 제외 계산 (M-1)
7. `artifactnet` 구간 clamp 중복 (C-6)

**설정 무결성**
8. `detector_options` 0-가중치 가드에 `attribution` 제외 (C-5)
9. 잘못된 옵션 값을 기본값이 아닌 **기존 저장값**으로 coerce (C-11)
10. `app_settings` 부분 손상 시 전체 초기화 방지 (M-12)

**프론트엔드**
11. `audio-compare.js` / `app.js` fetch에 요청 순서화 또는 `AbortController` (C-14, C-13)
12. 업로드 이름 매핑을 `item["file"]` 기준으로 (C-12)

**테스트 기반 안전망**
13. `conftest.py` + `pytest.ini`의 `pythonpath`로 루트 밖 실행 가능하게 (C-15)
14. `test_anchor_evaluation.py`의 `scratch/` 의존 제거
15. F-1/F-5/F-6 수정에 회귀 테스트 추가 — 셋 다 지금은 **무방비**
16. `report.py`(`save` 제외)와 `analyze_files`/`analyze_file`에 테스트 추가 — 현재 사실상 0개

---

# 부록: 수정본 재검증 로그 (2026-09-27)

총 5개 회차로 나눠 기록합니다. Round 1은 Codex 수정본(당시 미커밋), Round 2는 그 커밋
(`70a0829`), Round 3은 자체 10건 수정, Round 4는 재리뷰, Round 5는 그 재리뷰에서 나온
후속 조치입니다.

| 회차 | 대상 | 테스트 | 상태 |
|---|---|---|---|
| 최초 | `656cf1c` 원본 | 76 passed | 읽기 전용 |
| Round 1 | Codex 15건 (워킹 트리) | 87 passed | → `70a0829`로 커밋 |
| Round 2 | Codex 최종 배치 | 90 passed | 커밋에 포함 |
| Round 3 | 자체 10건 수정 | 113 passed | **미커밋** |
| Round 4 | 재리뷰 | 115 passed | **미커밋** |

## Round 1: Codex 수정본 (당시 미커밋)

`656cf1c` 대비 **25개 파일 변경**(+441/-177),
신규 파일 `probe/evaluation.py`, `tests/test_recompute_totals.py`.

기준선: `pytest` **87 passed** (+11), `node --check` 양쪽 통과, **다른 CWD에서도 87 passed**.

## 종합 판정

| 항목 | 결과 |
|---|---|
| 높음 15건 | **15/15 해결** |
| 중간 24건 | 8건 해결, 16건 잔존 |
| errors_report E-1~E-4 | **4/4 해결** |
| 신규 회귀 | **0건** |
| 신규 발견 | 1건 (아래 N-1) |

높음 등급은 **전부 직접 재현해 확인**했습니다. 인용만으로 믿지 않았고, 서브에이전트·이전
리뷰의 수치 주장을 같은 스크립트로 다시 돌렸습니다.

## 높음 15건 ? 해결 확인

| # | 재현 결과 (수정 후) | 판정 |
|---|---|---|
| C-1 `delete_history` traversal | `Path(stem).name != stem` + `/ \ ..` 거부 + `_SAVE_LOCK` 추가. `'../outside:0'` → `False`, 파일 생존 확인 | 해결 |
| C-2 true peak 마지막 샘플 누락 | `np.interp` → `scipy.signal.resample_poly(x,4,1,padtype="line")`. `input max 0.900` → **`output max 1.128`**. `true_peak = max(peak, oversampled)`로 불변식 보장 | 해결 |
| C-3 BS.1770 채널 가중치 | `_channel_gains()` 신설 + **line 182에서 실제 호출 확인**. 6ch → `[1, 1, 1, 0, 1.41, 1.41]` (LFE=0, 규격 정확) | 해결 |
| C-4 `robustMean` MAD=0 | `np.isclose` 분기 신설. `[0.854, 0.854, 0.0]` → `0.8540, outliers=['d2']` (수정 전 `0.5693, []`) | 해결 |
| C-5 0-가중치 가드 무력화 | `DEFAULT_INCLUDED["attribution"] = False` **+ `IMPLEMENTED_DETECTORS` 화이트리스트**. `included`에 attribution 미포함, 가드 정상 발동 | 해결 (방어 이중화) |
| C-6 ArtifactNet 구간 clamp | `range(0, tail+1, SEGMENT)` + tailappend. 4.5초 → 중복 11개가 아니라 **2개 창**. 200초 파일은 `n=11, unique=11, monotonic=True`로 **무회귀** | 해결 |
| C-7 `--method` 미검증 | `choices=ENSEMBLE_METHODS`. `harmonic` → **exit 2**, argparse 오류. 조용한 기하평균 대체 없음 | 해결 |
| C-8 파괴적 재작성 | `_atomic_write_json`(tmp+fsync+replace) + `--dry-run`. dry-run 실행 시 파일 36→36, exit 0. **`--backup` 플래그는 여전히 없음** | 부분 해결 |
| C-9 저장 가중치 폐기 | `_stored_ensemble()`가 `detectorSettings.ensemble.weights` 보존. 테스트가 `{sonics:2, lofcz:1}` 유지까지 검증 | 해결 |
| C-10 subprocess 무한정 | `FFPROBE_TIMEOUT_S=30`, `FFMPEG_TIMEOUT_S=1800` + `TimeoutExpired → AudioToolError`. 부수적으로 M-22(JSON)도 해결 | 해결 |
| C-11 잘못된 값이 기본값으로 덮어씀 | `_normalize_detector(..., fallback)` 신설, coerce 폴백이 **기존 저장값**. `merge()`도 `_normalize_detector` 경유. `maxWindows` 16 유지 테스트 통과 | 해결 |
| C-12 업로드 이름 오매핑 | `_restore_upload_names()`가 경로 키 매핑. 원본 재현에서 각 결과가 자기 파일명 유지 (`middle/alpha/zebra` 정확) | 해결 |
| C-13 리소스 폴링 역전 | `resourceRequestInFlight` 가드 + `finally` 해제 | 해결 |
| C-14 stale fetch 오염 | `detailVisualRequest`, `comparisonRequest`, `peakRequests[row-1]` + 경로 재확인. 상세/비교 모두 | 해결 |
| C-15 테스트 재현성 | `pytest.ini`에 `pythonpath = .`. 다른 CWD에서도 87 passed. `test_anchor_evaluation`이 `scratch/` 대신 `probe.evaluation` import | 해결 |

## 중간 항목 ? 해결 8건 / 잔존 16건

**해결**: M-1(`agreement_values`가 이상치 제외 후 계산 ? 테스트가 `confidence > 70`까지 검증),
M-3 아님, M-11(리더 `isinstance(payload, dict)` 가드), M-13(`stat()`이 try 안으로),
M-14(`read_report`가 400 반환), M-16(`_atomic_write_json` + `RLock`), M-17,
M-22(ffprobe JSON → `AudioToolError`), M-24(`merge`가 method/weights 검증).
추가로 `stages.py` 74-75 인접 수정.

**잔존 (수정 안 됨)**:

| # | 위치 | 남은 문제 |
|---|---|---|
| M-3 | `artifactnet.py:136` | `required = min(min_valid, len(segments))` 그대로. 16초 미만 파일에서 4구간 최소가 강제되지 않음 |
| M-4 | `detector_options.py:165` | 힌트는 "총점 계산에서 제외", 코드는 `ValueError` → 탐지기가 에러로 사라짐. **사용자에게 반대 말** |
| M-8 | `sonics.py:56` | `max(std, 1e-6)` 그대로. 상수 구간에서 100만 배 증폭 |
| M-9 | `lofcz.py:119` | `MAX_DURATION_S * SAMPLE_RATE` 하드코딩 그대로. `maxDurationS`를 여전히 무시 |
| M-10 | `stages.py:19-20` | `source-44k.wav`와 `source.wav`가 둘 다 `"source"`로 매핑. 하나가 조용히 사라짐 |
| M-12 | `app_settings.py` | 손상 필드 하나가 `_merged`를 raise시키면 **전체 설정이 조용히 초기화**. 미수정 |
| M-15 | `history.py:135` | `sorted(..., key=lambda e: e[0])` ? 여전히 **문자열 정렬**. 혼합 오프셋 ISO에서 잘못 정렬되고 `historyLimit`이 삭제 대상을 결정 |
| M-18 | `cli.py:44` | `health`가 전부 MISSING여도 `return 0`. 미수정 |
| M-19 | `cli.py:121` | `Path("reports")` CWD 상대. 미수정 |
| E-2 | `app.py` | 업로드 **성공 시 정리 여전히 없음** (unlink은 480 실패경로, 697 리포트 삭제뿐) |
| C-8잔여 | `recompute_totals.py` | `--backup` 없음. 원자적 쓰기로 손상 위험은 줄었으나 **되돌릴 수 없음** |

## 신규 회귀 검사 ? 0건

수정이 새 버그를 만들지 않았는지 변경된 수치 코드 전부를 경계 조건으로 검증했습니다.

- `resample_poly`: 정현파/무음/상수 신호에서 오버슈트 +0.0003~+0.0006(필터 리플). 허용 범위.
  클리핑된 0.99 구형파는 +0.264 → 이는 **실제 인터샘플 피크**라 의도된 동작.
  다만 완전 full-scale 신호가 `truePeakDbfs +0.01`로 표시되는 미세 편향 존재
- `_robust_mean` 7개 경계값: 단일값·2개·전부 동일·`[0,0,0,1]`·`[0.9,0.9,0.1,0.1]` 모두 합리적
- `_channel_gains` 1~8ch: 전부 BS.1770 규격 일치
- `_segment_starts` 200초 파일: `start`/`even` 모두 11 unique, 단조 ? **정상 파일 동작 불변**
- `merge()`가 `return result`로 바뀐 것: line 303에서 `normalize(current_data)`로 시작하고
  패치를 `_normalize_detector`로 적용하므로 **정상화 누락 없음**
- `trim_history`에 `_SAVE_LOCK` 추가: `save_history` → `trim_history` 재진입이 생기므로
  `Lock` → **`RLock` 변경이 필수**였고, 정확히 반영됨
- end-to-end: 서버 기동 → `/health` 3탐지자 active → 22초 클립 실제 분석
  (`sonics=0.0747, artifactnet=0.7167, lofcz=0.0`, total 3.7, confidence 85.6,
  이상치 `artifactnet` 정상 제외, `detectorErrors` 없음)

## N-1 [신규 발견 → **해결**] BS.1770 모듈 216줄이 프로덕션에서 죽은 코드

Round 1 스모크 테스트에서 발견했습니다. **Codex 회귀가 아니라 기존 결함**이며,
이전 리뷰에서 놓친 항목이었습니다. **Round 2(`70a0829`)에서 Codex가 해결했습니다.**

당시 상황:
- `probe/loudness.py`의 `integrated_loudness()`가 어디에서도 호출되지 않음
- 실제 분석 응답의 `parameters.levels`에 `lufsIntegrated`/`lra`/`loudnessRangePeak` 키가 없음
- `web/app.js:130`은 `levels.integratedLufs == null ? '?' : ...`로 **이 필드를 렌더링**
  → UI의 LUFS-I가 **항상 `?`**로 표시됨
- 게다가 키 이름 불일치: UI는 `integratedLufs`, 모듈은 `lufsIntegrated` 반환

이야기가 복잡했던 이유: `test_loudness.py` 14개는 스위트에서 가장 강한 테스트(BS.1770-4 절대
기준값, 게이트, LRA-10, 48 kHz 계수표)였지만, **아무도 호출하지 않는 모듈을 정확히 검증**하고
있었습니다.

**해결 확인 (Round 2)**: `git log -S`, `git show HEAD:probe/dsp.py`, 직접 `level_profile()` 호출로
3중 확인했습니다.

| 지점 | 내용 |
|---|---|
| `probe/dsp.py:471` | `level_profile()` 신설 — `integrated_loudness()`를 실제 호출 |
| `probe/dsp.py:548` | report의 `"levels": level_profile(audio)` 배선 |
| `web/app.js:127` | `integratedLufs` 키로 UI 렌더링 |

실측 출력: `integratedLufs=-21.75`, `lra=4.44`, `crestDb=16.72`. 키 불일치도 해소됐습니다.

> **단, 이 배선은 R-3 성능 회귀를 동반했습니다.** 「현재 미해결 목록」 참조.

## Round 3: 자체 수정 10건 + C-8 잔여

사용자 승인 항목만 수정했습니다. **115 tests pass** (Round 2의 90 → +25).

| # | 위치 | 수정 내용 |
|---|---|---|
| M-15 | `probe/history.py` | `_sort_timestamp()` 신설 후 **모든 정렬 4곳**을 datetime 비교로 변경. `Z` 표기, 혼합 오프셋, naive(UTC 간주), mtime fallback, malformed 값 대응 |
| M-12 | `probe/app_settings.py` | `_as_int()`/`_as_bool()` 신설. threshold·경로·필드별 방어 파싱. 필드 하나가 나빠도 전체 설정이 초기화되지 않음. 신규 `tests/test_app_settings.py` 5개 |
| M-18 | `probe/cli.py` | `health`가 ffmpeg/ffprobe 누락 시 **exit 1**. detector unavailable은 비치명적 |
| M-19 | `probe/cli.py` | `--save`가 CWD 상대 `Path("reports")` 대신 `config.REPORTS_DIR` 사용 |
| M-7 | `probe/detectors/base.py` | `unavailable_reason()`이 누락 파일을 runtime보다 먼저 보고. 진짜 원인이 surfaced됨 |
| M-4 | `probe/detector_options.py` | `minValidSegments` 힌트를 실제 오류 처리 및 short-track 기준 하향 설명으로 수정 |
| M-5 | `probe/detectors/artifactnet.py` | `levelNormalize=False` 기본값과 점수 변경 위험을 주석에 명시 |
| M-2 / M-23 | `probe/file_analysis.py` | agreement를 **sample 표준편차 `ddof=1`**로 변경. 탐지기 수 간 비교가 가능해짐 |
| C-8 | `scripts/recompute_totals.py` | `--backup` 추가. 최초 `<파일>.bak` 보존, dry-run/무변경 시 백업 미생성 |
| M-6 | `probe/detector_options.py` | `DETECTORS`↔`DETECTOR_SCHEMA`↔`IMPLEMENTED_DETECTORS` 불변식 테스트 추가. attribution에 양수 가중치 부여 |

> **주의 — M-2/M-23는 confidence 값을 바꿉니다.** 2탐지기 `0.90/0.10`이면 agreement가
> `0.2 → 0.0`, confidence가 `8.0 → 0.0`이 됩니다. **변경 전 confidence와 수치 비교가
> 불가능합니다.** 저장된 리포트의 confidence는 `recompute_totals.py`로 재계산해야 합니다.

검증: 프로젝트 루트 113 passed / `%TEMP%`에서도 113 passed / 수정 모듈 `py_compile` 통과 /
서버 기동 + `/health` + `/api/settings` smoke 통과.

## Round 4: 재리뷰

### R-1 [자기 점검] 제가 만든 회귀 — 수정 완료

`trim_history`에 `fallback_mtime=source.stat().st_mtime`를 인자로 넘겼는데 **인자는 호출 전에
평가**됩니다. 그 결과 `generatedAt`가 있어도 `stat()`이 실행되고, `stat()`이 OSError를 내면
원래는 처리되던 report가 통째로 건너뛰어졌습니다. 기존 `or`의 단락 평가가 사라진 것입니다.

수정 후 검증:

| 조건 | 결과 |
|---|---|
| `generatedAt` 존재 + `stat()` 실패 | `stat()` **0회** 호출, trim 정상 동작 |
| `generatedAt` 없음 + `stat()` 실패 | 1회 호출 후 skip (문서화된 fallback 경로) |
| 대조군 ( stat 정상, limit 1 / 결과 2개) | 2 → 1로 정상 trim |

버그를 다시 주입해 테스트가 실제로 실패하는지 확인한 뒤 `tests/test_history.py`에 회귀 테스트
2개를 추가했습니다 (`1 failed` 확인). **115 tests pass.**

### R-2 `--backup` 안전성 — 이상 없음

모든 소비자가 `*.json`으로 glob합니다: `app.py:642`, `history.py:93,134,136,154,193,195`,
`scratch_cleanup.py:15,18`, `recompute_totals.py:152,156,166`. `report.json.bak`은 어느 것도
매칭하지 않으므로 history·report 목록·recompute에서 제외됩니다.

### R-3 [성능, HIGH] LUFS 배선이 분석을 7.4배 느리게 만듦 — **미수정**

`level_profile`이 N-1 해결 과정에서 모든 분석 경로에 들어가면서 파일당 **+3.4초**가
추가됐습니다. 3분 트랙 기준 `level_metrics` 0.53s → `level_profile` **3.93s**.

원인은 `probe/loudness.py:138 _fft_convolve`입니다. 4096탭 FIR 커널을 **신호 전체 길이로
zero-pad**해 FFT합니다.

| 항목 | 값 |
|---|---|
| 신호 샘플 | 8,722,560 |
| pad 후 FFT 크기 | **16,777,216** (`1 << bit_length()` → 1.92배 낭비) |
| 커널 | 4096탭 → 대부분 0인 배열을 16.7M 길이로 FFT (4회) |
| 프로파일 | `_raw_fft` 12회 = 2.97s, 전체 3.31s 중 90% |

**기존 코드는 수학적으로 정확합니다** (`np.convolve`와 2.665e-15 일치). 성능만의 문제입니다.

검증한 대체안 — overlap-add (**입력은 겹치지 않고 출력만 겹침**):

| 항목 | 결과 |
|---|---|
| 정확도 | 현재 구현과 `3.6e-16` 일치 (**무손실**) |
| 속도 (factor 4~8) | 843ms → **93ms**, **9.0배** |
| `next_fast_len` 단독 | 671ms, 1.19배 — 주된 레버 아님 |

적용하면 `level_profile`이 약 1.0초로 내려가 파일당 오버헤드가 +3.4초 → +0.5초가 됩니다.
**리뷰 단계라 적용하지 않았습니다.**

> 참고: 첫 프로토타입은 **입력 구간을 겹쳐** 이중 합산했고(오차 4.945e-01), 두 번째는
> `m < block + n - 1`로 원형 앨리어싱을 만들었습니다. `np.convolve` 기준 삼중 비교로
> 잡았습니다. 수치 검증 없이 속도만 보고하면 이런 오류를 통과시킬 수 있습니다.

## 현재 미해결 목록

> 2026-09-27 Round 7 종료 시점. 코드를 직접 읽어 확인한 결과입니다.

### 중간 1건 — 설계 (제품 결정 필요)

| # | 위치 | 내용 |
|---|---|---|
| M-20 | `file_browser.py:35-41` | 루트 구속·인증 없음 → 전체 디스크 목록 + 임의 경로 분석. 기본 `127.0.0.1` loopback 바인딩이면 설계상 허용되지만, 바인딩 주소를 외부로 바꾸는 순간 문제가 됩니다 |

### 중간 1건 — 단순 버그 (안전하게 수정 가능)

| # | 위치 | 내용 |
|---|---|---|
| M-23 | `audioio.py:156-159` | `nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)`가 손상 파일을 **디지털 무음으로 조용히 변환**합니다. 정상 무음 파일과 `peakDbfs: -240.0`으로 구별되지 않고, `Audio` 객체에 처리 아티팩트를 표시할 플래그도 없습니다. 디코드 실패를 측정값으로 내는 무결성 문제입니다. |

> **M-23 집계 정정**: Round 3 표에서 M-2와 묶어 "자체 수정"으로 세었으나, 실제로는
> M-2의 `ddof=1`만 반영되고 M-23은 손대지 않았습니다. 아래 「오류 정정 기록」 참고.

### R-3 성능 — 해결됨

Overlap-add convolution(`scipy.signal.oaconvolve`)으로 교체 완료. 상세는 「R-3」 및 「Round 6」.

### 리뷰 중 발견한 경미 사항

- `--backup`이 만든 `.bak`을 정리하는 경로가 없습니다 (`scratch_cleanup`은 `scratch/`만 처리)
- `cli._print_health`의 필수 도구 누락 메시지가 모든 detector 출력 **뒤**에 출력됨
- `_backup_file`의 반환값이 호출부에서 사용되지 않음

### 낮음/정적 64건 — 전부 미착수

3절 전체. `dsp.py:48`의 `BRICKWALL_DB_PER_KHZ`가 정의만 되고 어디서도 미사용이라
`steepest_rolloff`의 docstring이 약속하는 "brickwall 판정"이 적용되지 않는 항목이 포함됩니다.

### 코드 외 미착수

- `C:\Claude\SongYUE2` 실제 health 폴링 경로 미조사
- 4개 대상 파일의 2탐지자 → 3탐지자 flow 미재실행 (`scratch/run_flows.py`의 `\u` escape 버그)
- `--dry-run` 대기 212건은 **M-2만** 변경 전 수치입니다. confidence 정의가 바뀌었으므로
  재계산 전 카운트를 신뢰하지 마십시오.

## 오류 정정 기록

리뷰 과정에서 제가 잘못 판정한 항목을 기록해 둡니다.

### 1. 패턴 grep 부재 오판 (존재하는 코드를 "미해결"로 집계)

| 항목 | 정정 |
|---|---|
| M-14 | `def read_report` 패턴만 grep하고 본문을 안 읽어 "미해결"로 집계. 실제로는 `app.py:726`에 `except (OSError, json.JSONDecodeError) → HTTPException(400)`이 **있음** → Codex가 해결 |
| M-22 | `json.loads` 라인만 grep해 "미해결"로 집계. 실제로는 `audioio.py:89-92`에 `try/except json.JSONDecodeError → AudioToolError`가 **있음** → Codex가 해결 |
| M-1·M-13·M-16 | 최초 집계에서 "미해결"로 셌으나 Codex가 이미 해결 (M-1은 `agreement_values`가 이상치 제외, M-13은 `stat()`이 try 내부, M-16은 `_atomic_write_json`+`RLock`) |
| M-8·M-17 | **같은 실수를 재범**했습니다. M-8은 상수 선언 `MIN_NORMALISATION_STD = 1e-6`이 남아 있는 것만 보고 "미해결"로 보고했고, 실제로는 `sonics.py:58-61`에서 퇴화 구간을 **0으로 치환**하도록 수정돼 있었습니다. M-17은 `payload.get(` 라인이 남아 있는 것만 보고 "미해결"로 보고했지만, 가드는 **별도 라인**의 `isinstance(payload, dict)`이고 5곳에 존재했습니다. 둘 다 이미 해결된 상태였습니다. |

### 2. 집계·해석 오류

| 항목 | 정정 |
|---|---|
| M-23 | Round 3 표에서 M-2와 묶어 "자체 수정"으로 세었으나, 실제 반영은 M-2의 `ddof=1`뿐이었습니다. `audioio.py:156-159`의 `nan_to_num` 무음 치환은 그대로 남아 **미해결**입니다 |
| M-21 | 최초 리뷰가 `-ar`/`-ac`가 44100/1을 강제한다고 적은 것은 **오독**입니다. `audioio.load()`는 ffprobe로 읽은 `meta.sample_rate`/`meta.channels`(파일 네이티브 값)을 넘기며, `git diff`에도 해당 변경이 없습니다. docstring과 코드가 처음부터 일치하므로 **기각**합니다 |

### 3. 부작용

위 M-8·M-17 오판 때문에 이미 해결된 항목을 "미해결"로 보고 사용자에게 통보했고, M-23·M-21 집계도
잘못 알렸습니다. 문서 수정만으로 실제 결함이 고쳐지는 것은 아니므로, **판정은 항상 함수의 전체
본문**을 읽은 뒤에 내립니다. 패턴 grep은 **존재 부부의 증거**이지 부재의 증거가 아닙니다.

---

## Round 6: 권장 수정 및 정책 결정

| 항목 | 적용 내용 | 판정 |
|---|---|---|
| R-3 | 전체 신호 zero-padding FFT를 `scipy.signal.oaconvolve`로 교체. 3분·48 kHz 모노 기준 0.778초 → 0.200초, 직접 convolution과 회귀 테스트 추가 | 해결 |
| M-8 | SONICS의 표준편차가 1e-6 이하이거나 비정상이면 해당 구간을 무음으로 전달해 상수 신호의 100만 배 증폭 차단 | 해결 |
| M-17 | `favorites.json`과 이력 파일의 최상위 JSON이 객체가 아니면 안전하게 무시 | 해결 |
| M-11 | 첫 단계와 마지막 단계에 모두 존재하는 지표만 변화량으로 계산 | 해결 |
| C-8 잔여 | `--backup` 복사 실패를 삼키지 않고 실제 파일 갱신 전에 중단 | 해결 |
| M-24 | 빈 오디오의 crest factor를 `None`으로 처리 | 해결 |
| M-3 | 짧은 음원은 계속 분석하되 `effectiveMinValidSegments`와 `minimumAdjustedForShortAudio`를 결과에 기록 | 정책 확정·해결 |
| M-9 | lofcz의 `segments`와 segment 통계를 Total 계산에 실제 사용한 동일 scoring window로 통일. 별도 300초 진단 재추론 제거 | 정책 확정·해결 |
| M-10 | SongYUE2의 `source.wav`와 `source-44k.wav`를 `source_original`·`source_44k`로 각각 보존 | 정책 확정·해결 |
| M-21 | `-ar`/`-ac`가 네이티브 값(`meta.sample_rate`/`meta.channels`)을 넘기므로 docstring과 일치. 44.1 kHz 입력에서 명시 옵션 유무의 출력 PCM이 동일 | **기각** (문서 불일치 아님) |
| M-20 | 기본 `127.0.0.1` 실행에서는 유지. 외부 바인딩 지원 전 인증 또는 루트 제한 필요 | 조건부 잔존 |
| M-23 | — | **잔존** (Round 3 집계 오류 정정) |

검증: 프로젝트 루트와 외부 CWD에서 각각 `124 passed`. `compileall` 및 `git diff --check`
통과. 실제 MP3 한 곡으로 3개 탐지기 분석과 loudness 출력까지 확인했습니다.

---

## Round 7: `start.bat`/`stop.bat` 포트 처리 (R-4)

사용자 요청으로 **이 두 파일만** 수정했습니다. 다른 소스 파일은 건드리지 않았습니다.

### R-4 [신규 발견 → 해결] 실행 중인 서버가 신생 서버의 포트를 빼앗음

| 항목 | 내용 |
|---|---|
| 증상 | 서버 실행 중 `start.bat`을 다시 실행하면 브라우저(SSE)가 `/api/analysis/stream`에서 끊겼다가 새 서버에 붙음. "분석 완료 3/4"가 멈춤 |
| 오해 | Python 크래시로 보였으나 Application Error ID 1000 기록이 없음. 정작 서버는 살아 있었음 |
| 실제 원인 | 포트 소지 서버를 못 잡아 **새 인스턴스가 포트 8792를 빼앗음** |
| 왜 | 1) Windows 소켓은 `SO_REUSEADDR`로 **TIME_WAIT가 있어도 이미 LISTEN 중인 포트에 다른 프로세스가 bind/bind+listen에 성공**합니다. 2) 기존 `stop.bat`은 `netstat -ano`의 PID만 종료했으나 실제 프로세스 트리는 `python.exe`가 아니라 그보다 위쪽 launcher였습니다. 3) 따라서 kill→start 사이에 포트가 안 정리돼 새 인스턴스가 살아남은 인스턴스를 밀어냈습니다 |
| 수정 | `stop.bat`을 `Win32_Process` 조회로 전환: `python.exe`이면서 명령행에 `probe.app`이 있는 **모든** 프로세스를 종료 후 8792 해제를 최대 10초 대기. `start.bat`은 시작 전 `stop.bat` 호출 |

### 검증 (실환경)

- 기존 방식이 놓치던 유령 서버 3개 정리, 잔여 메모리 2,317 MB 회수.
- 같은 포트의 무관한 ComfyUI 서버(8190)는 **생존** — 매칭이 `probe.app`으로 한정되어 있음.
- 서버 실행 중 `start.bat` 재실행 → launcher/server는 **신규 2개만** 남고 기존 인스턴스 0개.
- `/health` OK, 탐지자 4개 active, `/api/analysis/status` idle.
- 전체 테스트 `127 passed`. `node --check web/app.js` 통과.

> 이 교훈은 Windows 개발 서버 전반에 재사용 가능하므로
> `memory-bank/knowledge/trouble-shooting.md`와 글로벌 `C:\Claude\memory-bank`에 기록했습니다.
