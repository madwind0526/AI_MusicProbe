# AI Music Probe

음원 파일마다 **AI 생성 흔적**을 분석해 측정 파라미터, 탐지기별 근거, `totalScore`(0–100)를 반환하는 로컬 분석 앱입니다. 모든 처리가 이 PC 안에서 끝나며, SongYUE2와 독립적으로 실행됩니다.

> **`totalScore`는 확률이 아닙니다.** 공개 탐지기의 원시 출력을 결합한 잠정 비교 점수이며, 사람과 AI의 법적 판정값도 아닙니다. 짝 데이터를 충분히 모은 뒤 비선형 보정을 적용할 예정입니다.

## 요구 사항

| 항목 | 내용 |
|------|------|
| Python | 3.12 |
| 외부 도구 | `ffmpeg`, `ffprobe` (PATH에 등록되어 있어야 합니다) |
| GPU | 필요하지 않습니다. CPU 전용 ONNX/ PyTorch 추론입니다 |

## 설치와 실행

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.\start.bat
```

브라우저에서 `http://127.0.0.1:8792`를 엽니다. OpenAPI 문서는 `http://127.0.0.1:8792/api/docs`에 있습니다.

서버를 멈추려면 해당 포트(8792)의 프로세스를 종료하면 됩니다.

## 탐지기 설치

탐지기는 **가중치를 내려받아 놓아야** 동작합니다. 하나도 없어도 DSP 지표는 정상 동작합니다.

