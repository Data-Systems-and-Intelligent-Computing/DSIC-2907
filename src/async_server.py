"""Asynchronous FL server: immediate apply, versioning, staleness logging."""

import math

import torch

from src.compressor import BUDGETS


class AsyncServer:
    def __init__(
        self,
        model,
        total_samples,
        learning_rate=1.0,
        staleness_multiplier=1.0,
        allowed_budgets=(1.0,),
    ):
        if type(total_samples) is not int or total_samples <= 0:
            raise ValueError("total_samples must be a positive integer")
        if not math.isfinite(learning_rate) or learning_rate <= 0:
            raise ValueError("Server learning rate must be finite and positive")
        if not math.isfinite(staleness_multiplier) or not 0 < staleness_multiplier <= 1:
            raise ValueError("Fixed staleness multiplier must be in (0, 1]")
        if (
            not isinstance(allowed_budgets, (tuple, list))
            or not allowed_budgets
            or any(type(b) not in (int, float) or b not in BUDGETS for b in allowed_budgets)
        ):
            raise ValueError("Invalid allowed update budgets")
        self.model = model
        self.total_samples = total_samples
        self.learning_rate = learning_rate
        self.staleness_multiplier = staleness_multiplier
        self.allowed_budgets = tuple(allowed_budgets)
        self.version = 0

    def apply_update(self, client_update, model_start_version: int):
        if type(model_start_version) is not int or not 0 <= model_start_version <= self.version:
            raise ValueError("Invalid/future model_start_version")
        samples = client_update["num_samples"]
        if type(samples) is not int or not 0 < samples <= self.total_samples:
            raise ValueError("Invalid client sample count")
        budget = client_update["budget"]
        if type(budget) not in (int, float) or budget not in self.allowed_budgets:
            raise ValueError("Unsupported update budget")
        state, delta = self.model.state_dict(), client_update["delta"]
        if state.keys() != delta.keys():
            raise ValueError("Update must contain every model tensor")
        weight = self.learning_rate * samples / self.total_samples * self.staleness_multiplier
        candidate = {}
        for name, tensor in state.items():
            change = delta[name]
            if (
                not isinstance(change, torch.Tensor)
                or change.shape != tensor.shape
                or change.dtype != tensor.dtype
                or change.device != tensor.device
                or not torch.isfinite(change).all()
            ):
                raise ValueError(f"Invalid update tensor: {name}")
            candidate[name] = tensor + change * weight
            if not torch.isfinite(candidate[name]).all():
                raise ValueError(f"Nonfinite aggregated tensor: {name}")
        staleness = self.version - model_start_version
        self.model.load_state_dict(candidate, strict=True)
        self.version += 1
        return {
            "version_before": self.version - 1,
            "version_after": self.version,
            "staleness": staleness,
            "weight": weight,
        }
