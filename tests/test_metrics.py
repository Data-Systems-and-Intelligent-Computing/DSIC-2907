import numpy as np
import pytest

from src.metrics import binary_metrics


def test_controlled_metrics_and_attack_positive():
    result = binary_metrics([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8])
    assert result["macro_f1"] == pytest.approx((0.8 + 2 / 3) / 2)
    assert result["attack_recall"] == 0.5
    assert result["auprc_average_precision"] == pytest.approx(5 / 6)
    assert result["accuracy"] == 0.75
    assert result["auroc"] == 0.75
    assert result["balanced_accuracy"] == 0.75
    assert result["confusion_matrix"] == [[2, 0], [1, 1]]


def test_threshold_inclusive_and_confusion_order():
    result = binary_metrics([0, 0, 1, 1], [0.5, 0.1, 0.5, 0.8])
    assert result["confusion_matrix"] == [[1, 1], [0, 2]]
    assert result["attack_recall"] == 1.0


@pytest.mark.parametrize(
    "labels, probabilities",
    [
        ([], []),
        ([0, 1], [0.5]),
        ([[0, 1]], [[0.1, 0.9]]),
        ([0, 2], [0.1, 0.8]),
        ([1, 1], [0.2, 0.8]),
        ([0, 1], [np.nan, 0.8]),
        ([0, 1], [0.1, np.inf]),
        ([0, 1], [-0.1, 0.8]),
        ([0, 1], [0.1, 1.1]),
        ([0, 1], ["low", "high"]),
        ([0, 1], [1j, 0.8]),
        (["Normal", "Attack"], [0.1, 0.8]),
    ],
)
def test_malformed_inputs_fail(labels, probabilities):
    with pytest.raises(ValueError):
        binary_metrics(labels, probabilities)
