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
- [x] 테스트 16개 통과, Python compile, JavaScript syntax 검사
- [x] 실행 문서와 `start.bat`

## 다음 P1

- [ ] 설정 화면에 탐지기별 분석 옵션 추가
  - [ ] SONICS: 최대 분석 구간 수, 구간 간격, Top-K 개수, 집계 방법, 판정 임계값
  - [ ] lofcz: 최대 분석 길이, 분석 위치, 집계 방법, 판정 임계값
  - [ ] ArtifactNet: 구간 수, 최소 유효 구간 수, 집계 방법, 판정 임계값
  - [ ] 각 옵션에 기본값·단위·간단한 설명 표시
  - [ ] 모델 입력과 결합된 샘플레이트·FFT·주파수 대역은 고정값으로 안내
- [ ] 탐지기별 `Total 반영`과 `평가만` 선택 추가
- [ ] Total 점수 결합 방식 선택 추가
  - [ ] 기하평균 (현재 기본값)
  - [ ] 산술평균
  - [ ] 중앙값
  - [ ] 가중 기하평균과 탐지기별 가중치
- [ ] 설정값을 `settings.json`에 저장하고 다음 분석부터 적용
- [ ] 탐지기 옵션별 원점수·집계법·임계값을 분석 결과와 리포트에 기록
- [ ] 기본값으로 기존 E0001/E0002/E0003 결과를 재분석해 회귀 검증
- [ ] 탐지기별 옵션 조합을 paired corpus와 hold-out corpus에서 비교
- [ ] ArtifactNet을 Total에 포함할 때와 평가 전용으로 둘 때의 결과를 나란히 검증

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
