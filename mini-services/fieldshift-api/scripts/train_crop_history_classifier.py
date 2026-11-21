"""Train/evaluate a CatBoost crop head with strict spatial-temporal holdouts.

CSV columns: field_id, farm_group_id, region_id, season_year, crop_code,
label_source, label_source_verified, label_license, label_license_verified, valid_pixel_coverage, embedding_model, input_schema_version, embedding_0..embedding_127.
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
from sklearn.model_selection import GroupKFold

from app.intelligence.crop_history.training import spatial_temporal_holdout, validate_training_rows


def _load(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for source in reader:
            row = {key: source[key] for key in (
                "field_id", "farm_group_id", "region_id", "crop_code", "label_source", "label_license", "embedding_model", "input_schema_version"
            )}
            row["label_source_verified"] = source["label_source_verified"].strip().casefold() == "true"
            row["embedding_model"] = source["embedding_model"]
            row["input_schema_version"] = source["input_schema_version"]
            row["label_license_verified"] = source["label_license_verified"].strip().casefold() == "true"
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

    if len(set(groups)) < 3:
        raise ValueError("at least three training farm groups are required for grouped calibration")
    classes = sorted(set(y_train))
    oof_logits = np.full((len(y_train), len(classes)), np.nan, dtype=np.float64)
    oof_seen = np.zeros(len(y_train), dtype=bool)
    splitter = GroupKFold(n_splits=3)
    for inner_train, calibration_idx in splitter.split(X_train, y_train, groups=groups):
        X_fit, y_fit = X_train[inner_train], y_train[inner_train]
        X_cal, y_cal = X_train[calibration_idx], y_train[calibration_idx]
        if set(y_fit) != set(classes):
            raise ValueError("a farm-disjoint calibration fold is missing one or more crop classes")
        fold_model = CatBoostClassifier(
            iterations=400, depth=6, learning_rate=0.05,
            loss_function="MultiClass", random_seed=seed,
            verbose=False, thread_count=2, allow_writing_files=False,
        )
        fold_model.fit(X_fit, y_fit)
        fold_classes = [str(value) for value in fold_model.classes_]
        if fold_classes != classes:
            raise ValueError("CatBoost class order changed across calibration folds")
        oof_logits[calibration_idx] = np.asarray(
            fold_model.predict(X_cal, prediction_type="RawFormulaVal"), dtype=np.float64
        )
        oof_seen[calibration_idx] = True
    if not oof_seen.all() or not np.isfinite(oof_logits).all():
        raise ValueError("farm-disjoint out-of-fold calibration did not cover every training record")
    if not set(y_test) <= set(classes):
        raise ValueError("training partition does not cover all test crop classes")

    def objective(log_temperature: float) -> float:
        temperature = math.exp(log_temperature)
        return float(log_loss(y_train, _softmax(oof_logits, temperature), labels=classes))

    optimum = minimize_scalar(objective, bounds=(-3.0, 3.0), method="bounded")
    temperature = math.exp(float(optimum.x))
    model = CatBoostClassifier(
        iterations=400, depth=6, learning_rate=0.05,
        loss_function="MultiClass", random_seed=seed,
        verbose=False, thread_count=2, allow_writing_files=False,
    )
    model.fit(X_train, y_train)
    final_classes = [str(value) for value in model.classes_]
    if final_classes != classes:
        raise ValueError("final CatBoost class order differs from calibrated out-of-fold order")
    test_logits = np.asarray(model.predict(X_test, prediction_type="RawFormulaVal"), dtype=np.float64)
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
