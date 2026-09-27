# errors_report.md

ai-music-probe 오류·결함 보고서

- 기준 커밋: `656cf1c` (2026-09-27, "Update analysis evaluation and UI settings")
- 검증 환경: Windows, Python 3.12, `.venv`, 서버 `http://127.0.0.1:8792`
- 작성 시점 테스트 결과: `pytest` **76 passed**
- 작성 시점 이력: 100건 (3탐지자 99건 + 2탐지자 1건)

모든 항목은 소스 코드를 직접 열어 확인한 것이며, 추측이 아닌 재현 결과로 뒷받침했다.
**이번 문서 작성 과정에서는 코드를 수정하지 않았다.**

---

## 1. 이미 해결된 항목 (재확인 완료)

| # | 항목 | 위치 | 확인 방법 |
|---|------|------|-----------|
| F-1 | 파형이 슬래브처럼 뭉개짐 — 서버가 슬라이스별 `abs().max()`를 써서 조밀한 마스터에서 177/180바가 최대값에 붙음 | `probe/visuals.py:38` | 슬라이스 RMS로 변경. 인간 원곡 최대높이 바 98% → 29%. `metric: "rms"` 응답 확인 |
| F-2 | 스펙토그램 Y축 상한 `22.1 kHz` 하드코딩 — 48 kHz 음원에서 축 전체가 오표시 | `web/app.js` `frequencyAxisLabels()` | 파일 실제 샘플레이트로 산출. 44.1 kHz → `22.1/16.5/11.0/5.5/0`, 48 kHz → `24.0/18.0/12.0/6.0/0`. Chromium에서 2종 라벨셋 렌더 확인 |
| F-3 | 주파수축 라벨이 이미지와 어긋남 (최대 6.5px 드리프트) | `web/styles.css` `.compare-frequency-axis` | `space-between`(라벨 가장자리 정렬)이 주파수 스톱(라벨 중심 정렬)과 불일치. 절대 위치 + `translateY(-50%)`로 변경 → 드리프트 `0.0px`, 1500px/500px 모두 확인 |
| F-4 | 동일 파일 재분석 시 결과가 조용히 사라짐 — `key in seen` 으로 `(file, totalScore, status)` 중복 제거 | `probe/history.py` | 제거됨. `sourceName` 보존 + 표시 시 `_name_with_index()` 로 `(1)`, `(2)` 접미사 부여. 실제 이력에서 `K0062-1 ... (1).wav`, `(2).wav` 확인됨 |
| F-5 | ArtifactNet이 근-full-scale 입력에서 NaN 반환 → 구간 3/7 유효로 판정 실패하여 탐지기 자체가 탈락 | `probe/detectors/artifactnet.py:121` | `_level_normalise()` 적용(옵션 게이트). 4개 트랙 전 구간 NaN 0건 확인 |
| F-6 | `_progress_response` 타임아웃 분기의 `emit()` 미정의 → 1800초 무응답 시 `NameError` | `probe/app.py:525` | 올바른 오류 yield로 수정됨 |
| F-7 | 파형/스펙트로그램이 컨테이너 밖으로 넘침 주장 | `probe/visuals.py`, `web/styles.css` | `object-fit: fill`로 1200×300 전체가 722×180에 들어감. 모든 조상 `clipsTop/clipsBottom = 0`, `topClippedAnywhere: false`. **잘려나감 없음** |

### F-1/F-5 관련 근거 데이터

인간 원곡(44.1 kHz FLAC) 세그먼트별 모델 출력:

```
seg  rms      peak     원출력   정규화후
0    0.2797   0.9965   NaN      0.0000
1    0.3337   0.9966   NaN      0.0000
2    0.4287   0.9973   0.0000   0.0001
3    0.3684   0.9963   NaN      0.0004
4    0.4111   0.9964   0.0000   0.0001
5    0.3995   0.9967   NaN      0.0509
6    0.2088   0.9976   0.0001   0.0006
```

