import copy

import numpy as np
import torch

from src.centralized import build_model
from src.client import FLClient


def test_local_training_starts_at_download_and_repeats_full_delta():
    config = {
        "hidden_dimensions": [8, 4],
        "dropout": 0.2,
        "epochs": 1,
        "batch_size": 8,
        "optimizer": "Adam",
        "learning_rate": 0.001,
    }
    model = build_model(2, config)
    start = copy.deepcopy(model.state_dict())
    data = (np.arange(80, dtype=np.float32).reshape(40, 2) / 80, np.array([0, 1] * 20))
    client = FLClient(config, seed=42, cpu_threads=1)
    first = client.train(start, data)
    repeated = client.train(start, data)
    assert first["num_samples"] == 40
    assert first["budget"] == 1.0
    assert first["training_bce_by_epoch"] == repeated["training_bce_by_epoch"]
    assert set(first["delta"]) == set(start)
    for name, tensor in first["delta"].items():
        assert torch.equal(tensor, repeated["delta"][name])
        assert tensor.shape == start[name].shape
        assert tensor.dtype == torch.float32
        assert torch.equal(start[name], model.state_dict()[name])
    assert any(torch.count_nonzero(t).item() for t in first["delta"].values())
