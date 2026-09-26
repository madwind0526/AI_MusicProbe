# Rules

> 이 프로젝트의 규칙과 컨벤션. 모든 sub-agent가 반드시 따라야 함.

## G-01: 코드 주석은 영어만 사용 (MANDATORY)

**규칙:** 모든 코드 주석(`//`, `/* */`, `///`)은 영어로 작성. 한글 주석 금지.
**이유:** 소스 파일 내 한글은 인코딩 문제 및 빌드 오류를 유발할 수 있음.
**적용 시점:** 코드 작성 또는 수정 시 항상. UI 텍스트(사용자에게 보이는 문자열)는 한국어 유지.

<!-- 예시 형식:

## [규칙 이름]

**규칙:** [한 줄 요약]
**이유:** [왜 이 규칙이 필요한가]
**적용 시점:** [언제 이 규칙이 발동되나]

-->
## AI generation score

- Do not present the 0–100 score as a probability or a fixed five-class label.
- Do not assume the scale is linear. Fit monotonic calibration only after paired anchor groups are sufficiently diverse.
- A mastering operation is not evidence of AI generation by itself. Human and AI originals must keep their provenance label after postprocessing.

## Detector settings boundaries (2026-09-27)

- Keep model-coupled preprocessing values such as sample rate, FFT dimensions, frequency bands, and fixed model input duration locked to the model version.
- Expose segment selection, song-level aggregation, decision threshold, and execution-provider controls separately and label whether each control changes the raw score, only the verdict, or only performance.
- Validate aggregation and ensemble changes on held-out human/AI pairs instead of tuning them to one track family.