NaN은 무음이 아니라 **화음량(hot master)** 때문에 발생했다. 모델은 레벨 의존적이다:

```
RMS 1e-8 노이즈 -> 0.00002
RMS 1e-4 노이즈 -> 0.0246
RMS 1e-1 노이즈 -> 0.9788
```

정규화 변형별 NaN 개수 (4개 트랙 전 구간):

```
변환          인간원곡   AI원본   LANDR   SongYUE2
raw            4         0        0        0
peak->0.95     3         1        0        0
rms->0.1       0         0        0        0     <- 유일하게 전부 무효화 없음
```

---

## 2. 미해결 항목 (현재 코드에서 재확인함)

### E-1 [높음] 업로드 파일명이 결과에 잘못 매핑됨

- 위치: `probe/app.py:492`, `probe/app.py:580`
- 원인: `probe/file_analysis.py:36` 의 `expand_inputs()` 가 `return sorted(files, key=lambda item: str(item).casefold())` 로 **항상 정렬하여 입력 순서를 버린다.** 업로드는 `scratch/uploads/<uuid>-<original>`(`app.py:465`)로 저장되므로 경로 정렬 = **UUID hex 정렬 = 무작위**

```python
# app.py:492 / app.py:580 — 위치를 기준으로 이름을 되돌린다
for item, original in zip(result["results"], original_names):
    item["name"] = original
```

재현 (2개 이상 업로드 시 이름이 섞임):

```
upload order  : ['zebra.wav', 'alpha.wav', 'middle.wav']
result order  : ['middle.wav', 'alpha.wav', 'zebra.wav']
positional zip: {'middle.wav': 'zebra.wav', 'alpha.wav': 'alpha.wav', 'zebra.wav': 'middle.wav'}
>>> MISMATCH <<<
```

**영향:** 이력 카드에 **잘못된 파일명**이 실제 오디오와 함께 표시된다. 업로드 1개일 때는 우연히 맞아서 드러나지 않는다.

**수정 방향:** 위치 기준이 아니라 `item["file"]` 로 원래 이름에 매핑.
참고: 같은 파일의 진행 콜백(`app.py:576`)은 `paths.index(path)` 를 사용해 **정확히** 처리한다. `Path.resolve()` 가 해당 경로에서 무의미한 변경임을 확인했다. 최종 결과 매핑만 잘못되어 있다.

---

### E-2 [중간] 업로드 파일이 성공 시 정리되지 않음

- 위치: `probe/app.py:451-484` (`_store_uploads`)
- `except` 분기(`app.py:480`)에서만 `unlink` 한다. **성공 시 삭제 코드 없음**
- `app.py` 내 `unlink` 은 480(실패 정리)과 674(리포트 삭제) 두 곳뿐이며 분석 후 정리가 아니다
- **영향:** `scratch/uploads/`가 무한 증가. 대용량 업로드 반복 시 디스크 소진

---

### E-3 [중간] 파일별 예외 보호가 좁음

- 위치: `probe/file_analysis.py:206`

```python
except (AudioToolError, ValueError, OSError) as error:
```

- `dsp.analyze()`가 다른 예외(numpy `MemoryError`, `RuntimeError` 등)를 던지면 보호되지 않는다
- **영향:** 요청 전체가 500이 되고 **남은 파일이 전부 건너뛰어진다.** 부분 결과 없음
- 비교: `file_analysis.py:164` 의 탐지기 예외는 `except Exception` 으로 넓게 잡고 `detectorErrors` 에 기록한다(E-3와 달리 정상 동작)

---

### E-4 [중간] 클라이언트 연결 끊김 시 작업이 취소되지 않음

- 위치: `probe/app.py:563`, `probe/app.py:582` — 워커 스레드 안의 `save_history(result)`
- SSE 클라이언트가 끊겨도 워커 스레드는 끝까지 분석을 계속하고 결과를 저장한다
- **실측:** 연결이 끊어진 실행에서 이력 4건이 정상 저장됨을 확인
- **영향:** 브라우저에서 취소해도 CPU를 계속 소모하고 결과가 나중에 나타남. `_ANALYSIS_QUEUE` 점유 slot도 그 동안 유지되어 후속 요청이 429에 걸릴 수 있음