| 탐지기 | 배치 위치 | 출처 |
|--------|-----------|------|
| SONICS / SpecTTTra gamma 5s | `models/sonics/cache/` | [github.com/awsaf49/sonics](https://github.com/awsaf49/sonics) |
| lofcz vocoder fakeprint | `models/lofcz/ai-music-detector.onnx` | [github.com/lofcz/ai-music-detector](https://github.com/lofcz/ai-music-detector) |
| ArtifactNet v9.4 | `models/artifactnet/artifactnet_v94_full.onnx` (+ `.data`) | [huggingface.co/intrect/artifactnet](https://huggingface.co/intrect/artifactnet) |

WebUI의 **탐지기** 화면에서 `활성/설치/전체` 상태를 확인하고, 없는 모델은 각 카드의 설치 안내를 따라 받으면 됩니다. 활성/비활성은 `models/detector-settings.json`에 저장됩니다.

**라이선스 주의:** ArtifactNet 공개 ONNX는 **CC BY-NC 4.0** 연구·개인 평가용이며 특허 권리를 포함하지 않습니다. 상업 제품·유료 API에 별도 허가 없이 사용할 수 없습니다.

## 사용법

### WebUI

1. **음원 분석** — 파일 드래그&드롭, 내장 탐색기로 폴더 선택, 또는 경로 직접 입력. 여러 파일을 넣어도 결과는 파일별로 따로 나옵니다.
2. **탐지기** — 모델별 활성 토글과 라이선스·설치 상태.
3. **리포트** — API로 저장한 JSON 요약.
4. **설정** — 점수 색상 구간, 이력 보관 개수, 카드 크기, 기본 폴더.

분석 이력 카드를 누르면 상세 창이 열리고, 원본 재생과 함께 파형·스펙트로그램에서 재생 위치를 확인할 수 있습니다.

### CLI

```powershell
python -m probe.cli health                                        # 외부 도구와 탐지기 가용성
python -m probe.cli score --path C:\Claude\SongYUE2\runs\<id>      # stage 집합 분석
python -m probe.cli score --map stages.json --control control.json # 대조군 포함
python -m probe.cli serve --port 8792                              # API + UI 서버
```

## HTTP API

로컬 파일 또는 폴더:

```http
POST /api/analyze
Content-Type: application/json

{
  "paths": ["C:\\Music\\song.wav", "C:\\Music\\album"],
  "recursive": true,
  "save": false
}
```

업로드는 `POST /api/analyze/upload`에 `files` multipart 필드를 반복해서 전달합니다.

| 메서드 | 경로 | 용도 |
|--------|------|------|
| `GET` | `/health` | ffmpeg/ffprobe 상태 + 탐지기 목록 |
| `GET` | `/api/detectors` | 탐지기 목록 |
| `PATCH` | `/api/detectors/{name}` | 탐지기 활성/비활성 |
| `POST` | `/api/analyze` | 경로·폴더 분석 |
| `POST` | `/api/analyze/upload` | 업로드 분석 |
| `GET` | `/api/files/browse` | 내장 탐색기 |
| `GET` | `/api/settings` · `PUT` `/api/settings` | UI 설정 |
| `GET` | `/api/detector-options` · `PUT` `/api/detector-options` | 탐지기 분석 옵션과 Total 결합 방식 |
| `GET` | `/api/history` | 분석 이력 |
| `GET` | `/api/reports` · `/api/reports/{name}` | 저장된 리포트 |
| `GET` | `/api/reports/{name}/export?format=json\|csv` | 리포트 파일 내보내기 |
| `GET` | `/api/resources` | CPU·RAM·GPU 사용량 |

브라우저 업로드는 파일당 500 MB, 요청 전체 1 GB로 제한됩니다. 분석은 동시에 1건만 실행하고 최대 2건까지 대기하며, 그 이상은 HTTP 429로 바로 알립니다. 제한값은 `AIPROBE_MAX_UPLOAD_FILE_BYTES`, `AIPROBE_MAX_UPLOAD_TOTAL_BYTES`, `AIPROBE_MAX_ANALYSIS_ACTIVE`, `AIPROBE_MAX_ANALYSIS_PENDING` 환경 변수로 바꿀 수 있습니다.

`POST /api/analyze` 응답의 `results` 배열은 **입력 파일별** 결과이며 각 항목에 다음이 들어갑니다.

```jsonc
{
  "file": "C:\\Music\\song.wav",
  "status": "completed",
  "parameters": { "meta": {}, "spectral": {}, "levels": {}, "stereo": {}, "transient": {}, "artifactFingerprint": [] },
  "detectors": [ { "name": "sonics", "score": 0.81, "segments": [], "modelVersion": "..." } ],
  "totalScore": 72.4,
  "confidence": 44.8,
  "conclusion": "AI 생성 흔적이 비교적 강함"
}
```

## 탐지 분석 옵션

탐지 옵션은 **탐지기 페이지**에서 바꿉니다. 설정 페이지에는 없습니다.

- 페이지 상단 스트립: Total 점수 결합 방식과 탐지기별 가중치
- 탐지기 카드 옆 톱니바퀴 아이콘: 해당 탐지기의 분석 옵션과 `Total 반영` / `평가만` 토글

저장한 값은 `detector-options.json`에 남고 **다음 분석부터** 적용됩니다. 이미 끝난 결과는 바뀌지 않습니다.

결합 방식은 이상치 제외 평균(기본), 가중 기하평균, 기하평균, 산술평균, 중앙값 중에서 고릅니다.

| 탐지기 | 바꿀 수 있는 항목 | 고정한 항목 |
|--------|-------------------|-------------|
| SONICS gamma | 최대 구간 수, 구간 간격, Top-K, 집계 방식, 임계값 | 16 kHz, 5초 구간 |
| lofcz vocoder fakeprint | 최대 분석 길이, 분석 위치, 집계 방식, 임계값 | 16 kHz, FFT 8192, 1–8 kHz |
| ArtifactNet v9.4 | 구간 수, 구간 선택, 집계 방식, 최소 유효 구간, 임계값 | 44.1 kHz, 4초 구간 |

모델 입력과 결합된 샘플레이트·FFT·주파수 대역은 바꾸지 않습니다. 팝업에서 `변경 불가`로 표시됩니다.

### ArtifactNet은 현재 `Total 반영`

ArtifactNet은 초기에는 낮은 원점수가 기하평균을 크게 누르는 문제가 있어 `평가만`으로 사용했습니다. 이후 E0001 네 곡과 90곡 앵커를 비교해 기본 집계를 `11구간/even/Top-3/정규화 끔`으로 바꾸고 현재는 Total에 반영합니다. 여전히 잠정 설정이므로 필요하면 팝업에서 `평가만`으로 바꿀 수 있습니다.

분석 결과에는 이 설정이 그대로 기록되므로 나중에 왜 그 점수가 나왔는지 확인할 수 있습니다.

```jsonc
"detectorSettings": {
  "ensemble": { "method": "robustMean", "weights": {} },
  "detectors": { "sonics": { "includedInTotal": true, "maxWindows": 24, "...": "..." } }
},
"scoreInfo": {
  "components": { "method": "detector-geometric-mean-v1", "inputs": {}, "included": ["artifactnet", "lofcz", "sonics"], "excluded": [] }
}
```

## 동작 원리

분석은 파일마다 독립적으로 돌아가며, 4단계로 나뉩니다.

### 1. 복호화 — 원본 샘플레이트 유지

`ffprobe`로 메타데이터를 읽고 `ffmpeg`로 PCM을 받습니다. **이 단계에서 리샘플링하지 않습니다.** 리샘플링은 스펙트럼 상단을 다시 쓰기 때문에, 이 도구가 모으려는 증거 자체를 지워 버립니다. 감쇠 대역(digital null)은 파일 자체의 대역 한계인지, 리샘플·코덱이 잘라낸 것인지를 구분해 보고합니다.

### 2. DSP 지표 — 설명과 디버깅용 근거

스펙트럼 기울기, rolloff 99%, 아티팩트 피크 위치, 트랜지언트, 스테레오 상관·Side/Mid, LUFS/LRA/True peak 등을 측정합니다. 이 값들은 **근거로만 제공되며 총점 계산에는 직접 들어가지 않습니다.** 이유는 명확합니다: 마스터링만으로도 LUFS가 +3.5 dB, LRA가 −3.2 LU 움직여서, 코퍼스 간 격차보다 후처리 프로필의 차이가 더 큽니다. 마스터링 강도를 AI 생성 근거로 읽으면 안 됩니다.

### 3. 학습 기반 탐지기 — 서로 다른 흔적을 독립적으로 본다

세 탐지기가 같은 종류의 신호를 보지 않습니다.

| 탐지기 | 고정 전처리 (모델 규격) | 구간 → 곡 점수 |
|--------|------------------------|-----------------|
| **SONICS** SpecTTTra gamma 5s | 16 kHz, 5초 구간, 구간별 표준편차 정규화 | 최대 24구간 중 가장 높은 3구간 평균 |
| **lofcz** vocoder fakeprint | 16 kHz, FFT 8,192/4,096, 1–8 kHz, lower-envelope 10, −45~+5 dB | 곡 앞 최대 300초를 한 번에 판정 |
| **ArtifactNet** v9.4 | 44.1 kHz 모노, 4초 구간 (STFT→sigmoid 단일 ONNX) | 균등 11구간, 최소 4구간 유효, 상위 3개 평균 (기본) |

샘플레이트·FFT·주파수 대역·고정 입력 길이는 **체크포인트가 학습된 값**입니다. 바꾸면 다른 길이의 학습 데이터로 평가하는 셈이므로 코드에 고정되어 있고, UI에서도 고정값으로만 표시됩니다. 조절 가능한 것은 구간 선택·구간 집계·판정 임계값·Total 반영 여부뿐입니다.

### 4. 점수 결합 — 한 모델이 결정하지 못하게

활성 탐지기의 원점수는 기본적으로 **이상치 제외 평균**으로 합쳐집니다. 중앙값과 크게 벗어난 탐지기를 MAD 기반 기준으로 제외한 뒤, 남은 점수를 평균합니다. 탐지기가 2개 이하이면 모두 사용합니다. 기하평균·산술평균·중앙값·가중 기하평균도 설정에서 선택할 수 있습니다.

```
Total = 100 × mean(이상치로 판정되지 않은 sᵢ)
```

이 방식은 한 탐지기의 극단값이 Total을 단독으로 결정하는 것을 줄입니다. `confidence`는 점수가 0.5에서 얼마나 떨어져 있는지와 탐지기 간 일치도를 함께 반영한 지표입니다.

ArtifactNet은 알려진 AI 음원에도 낮은 점수를 반환하는 구간이 있어 집계 방법에 따라 3탐지기 Total을 크게 바꿉니다. 현재 기본값은 E0001 네 곡 비교에서 단일 고점 의존을 줄인 **균등 11구간 + 상위 3개 평균 + 음량 정규화 끔**입니다. ArtifactNet은 현재 Total에 반영하도록 설정되어 있지만, 점수 방향은 아직 provisional이며 더 넓은 paired corpus에서 재검증해야 합니다.

### ArtifactNet 기본값 실험 결과

E0001 기준 네 곡을 SONICS와 lofcz에 ArtifactNet을 추가해 비교했습니다. 두 조건 모두 가중 기하평균을 사용했습니다.

| 음원 | 5구간 + 최댓값 | 11구간 + Top-3 평균 |
|------|----------------:|--------------------:|
| 인간 원곡 | 0.1 | **0.0** |
| E0001 AI 원곡 | **93.2** | 91.3 |
| E0001 AI 원곡 + LANDR 후처리 | 86.3 | **74.5** |
| E0001 AI 원곡 + SongYUE2 다듬기 + Mastering-1 | 84.7 | 86.4 |

11구간 + Top-3는 인간 원곡을 낮게 유지하면서 AI 원곡을 높게 분리하고, 한 구간만 선택하는 최댓값보다 이상치 영향을 줄였습니다. 후처리 두 결과의 상대 순서 원인 분석은 사용자 결정에 따라 이번 범위에서 제외했습니다. 리포트는 `reports/20260926T183136+0000-file-analysis.json`과 `reports/20260926T183327+0000-file-analysis.json`에 저장되어 있습니다.

### 90곡 anchor 교차 검증

SongYUE2의 `Mastering-1` 프리셋과 후처리 그래프를 배치 처리로 재현해, 13개 컬렉션에서 고른 인간 원곡 30개와 처리본 30개를 만들었습니다. AI는 후처리본을 섞지 않고 `F:\Music\Music-원본`에서 E/J/K 계열 원본을 각각 10개씩 균등하게 골랐습니다. 모든 파일은 ArtifactNet `11/even/Top-3/정규화 끔`과 SONICS·lofcz를 함께 사용했습니다.

| 코호트 | 개수 | 최솟값 | 중앙값 | 최댓값 |
|--------|----:|------:|------:|------:|
| 인간 원곡 | 30 | 0.0 | 0.4 | 26.6 |
| 인간 + Mastering-1 | 30 | 0.0 | 0.1 | 25.6 |
| E 계열 AI 원본 | 10 | 51.5 | 82.1 | 99.6 |
| J 계열 AI 원본 | 10 | 44.2 | 58.3 | 99.4 |
| K 계열 AI 원본 | 10 | 43.2 | 53.5 | 97.3 |

인간 원곡과 처리본의 Total 변화 중앙값은 0.0점, 절댓값 중앙값은 0.3점, 절댓값 75백분위는 1.8점이었습니다. 이 표본에서는 `Mastering-1`이 인간 음원을 AI처럼 보이게 만들지 않았습니다. 반면 50점 경계를 그대로 쓰는 원시 Total은 민감도 76.7%, 특이도 100%, balanced accuracy 88.3%였습니다(이상치 제외 평균 적용 후 재계산; 이전 평가의 43.3%/71.7%보다 크게 개선되었지만 K 계열 일부는 여전히 50점 아래로 남습니다).

class-balanced PAVA isotonic 보정은 같은 곡 pair 5-fold에서 balanced accuracy 99.2%, 가수/연도 그룹 5-fold에서도 99.2%를 냈습니다. 그러나 인간 최댓값 26.6과 AI 최솟값 43.2 사이 16.6점 구간에 표본이 거의 없어 보정 함수가 여전히 **레벨 2개로만 붕괴**합니다(간격은 이전 평가의 6.6점보다 넓어졌지만, 붕괴 자체는 재현됩니다). 분류 경계에는 유리하지만 연속적인 Total의 강도와 AI 곡 사이 순위를 모두 없애므로 런타임에는 적용하지 않았습니다. 결과와 행 단위 데이터는 `scratch/evaluations/anchor-corpus-evaluation.json` 및 `.csv`에 저장됩니다.

## 검증 방식

이 도구는 점수를 만들어 내는 것에서 끝나지 않고, **틀렸다는 게 증명되는 경우를 먼저 찾습니다.**

- **게시된 외부 규격으로 교정** — LUFS는 BS.1770-4의 997Hz / −23dBFS stereo 합성 신호로 절대 교정합니다. 자기 자신과의 일관성만으로는 필터 오류가 통과합니다.
- **디스크리미네이터는 인간 대조군에서 검증** — 검출 능력뿐 아니라 **특이도**를 봅니다. 실제로 `spectral_comb` 지표는 검출 능력·컨테이너 불변성·처리 체인 불변성을 통과한 뒤 인간 대조군에서 실패했습니다(인간 17/17곡에서 AI보다 더 강하게 발현). 마지막 게이트가 유일하게 결정적이었습니다.
- **마스터링 전후가 유일한 지상 참값** — 같은 세대의 원본/마스터 짝은 "후처리가 무엇을 바꾸는가"에 대한 유일한 지상 참값입니다.
- **랜덤 split은 마지막에야** — 코퍼스 단위 hold-out → 코퍼스 안에서 가수/연도 그룹 hold-out → 랜덤 split 순서로 봅니다. 순서를 뒤집으면 항상 좋은 수치가 나옵니다.

```powershell
scratch\build_mastering_pairs.py    # 인간 원본의 후처리 짐 생성
scratch\build_e0003_comparison.py   # E0003 기준군 비교 리포트
.venv\Scripts\pytest                 # 테스트
```

현재 상태는 **잠정(provisional)** 입니다. 이번 anchor에서도 인간 최댓값(26.6)과 AI 최솟값(43.2) 사이 구간에 표본이 거의 없어 isotonic 보정이 레벨 2개로 붕괴했습니다. 인간 오탐 후보, 더 낮은 AI 점수, 외부 생성기 코퍼스를 추가해 0–100 구간의 실제 분포가 확보될 때까지 원시 Total을 유지합니다.

### 최근 평가 요약 (2026-09-27, 이상치 제외 평균 재계산)

이번 평가는 현재 설치된 3개 탐지기(SONICS, lofcz, ArtifactNet)를 `이상치 제외 평균(robustMean)`으로 결합하고,
ArtifactNet은 `11구간 / even / Top-3 / levelNormalize=false` 조건으로 고정했다.
비교 대상은 인간 원본 30곡, 같은 곡의 SongYUE2 Mastering-1 처리본 30곡,
그리고 AI 원본 E/J/K 계열 각 10곡이다. AI 후처리본은 이번 평가에서 제외했다.

- 인간 원본 중앙값은 **0.4**, 인간 Mastering-1 중앙값은 **0.1**로 여전히 낮게 유지됐다.
- 인간 원본·Mastering-1의 최댓값은 각각 **26.6**, **25.6**으로 이전 평가(2.3)보다 크게 올랐다. `George Michael - Outside` 등 개별 오탐 후보를 확인할 필요가 있다.
- AI 원본 중앙값은 E 계열 **82.1**, J 계열 **58.3**, K 계열 **53.5**였다.
- AI 원본의 최솟값은 **43.2**였으므로, 인간 최댓값 26.6과의 분리는 유지됐지만 간격은 6.6점에서 16.6점으로 넓어졌다(방향은 개선, 절대 여유는 여전히 좁음).
- 50점 단일 임계값의 balanced accuracy는 **88.33%**로 이전 71.67%보다 크게 개선됐다(민감도 76.67%, 특이도 100%).
- isotonic 보정은 5-fold balanced accuracy가 여전히 99%대로 높았지만, 결과가 레벨 2개로 압축되는 문제는 재현되어
  연속적인 Total 순위를 보존해야 하는 현재 제품에는 적용하지 않았다.

따라서 현재 Total은 확정적인 저작자 판정이나 확률이 아니라, 여러 탐지기의 결과를
이상치 제외 평균으로 결합한 **비교용 원시 점수**다. 이번 재계산으로 AI 쪽 최솟값은 크게 올랐지만
인간 원곡 쪽에도 20점대 오탐 후보가 나타났으므로, 그 개별 파일을 먼저 확인하고 더 다양한 인간 대조군과 AI 표본을 추가한 뒤 임계값과
보정 방법을 다시 검증해야 한다. 상세 행 단위 결과는
`scratch/evaluations/anchor-corpus-evaluation.json`과 `.csv`에 저장된다.

## 프로젝트 구조

```
probe/
  app.py            FastAPI 앱, API 라우트, 정적 UI 호스팅
  cli.py            CLI 진입점 (health / score / serve)
  audioio.py        ffprobe·ffmpeg 래퍼 (원본 샘플레이트 유지)
  dsp.py            스펙트럼 지표
  loudness.py       BS.1770-4 기반 LUFS·LRA·true peak
  detectors/
    base.py         탐지기 레지스트리와 활성 상태
    sonics.py       SpecTTTra 어댑터
    lofcz.py        vocoder fakeprint 어댑터
    artifactnet.py  ONNX 어댑터
  file_analysis.py  파일별 분석과 총점 결합
  report.py         stage 비교와 체인/콘텐츠 변화 분리
web/                WebUI (index.html, app.js, styles.css)
corpus/             짝 데이터와 manifest (git 미포함)
reports/            저장된 리포트 (JSON은 git 미포함)
memory-bank/        프로젝트 규칙·패턴·장애 기록
```

## 라이선스

코드 라이선스는 각 탐지지가 별도로 관리합니다. `models/artifactnet/README.md`의 ArtifactNet 조건(CC BY-NC 4.0, 특허 출원 중)이 특히 엄격합니다.
