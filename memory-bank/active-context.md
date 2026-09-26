# Active Context

## Current Focus

- 다음 작업: paired corpus와 hold-out corpus에서 탐지기별 옵션 조합 비교.
- 탐지 분석 옵션 구현 완료: 카드 옆 톱니바퀴 팝업 + 탐지기 페이지 상단 결합 방식 스트립.
- 설정은 `detector-options.json`에 저장, 다음 분석부터 적용. git ignore 대상.
- 결합 방식 4가지: 기하평균(기본), 산술평균, 중앙값, 가중 기하평균.
- ArtifactNet 기본 `평가만`. 원점수 자릿수가 작아 기하평균에서 대조군까지 누락시키는 문제 때문.
- 모델 고정값(샘플레이트·FFT·주파수 대역)은 `locked`로 팝업에 읽기 전용 표시.
- 분석 리포트에 `detectorSettings` 스냅샷과 `scoreInfo.components`(included/excluded/weights) 기록.
- 기본값 회귀 재검증 완료: E0001 94.0/85.4/89.6, E0002 99.6/99.4/99.5, E0003 78.4/76.7/71.5, 인간 대조군 0.1.
- 테스트 55개 통과. `pytest` + compileall + `node --check` + API smoke test 확인.
- 남은 UI 검증: 실제 브라우저에서 팝업 열기·저장·다음 분석 반영 확인.
- `gh` 미설치. Git push는 자격 증명으로 정상 동작.

<!--
규칙:
- 최근 작업 10개만 유지 (이전 작업은 추적 금지)
- 완료된 Wave 지식은 knowledge/으로 flush 해서 이동
- 다음 세션에 "무엇 했고, 뭐가 남았나" 스냅샷 원칙
-->
