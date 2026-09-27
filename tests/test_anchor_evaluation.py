from scratch.evaluate_anchor_corpus import fit_isotonic, grouped_five_fold, predict_isotonic


def test_isotonic_fit_is_monotonic_and_class_balanced() -> None:
    rows = [
        {"totalScore": 10.0, "label": 0},
        {"totalScore": 20.0, "label": 1},
        {"totalScore": 30.0, "label": 0},
        {"totalScore": 80.0, "label": 1},
    ]

    blocks = fit_isotonic(rows)
    scores = [block["score"] for block in blocks]

    assert scores == sorted(scores)
    assert predict_isotonic(5.0, blocks) == scores[0]
    assert predict_isotonic(95.0, blocks) == scores[-1]


def test_grouped_holdout_reports_raw_and_calibrated_metrics() -> None:
    rows = []
    for index in range(10):
        rows.append({"totalScore": float(index), "label": 0, "pairGroup": f"human-{index}"})
        rows.append({"totalScore": float(90 + index), "label": 1, "pairGroup": f"ai-{index}"})

    result = grouped_five_fold(rows, "pairGroup")

    assert result["combined"]["raw"]["count"] == 20
    assert result["combined"]["calibrated"]["balancedAccuracy"] >= 0.8
