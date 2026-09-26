# State

## Current Wave

- **Wave:** 13
- **Status:** Done — detector runtime and aggregation parameter audit
- **Cache Status:** CLEAN
- **Last Checkpoint:** 2026-09-27 — 탐지기별 고정 전처리와 조절 가능한 구간·집계·판정·성능 값을 구분

## Wave History

| Wave | 작업 내용 | 상태 |
|------|-----------|------|
| 1 | 프로젝트 초기화, DSP/오디오 분석기 구현, FastAPI + UI | Done |
| 2 | LUFS 교정, mastering/대조군 검증, comb 폐기, Y: 코퍼스 추가, 0-100 점수 실험 및 문서화 | Done |
| 3 | 파일별 API, SONICS+lofcz ensemble, 보라색 WebUI, 인간 Mastering-1 3쌍 생성·검증 | Done |
| 4 | E0001 LANDR master와 SongYUE2 AI 곡 다듬기+Mastering-1 비교 | Done |
| 5 | 내장 탐색기·이력 카드·상세 시각화·자원 모니터·8개 기준 음원 | Done |
| 6 | SongYUE2 파형·스펙트로그램 축/스타일, 재생 seek 강조, 설정 화면 | Done |
| 7 | 이력 좋아요·좋아요 우선 정렬·보관 제한 보호 | Done |
| 8 | ArtifactNet v9.4 설치·어댑터·8곡 기준군 평가·Total 안전 제외 | Done |
| 9 | E0003 4곡 평가·결과별 적용 탐지기 수·활성/설치/전체 표시 | Done |
| 10 | ArtifactNet 제외 E0003 재평가·카드 최소 크기·판정 문구 단축 | Done |
| 11 | 이력 카드 320px 고정 정사각형·14px 그리드 간격·겹침 회귀 수정 | Done |
| 12 | 카드 크기 설정·고정/가변 모드·기존 내부 스타일 복구 | Done |
| 13 | ArtifactNet·SONICS·lofcz 조절 가능 파라미터와 앙상블 영향 조사 | Done |

## Session Notes

- `POST /api/analyze`: 로컬 파일·폴더, `POST /api/analyze/upload`: 다중 업로드.
- 총점은 provisional이며 paired corpus 확장 후 monotonic calibration 예정.
- 3개 인간 Mastering-1 짝에서 totalScore 변화 없음. 생성 흔적과 mastering 흔적을 분리해야 함.
- 브라우저 실제 경로 분석과 파일별 결과 카드 표시 확인.
