import copy
import hashlib
import json

import pytest
import torch

from src.async_server import AsyncServer
from src.budget_probe import run_probe
from src.centralized import build_model
from src.client import deserialize_message, serialize_message
from src.compressor import decode_update, encode_update, measure_budget_upload, topk_compress


@pytest.mark.parametrize("budget,count", [(0.25, 2), (0.50, 3), (1.00, 5)])
def test_topk_uses_per_tensor_ceil_and_stable_boundary_ties(budget, count):
    delta = {"weight": torch.tensor([[2.0, -2.0, 2.0, 0.5, -0.1]])}
    selected = topk_compress(delta, budget)["weight"]
    expected = {0.25: [0, 1], 0.50: [0, 1, 2], 1.00: [0, 1, 2, 3, 4]}[budget]
    assert selected["indices"].dtype == torch.int32
    assert selected["indices"].tolist() == expected
    assert selected["values"].tolist() == delta["weight"].flatten()[expected].tolist()
    assert selected["shape"] == [1, 5]
    assert selected["dtype"] == "float32"
    assert selected["indices"].numel() == count
    assert torch.equal(selected["indices"], topk_compress(delta, budget)["weight"]["indices"])


@pytest.mark.parametrize("budget", [0, 0.3, 2, float("nan"), True])
def test_invalid_budget_rejected(budget):
    with pytest.raises(ValueError, match="budget"):
        topk_compress({"weight": torch.ones(2)}, budget)


def test_boolean_full_budget_source_rejected():
    with pytest.raises(ValueError, match="full-budget"):
        encode_update({"budget": True, "delta": {"weight": torch.ones(2)}}, 0.25)


@pytest.mark.parametrize(
    "tensor",
    [
        torch.empty(0),
        torch.tensor([float("nan")]),
        torch.tensor([float("inf")]),
        torch.ones(2, dtype=torch.int64),
    ],
)
def test_invalid_tensor_rejected(tensor):
    with pytest.raises(ValueError, match="tensor"):
        topk_compress({"weight": tensor}, 0.25)


def test_invalid_tensor_name_rejected():
    with pytest.raises(ValueError, match="tensor map"):
        topk_compress({1: torch.ones(2), "weight": torch.ones(2)}, 0.25)


def test_sparse_round_trip_preserves_float64_dtype():
    model = torch.nn.Linear(3, 1, bias=False).double()
    update = {
        "budget": 1.0,
        "delta": {"weight": torch.tensor([[1.0, -2.0, 0.5]], dtype=torch.float64)},
    }
    wire = encode_update(update, 0.25)
    restored = decode_update(deserialize_message(serialize_message(wire)), model.state_dict())
    assert restored["delta"]["weight"].dtype == torch.float64
    torch.testing.assert_close(
        restored["delta"]["weight"], torch.tensor([[0.0, -2.0, 0.0]], dtype=torch.float64)
    )


@pytest.mark.parametrize("budget", [0.25, 0.5, 1.0])
def test_wire_round_trip_reconstructs_and_applies(budget):
    model = torch.nn.Linear(5, 1, bias=True)
    with torch.no_grad():
        model.weight.zero_()
        model.bias.zero_()
    delta = {
        "weight": torch.tensor([[2.0, -2.0, 2.0, 0.5, -0.1]]),
        "bias": torch.tensor([3.0]),
    }
    update = {"num_samples": 4, "budget": 1.0, "delta": delta, "job_id": "job_0"}
    wire = encode_update(update, budget)
    payload = serialize_message(wire)
    decoded = deserialize_message(payload)
    reconstructed = decode_update(decoded, model.state_dict())
    expected = {name: torch.zeros_like(tensor) for name, tensor in delta.items()}
    for name, entry in topk_compress(delta, budget).items():
        expected[name].view(-1)[entry["indices"].long()] = entry["values"]
    assert reconstructed["job_id"] == update["job_id"]
    assert reconstructed["budget"] == budget
    for name in delta:
        torch.testing.assert_close(reconstructed["delta"][name], expected[name])
        assert reconstructed["delta"][name].shape == delta[name].shape
        assert reconstructed["delta"][name].dtype == delta[name].dtype
    if budget == 1.0:
        assert "delta" in wire and "sparse_delta" not in wire
    else:
        assert "delta" not in wire and "sparse_delta" in wire
    server = AsyncServer(model, total_samples=8, allowed_budgets=(0.25, 0.5, 1.0))
    receipt = server.apply_update(reconstructed, model_start_version=0)
    assert receipt["version_after"] == 1
    for name, tensor in model.state_dict().items():
        torch.testing.assert_close(tensor, expected[name] * 0.5)


