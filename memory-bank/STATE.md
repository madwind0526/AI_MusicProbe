# State

## Current Wave

- **Wave:** 14
- **Status:** Done — 탐지기별 분석 옵션과 Total 결합 방식을 탐지기 페이지에 구현
- **Cache Status:** CLEAN
- **Last Checkpoint:** 2026-09-27 — 탐지기 카드 설정 팝업, 4가지 결합 방식, `detector-options.json` 저장, E0001/E0002/E0003 회귀 재검증

## Wave History

| Wave | 작업 요약 | 상태 |
|------|-----------|------|
| 1 | 프로젝트 초기화, DSP/파형 분석 구현, FastAPI + UI | Done |
| 2 | LUFS 교정, mastering 대조군 검증, comb 필터, 0-100 점수 실험·문서화 | Done |
| 3 | 파일일괄 API, SONICS+lofcz ensemble, 보라색 WebUI, 3쌍 완성·검증 | Done |
| 4 | E0001 LANDR master ↔ SongYUE2 AI 반음混响+Mastering-1 비교 | Done |
| 5 | 배경색·아이카드·테두리 각 inadequacy 원인과 자문 모니터링·기록 개선 | Done |
| 6 | SongYUE2波形·스펙트로그램 대칭축, 탐색 seek 강조, 설정 탭 분리 | Done |
| 7 | 출력 좋음·나쁨 결론 분리, 고립 段落 보호 | Done |
| 8 | ArtifactNet v9.4 배치·리더노트 출처·라이선스, Total 계산에서 제외 | Done |
| 9 | E0003 4종 비교, 결과 활용 문서, 활성화 탐지/가중치 표시 | Done |
| 10 | ArtifactNet 제외 E0003 재평가, 카드 최소 크기·설정 문구 축소 | Done |
| 11 | 결과 카드 320px 고정 사각형, 14px 그리드 간격, 겹침 제거, 설정 복원 | Done |
| 12 | 카드 크기 설정, 고정/가변 모드, 기존 설정 백업 자동 복구 | Done |
| 13 | ArtifactNet·SONICS·lofcz 조절 가능 파라미터와 방향성 영향 조사 | Done |
| 14 | 탐지기별 옵션 팝업, Total 반영/평가만, 4가지 결합 방식, 회귀 재검증 | Done |

## Session Notes

- `POST /api/analyze`: 로컬 파일·폴더, `POST /api/analyze/upload`: 브라우저 업로드
- 총점은 provisional이며 paired corpus 확보 후 monotonic calibration 예정.
- 탐지 분석 옵션은 설정 페이지가 아니라 **탐지기 페이지**에 있다. 카드 옆 톱니바퀴 팝업 + 상단 결합 방식 스트립.
- 설정은 `detector-options.json`(git ignore)에 저장되고 다음 분석부터 적용된다.
- ArtifactNet 기본은 `평가만`. E0001/E0002에서 집계법·가중치를 바꿔도 방향성이 고쳐지지 않았다.
- 기본값 회귀 결과: E0001 원본 94.0 / LANDR 85.4 / 반음混响+Mastering-1 89.6, E0002 99.6 / 99.4 / 99.5, E0003 78.4 / 76.7 / 71.5. 인간 대조군 0.1.
- 브라우저 별제 경로 분석과 파일별 결과 카드 표시는 확인 완료.
