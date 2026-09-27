# Active Context

## Current Focus

- `codereview.md`의 높은 중요도 15건을 수정하고, `recompute_totals.py`의 의도된 덮어쓰기에 dry-run·검증·가중치 보존·원자 저장을 적용함.
- 이력 경로 이탈 차단, history 원자 저장, True Peak·BS.1770·MAD=0 계산을 수정함.
- ArtifactNet 중복 구간, 0 가중치 우회, 업로드 이름 순서, 설정 부분 갱신 문제를 수정함.
- 외부 도구 timeout, 손상 리포트 400 응답, 프론트의 중복·오래된 요청 차단을 적용함.
- 테스트의 ignored `scratch/` 의존을 `probe/evaluation.py`로 이동함.
- 앱 시작·분석 저장·이력/리포트 삭제 시 저장 결과에서 참조하지 않는 scratch 업로드와 비주얼 캐시를 정리함.
- 참조 중인 업로드 원본은 이력 상세 재생을 위해 유지하고, 중단된 새 업로드는 다음 요청에서 1시간 유예 후 정리함.
- BS.1770 loudness 모듈을 실제 DSP `levels`에 연결하고 UI 키 `integratedLufs`·`truePeakDbtp`·`crestDb`를 통일함.
- 실제 음원에서 LUFS-I -12.97, True Peak 0.31 dBTP, Crest 15.6 dB, LRA 17.37 응답을 확인함.
- 검증: 90 tests passed, compileall 및 JS 문법 검사 통과.

<!--
규칙:
- 최근 작업 10개만 유지 (이전 작업은 추적 금지)
- 완료된 Wave 지식은 knowledge/으로 flush 해서 이동
- 다음 세션에 "무엇 했고, 뭐가 남았나" 스냅샷 원칙
-->
