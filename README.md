# AI Music Probe

음원 파일마다 AI 생성 흔적을 분석해 파라미터, 탐지기 근거, `totalScore`(0–100)를 반환하는 로컬 앱입니다. SongYUE2와 독립적으로 실행되며, 단일 파일·여러 파일·폴더 입력을 지원합니다.

## 실행

```powershell
.\start.bat
```

브라우저에서 `http://127.0.0.1:8792`를 엽니다. OpenAPI 문서는 `http://127.0.0.1:8792/api/docs`에 있습니다.

## API

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

업로드는 `POST /api/analyze/upload`에 `files` multipart 필드를 반복해서 전달합니다. 응답의 `results` 배열은 입력 파일별 결과이며 각 항목에 `parameters`, `detectors`, `totalScore`, `confidence`, `conclusion`이 들어갑니다.

WebUI의 내장 탐색기는 `GET /api/files/browse`, 누적 분석 이력은 `GET /api/history`, 상단 CPU·RAM·GPU 표시는 `GET /api/resources`를 사용합니다. 이력 카드의 상세 창에서는 원본 재생과 FFmpeg로 생성한 파형·스펙트로그램을 확인할 수 있습니다.

`totalScore`는 현재 공개 탐지기들의 원시 신호를 결합한 비교 점수입니다. 확률이나 인간/AI의 법적 판정값이 아니며, 충분한 짝 데이터가 쌓이면 비선형 보정을 적용할 예정입니다.

## 현재 탐지기

- ArtifactNet v9.4: 44.1 kHz 모노 4초 구간의 코덱 잔차를 분석하고 중앙값으로 곡 점수를 만듭니다.
- SONICS / SpecTTTra gamma 5s: 5초 구간을 여러 지점에서 분석합니다.
- lofcz vocoder fakeprint: 보코더 재구성 흔적을 분석합니다.

한 탐지기의 높은 값만으로 총점을 밀어 올리지 않도록 활성 모델들의 일치도를 반영합니다. DSP 파라미터는 설명과 디버깅에 제공하며 총점의 직접 근거로 쓰지 않습니다.

ArtifactNet 공개 ONNX는 CC BY-NC 4.0의 연구·개인 평가용 모델이며 특허 라이선스를 포함하지 않습니다. 상업 제품이나 유료 API에는 별도 라이선스 없이 사용할 수 없습니다.

## 인간 원본 Mastering-1 짝 데이터

`scratch/build_mastering_pairs.py`는 SongYUE2의 현재 `Setting/PostProcess/Mastering-1.json`을 직접 읽어 인간 원본 세 곡의 후처리 짝을 만듭니다. 출력과 프리셋 해시는 `corpus/human_mastering1/manifest.json`에 기록됩니다.