---

### E-5 [낮음] 분석 큐 포화로 429

- 위치: `probe/app.py` `_ANALYSIS_QUEUE.reserve()` (`AnalysisQueue(MAX_ANALYSIS_ACTIVE, MAX_ANALYSIS_PENDING)`)
- `submitted >= active + pending` 이면 429 발생
- **영향:** 동시 요청이 몰리면 정상적으로 429. 긴 파일 분석 중이면 오래 지속될 수 있음

---

### E-6 [중간] 스펙트로그램 dB 창이 트랙 고정

- 위치: `probe/visuals.py:71`
- 현재 필터: `showspectrumpic=s=1200x300:legend=disabled:scale=log:color=rainbow`
- dB 축 라벨은 `web/app.js` 에 `0` / `-100` `dBFS` 로 하드코딩
- **영향:** 트랙 간 레벨 차이를 흡수하지 못해 조용한 곡이 어둡거나, 조밀한 곡이 균일하게 밝게 뭉개진다

수치 근거 (픽셀 평균 / 어두운 픽셀 비율):

```
인간 원곡   mean RGB [87.0, 182.7,  50.3]   near-black  0.0%
AI 원본     mean RGB [20.2,  77.1, 109.6]   near-black 23.8%
LANDR       mean RGB [33.6, 108.6, 101.7]   near-black  7.4%
SongYUE2    mean RGB [27.3,  92.0, 118.7]   near-black  9.8%
```

인간 원곡은 어두운 영역이 0% — 구조가 보존되지 않는다. 트랙별 dB 창(예: 퍼센타일 기반)으로 opened dynamic range를 확보하는 것이 후속 과제.

> 참고: 주파수 축(선형, 0 Hz~Nyquist) 자체는 정확하다. `scale=lin`과 `scale=log`에서 1 kHz/4 kHz/10 kHz/21 kHz 톤의 행 위치가 **동일**(285/285, 163/163, 13/13, 6/6)하고 `1 - f/22050` 예측과 일치한다. dB 창 문제와 주파수 축 문제는 별개다.

---

### E-7 [낮음] 비주얼 캐시 고아 파일 누적 및 오래된 이미지 가능성

- 위치: `probe/visuals.py:63`

```python
identity = f"{path}|{path.stat().st_mtime_ns}|{kind}"
target = VISUAL_DIR / f"{hashlib.sha256(identity).hexdigest()}.png"
```

- 동일 파일은 **덮어쓰지 않는다** (해시 이름이라 충돌 불가). 같은 파일+같은 mtime이면 캐시 재사용, mtime 바뀌면 새 해시로 새 파일이 **나란히** 생성됨
- **문제 1:** 이력에서 삭제된 항목의 PNG가 영구히 남음 (orphans)
- **문제 2:**内容的을 바꾼 뒤 mtime을 보존하면 **오래된 이미지가 그대로 served**된다. 콘텐츠 해시 키로 바꾸면 방지 가능

---

### E-8 [낮음] 콘솔 인코딩(cp949)으로 스크립트 크래시

- 위치: 이 프로젝트의 Python CLI/검사 스크립트 전반
- 재현: 파일명에 일본어/한글이 섞인 이력을 출력하면 `UnicodeEncodeError: 'cp949' codec can't encode character '\u30ea'`
- **영향:** 검증 스크립트가 중간에 죽어 후속 확인을 못 함. `PYTHONIOENCODING=utf-8` 또는 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` 필요
- 이 문서 작성 중에도 실제로 발생했다

---

## 3. 오류가 아닌 것 (오해 사례)

### N-1 `ConnectionResetError: [WinError 10054]`

```
INFO: 127.0.0.1:64888 - "GET /api/media?path=... HTTP/1.1" 206 Partial Content
Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)
  File "asyncio\proactor_events.py", line 165, in _call_connection_lost
    self._sock.shutdown(socket.SHUT_RDWR)
