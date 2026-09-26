# E0001-1 후처리본 비교

분석일: 2026-09-26

## 비교 파일

1. LANDR 마스터링본  
   `F:\Music\Music-LANDR-Mastered\E0001-1 A Whisper of a Forgotten Name (ambient pop)-Remastered.wav`
2. SongYUE2 기본 AI 곡 다듬기 3단계 후 Mastering-1 적용본  
   `C:\Claude\ai-music-probe\corpus\e0001_comparison\E0001-1 A Whisper of a Forgotten Name (ambient pop)__SongYUE2-polish-default__Mastering-1.wav`

## 파일별 결과

| 항목 | LANDR 마스터링 | SongYUE2 곡 다듬기 + Mastering-1 |
|---|---:|---:|
| totalScore | **85.4** | **89.6** |
| 신뢰 지표 | 51.6 | 63.6 |
| SONICS | 0.7290 | 0.8028 |
| SONICS 구간 평균 | 0.1762 | 0.2108 |
| SONICS 최대 구간 | 0.8951 | 0.9115 |
| SONICS 양성 구간 비율 | 12.5% | 16.7% |
| lofcz 전체 점수 | 1.0000 | 1.0000 |
| lofcz 구간 평균 | 0.8879 | 0.8040 |
| 피크 | -0.26 dBFS | -6.23 dBFS |
| RMS | -13.40 dBFS | -23.68 dBFS |
| 99% rolloff | 8,859 Hz | 4,078 Hz |
| 스테레오 상관 | 0.6950 | 0.6568 |
| Side/Mid | -7.44 dB | -6.83 dB |

## 처리 단계별 점수

| 단계 | totalScore | SONICS | lofcz |
|---|---:|---:|---:|
| AI 원본 | 94.0 | 0.8839 | 1.0000 |
| SongYUE2 AI 곡 다듬기 | 96.4 | 0.9291 | 1.0000 |
| SongYUE2 AI 곡 다듬기 + Mastering-1 | 89.6 | 0.8028 | 1.0000 |
| LANDR 마스터링 | 85.4 | 0.7290 | 1.0000 |

## 해석

- 두 최종본 모두 현재 탐지기에서 AI 생성 흔적이 강하다.
- LANDR 마스터링본이 SongYUE2 조합보다 4.2점 낮아, 이 한 곡에서는 LANDR 쪽이 탐지 흔적을 더 많이 약화했다.
- SongYUE2의 AI 곡 다듬기만 적용했을 때는 점수가 94.0에서 96.4로 오히려 상승했다. 노이즈 제거와 고역 억제가 SONICS가 학습한 패턴을 강화했을 가능성이 있다.
- 그 뒤 Mastering-1을 적용하면 96.4에서 89.6으로 내려갔다. Mastering-1 자체는 탐지 흔적을 일부 약화했다.
- lofcz는 모든 AI 버전에서 1.0으로 포화되어 이 곡의 후처리 정도를 구분하지 못했다.
- SongYUE2 조합은 LANDR보다 RMS가 약 10.3 dB 낮고 99% rolloff가 약 4.8 kHz 낮다. 더 인간적으로 바뀌었다기보다 고역과 전체 레벨이 많이 줄어든 결과일 수 있다.

현재 결과는 한 곡에 대한 관측이다. 후처리 방식의 일반적인 우열이나 YouTube 탐지 결과로 일반화할 수 없다.

## 재현 정보

- AI 곡 다듬기: SongYUE2 `backend/postfx/worker.mjs`
- 단계: 노이즈 제거 0.4 → Spectral Lifter 기본값 → 보컬 자연화 기본값
- 후처리: SongYUE2 `Setting/PostProcess/Mastering-1.json`
- Mastering-1 렌더링은 SongYUE2 WebAudio 파라미터를 FFmpeg 대응 필터로 변환했으므로 브라우저 렌더와 비트 단위로 같지는 않다.
- 전체 JSON: `reports/e0001-two-mastering-comparison.json`
