# Active Context

## Current Focus

- Wave 37 완료: 분석 이력 배지가 실제 보관 개수보다 컸던 원인을 찾아 고쳤다(사용자 제보: "156은 현재 남은 개수여야지 누적 실행 횟수가 아니다").
- 원인: `load_history()`가 `REPORTS_DIR`(영구 저장 리포트)와 `HISTORY_DIR`(historyLimit로 트림되는 자동 사본)를 값 기반으로 합쳐 중복 제거했는데, HISTORY_DIR 사본이 `trim_history()`로 지워지면 REPORTS_DIR 원본이 다음 로드부터 "새 항목"처럼 부활했다. 실측: historyLimit 300, 배지 156, 실제 유효 historyItemId는 100개뿐(좀비 56개).
- 고침: `load_history()`/`change_signature()`를 `HISTORY_DIR` 단일 소스로 변경. `REPORTS_DIR`(저장된 리포트)는 `/api/reports`가 이미 독립적으로 완전히 다루므로 기능 손실 없음. 서버 재시작 후 배지 156→100 확인, 테스트 127개 통과.
- "Max 분석 이력 초과 시 오래된 것부터 삭제"는 `trim_history()`(저장 후)와 `PUT /api/settings`(한도 낮출 때 즉시)에 이미 구현돼 있었다 — 배지 버그가 이 동작이 작동 중인 걸 가려서 안 보였을 뿐.
- Wave 36: 코드 리뷰 Round 7 — `start.bat`/`stop.bat`의 포트 처리 결함(R-4, Windows `SO_REUSEADDR`로 새 인스턴스가 살아있는 서버 포트를 빼앗는 문제) 수정, `stop.bat`을 `Win32_Process` 조회 기반으로 교체.
- 리뷰 최종 집계: 높음 15/15 해결, 중간 21 해결 + 2 잔존(M-20 설계, M-23 `nan_to_num` 무음 치환) + 1 기각(M-21 오독), 낮음 64 미착수.
- 판정은 항상 함수 본문을 읽은 뒤에 내린다 — 패턴 grep만으로 "미해결"이라 오판한 사례가 세 번 반복 기록됨.
- `pollHistorySignature`의 2.5초 `setInterval`을 제거하고 `visibilitychange`(탭 포커스 복귀)만 남김. 같은 탭 안의 분석/삭제/즐겨찾기/설정 저장은 원래부터 즉시 `loadHistory()`를 부르므로 영향 없음 — 잃는 건 "이 탭을 계속 보고 있는 동안 CLI/다른 탭에서 생긴 변화"의 실시간 반영뿐, 사용자가 그 트레이드오프를 확인하고 선택함.

## 남은 작업

- 중간 2건 처리: M-23(`nan_to_num` 무음 치환을 플래그로 표시), M-20(외부 바인딩 전 인증·루트 구속)
- 낮음/정적 64건 미착수. `dsp.py:48`의 `BRICKWALL_DB_PER_KHZ` 미사용이 포함
- `C:\Claude\SongYUE2` 실제 health 폴링 경로 미조사
- `errors_report.md`의 E-1(업로드 파일명 매핑, 높음) 등 E-1~E-8 미착수

<!--
규칙:
- 최근 작업 10개만 유지 (이전 작업은 추적 금지)
- 완료된 Wave 지식은 knowledge/으로 flush 해서 이동
- 다음 세션에 "무엇 했고, 뭐가 남았나" 스냅샷 원칙
-->
