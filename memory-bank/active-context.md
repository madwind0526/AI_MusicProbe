# Active Context

## Current Focus

- Wave 36 완료: 코드 리뷰 Round 7에서 `start.bat`/`stop.bat`의 포트 처리 결함(R-4)을 수정하고 실환경 검증했다.
- 서버를 실행한 채 `start.bat`을 다시 실행하면 Windows `SO_REUSEADDR` 때문에 새 인스턴스가 살아남은 인스턴스의 8792 포트를 빼앗는다. 서버는 정상이고 로그에도 오류가 없다.
- `stop.bat`을 `Win32_Process` 조회로 바꿔 `python.exe` + 명령행 `probe.app` 프로세스를 전부 종료하고 10초까지 포트 해제를 기다린다. `start.bat`은 시작 전에 `stop.bat`을 호출한다.
- 유령 서버 3개(2,317 MB)를 회수했고, 같은 포트를 쓰는 무관한 ComfyUI 서버(8190)는 생존했다. 재시작 후 신규 인스턴스만 남고 `/health` OK·탐지자 4개 active를 확인했다.
- 리뷰 최종 집계: 높음 15/15 해결, 중간 21 해결 + 2 잔존(M-20 설계, M-23 `nan_to_num` 무음 치환) + 1 기각(M-21 오독), 낮음 64 미착수. 테스트 127개 통과.
- M-8·M-17을 패턴 grep만 보고 이미 해결된 상태를 "미해결"로 잘못 보고했다. 세 번째 반복이므로 판정은 항상 함수 본문을 읽은 뒤에 내린다.
- `codereview.md`·`README.md`·`progress.md`·`revision.md`와 memory-bank을 현재 상태로 동기화했다.

## 남은 작업

- 중간 2건 처리: M-23(`nan_to_num` 무음 치환을 플래그로 표시), M-20(외부 바인딩 전 인증·루트 구속)
- 낮음/정적 64건 미착수. `dsp.py:48`의 `BRICKWALL_DB_PER_KHZ` 미사용이 포함
- `C:\Claude\SongYUE2` 실제 health 폴링 경로 미조사
- `scratch/run_flows.py`의 `\u` escape 버그로 4개 파일 flow 재실행 미완료

<!--
규칙:
- 최근 작업 10개만 유지 (이전 작업은 추적 금지)
- 완료된 Wave 지식은 knowledge/으로 flush 해서 이동
- 다음 세션에 "무엇 했고, 뭐가 남았나" 스냅샷 원칙
-->
