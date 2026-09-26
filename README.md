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
| `GET` | `/api/resources` | CPU·RAM·GPU 사용량 |

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

결합 방식은 기하평균(기본), 산술평균, 중앙값, 가중 기하평균 중에서 고릅니다.

| 탐지기 | 바꿀 수 있는 항목 | 고정한 항목 |
|--------|-------------------|-------------|
| SONICS gamma | 최대 구간 수, 구간 간격, Top-K, 집계 방식, 임계값 | 16 kHz, 5초 구간 |
| lofcz vocoder fakeprint | 최대 분석 길이, 분석 위치, 집계 방식, 임계값 | 16 kHz, FFT 8192, 1–8 kHz |
| ArtifactNet v9.4 | 구간 수, 구간 선택, 집계 방식, 최소 유효 구간, 임계값 | 44.1 kHz, 4초 구간 |

모델 입력과 결합된 샘플레이트·FFT·주파수 대역은 바꾸지 않습니다. 팝업에서 `변경 불가`로 표시됩니다.

### ArtifactNet은 기본이 `평가만`

ArtifactNet 원점수는 다른 탐지기보다 자릿수가 작습니다. E0001·E0002에서 집계법과 가중치를 바꿔도 방향성이 고쳐지지 않아, 근사 0인 값을 기하평균에 넣어 Human 대조군 점수까지 같이 눌러버리는 일이 생겼습니다. 그래서 산출은 하되 Total에는 넣지 않는 `평가만`이 기본입니다. 필요하면 팝업에서 `Total 반영`으로 바꿀 수 있습니다.

분석 결과에는 이 설정이 그대로 기록되므로 나중에 왜 그 점수가 나왔는지 확인할 수 있습니다.

```jsonc
"detectorSettings": {
  "ensemble": { "method": "geometric", "weights": {} },
  "detectors": { "sonics": { "includedInTotal": true, "maxWindows": 24, "...": "..." } }
},
"scoreInfo": {
  "components": { "method": "detector-geometric-mean-v1", "inputs": {}, "included": ["sonics", "lofcz"], "excluded": ["artifactnet"] }
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
| **ArtifactNet** v9.4 | 44.1 kHz 모노, 4초 구간 (STFT→sigmoid 단일 ONNX) | 균등 7구간, 최소 4구간 유효, 중앙값 |

샘플레이트·FFT·주파수 대역·고정 입력 길이는 **체크포인트가 학습된 값**입니다. 바꾸면 다른 길이의 학습 데이터로 평가하는 셈이므로 코드에 고정되어 있고, UI에서도 고정값으로만 표시됩니다. 조절 가능한 것은 구간 선택·구간 집계·판정 임계값·Total 반영 여부뿐입니다.

### 4. 점수 결합 — 한 모델이 결정하지 못하게

활성 탐지기의 원점수는 동일 가중 **기하평균**으로 합쳐집니다.

```
Total = 100 × (s₁ · s₂ · … · sₙ)^(1/n)
```

기하평균은 여러 모델이 서로 동의할 때만 점수가 올라갑니다. 포화값(1.0) 하나가 전체를 끌어올리는 것도, 0에 가까운 값 하나가 전체를 끌어내리는 것도 막습니다. `confidence`는 점수가 0.5에서 얼마나 떨어져 있는지와 탐지기 간 일치도를 함께 반영한 지표입니다.

ArtifactNet은 알려진 AI 음원에도 0.0022~0.1088을 반환해 3탐지기 기하평 평균을 크게 낮췄습니다. 이 방향성 문제는 E0001/E0002 기준군에서 평균·최댓값·Top-3 집계로도 고쳐지지 않아, **기본값에서 Total 반영을 끄고 평가 전용으로 두었습니다.** 더 넓은 paired corpus에서 재검증하기 전까지는 총점에 넣지 않습니다.

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

현재 상태는 **잠정(provisional)** 입니다. 총점은 paired anchor 분포가 안정되면 isotonic regression 같은 단조 보정을 적용할 예정이며, 그전까지는 코퍼스간 비교용으로만 읽어야 합니다.

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