ConnectionResetError: [WinError 10054]
```

- **정상 동작이다.** 206은 Range 요청의 **성공** 응답
- `<audio>` 시킹(되감기/건너뛰기) 시 브라우저가 in-flight Range 요청을 버리고 새 요청을 만들기 때문에 서버는 스트리밍 도중 연결이 끊긴다. uvicorn의 asyncio 이벤트 루프가 소켓 정리 중 `shutdown()` 호출 시 이 예외 발생
- **위험 위치가 `_call_connection_lost` 정리 콜백 내부**이며, 이미 206 응답이 끝난 **뒤에** 발생한다
- 오디오 Range/Seek 파이프라인 정상, 서버 무영향, 콘솔 잡음일 뿐
- Windows + uvicorn + `<audio>` 시킹 조합의 알려진 현상

### N-2 probe는 SongYUE2를 호출하지 않는다

요청하신 "SongYUE2에서 AI 점수 계산을 요청하고 오디오를 받아 결과 반환하는" 경로는 이 코드베이스에 **없다.** 확인 결과:

- `probe/stages.py:18` — `SONGYUE_STEM_MAP`, SongYUE2의 **결과물**을 읽기만 함
- `probe/cli.py:4` — docstring의 `SongYUE2\runs\<id>` 경로
- `probe/app.py:706` — 주석: **SongYUE2의 Settings 페이지가 이 서버 `/health`를 1~3초마다 폴링**

데이터 흐름은 일방향·오프라인이다. SongYUE2가 mastering WAV를 사전 생성하고 probe는 그 파일을 분석할 뿐이다. N-1의 `ConnectionResetError`도 `/api/media` 스트리밍에서 난 것으로 점수 계산과 무관하다.

---

## 4. 미완료 작업

- [ ] 4개 트랙(인간 원곡 / AI 원본 / LANDR / SongYUE2+mastering-1)의 **2탐지자 + 3탐지자 결과 동시 보관** flow
      — F-4가 해결되어 중복 표시가 가능해졌으나, 이력은 이후 100건 코퍼스 분석으로 대체됨
- [ ] E-1 업로드 파일명 매핑 수정
- [ ] E-2 업로드 정리 추가
- [ ] E-6 스펙트로그램 트랙별 dB 창
- [x] `todo.md` / `memory-bank` 갱신 — E-1~E-8을 `todo.md`의 `## 알려진 버그` 절로 옮김 (2026-09-27)

---

## 5. 재현 명령

```powershell
# 테스트
.\.venv\Scripts\python.exe -m pytest -q                 # 76 passed

# 문법/컴파일
.\.venv\Scripts\python.exe -m compileall -q probe
node --check web\app.js

# 서버 재시작
cmd /c stop.bat
.\.venv\Scripts\python.exe -m probe.app

# 이력/탐지기 상태
.\.venv\Scripts\python.exe -c "import json,urllib.request; print(len(json.load(urllib.request.urlopen('http://127.0.0.1:8792/api/history',timeout=30))['results']))"

```

F-1/F-2/F-3 검증에 쓴 `scratch/browser_waveform_check.py`·`browser_freqaxis_check.py`·`browser_specclip_check.py`·`cdp_client.py`와 `scratch/run_flows.py`는 위 세 항목이 "재확인 완료"로 굳어진 뒤 2026-09-27에 정리했다(목적을 다한 일회성 스크립트). 다시 회귀가 의심되면 같은 방식(자체 CDP 클라이언트로 실제 렌더 결과 픽셀/geometry 측정)으로 새로 작성할 것 — 결론 자체는 위 표에 남아 있다.

진단용 스크립트: `scratch/diag_artifactnet.py`, `scratch/diag_artifactnet_norm.py`,
`scratch/probe_freq_axis.py`
