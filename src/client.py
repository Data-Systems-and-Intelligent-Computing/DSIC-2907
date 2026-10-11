"""Fixed local Adam training from a downloaded state; dense full model delta."""

import io
import pickle
import time

import torch

from src.centralized import train_model


def serialize_message(message):
    stream = io.BytesIO()
    torch.save(message, stream)
    return stream.getvalue()


def deserialize_message(payload):
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("Serialized payload must be nonempty bytes")
    try:
        return torch.load(io.BytesIO(payload), map_location="cpu", weights_only=True)
    except (EOFError, pickle.UnpicklingError, RuntimeError) as exc:
        raise ValueError("Invalid serialized payload") from exc


def measure_message(payload, tensors):
    """Count complete B0 message bytes and the dense tensor-value portion."""
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("Serialized payload must be nonempty bytes")
    if (
        not isinstance(tensors, dict)
        or not tensors
        or any(not isinstance(tensor, torch.Tensor) for tensor in tensors.values())
    ):
        raise ValueError("Message must contain dense tensors")
    tensor_value_bytes = sum(tensor.numel() * tensor.element_size() for tensor in tensors.values())
    if tensor_value_bytes > len(payload):
        raise ValueError("Serialized payload is shorter than its tensor values")
    return {
        "payload_bytes": len(payload),
        "frame_bytes": 0,
        "tensor_value_bytes": tensor_value_bytes,
        "serialization_overhead_bytes": len(payload) - tensor_value_bytes,
    }


class FLClient:
    def __init__(self, model_config, seed, cpu_threads=1):
        self.model_config = model_config
        self.seed = seed
        self.cpu_threads = cpu_threads

    def train(self, global_model, local_data):
        values, labels = local_data
        if not len(labels) or len(labels) != values.shape[0]:
            raise ValueError("Local data must be nonempty with matching features and labels")
        model, losses, duration, _ = train_model(
            values,
            labels,
            self.model_config,
            self.seed,
            self.cpu_threads,
            initial_state=global_model,
            log_epochs=False,
        )
        return {
            "num_samples": len(labels),
            "budget": 1.0,
            "training_bce_by_epoch": losses,
            "local_train_seconds": duration,
            "delta": {
                name: tensor - global_model[name] for name, tensor in model.state_dict().items()
            },
        }


def train_client(download_bytes, local_data, model_config, cpu_threads):
    """Process-pool entry point: each worker has its own PyTorch RNG state."""
    download = deserialize_message(download_bytes)
    client = FLClient(model_config, download["training_seed"], cpu_threads)
    update = client.train(download["model_state"], local_data)
    update.update(
        {
            key: download[key]
            for key in ("job_id", "client_id", "model_start_version", "training_seed")
        }
    )
    started = time.perf_counter()
    payload = serialize_message(update)
    return payload, time.perf_counter() - started
