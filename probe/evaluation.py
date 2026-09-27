"""Reusable evaluation helpers for score calibration experiments."""

from __future__ import annotations

import hashlib
import statistics
from collections import defaultdict


def fit_isotonic(rows: list[dict]) -> list[dict]:
    label_counts = {label: sum(int(row["label"]) == label for row in rows) for label in (0, 1)}
    tied: dict[float, list[tuple[int, float]]] = defaultdict(list)
    for row in rows:
        label = int(row["label"])
        weight = 1.0 / max(1, label_counts[label])
        tied[float(row["totalScore"])].append((label, weight))
    blocks = [
        {
            "low": score,
            "high": score,
            "sum": sum(label * weight for label, weight in samples),
            "weight": sum(weight for _label, weight in samples),
        }
        for score, samples in sorted(tied.items())
    ]
    index = 0
    while index < len(blocks) - 1:
        left = blocks[index]
        right = blocks[index + 1]
        if left["sum"] / left["weight"] <= right["sum"] / right["weight"]:
            index += 1
            continue
        left["high"] = right["high"]
        left["sum"] += right["sum"]
        left["weight"] += right["weight"]
        blocks.pop(index + 1)
        index = max(0, index - 1)
    return [
        {"low": round(block["low"], 6), "high": round(block["high"], 6), "score": round(100 * block["sum"] / block["weight"], 6)}
        for block in blocks
    ]


def predict_isotonic(score: float, blocks: list[dict]) -> float:
    if not blocks:
        return score
    if score <= blocks[0]["high"]:
        return float(blocks[0]["score"])
    for block in blocks[1:]:
        if score <= block["high"]:
            return float(block["score"])
    return float(blocks[-1]["score"])


def classification_metrics(rows: list[dict], predictions: list[float]) -> dict:
    positives = [index for index, row in enumerate(rows) if row["label"] == 1]
    negatives = [index for index, row in enumerate(rows) if row["label"] == 0]
    true_positive = sum(predictions[index] >= 50 for index in positives)
    true_negative = sum(predictions[index] < 50 for index in negatives)
    sensitivity = true_positive / len(positives) if positives else 0.0
    specificity = true_negative / len(negatives) if negatives else 0.0
    probabilities = [max(0.0, min(1.0, prediction / 100.0)) for prediction in predictions]
    brier = statistics.fmean(
        (probability - int(row["label"])) ** 2
        for row, probability in zip(rows, probabilities)
    ) if rows else 0.0
    return {
        "count": len(rows),
        "accuracy": round((true_positive + true_negative) / len(rows), 4) if rows else 0.0,
        "balancedAccuracy": round((sensitivity + specificity) / 2, 4),
        "sensitivity": round(sensitivity, 4),
        "specificity": round(specificity, 4),
        "brierScore": round(brier, 4),
    }


def grouped_five_fold(rows: list[dict], key: str) -> dict:
    folds: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        digest = hashlib.sha256(row[key].encode("utf-8")).digest()
        folds[int.from_bytes(digest[:4], "big") % 5].append(row)
    output = {}
    combined_rows = []
    combined_raw_predictions = []
    combined_predictions = []
    for fold in range(5):
        test = folds[fold]
        train = [row for other_fold, items in folds.items() if other_fold != fold for row in items]
        if not test or len({row["label"] for row in train}) < 2:
            continue
        blocks = fit_isotonic(train)
        predictions = [predict_isotonic(row["totalScore"], blocks) for row in test]
        output[str(fold)] = {
            "raw": classification_metrics(test, [row["totalScore"] for row in test]),
            "calibrated": classification_metrics(test, predictions),
        }
        combined_rows.extend(test)
        combined_raw_predictions.extend(row["totalScore"] for row in test)
        combined_predictions.extend(predictions)
    output["combined"] = {
        "raw": classification_metrics(combined_rows, combined_raw_predictions),
        "calibrated": classification_metrics(combined_rows, combined_predictions),
    }
    return output
