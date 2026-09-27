# Active Context

## Current Focus

- `web/favicon.ico` 추가로 정적 마운트 404 제거.
- SONICS 구간 집계 선택지에 `중앙값 (기본)` 표시 추가([probe/detector_options.py:113](../probe/detector_options.py)).
- ensemble method 기본값 `robustMean`(이상치 제외 평균) 확정 후 90곡 anchor 코퍼스를 `analyze_files` 직접 호출로 재계산(실 분석 이력은 안 건드림).
- 재계산 결과: 인간 원곡 최댓값 26.6, AI 최솟값 43.2(간격 6.6→16.6), 50점 임계값 balanced accuracy 71.7%→88.3%.
- `_robust_mean`은 버그 아님 확인: n=3에서 median이 항상 가운데 값이라, 낮은 값이 median에 더 가까우면 오히려 높은 값이 이상치 후보가 됨(K0062: 0.0/20.8/99.8 → 아무도 제외 안 됨). 사용자 확인 후 임계값 변경 없이 현행 유지 결정.
- README `90곡 anchor 교차 검증` 표·요약, `scratch/evaluations/anchor-corpus-evaluation.json`·`.csv` 갱신 완료.
- 인간 원곡 쪽에도 20점대 오탐 후보(예: George Michael - Outside 26.6)가 새로 나타나 개별 확인 필요로 기록.
- 90곡 기준 평가는 인간 원본 30 / 동일 곡 Mastering-1 30 / AI 원본 E·J·K 각 10으로 구성, 후처리 AI 음원은 제외.
- isotonic 보정은 5-fold balanced accuracy 99%대지만 여전히 레벨 2개로 붕괴해 런타임 미적용 유지.
- 다음 검증 대상: 20점대로 오른 인간 오탐 후보 개별 확인, 43.2 미만 AI 외부 표본 확충.
- `errors_report.md`의 미해결 버그 E-1~E-8(특히 E-1 업로드 파일명 매핑, 높음)을 `todo.md` `## 알려진 버그`로 옮김. 아직 코드 수정은 안 함 — 다음 세션 착수 대상.

<!--
규칙:
- 최근 작업 10개만 유지 (이전 작업은 추적 금지)
- 완료된 Wave 지식은 knowledge/으로 flush 해서 이동
- 다음 세션에 "무엇 했고, 뭐가 남았나" 스냅샷 원칙
-->
