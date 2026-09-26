# Cache

> 임시 발견사항 저장소. Wave 완료 후 knowledge/ 로 flush하고 이 섹션을 비울 것.
> Sub-agent는 작업 완료 후 발견사항을 아래에 추가한다.

## Active Findings

비어 있음.

---

## 유형 분류

| 유형 | 이동 대상 |
|------|-----------|
| 코드 패턴 | `knowledge/PATTERNS.md` |
| 규칙/원칙 | `knowledge/RULES.md` |
| 버그/해결 | `knowledge/trouble-shooting.md` |

---

## Flush 방법

Wave 완료 시:
1. 각 항목을 위 표에 따라 `knowledge/` 파일로 이동
2. Active Findings 테이블 비우기
3. `STATE.md`의 Cache Status → `CLEAN`으로 업데이트

## Wave 2에서 flush한 항목

| 발견사항 | 이동된 곳 |
|----------|-----------|
| 937곡 7코퍼스 점수 실험 결과 (13.0% / 98.0%) | `knowledge/trouble-shooting.md` §0-100 human/AI |
| crest 가설 사망 (김현식 outlier) | `knowledge/trouble-shooting.md` + `PATTERNS.md` §4 |
| `onsetCount` = duration proxy | `knowledge/trouble-shooting.md` |
| 그룹 CV에서 자명한 100% | `knowledge/trouble-shooting.md` |
| 대조군 다양성이 신뢰도를 결정 | `PATTERNS.md` §4 |
| cache에서 onsetRate 파생, `--refresh` 10분 | `knowledge/trouble-shooting.md` |

## Wave 3에서 flush한 항목

| 발견사항 | 이동된 곳 |
|----------|-----------|
| detector 구간 출력·버전 보존 후 파일별 corroboration | `knowledge/PATTERNS.md` |
| totalScore를 고정 분류/선형식으로 보지 않고 paired anchor로 보정 | `knowledge/RULES.md` |
| mastering/포맷 특징은 생성 근거와 분리 | `knowledge/trouble-shooting.md` |
| 인간 Mastering-1 3쌍의 totalScore 변화 없음 | `knowledge/trouble-shooting.md` |

## Wave 4에서 flush한 항목

| 발견사항 | 이동된 곳 |
|----------|-----------|
| E0001 후처리 단계별 점수와 LANDR 비교 | `knowledge/trouble-shooting.md` |
| Audio Tools polish의 mono 44.1 kHz 정규화 함정 | `knowledge/trouble-shooting.md` |

## Wave 5에서 flush한 항목

| 발견사항 | 이동된 곳 |
|----------|-----------|
| 로컬 탐색기의 파일/폴더 모드와 드라이브 이동 패턴 | `knowledge/PATTERNS.md` |
| 경로+mtime 해시 기반 FFmpeg 파형·스펙트로그램 캐시 | `knowledge/PATTERNS.md` |
| E0002 후처리 전후 탐지 점수가 거의 같았던 사례 | `knowledge/trouble-shooting.md` |

## Wave 6에서 flush한 항목

| 발견사항 | 이동된 곳 |
|----------|-----------|
| 고정 API 경로는 FastAPI 동적 경로보다 먼저 선언해야 함 | `knowledge/trouble-shooting.md` |
| SongYUE2 SVG 파형과 축/컬러바 레이아웃 이식 | `knowledge/PATTERNS.md` |

## Wave 9에서 flush한 항목

| 발견사항 | 이동된 곳 |
|----------|-----------|
| ArtifactNet이 E0003 AI 음원에서 낮은 P(AI)를 반환해 3-detector 기하평균 Total을 낮춘 사례 | `knowledge/trouble-shooting.md` |

## Wave 10에서 flush한 항목

| 발견사항 | 이동된 곳 |
|----------|-----------|
| ArtifactNet 제외 시 E0003 AI 계열 Total이 71.5~78.4로 회복된 비교 결과 | `knowledge/trouble-shooting.md` |
| auto-fill 카드 그리드는 최소 너비와 최소 높이를 함께 고정하고 좁은 화면에서는 한 열로 전환 | `knowledge/PATTERNS.md` |

## Wave 11에서 flush한 항목

| 발견사항 | 이동된 곳 |
|----------|-----------|
| stretched Grid item에 aspect-ratio와 min-height를 함께 사용하면 행 높이보다 카드가 커져 겹칠 수 있음 | `knowledge/trouble-shooting.md` |
| 고정 정사각형 카드에는 열과 암시적 행을 같은 px로 지정해 양축 간격을 보장 | `knowledge/PATTERNS.md` |

## Wave 12에서 flush한 항목

| 발견사항 | 이동된 곳 |
|----------|-----------|
| 카드 크기와 고정/가변 모드를 영구 설정으로 저장하고 CSS 변수에 적용 | `knowledge/PATTERNS.md` |

## Wave 13에서 flush한 항목

| 발견사항 | 이동된 곳 |
|----------|-----------|
| 탐지기 전처리 상수는 학습 입력과 결합되어 있으며 구간 선택·집계·임계값·실행 성능 값과 구분해야 함 | `knowledge/RULES.md` |
| lofcz 구간 설정은 현재 진단 출력에만 쓰이고 Total에는 곡 전체 점수만 반영됨 | `knowledge/trouble-shooting.md` |
| ArtifactNet 집계법 변경은 E0003 일부에는 유리했지만 E0001/E0002 및 인간 대조군에서 방향성을 고치지 못함 | `knowledge/trouble-shooting.md` |
