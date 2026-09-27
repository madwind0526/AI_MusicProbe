# State

## Current Wave

- **Wave:** 33
- **Status:** Done — BS.1770 loudness 프로덕션 배선과 UI 키 통일
- **Cache Status:** CLEAN
- **Last Checkpoint:** 2026-09-27 — 실제 음원 levels 확인, 90 tests passed, compileall·JS 문법 검사 통과

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
| 15 | 코드 리뷰 수정: 0 가중치 검증, 부분 저장, 신뢰 지표, ArtifactNet 입력, 이력 식별·폴링 | Done |
| 16 | 동일 음원 반복 분석의 이력 표시명과 리포트 파일 덮어쓰기 방지 | Done |
| 17 | 리포트 생성 시각·삭제·정렬 UI와 빈 이력 아이콘 정리 | Done |
| 18 | 빈 분석 이력 안내를 카드 영역의 가로·세로 중앙에 정렬 | Done |
| 19 | E0001 4종을 2/3 탐지기로 비교하고 같은 실행의 리포트·이력 사본 중복 제거 | Done |
| 20 | SongYUE2 음원 비교를 독립 모듈로 이식하고 리포트·분석·이력 글꼴 확대 | Done |
| 21 | 탐지기 설정 팝업의 모델 고정값 라벨·값 Y축 중앙 정렬 | Done |
| 22 | E0001 ArtifactNet 옵션 전 조합 분할 실험, levelNormalize API 누락 수정 | Done |
| 23 | E0001 4개 기준 음원으로 ArtifactNet 5/max와 11/top-3 비교 | Done |
| 24 | ArtifactNet 11/even/top-3 기본값 적용 및 실험 문서 동기화 | Done |
| 25 | 음원 비교 대역별 변화량 패널과 비교 API 복원 | Done |
| 26 | 상세 보기 상단 탐지기별 점수표, 미사용·미설치 상태 구분 | Done |
| 27 | E/J/K 균형 90곡 평가, 업로드·대기열 제한, 진행률·내보내기·sticky 헤더 | Done |
| 28 | 설정의 1–5구간 제목과 범위 텍스트 중앙 정렬 | Done |
| 29 | 구간 제목·첫 숫자 시작점 정렬, 왼쪽 작업 현황 Box와 yy/zz 상태 연결 | Done |
| 30 | favicon 추가, SONICS `중앙값(기본)` 라벨, ensemble robustMean 확정 후 90곡 anchor 재계산·README 갱신 | Done |
| 31 | 코드 리뷰: 경로 보안·측정 정확도·원자 저장·설정/업로드/프론트 경합 수정 | Done |
| 32 | 앱 시작과 저장/삭제 후 참조되지 않는 scratch 업로드·비주얼 캐시 정리 | Done |
| 33 | BS.1770 loudness 계산을 실제 DSP/API/UI에 연결 | Done |

## Session Notes

- `POST /api/analyze`: 로컬 파일·폴더, `POST /api/analyze/upload`: 브라우저 업로드
- 총점은 provisional이며 paired corpus 확보 후 monotonic calibration 예정.
- 탐지 분석 옵션은 설정 페이지가 아니라 **탐지기 페이지**에 있다. 카드 옆 톱니바퀴 팝업 + 상단 결합 방식 스트립.
- 설정은 `detector-options.json`(git ignore)에 저장되고 다음 분석부터 적용된다.
- ArtifactNet 기본은 `11구간/even/Top-3/정규화 끔`이며 Total 반영 상태다. 점수 방향은 provisional이라 paired corpus 추가 검증이 필요하다.
- E0001에서 ArtifactNet 5구간·전체 고르기·최댓값·정규화 끄기는 3탐지기 Total 93.2로 2탐지기 94.0에 가장 가깝지만 단일 구간 고점에 의존한다.
- E0001 4종 비교에서는 11구간·Top-3가 인간 0.0/AI 원곡 91.3을 유지하며 최댓값의 단일 이상치 의존을 줄여 우선 실험 후보가 되었다.
- 기본값 회귀 결과: E0001 원본 94.0 / LANDR 85.4 / 반음混响+Mastering-1 89.6, E0002 99.6 / 99.4 / 99.5, E0003 78.4 / 76.7 / 71.5. 인간 대조군 0.1.
- 브라우저 별제 경로 분석과 파일별 결과 카드 표시는 확인 완료.
- 가중 기하평균은 Total 대상 가중치가 모두 0이면 저장하지 않고 오류를 표시한다.
- 동일 음원을 다시 분석하면 새 항목에 `(1)`, `(2)`를 붙이고 원본 파일 경로는 유지한다.
- 리포트 목록은 생성 시각을 표시하며 시간·제목·용량으로 정렬하고 개별 삭제할 수 있다.
- 배치 분석 1회당 리포트 1개가 생성되고 그 안에 파일별 결과가 들어간다. 이력은 파일별 카드로 표시한다.
- 음원 비교는 AI Music Probe 내부 모듈이며 SongYUE2 실행 파일이나 소스 경로를 런타임에 참조하지 않는다.
- ensemble method 기본값은 `robustMean`(이상치 제외 평균). n=3에서 median이 항상 가운데 값이라, 셋이 서로 고르게 떨어져 있으면(예: 0.0/20.8/99.8) MAD 컷오프(3.5)를 아무도 못 넘어 전원 평균으로 떨어질 수 있다 — 버그 아님, 사용자 확인 후 임계값 유지로 결정.
- anchor 코퍼스(90곡)를 재계산할 땐 `scratch/evaluate_anchor_corpus.py`의 통계 함수를 재사용하되 `analyze_batch`(HTTP `save:true`) 대신 `probe.file_analysis.analyze_files`를 직접 호출한다 — 그래야 실 분석 이력(`historyLimit` 트림)을 건드리지 않는다.
