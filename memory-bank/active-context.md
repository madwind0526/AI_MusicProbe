# Active Context

## Current Focus

- ArtifactNet 기본값을 `11구간/even/Top-3/정규화 끔`으로 적용하고 설정 파일·README·progress·revision·todo를 동기화.
- 음원 비교 팝업에 두 파일의 대역별 dB 변화량과 RMS·peak·True peak 요약 패널을 복원하고 API·DOM 검증.
- E0001 4개 기준 음원을 `5구간+최댓값`과 `11구간+Top-3`로 각각 배치 분석하고 설정별 리포트 저장.
- `11구간+Top-3`는 인간 0.0, AI 원곡 91.3, LANDR 74.5, SongYUE2 다듬기+Mastering-1 86.4.
- 현재 비교에서는 `11구간+Top-3`를 ArtifactNet의 우선 실험 후보로 판단하되 후처리 상대 순서는 추가 기준곡으로 검증 필요.
- E0001-1 AI 원곡의 ArtifactNet 옵션 전 조합을 분할 실험하고 2개 탐지기 Total 94.0과 비교.
- 가장 가까운 조합은 5구간·곡 전체 고르기·최댓값·정규화 끄기이며 실제 API Total 93.2로 재현.
- 최댓값 조합은 단일 고점 구간에 의존하므로 E0002/E0003·인간 원곡 교차 검증 전 기본값으로 채택하지 않음.
- ArtifactNet `levelNormalize`가 API 요청 모델에서 누락되어 UI 값이 버려지던 문제를 수정하고 회귀 테스트 추가.
- 탐지기 설정 팝업의 모델 고정값 라벨과 값을 Y축 중앙 정렬하고 ArtifactNet 화면에서 확인.

<!--
규칙:
- 최근 작업 10개만 유지 (이전 작업은 추적 금지)
- 완료된 Wave 지식은 knowledge/으로 flush 해서 이동
- 다음 세션에 "무엇 했고, 뭐가 남았나" 스냅샷 원칙
-->
