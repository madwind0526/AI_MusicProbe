# TODO — AI Music Probe

최종 갱신: 2026-09-27

## 완료

- [x] 독립 FastAPI 앱과 보라색 SongYUE2 스타일 WebUI
- [x] 단일 파일·여러 파일·폴더 입력과 파일별 결과
- [x] `POST /api/analyze` 경로 API, `POST /api/analyze/upload` 업로드 API
- [x] SONICS gamma 5s 구간 탐지기 연결
- [x] lofcz vocoder fakeprint 탐지기 연결
- [x] 탐지기 원시 출력·구간 타임라인·모델 버전 보존
- [x] 0–100 provisional ensemble 점수와 신뢰 지표
- [x] SongYUE2 Mastering-1 기반 인간 원본 3쌍과 manifest 생성
- [x] 인간 원본, AI 원본, AI+후처리 1차 동작 검증
- [x] 브라우저에서 복수 경로 → 파일별 카드 결과 회귀 검증
- [x] 초기 테스트 16개 통과, Python compile, JavaScript syntax 검사
- [x] 실행 문서와 `start.bat`
- [x] README에 프로젝트 개요·사용법·동작 원리 정리

## 완료 — 탐지기별 분석 옵션 (2026-09-27)

설정은 기존 설정 페이지가 아니라 **탐지기 페이지**에 넣었다. 전역 Total 결합 방식은 탐지기 페이지 상단 스트립, 탐지별 항목은 카드 옆 설정 아이콘 팝업.

- [x] SONICS: 최대 분석 구간 수, 구간 간격, Top-K 개수, 집계 방법, 판정 임계값
- [x] lofcz: 최대 분석 길이, 분석 위치, 집계 방법, 판정 임계값
- [x] ArtifactNet: 구간 수, 구간 선택, 집계 방법, 최소 유효 구간 수, 판정 임계값
- [x] 각 옵션에 기본값·단위·간단한 설명 표시
- [x] 모델 입력과 결합된 샘플레이트·FFT·주파수 대역은 고정값으로 안내 (`locked` + `lockedNote`)
- [x] 탐지기별 `Total 반영`과 `평가만` 선택 추가
- [x] Total 점수 결합 방식 선택 추가
  - [x] 기하평균 (기본값)
  - [x] 산술평균
  - [x] 중앙값
  - [x] 가중 기하평균과 탐지기별 가중치
- [x] 설정값을 `detector-options.json`에 저장하고 다음 분석부터 적용
- [x] 탐지기 옵션별 원점수·집계법·임계값을 분석 결과와 리포트에 기록
- [x] 기본값으로 기존 E0001/E0002/E0003 결과를 재분석해 회귀 검증
- [x] ArtifactNet을 Total에 포함할 때와 평가 전용으로 둘 때의 결과를 나란히 검증
- [x] 테스트 67개 통과, Python compile, JavaScript syntax 검사, API smoke test
- [x] 부분 설정 저장 시 다른 탐지기 설정 유지
- [x] 가중 기하평균의 모든 Total 가중치가 0이면 UI와 API에서 저장 거부
- [x] 가중치 0 탐지기를 Total·신뢰 지표 계산에서 함께 제외
- [x] ArtifactNet 공식 입력을 기본값으로 복구하고 음량 정규화는 실험 옵션으로 분리
- [x] ArtifactNet 기본값을 11구간·곡 전체 고르기·Top-3 평균·음량 정규화 끔으로 변경
- [x] E0001 네 곡에서 5구간+최댓값과 11구간+Top-3 결과를 비교하고 리포트 저장
- [x] 동일 파일 반복 분석 이력의 좋아요 상태를 독립적으로 저장
- [x] 분석 이력 변경 확인 시 JSON 전체 재파싱 제거
- [x] 동일 음원 반복 분석 시 새 결과와 리포트에 `(1)`, `(2)` 순번을 붙여 기존 결과 보존
- [x] 저장 리포트에 생성 날짜·시간, 상세보기, 삭제 버튼과 시간·제목·용량 정렬 추가
- [x] 빈 분석 이력의 불필요한 아이콘 제거와 X/Y 중앙 정렬
- [x] E0001 4종을 SONICS+lofcz 및 ArtifactNet 포함 구성으로 각각 비교
- [x] 같은 실행의 리포트 원본과 이력 사본이 분석 이력에 중복 표시되는 문제 수정
- [x] 탐지기 위에 독립 음원 비교 도구 추가: 2개 음원, 공통 seek, 전환 재생, 파형·스펙트로그램
- [x] 음원 비교 팝업에 주파수 대역별 변화량과 전체 음량·peak 변화 표시
- [x] 리포트 목록·상세 팝업과 음원 분석·분석 이력의 작은 안내 글꼴 확대

## 다음 P1

- [ ] 11구간+Top-3를 E0002·E0003·다양한 인간 원곡 paired corpus에서 교차 검증
- [x] UI 검증: 브라우저에서 옵션 표시·결합 저장 버튼·모든 가중치 0 오류·기존 화면 진입 확인
- [x] 실제 음원으로 설정 저장 후 다음 분석 결과 반영 확인

- [ ] 인간 Mastering-1 짝을 장르·시대가 다른 30곡 이상으로 확장
- [ ] AI 원본과 AI+후처리 짝을 30쌍 이상 분석해 분포 저장
- [ ] paired anchor 분포가 안정되면 isotonic regression 등 monotonic calibration 적용
- [ ] calibration 전후 코퍼스 hold-out과 가수/연도 group hold-out 비교
- [x] ArtifactNet v9.4를 연구 기준선으로 연결하고 CC BY-NC/특허 제약을 UI와 문서에 표시
- [ ] WebUI에서 detector 구간 타임라인 시각화
- [ ] JSON/CSV 결과 내보내기
- [ ] 업로드 파일 총용량·동시 분석 작업 큐 제한

## 계속 금지

- [x] 고정 5단계 라벨 또는 사전 정의 점수 구간
- [x] 선형 점수라고 가정
- [x] LUFS, LRA, true peak, side/mid, tilt, rolloff, sample rate, codec, duration을 생성 주체 점수에 직접 사용
- [x] mastering 강도를 AI 생성 흔적으로 간주
- [x] 랜덤 split만으로 정확도를 주장
