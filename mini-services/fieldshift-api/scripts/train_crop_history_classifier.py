"""Train/evaluate a CatBoost crop head with strict spatial-temporal holdouts.

CSV columns: field_id, farm_group_id, region_id, season_year, crop_code,
label_source, label_license, valid_pixel_coverage, embedding_0..embedding_127.
This script does not run until labels carry a reviewed source and license.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from catboost import CatBoostClassifier
from scipy.optimize import minimize_scalar
from sklearn.metrics import balanced_accuracy_score, f1_score, log_loss
from sklearn.model_selection import GroupShuffleSplit

from app.intelligence.crop_history.training import spatial_temporal_holdout, validate_training_rows


def _load(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for source in reader:
            row = {key: source[key] for key in (
                "field_id", "farm_group_id", "region_id", "crop_code", "label_source", "label_license"
            )}
            row["season_year"] = int(source["season_year"])
            row["valid_pixel_coverage"] = float(source["valid_pixel_coverage"])
            row["embedding"] = [float(source[f"embedding_{i}"]) for i in range(128)]
            rows.append(row)
    validate_training_rows(rows)
    return rows


def _softmax(logits: np.ndarray, temperature: float) -> np.ndarray:
    scaled = logits / temperature
    scaled -= scaled.max(axis=1, keepdims=True)
    values = np.exp(scaled)
    return values / values.sum(axis=1, keepdims=True)


def _ece(probabilities: np.ndarray, y_true: np.ndarray, classes: list[str], bins: int = 10) -> float:
    predictions = np.asarray(classes)[probabilities.argmax(axis=1)]
    confidence = probabilities.max(axis=1)
    correct = (predictions == y_true).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(y_true)
    error = 0.0
    for index in range(bins):
        selected = (confidence > edges[index]) & (confidence <= edges[index + 1])
        if selected.any():
            error += selected.sum() / total * abs(confidence[selected].mean() - correct[selected].mean())
    return float(error)


def _evaluate_fold(rows: list[dict], train_idx: list[int], test_idx: list[int], *, seed: int) -> dict:
    train_rows = [rows[i] for i in train_idx]
    test_rows = [rows[i] for i in test_idx]
    X_train = np.asarray([r["embedding"] for r in train_rows], dtype=np.float32)
    y_train = np.asarray([r["crop_code"] for r in train_rows])
    groups = np.asarray([r["farm_group_id"] for r in train_rows])
    X_test = np.asarray([r["embedding"] for r in test_rows], dtype=np.float32)
    y_test = np.asarray([r["crop_code"] for r in test_rows])

    if len(set(groups)) < 5:
        raise ValueError("at least five training farm groups are required for grouped calibration")
    fit_idx = calibration_idx = None
    for attempt in range(10):
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed + attempt)
        candidate_fit, candidate_cal = next(splitter.split(X_train, y_train, groups=groups))
        if set(y_train[candidate_fit]) == set(y_train) and set(y_train[candidate_cal]) == set(y_train):
            fit_idx, calibration_idx = candidate_fit, candidate_cal
            break
    if fit_idx is None or calibration_idx is None:
        raise ValueError("could not create farm-disjoint fit/calibration groups with all crop classes")
    X_fit, y_fit = X_train[fit_idx], y_train[fit_idx]
    X_cal, y_cal = X_train[calibration_idx], y_train[calibration_idx]
    fit_classes = set(y_fit)
    if not set(y_test) <= fit_classes:
        raise ValueError("grouped fit partition does not cover all test crop classes")

    model = CatBoostClassifier(
        iterations=400, depth=6, learning_rate=0.05,
        loss_function="MultiClass", random_seed=seed,
        verbose=False, thread_count=2, allow_writing_files=False,
    )
    model.fit(X_fit, y_fit)
    classes = [str(value) for value in model.classes_]
    cal_logits = np.asarray(model.predict(X_cal, prediction_type="RawFormulaVal"), dtype=np.float64)
    test_logits = np.asarray(model.predict(X_test, prediction_type="RawFormulaVal"), dtype=np.float64)

    def objective(log_temperature: float) -> float:
        temperature = math.exp(log_temperature)
        return float(log_loss(y_cal, _softmax(cal_logits, temperature), labels=classes))

    optimum = minimize_scalar(objective, bounds=(-3.0, 3.0), method="bounded")
    temperature = math.exp(float(optimum.x))
    probabilities = _softmax(test_logits, temperature)
    predictions = np.asarray(classes)[probabilities.argmax(axis=1)]
    confidence = probabilities.max(axis=1)
    accepted = confidence >= 0.60
    one_hot = np.zeros_like(probabilities)
    class_index = {name: i for i, name in enumerate(classes)}
    for row_index, label in enumerate(y_test):
        one_hot[row_index, class_index[label]] = 1.0
    brier = float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1)))
    return {
        "test_count": len(y_test),
        "classes": classes,
        "macro_f1": float(f1_score(y_test, predictions, average="macro")),
        "balanced_accuracy": float(balanced_accuracy_score(y_test, predictions)),
        "brier_score": brier,
        "expected_calibration_error": _ece(probabilities, y_test, classes),
        "temperature": temperature,
        "abstention_threshold": 0.60,
        "coverage": float(accepted.mean()),
        "selective_accuracy": float((predictions[accepted] == y_test[accepted]).mean()) if accepted.any() else None,
        "per_class_f1": {
            name: float(f1_score(y_test, predictions, labels=[name], average="macro", zero_division=0))
            for name in classes
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    rows = _load(args.dataset)
    target_year = max(int(row["season_year"]) for row in rows)
    regions = sorted({row["region_id"] for row in rows})
    folds = []
    for region in regions:
        try:
            train_idx, test_idx = spatial_temporal_holdout(
                rows, held_out_region=region, target_year=target_year
            )
            metrics = _evaluate_fold(rows, train_idx, test_idx, seed=args.seed)
            folds.append({"held_out_region": region, "target_year": target_year, "status": "evaluated", **metrics})
        except ValueError as exc:
            folds.append({"held_out_region": region, "target_year": target_year, "status": "blocked", "reason": str(exc)})
    valid = [fold for fold in folds if fold["status"] == "evaluated"]
    report = {
        "model": "CatBoost on NASA Harvest Presto 128-D embeddings",
        "split": "leave-one-region-out + latest-season temporal holdout",
        "target_year": target_year,
        "folds": folds,
        "macro_f1_mean": float(np.mean([fold["macro_f1"] for fold in valid])) if valid else None,
        "balanced_accuracy_mean": float(np.mean([fold["balanced_accuracy"] for fold in valid])) if valid else None,
        "brier_score_mean": float(np.mean([fold["brier_score"] for fold in valid])) if valid else None,
        "expected_calibration_error_mean": float(np.mean([fold["expected_calibration_error"] for fold in valid])) if valid else None,
        "warning": "No crop classifier is approved unless all required regions and crop classes have valid held-out folds.",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if valid and len(valid) == len(regions) else 2


if __name__ == "__main__":
    raise SystemExit(main())
