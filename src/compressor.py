"""Deterministic magnitude top-k uploads and application-message byte counts."""

import math

import torch

BUDGETS = (0.25, 0.5, 1.0)
FORMAT_VERSION = 1
OPERATOR = "magnitude_topk"
DTYPES = (torch.float32, torch.float64)


def _check_budget(budget):
    if type(budget) not in (int, float) or budget not in BUDGETS:
        raise ValueError("Unsupported update budget")


def _check_tensor(name, tensor):
    if (
        not isinstance(name, str)
        or not name
        or not isinstance(tensor, torch.Tensor)
        or tensor.device.type != "cpu"
        or tensor.dtype not in DTYPES
        or tensor.numel() == 0
        or tensor.numel() > torch.iinfo(torch.int32).max + 1
        or not bool(torch.isfinite(tensor).all())
    ):
        raise ValueError(f"Invalid update tensor: {name}")


def topk_compress(delta, budget: float):
    """Select ceil(qN) entries per tensor; equal magnitudes favor low flat indices."""
    _check_budget(budget)
    if (
        not isinstance(delta, dict)
        or not delta
        or any(not isinstance(name, str) or not name for name in delta)
    ):
        raise ValueError("Update must contain nonempty tensor map")
    selected = {}
    for name in sorted(delta):
        tensor = delta[name]
        _check_tensor(name, tensor)
        flat = tensor.reshape(-1)
        count = math.ceil(budget * flat.numel())
        ranked = torch.argsort(flat.abs(), descending=True, stable=True)
        indices = torch.sort(ranked[:count]).values
        selected[name] = {
            "shape": list(tensor.shape),
            "dtype": str(tensor.dtype).removeprefix("torch."),
            "count": count,
            "indices": indices.to(torch.int32),
            "values": flat[indices].clone(),
        }
    return selected


def encode_update(update, budget: float):
    """Keep full updates dense; encode sparse actions without a dense copy."""
    _check_budget(budget)
    if (
        not isinstance(update, dict)
        or type(update.get("budget")) not in (int, float)
        or update.get("budget") != 1.0
        or "format" in update
        or "sparse_delta" in update
    ):
        raise ValueError("Expected a full-budget dense update")
    selected = topk_compress(update.get("delta"), budget)
    if budget == 1.0:
        return dict(update)
    return {
        **{key: value for key, value in update.items() if key != "delta"},
        "budget": budget,
        "format": {
            "version": FORMAT_VERSION,
            "operator": OPERATOR,
            "budget": budget,
            "tensor_count": len(selected),
        },
        "sparse_delta": selected,
    }


def decode_update(update, model_state):
    """Validate and reconstruct a complete dense delta before server apply."""
    if not isinstance(update, dict) or not isinstance(model_state, dict) or not model_state:
        raise ValueError("Invalid update or model state")
    budget = update.get("budget")
    _check_budget(budget)
    if budget == 1.0:
        if "format" in update or "sparse_delta" in update or "delta" not in update:
            raise ValueError("Invalid dense update format")
        delta = update["delta"]
        if not isinstance(delta, dict) or set(delta) != set(model_state):
            raise ValueError("Dense update tensor names differ from model")
        for name, tensor in delta.items():
            _check_tensor(name, tensor)
            reference = model_state[name]
            _check_tensor(name, reference)
            if tensor.shape != reference.shape or tensor.dtype != reference.dtype:
                raise ValueError(f"Dense update tensor differs from model: {name}")
        return dict(update)
    header, sparse = update.get("format"), update.get("sparse_delta")
    valid_header = (
        isinstance(header, dict)
        and set(header) == {"version", "operator", "budget", "tensor_count"}
        and type(header["version"]) is int
        and header["version"] == FORMAT_VERSION
        and type(header["operator"]) is str
        and header["operator"] == OPERATOR
        and type(header["budget"]) in (int, float)
        and header["budget"] == budget
        and type(header["tensor_count"]) is int
        and header["tensor_count"] == len(model_state)
    )
    if (
        "delta" in update
        or not valid_header
        or not isinstance(sparse, dict)
        or set(sparse) != set(model_state)
    ):
        raise ValueError("Invalid sparse update header or tensor names")
    delta = {}
    for name, reference in model_state.items():
        _check_tensor(name, reference)
        entry = sparse[name]
        if not isinstance(entry, dict) or set(entry) != {
            "shape",
            "dtype",
            "count",
            "indices",
            "values",
        }:
            raise ValueError(f"Invalid sparse tensor metadata: {name}")
        indices, values = entry["indices"], entry["values"]
        count = math.ceil(budget * reference.numel())
        if (
            not isinstance(entry["shape"], list)
            or entry["shape"] != list(reference.shape)
            or type(entry["dtype"]) is not str
            or entry["dtype"] != str(reference.dtype).removeprefix("torch.")
            or type(entry["count"]) is not int
            or entry["count"] != count
            or not isinstance(indices, torch.Tensor)
            or indices.dtype != torch.int32
            or indices.device.type != "cpu"
            or indices.ndim != 1
            or indices.numel() != count
            or not isinstance(values, torch.Tensor)
            or values.dtype != reference.dtype
            or values.device.type != "cpu"
            or values.ndim != 1
            or values.numel() != count
            or not bool(torch.isfinite(values).all())
        ):
            raise ValueError(f"Invalid sparse tensor shape/dtype/count: {name}")
        if bool((indices < 0).any()) or bool((indices >= reference.numel()).any()):
            raise ValueError(f"Sparse tensor index out of range: {name}")
        if count > 1 and not bool(torch.all(indices[1:] > indices[:-1])):
            raise ValueError(f"Sparse tensor indices must be strictly increasing: {name}")
        restored = torch.zeros_like(reference)
        restored.reshape(-1)[indices.long()] = values
        delta[name] = restored
    return {
        **{key: value for key, value in update.items() if key not in ("format", "sparse_delta")},
        "delta": delta,
    }


def serialized_size_bytes(payload) -> int:
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("Serialized payload must be nonempty bytes")
    return len(payload)


def measure_budget_upload(payload, wire_update):
    """Split exact serialized bytes into stored values, indices, and all else."""
    size = serialized_size_bytes(payload)
    if not isinstance(wire_update, dict):
        raise ValueError("Invalid wire update")
    budget = wire_update.get("budget")
    _check_budget(budget)
    if budget == 1.0:
        if "sparse_delta" in wire_update or "format" in wire_update:
            raise ValueError("Invalid dense upload")
        entries = wire_update.get("delta")
        if not isinstance(entries, dict) or not entries:
            raise ValueError("Invalid dense upload")
        for name, tensor in entries.items():
            _check_tensor(name, tensor)
        value_bytes = sum(t.numel() * t.element_size() for t in entries.values())
        index_bytes = 0
    else:
        entries = wire_update.get("sparse_delta")
        if not isinstance(entries, dict) or not entries or "delta" in wire_update:
            raise ValueError("Invalid sparse upload")
        value_bytes = sum(
            e["values"].numel() * e["values"].element_size() for e in entries.values()
        )
        index_bytes = sum(
            e["indices"].numel() * e["indices"].element_size() for e in entries.values()
        )
    other_bytes = size - value_bytes - index_bytes
    if other_bytes < 0:
        raise ValueError("Payload shorter than its stored tensors")
    return {
        "payload_bytes": size,
        "value_bytes": value_bytes,
        "index_bytes": index_bytes,
        "other_bytes": other_bytes,
    }
