import copy

import pytest
import torch

from src.async_server import AsyncServer


def test_async_apply_sample_weighting_and_stale_delta():
    model = torch.nn.Linear(2, 1, bias=False)
    with torch.no_grad():
        model.weight.zero_()
    server = AsyncServer(model, total_samples=100)
    update = {"num_samples": 20, "budget": 1.0, "delta": {"weight": torch.ones(1, 2)}}
    first = server.apply_update(update, model_start_version=0)
    assert first == {"version_before": 0, "version_after": 1, "staleness": 0, "weight": 0.2}
    torch.testing.assert_close(model.weight, torch.full((1, 2), 0.2))
    second = server.apply_update(update, model_start_version=0)
    assert second["staleness"] == 1
    assert server.version == 2
    torch.testing.assert_close(model.weight, torch.full((1, 2), 0.4))


@pytest.mark.parametrize("bad", ["samples", "budget", "keys", "shape", "dtype", "nan", "future"])
def test_invalid_update_never_changes_model_or_version(bad):
    model = torch.nn.Linear(2, 1, bias=False)
    before = copy.deepcopy(model.state_dict())
    server = AsyncServer(model, total_samples=100)
    update = {"num_samples": 20, "budget": 1.0, "delta": {"weight": torch.ones(1, 2)}}
    start = 0
    if bad == "samples":
        update["num_samples"] = 0
    elif bad == "budget":
        update["budget"] = 0.5
    elif bad == "keys":
        update["delta"] = {}
    elif bad == "shape":
        update["delta"]["weight"] = torch.ones(2, 1)
    elif bad == "dtype":
        update["delta"]["weight"] = torch.ones(1, 2, dtype=torch.float64)
    elif bad == "nan":
        update["delta"]["weight"][0, 0] = float("nan")
    else:
        start = 1
    with pytest.raises(ValueError):
        server.apply_update(update, start)
    assert server.version == 0
    for key, tensor in before.items():
        assert torch.equal(tensor, model.state_dict()[key])
