"""Binary metrics: Attack=1, fixed threshold 0.5, AUPRC = Average Precision."""

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    recall_score,
    roc_auc_score,
)

THRESHOLD = 0.5


def binary_metrics(labels, attack_probabilities):
    labels = np.asarray(labels)
    probabilities = np.asarray(attack_probabilities)
    if labels.ndim != 1 or probabilities.ndim != 1 or labels.shape != probabilities.shape:
        raise ValueError("Labels and probabilities must be equally sized one-dimensional arrays")
    if not len(labels) or not np.isin(labels, [0, 1]).all():
        raise ValueError("Labels must be nonempty binary values: Normal=0, Attack=1")
    if set(labels.tolist()) != {0, 1}:
        raise ValueError("Both classes are required for AUROC and balanced evaluation")
    if not np.issubdtype(probabilities.dtype, np.number) or np.iscomplexobj(probabilities):
        raise ValueError("Probabilities must be real numbers")
    if not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("Probabilities must be finite values in [0, 1]")
    predictions = (probabilities >= THRESHOLD).astype(np.int64)
    return {
        "macro_f1": float(
            f1_score(labels, predictions, average="macro", labels=[0, 1], zero_division=0)
        ),
        "attack_recall": float(recall_score(labels, predictions, pos_label=1, zero_division=0)),
        "auprc_average_precision": float(
            average_precision_score(labels, probabilities, pos_label=1)
        ),
        "accuracy": float(accuracy_score(labels, predictions)),
        "auroc": float(roc_auc_score(labels, probabilities)),
        "balanced_accuracy": float(balanced_accuracy_score(labels, predictions)),
        "confusion_matrix": confusion_matrix(labels, predictions, labels=[0, 1]).tolist(),
    }