@pytest.mark.parametrize(
    "corruption",
    [
        "version",
        "version_type",
        "count",
        "count_type",
        "name",
        "shape",
        "shape_type",
        "dtype",
        "duplicate",
        "range",
        "index_dtype",
        "nan",
        "dense_copy",
    ],
)
def test_bad_sparse_payload_is_rejected_before_server_mutation(corruption):
    model = torch.nn.Linear(5, 1, bias=False)
    before = copy.deepcopy(model.state_dict())
    update = {"num_samples": 1, "budget": 1.0, "delta": {"weight": torch.arange(5.0).view(1, 5)}}
    wire = encode_update(update, 0.5)
    entry = wire["sparse_delta"]["weight"]
    if corruption == "version":
        wire["format"]["version"] = 2
    elif corruption == "version_type":
        wire["format"]["version"] = True
    elif corruption == "count":
        wire["format"]["tensor_count"] = 2
    elif corruption == "count_type":
        wire["format"]["tensor_count"] = True
    elif corruption == "name":
        wire["sparse_delta"]["unexpected"] = wire["sparse_delta"].pop("weight")
    elif corruption == "shape":
        entry["shape"] = [5, 1]
    elif corruption == "shape_type":
        entry["shape"] = torch.tensor([1, 5])
    elif corruption == "dtype":
        entry["dtype"] = "float64"
    elif corruption == "duplicate":
        entry["indices"][1] = entry["indices"][0]
    elif corruption == "range":
        entry["indices"][1] = 5
    elif corruption == "index_dtype":
        entry["indices"] = entry["indices"].long()
    elif corruption == "nan":
        entry["values"][0] = float("nan")
    else:
        wire["delta"] = update["delta"]
    server = AsyncServer(model, 2, allowed_budgets=(0.25, 0.5, 1.0))
    with pytest.raises(ValueError):
        server.apply_update(
            decode_update(deserialize_message(serialize_message(wire)), model.state_dict()), 0
        )
    assert server.version == 0
    for name, tensor in model.state_dict().items():
        assert torch.equal(tensor, before[name])


def test_sparse_accounting_includes_indices_and_overhead():
    update = {"num_samples": 2, "budget": 1.0, "delta": {"weight": torch.arange(20.0)}}
    dense = encode_update(update, 1.0)
    sparse = encode_update(update, 0.5)
    dense_bytes = serialize_message(dense)
    sparse_bytes = serialize_message(sparse)
    full = measure_budget_upload(dense_bytes, dense)
    half = measure_budget_upload(sparse_bytes, sparse)
    assert full["value_bytes"] == 80 and full["index_bytes"] == 0
    assert half["value_bytes"] == 40 and half["index_bytes"] == 40
    for measured, payload in ((full, dense_bytes), (half, sparse_bytes)):
        assert measured["payload_bytes"] == len(payload)
        assert measured["other_bytes"] > 0
        assert sum(measured[key] for key in ("value_bytes", "index_bytes", "other_bytes")) == len(
            payload
        )


def test_probe_saves_replayable_payloads_and_signed_byte_report(tmp_path):
    source = tmp_path / "source"
    messages = source / "messages"
    messages.mkdir(parents=True)
    config = {
        "n_features": 2,
        "local_training": {"hidden_dimensions": [4, 2], "dropout": 0.0},
        "total_train_fit": 4,
        "pilot_settings": {"server_learning_rate": 1.0, "fixed_staleness_multiplier": 1.0},
    }
    (source / "configuration.json").write_text(json.dumps(config), encoding="utf-8")
    model = build_model(2, config["local_training"])
    state = model.state_dict()
    download = {
        "job_id": "job_0000",
        "client_id": "client_0",
        "model_start_version": 0,
        "model_state": state,
    }
    upload = {
        "job_id": "job_0000",
        "client_id": "client_0",
        "model_start_version": 0,
        "num_samples": 2,
        "budget": 1.0,
        "delta": {name: torch.ones_like(tensor) for name, tensor in state.items()},
    }
    (messages / "job_0000_download.pt").write_bytes(serialize_message(download))
    (messages / "job_0000_upload.pt").write_bytes(serialize_message(upload))
    output, payload_dir = tmp_path / "report.json", tmp_path / "payloads"
    report = run_probe(source, output, payload_dir)
    assert output.is_file()
    assert report["source"]["job_id"] == "job_0000"
    full = report["actions"]["1.00"]
    for action in ("0.25", "0.50", "1.00"):
        result = report["actions"][action]
        payload = (payload_dir / f"job_0000_budget_{action}_upload.pt").read_bytes()
        assert result["upload"]["payload_bytes"] == len(payload)
        assert result["payload"]["sha256"] == hashlib.sha256(payload).hexdigest()
        assert result["total_bytes"] == len(payload) + report["download_bytes"]
        assert result["saved_total_bytes"] == full["total_bytes"] - result["total_bytes"]
        assert result["model_effect_verified"]
    assert full["upload"]["index_bytes"] == 0
    assert (payload_dir / "job_0000_budget_1.00_upload.pt").read_bytes() == (
        messages / "job_0000_upload.pt"
    ).read_bytes()
    assert report["actions"]["0.50"]["upload"]["index_bytes"] > 0
    assert report["actions"]["0.50"]["saved_total_bytes"] < 0
